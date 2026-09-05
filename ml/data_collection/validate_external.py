#!/usr/bin/env python3
"""Сверка собранных данных с данными организаторов — обязательный шаг перед обучением.

    python data_collection/validate_external.py --external external_train.csv \
        --reference train_dataset.csv

Мы не знаем, где лежат полигоны организаторов (они анонимизированы), поэтому
сверить построчно нельзя. Но можно сверить распределения: если наш сбор даёт
другую частоту наблюдений, другой сезонный ход NDVI или другие диапазоны —
новые данные будут тянуть модель в свою сторону, и обучать на них нельзя.
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd


def summarize(df: pd.DataFrame, name: str) -> pd.DataFrame:
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["year"] = df["date"].dt.year
    df["doy"] = df["date"].dt.dayofyear
    obs = df[df["primary_ndvi"].notna()]
    per = df.groupby(["anon_polygon_id", "year"])["primary_ndvi"].count()
    rows = {
        "полигонов": df["anon_polygon_id"].nunique(),
        "строк": len(df),
        "наблюдений": len(obs),
        "набл./полигон-сезон (медиана)": round(per.median(), 1),
        "NDVI медиана": round(obs["primary_ndvi"].median(), 4),
        "NDVI 5-й перцентиль": round(obs["primary_ndvi"].quantile(0.05), 4),
        "NDVI 95-й перцентиль": round(obs["primary_ndvi"].quantile(0.95), 4),
        "вне [-1,1]": int(((obs["primary_ndvi"] < -1) | (obs["primary_ndvi"] > 1)).sum()),
    }
    for col in ("s2_ndvi", "landsat_ndvi", "modis_ndvi"):
        if col in df:
            rows[f"доля {col}"] = round(df[col].notna().sum() / max(len(obs), 1), 3)
    return pd.Series(rows, name=name)


def seasonal_profile(df: pd.DataFrame) -> pd.Series:
    d = df.copy()
    d["date"] = pd.to_datetime(d["date"])
    d["bin"] = d["date"].dt.dayofyear // 15
    return d.dropna(subset=["primary_ndvi"]).groupby("bin")["primary_ndvi"].median()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--external", required=True)
    ap.add_argument("--reference", required=True)
    a = ap.parse_args()

    ext = pd.read_csv(a.external)
    ref = pd.read_csv(a.reference)
    table = pd.concat([summarize(ref, "организаторы"), summarize(ext, "наш сбор")], axis=1)
    print(table.to_string())

    pe, pr = seasonal_profile(ext), seasonal_profile(ref)
    common = pe.index.intersection(pr.index)
    diff = (pe[common] - pr[common]).abs()
    print(f"\nсезонный ход NDVI, расхождение по 15-дневным бинам:")
    print(f"  медиана {diff.median():.4f}, максимум {diff.max():.4f}")

    verdict = []
    if diff.median() > 0.05:
        verdict.append("сезонный ход заметно отличается — проверь маскирование облаков и агрегацию")
    per_ext = summarize(ext, "x")["набл./полигон-сезон (медиана)"]
    per_ref = summarize(ref, "y")["набл./полигон-сезон (медиана)"]
    if per_ext < per_ref * 0.6:
        verdict.append("наблюдений заметно меньше — маска слишком агрессивная")
    if per_ext > per_ref * 1.6:
        verdict.append("наблюдений заметно больше — маска слишком мягкая, могут пролезать облака")
    print("\nвердикт:", "; ".join(verdict) if verdict
          else "распределения сопоставимы, данные можно подмешивать в обучение")


if __name__ == "__main__":
    main()
