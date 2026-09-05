#!/usr/bin/env python3
"""Инференс из командной строки: CSV на входе — восстановленный ряд и аномалии на выходе.

    python backend/infer.py --input polygon.csv --outdir out/

Вход — та же схема, что у исходных данных: anon_polygon_id, date, primary_ndvi
(пусто там, где надо восстановить), плюс любые доступные спутниковые и погодные
колонки. Чем полнее суточная сетка сезона, тем лучше результат: соседи, окна и
погода считаются именно по ней.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

# Пакет ndvi_ml общий у сервиса с исследовательской частью, лежит в ml/
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "ml"))

from ndvi_ml.pipeline import NdviPipeline

DEFAULT_MODEL = REPO_ROOT / "ml" / "artifacts" / "ndvi_model.pkl"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=str(DEFAULT_MODEL))
    ap.add_argument("--input", required=True)
    ap.add_argument("--outdir", default="out")
    ap.add_argument("--no-anomalies", action="store_true")
    a = ap.parse_args()

    out = Path(a.outdir); out.mkdir(parents=True, exist_ok=True)
    pipe = NdviPipeline.load(a.model)
    df = pd.read_csv(a.input)
    res = pipe.predict_frame(df, with_anomalies=not a.no_anomalies)

    series_path = out / "series.csv"
    if not res.series.empty:
        res.series.drop(columns=["doy_bin"], errors="ignore").to_csv(series_path, index=False)
    else:
        pd.DataFrame({"ndvi_filled": res.filled}).to_csv(series_path, index=False)
    print(f"{series_path}: {len(res.filled)} строк, "
          f"восстановлено {int(pd.isna(df.get('primary_ndvi', pd.Series(dtype=float))).sum())}")

    if not res.anomalies.empty:
        p = out / "anomalies.csv"
        res.anomalies.to_csv(p, index=False)
        print(f"{p}: аномальных периодов {len(res.anomalies)}")
        print(res.anomalies.head(5)[["anon_polygon_id", "start", "end", "days",
                                     "z_min", "cause"]].to_string(index=False))
    else:
        print("аномальных периодов не найдено")


if __name__ == "__main__":
    main()
