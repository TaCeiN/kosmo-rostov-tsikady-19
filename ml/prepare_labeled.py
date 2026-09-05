#!/usr/bin/env python3
"""Сшивает тестовый набор с его ответами в размеченный датасет для обучения.

    python prepare_labeled.py --features test1_features.csv \
        --truth private_test_ground_truth.csv --out labeled_test1.csv

Организаторы выдали ответы на первый тестовый набор. Его контрольные точки
перестают быть загадкой и становятся обычными обучающими примерами — плюс
20 753 размеченных наблюдения к 30 520 из train, то есть выборка вырастает
почти вдвое.

Полученный файл подключается флагом --extra у predict_submission.py.

ВАЖНО: не подключай его, когда меряешь качество на этих же контрольных точках
(evaluate_truth.py) — это будет обучение на ответах и метрика соврёт.
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--features", required=True, help="тестовый набор с is_synthetic_gap")
    ap.add_argument("--truth", required=True, help="ответы: anon_polygon_id, date, primary_ndvi_true")
    ap.add_argument("--out", default="labeled_test.csv")
    a = ap.parse_args()

    feats = pd.read_csv(a.features)
    truth = pd.read_csv(a.truth)
    tcol = next((c for c in ("primary_ndvi_true", "primary_ndvi", "primary_ndvi_pred")
                 if c in truth.columns), None)
    if tcol is None:
        raise SystemExit(f"в файле ответов нет колонки со значением: {list(truth.columns)}")

    gaps = int((feats.get("is_synthetic_gap") == True).sum())  # noqa: E712
    before = int(feats["primary_ndvi"].notna().sum())

    merged = feats.merge(truth[["anon_polygon_id", "date", tcol]],
                         on=["anon_polygon_id", "date"], how="left")
    filled = merged["primary_ndvi"].isna() & merged[tcol].notna()
    merged.loc[filled, "primary_ndvi"] = merged.loc[filled, tcol]
    merged = merged.drop(columns=[tcol])

    # флаг контрольной точки больше не нужен: значения известны, это обычные данные
    if "is_synthetic_gap" in merged.columns:
        merged = merged.drop(columns=["is_synthetic_gap"])

    merged.to_csv(a.out, index=False, encoding="utf-8")
    after = int(merged["primary_ndvi"].notna().sum())
    print(f"{a.out}: {len(merged)} строк, {merged.anon_polygon_id.nunique()} полигонов")
    print(f"размеченных наблюдений: {before} -> {after} (+{after - before})")
    print(f"контрольных точек в исходнике было {gaps}, закрыто ответами {int(filled.sum())}")
    if int(filled.sum()) < gaps:
        print(f"ВНИМАНИЕ: {gaps - int(filled.sum())} контрольных точек остались без ответа")
    bad = int(((merged.primary_ndvi < -1) | (merged.primary_ndvi > 1)).sum())
    print(f"значений вне [-1, 1]: {bad}")


if __name__ == "__main__":
    main()
