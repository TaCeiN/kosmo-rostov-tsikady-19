#!/usr/bin/env python3
"""Графики диагностики: качество по срезам, ошибки, примеры восстановленных рядов."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from ndvi_ml.metrics import gap_bucket

PALETTE = ["#2F6F4E", "#C2703D", "#5B7DB1", "#8A5A9E", "#B0483C", "#7A7A7A", "#3E8E7E"]
plt.rcParams.update({
    "figure.dpi": 130, "font.size": 9, "axes.grid": True,
    "grid.alpha": 0.25, "axes.spines.top": False, "axes.spines.right": False,
})


def chart_methods(det: pd.DataFrame, out: Path):
    methods = [c[5:] for c in det.columns if c.startswith("pred_")]
    d = det[det.scenario.str.startswith("new_polygon")]
    rmse = {m: float(np.sqrt(np.mean((d[f"pred_{m}"] - d["y"]) ** 2))) for m in methods}
    s = pd.Series(rmse).sort_values()
    fig, ax = plt.subplots(figsize=(6.2, 3.2))
    colors = [PALETTE[0] if i == 0 else "#B8BDB5" for i in range(len(s))]
    ax.barh(s.index[::-1], s.values[::-1], color=colors[::-1])
    for i, (name, v) in enumerate(zip(s.index[::-1], s.values[::-1])):
        ax.text(v + 0.001, i, f"{v:.4f}", va="center", fontsize=8)
    ax.set_xlabel("RMSE на сценарии «новый полигон» (меньше — лучше)")
    ax.set_title("Сравнение методов восстановления")
    fig.tight_layout()
    fig.savefig(out / "01_methods.png")
    plt.close(fig)


def chart_gap_length(det: pd.DataFrame, out: Path):
    methods = [c[5:] for c in det.columns if c.startswith("pred_")]
    d = det.copy()
    d["bucket"] = gap_bucket(d["gap_len"])
    fig, ax = plt.subplots(figsize=(6.6, 3.4))
    for i, m in enumerate(["linear", "whittaker", "lightgbm"]):
        if f"pred_{m}" not in d:
            continue
        g = d.groupby("bucket", observed=True).apply(
            lambda x: float(np.sqrt(np.mean((x[f"pred_{m}"] - x["y"]) ** 2))), include_groups=False)
        ax.plot(g.index.astype(str), g.values, marker="o", color=PALETTE[i], label=m)
    ax.set_ylabel("RMSE")
    ax.set_xlabel("длина пропуска")
    ax.set_title("Чем длиннее дырка, тем важнее модель")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(out / "02_gap_length.png")
    plt.close(fig)


def chart_scatter(det: pd.DataFrame, out: Path, method: str):
    d = det[det.scenario.str.startswith("new_polygon")]
    fig, axes = plt.subplots(1, 2, figsize=(8.4, 3.6))
    ax = axes[0]
    ax.scatter(d["y"], d[f"pred_{method}"], s=3, alpha=0.15, color=PALETTE[0], edgecolors="none")
    ax.plot([0, 1], [0, 1], color="#B0483C", lw=1)
    ax.set_xlabel("факт NDVI")
    ax.set_ylabel("предсказание")
    ax.set_title(f"{method}: предсказано против факта")
    err = d[f"pred_{method}"] - d["y"]
    ax = axes[1]
    ax.hist(err, bins=80, color=PALETTE[2])
    ax.axvline(0, color="#B0483C", lw=1)
    ax.set_xlabel("ошибка (пред − факт)")
    ax.set_title(f"смещение {err.mean():+.4f}, σ {err.std():.4f}")
    fig.tight_layout()
    fig.savefig(out / "03_scatter_residuals.png")
    plt.close(fig)


def chart_importance(imp_path: Path, out: Path, k: int = 20):
    if not imp_path.exists():
        return
    imp = pd.read_csv(imp_path).head(k)
    col = "feature" if "feature" in imp else imp.columns[0]
    fig, ax = plt.subplots(figsize=(6.4, 5.2))
    ax.barh(imp[col][::-1], imp["gain_%"][::-1] if "gain_%" in imp else imp["gain"][::-1],
            color=PALETTE[0])
    ax.set_xlabel("вклад в gain, %")
    ax.set_title("Топ признаков")
    fig.tight_layout()
    fig.savefig(out / "04_feature_importance.png")
    plt.close(fig)


def chart_series(series_path: Path, out: Path, n: int = 3):
    if not series_path.exists():
        return
    s = pd.read_csv(series_path, parse_dates=["date"])
    # берём сезоны с наибольшим числом восстановленных точек
    s["season"] = s["anon_polygon_id"] + " " + s["date"].dt.year.astype(str)
    pick = (s[s.ndvi_obs.isna()].groupby("season").size().sort_values(ascending=False).head(n).index)
    fig, axes = plt.subplots(n, 1, figsize=(8.6, 2.5 * n), sharex=False)
    axes = np.atleast_1d(axes)
    for ax, season in zip(axes, pick):
        part = s[s.season == season].sort_values("date")
        ax.plot(part["date"], part["clim_mean"], color="#9AA39B", lw=1.2, ls="--", label="норма")
        ax.fill_between(part["date"], part["clim_mean"] - part["clim_std"],
                        part["clim_mean"] + part["clim_std"], color="#9AA39B", alpha=0.15)
        col = "ndvi_smooth" if "ndvi_smooth" in part else "ndvi_filled"
        ax.plot(part["date"], part[col], color=PALETTE[0], lw=1.4, label="восстановлено")
        obs = part[part.ndvi_obs.notna()]
        ax.scatter(obs["date"], obs["ndvi_obs"], s=10, color=PALETTE[1], zorder=3, label="наблюдения")
        bad = part[part["z"] < -1]
        if len(bad):
            ax.scatter(bad["date"], bad[col], s=8, color="#B0483C", zorder=4,
                       label="z < −1")
        ax.set_title(season, fontsize=9)
        ax.set_ylabel("NDVI")
    axes[0].legend(frameon=False, ncol=4, fontsize=8)
    fig.tight_layout()
    fig.savefig(out / "05_series.png")
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reports", default="reports")
    ap.add_argument("--artifacts", default="artifacts")
    ap.add_argument("--outdir", default="charts")
    ap.add_argument("--method", default="lightgbm")
    args = ap.parse_args()

    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    rep, art = Path(args.reports), Path(args.artifacts)

    det = pd.read_csv(rep / "validation_predictions.csv")
    chart_methods(det, out)
    chart_gap_length(det, out)
    chart_scatter(det, out, args.method)
    chart_importance(rep / "feature_importance.csv", out)
    chart_series(art / "series_with_zscore.csv", out)
    print(f"графики в {out}/")


if __name__ == "__main__":
    main()
