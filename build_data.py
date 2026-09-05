#!/usr/bin/env python3
"""Готовит статические JSON для фронта: чтобы веб можно было делать без Python.

    python build_data.py

Читает artifacts/ и reports*/ и раскладывает в web_handoff/data/. После этого
фронт собирается и работает на одних файлах, без запущенного бэкенда —
бэкенд нужен только для загрузки пользовательского CSV.

Формат рядов компактный: не список объектов, а параллельные массивы. Один
полигон — это 2015 суток за 16 лет, объектами это в четыре раза жирнее и
браузер на переключении полигона заметно тормозит.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

# Исследовательская часть с артефактами и отчётами лежит в ml/,
# готовые JSON для фронта — в data/ рядом со скриптом
ROOT = Path(__file__).resolve().parent / "ml"
OUT = Path(__file__).resolve().parent / "data"


def r(x, n=4):
    """None вместо NaN: JSON не умеет NaN, а JSON.parse на нём падает."""
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return None
    return round(float(x), n)


def col(df, name, n=4):
    return [r(v, n) for v in df[name]] if name in df else [None] * len(df)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "series").mkdir(exist_ok=True)

    ser = pd.read_csv(ROOT / "artifacts" / "series_with_zscore.csv")
    anom = pd.read_csv(ROOT / "artifacts" / "anomalies.csv")
    rec = pd.read_csv(ROOT / "artifacts" / "reconstructed_series.csv",
                      usecols=["anon_polygon_id", "date", "is_reconstructed",
                               "is_control_point"])
    ser = ser.merge(rec, on=["anon_polygon_id", "date"], how="left")

    # --- ряды по полигонам
    index = []
    for pid, g in ser.groupby("anon_polygon_id", sort=True):
        g = g.sort_values("date")
        payload = {
            "id": pid,
            "crop_type": str(g["crop_type"].iloc[0]),
            "years": sorted(int(y) for y in g["year"].unique()),
            # параллельные массивы, все одной длины
            "date": list(g["date"]),
            "ndvi_obs": col(g, "ndvi_obs"),
            "ndvi_filled": col(g, "ndvi_filled"),
            "ndvi_smooth": col(g, "ndvi_smooth"),
            "clim_mean": col(g, "clim_mean"),
            "clim_std": col(g, "clim_std"),
            "z": col(g, "z", 3),
            "status": [None if pd.isna(v) else str(v) for v in g["status_pred"]],
            "is_control_point": [bool(v) for v in g["is_control_point"].fillna(False)],
            "precip_30d": col(g, "precip_30d", 2),
            "temp_30d": col(g, "temp_30d", 2),
        }
        (OUT / "series" / f"{pid}.json").write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8")

        obs = int(g["ndvi_obs"].notna().sum())
        index.append({
            "id": pid,
            "crop_type": str(g["crop_type"].iloc[0]),
            "years": [int(g["year"].min()), int(g["year"].max())],
            "n_days": len(g),
            "n_observed": obs,
            "n_reconstructed": len(g) - obs,
            "n_control_points": int(g["is_control_point"].fillna(False).sum()),
            "n_anomalies": int((anom["anon_polygon_id"] == pid).sum()),
        })

    # --- аномалии
    a = anom.copy()
    a["comment"] = a["comment"].astype(str)
    anomalies = json.loads(a.to_json(orient="records", double_precision=4))

    # --- метрики
    metrics = {}
    truth = ROOT / "reports_truth" / "truth_metrics.csv"
    if truth.exists():
        t = pd.read_csv(truth).set_index("method")
        metrics["truth"] = json.loads(t.to_json(orient="index", double_precision=5))
    for name, path in (("validation", ROOT / "reports" / "metrics_overall.csv"),
                       ("by_gap_length", ROOT / "reports" / "rmse_by_gap_length.csv"),
                       ("anomaly_agreement", ROOT / "reports" / "anomaly_status_agreement.csv")):
        if path.exists():
            metrics[name] = json.loads(pd.read_csv(path).to_json(orient="records",
                                                                double_precision=5))
    for name, path in (("truth_by_group", ROOT / "reports_truth" / "truth_slice_группа.csv"),
                       ("truth_by_phase", ROOT / "reports_truth" / "truth_slice_phase.csv"),
                       ("truth_by_crop", ROOT / "reports_truth" / "truth_slice_crop_type.csv"),
                       ("truth_by_gap", ROOT / "reports_truth" / "truth_slice_gap_bucket.csv")):
        if path.exists():
            metrics[name] = json.loads(pd.read_csv(path).to_json(orient="records",
                                                                double_precision=5))

    meta = {
        "generated_from": "artifacts/ + reports_truth/ + reports/",
        "polygons": index,
        "crop_types": sorted(set(x["crop_type"] for x in index)),
        "totals": {
            "polygons": len(index),
            "days": int(sum(x["n_days"] for x in index)),
            "observed": int(sum(x["n_observed"] for x in index)),
            "reconstructed": int(sum(x["n_reconstructed"] for x in index)),
            "anomalies": len(anomalies),
        },
        "status_values": sorted(set(str(v) for v in ser["status_pred"].dropna().unique())),
        "severity_values": sorted(set(str(v) for v in anom["severity"].dropna().unique())),
        "causes": sorted(set(str(v) for v in anom["cause"].dropna().unique())),
    }

    for name, payload in (("meta", meta), ("anomalies", anomalies), ("metrics", metrics)):
        (OUT / f"{name}.json").write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8")

    total_mb = sum(f.stat().st_size for f in OUT.rglob("*.json")) / 1e6
    print(f"{OUT}: {len(index)} полигонов, {len(anomalies)} аномалий, {total_mb:.1f} МБ")
    print("  meta.json, anomalies.json, metrics.json, series/<id>.json")


if __name__ == "__main__":
    main()
