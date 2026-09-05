#!/usr/bin/env python3
"""Собирает reports/ из результатов ночной лаборатории — без повторного прогона.

Предсказания победившей конфигурации уже сохранены в night/preds/, метаданные
валидационных точек лежат в кэше фолдов, поэтому все таблицы и срезы считаются
из готового. Формат совпадает с тем, что делает run_experiment.py, так что
make_charts.py и make_report.py работают поверх без изменений.
"""
from __future__ import annotations
import argparse, pickle, sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ndvi_ml.anomalies import classify_z
from ndvi_ml.baselines import _fallback_chain
from ndvi_ml.metrics import core_metrics, worst_cases
from ndvi_ml.experiment import slice_diagnostics


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--winner", required=True, help="имя конфигурации из night/preds")
    ap.add_argument("--cache", required=True)
    ap.add_argument("--outdir", default="reports")
    a = ap.parse_args()

    out = ROOT / a.outdir; out.mkdir(parents=True, exist_ok=True)
    npz = np.load(ROOT / "night" / "preds" / f"{a.winner}.npz")

    rows = []
    for p in sorted((ROOT / a.cache).glob("new_polygon_fold*.pkl")):
        with open(p, "rb") as f:
            d = pickle.load(f)
        meta = d["meta"].copy()
        meta["y"] = d["y_ev"].astype(float)
        meta["scenario"] = p.stem
        meta["pred_lightgbm"] = npz[p.stem]
        meta["pred_linear"] = _fallback_chain(
            d["X_ev"]["lin_interp"].to_numpy(dtype=float).copy(), d["X_ev"],
            ["neighbor_mean", "clim_poly_mean", "clim_crop_mean", "clim_all_mean"])
        rows.append(meta)
    det = pd.concat(rows, ignore_index=True)
    det.to_csv(out / "validation_predictions.csv", index=False)

    methods = ["lightgbm", "linear"]
    overall = pd.DataFrame([{**core_metrics(det["y"], det[f"pred_{m}"]), "method": m}
                            for m in methods]).set_index("method").sort_values("RMSE")
    overall.round(5).to_csv(out / "metrics_overall.csv")

    per = []
    for sc, part in det.groupby("scenario"):
        for m in methods:
            r = core_metrics(part["y"], part[f"pred_{m}"]); r.update(scenario=sc, method=m)
            per.append(r)
    per = pd.DataFrame(per).set_index(["scenario", "method"])
    per.round(5).to_csv(out / "metrics_by_scenario.csv")
    pivot = per.reset_index().pivot(index="method", columns="scenario", values="RMSE")
    pivot.insert(0, "new_polygon_avg", pivot.mean(axis=1))
    pivot.sort_values("new_polygon_avg").round(5).to_csv(out / "rmse_pivot.csv")

    for name, tab in slice_diagnostics(det, "lightgbm").items():
        tab.to_csv(out / f"slice_{name}.csv")
    gap = pd.concat([slice_diagnostics(det, m)["gap_bucket"]["RMSE"].rename(m)
                     for m in methods], axis=1)
    gap.to_csv(out / "rmse_by_gap_length.csv")

    zt = (det["y"] - det["clim_mean"]) / det["clim_std"].replace(0, np.nan)
    st_rows = []
    for m in methods:
        zp = (det[f"pred_{m}"] - det["clim_mean"]) / det["clim_std"].replace(0, np.nan)
        ok = zt.notna() & zp.notna()
        s_t, s_p = zt[ok].map(classify_z), zp[ok].map(classify_z)
        st_rows.append({"method": m, "n": int(ok.sum()),
                        "status_accuracy_%": float((s_t == s_p).mean() * 100),
                        "z_RMSE": float(np.sqrt(np.mean((zp[ok] - zt[ok]) ** 2))),
                        "аномалия_recall_%": float(((s_p != "Штатное развитие") &
                                                    (s_t != "Штатное развитие")).sum()
                                                   / max((s_t != "Штатное развитие").sum(), 1) * 100)})
    pd.DataFrame(st_rows).set_index("method").to_csv(out / "anomaly_status_agreement.csv")

    worst_cases(det.assign(pred=det["pred_lightgbm"]), k=15).to_csv(out / "worst_cases.csv", index=False)
    print(f"reports/ пересобран по конфигурации {a.winner}")
    print(overall.round(5).to_string())


if __name__ == "__main__":
    main()
