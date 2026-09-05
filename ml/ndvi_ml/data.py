"""Загрузка и подготовка данных Космохакатона (кейс NDVI)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

# колонки, которые организаторы маскируют в контрольных строках
MASKED_COLS = [
    "s2_ndvi", "s2_evi", "s2_ndwi",
    "landsat_ndvi", "landsat_evi", "landsat_ndwi",
    "modis_ndvi", "modis_evi",
    "era5_temp_c", "era5_precip_mm",
    "primary_ndvi",
    "ndvi_climatology_mean", "ndvi_climatology_std", "n_reference_years",
]

# то, что остаётся видимым всегда
KEEP_COLS = ["anon_polygon_id", "date", "crop_type"]


def load_raw(train_path: str | Path, test_path: str | Path,
             extra_paths: list[str | Path] | None = None) -> pd.DataFrame:
    """Склеивает train и пригодные строки теста в один суточный грид.

    Контрольные строки (is_synthetic_gap == True) помечаются флагом is_target,
    но не выбрасываются: они часть суточной сетки и нужны как позиции для предсказания.

    extra_paths — дособранные полигоны (data_collection/). Они попадают ТОЛЬКО
    в обучение: валидация обязана остаться на полигонах организаторов, иначе
    метрики перестанут быть сравнимыми с предыдущими прогонами и с платформой.
    За это отвечает колонка source == "external" (см. validation.scenario_*).
    """
    train = pd.read_csv(train_path)
    test = pd.read_csv(test_path)

    train["source"] = "train"
    train["is_target"] = False
    test["source"] = "test"
    test["is_target"] = test["is_synthetic_gap"].fillna(False).astype(bool)

    parts = [train, test]
    for path in (extra_paths or []):
        ext = pd.read_csv(path)
        ext["source"] = "external"
        ext["is_target"] = False
        parts.append(ext)

    df = pd.concat(parts, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])

    for col in MASKED_COLS:
        if col not in df.columns:
            df[col] = np.nan
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # year/doy всегда из даты: в контрольных строках колонки замаскированы
    df["year"] = df["date"].dt.year.astype(np.int32)
    df["doy"] = df["date"].dt.dayofyear.astype(np.int32)
    df["crop_type"] = df["crop_type"].astype("category")

    df = df.drop(columns=[c for c in ("is_synthetic_gap", "ndvi_zscore", "status") if c in df.columns],
                 errors="ignore")

    # страховка: одна строка = полигон + дата
    df = (df.sort_values(["anon_polygon_id", "date", "source"])
            .drop_duplicates(["anon_polygon_id", "date"], keep="first")
            .sort_values(["anon_polygon_id", "date"])
            .reset_index(drop=True))
    return df


def load_status(train_path: str | Path) -> pd.DataFrame:
    """Эталонные ndvi_zscore/status из train — для проверки задачи 2."""
    t = pd.read_csv(train_path, usecols=["anon_polygon_id", "date", "ndvi_zscore", "status"])
    t["date"] = pd.to_datetime(t["date"])
    return t.dropna(subset=["status"])


def mask_rows(df: pd.DataFrame, hidden: np.ndarray) -> pd.DataFrame:
    """Возвращает копию df, где у строк hidden занулены все динамические признаки.

    Ровно так выглядят контрольные строки в private_features.csv, поэтому
    признаки считаем только по такой замаскированной копии — иначе утечка.
    """
    out = df.copy()
    out.loc[hidden, MASKED_COLS] = np.nan
    out["is_hidden"] = hidden
    return out


def observed_mask(df: pd.DataFrame) -> np.ndarray:
    """Строки с известным primary_ndvi — кандидаты в synthetic gaps."""
    return df["primary_ndvi"].notna().to_numpy()
