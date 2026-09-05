#!/usr/bin/env python3
"""Сводит выгрузку GEE в схему организаторов и готовит датасет для обучения.

    python data_collection/merge_external.py --raw exports/ --out external_train.csv

На входе — CSV из Drive: по файлу на сенсор и год (ndvi_s2_2024_b1.csv и т.п.),
плюс паспорт участков ndvi_fields_meta_b*.csv. ERA5 выгружается по ячейкам
0.1 градуса и пришивается к полям через cell_id из паспорта.

На выходе — схема train_dataset.csv: суточная сетка сезона, primary_ndvi по
приоритету S2 -> Landsat -> MODIS.
"""

from __future__ import annotations

import argparse
import glob
import re
from pathlib import Path

import numpy as np
import pandas as pd

SEASON_START, SEASON_END = (4, 1), (10, 30)
SENSOR_COLS = ["s2_ndvi", "s2_evi", "s2_ndwi", "landsat_ndvi", "landsat_evi",
               "landsat_ndwi", "modis_ndvi", "modis_evi"]
ERA5_COLS = ["era5_temp_c", "era5_precip_mm"]


def _read_many(paths: list[str], key: str) -> pd.DataFrame:
    frames = []
    for p in paths:
        # GEE отдаёт пустой файл, когда за сезон не нашлось ни одного снимка
        # (например, Sentinel-2 до 2017 года). Это норма, а не сбой.
        if Path(p).stat().st_size < 10:
            print(f"  {Path(p).name}: пусто, пропускаю")
            continue
        try:
            d = pd.read_csv(p)
        except pd.errors.EmptyDataError:
            print(f"  {Path(p).name}: нет заголовка, пропускаю")
            continue
        if key not in d.columns or "date" not in d.columns:
            print(f"  пропускаю {Path(p).name}: нет колонок {key}/date")
            continue
        cols = [key, "date"] + [c for c in d.columns if c in SENSOR_COLS + ERA5_COLS]
        frames.append(d[cols])
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"])
    # один снимок на ключ+дату: два пролёта в сутки усредняем
    return out.groupby([key, "date"], as_index=False).mean(numeric_only=True)


def load_raw(raw_dir: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    files = sorted(glob.glob(str(Path(raw_dir) / "*.csv")))
    meta_files = [f for f in files if "fields_meta" in Path(f).name]
    era5_files = [f for f in files if re.search(r"era5", Path(f).name)]
    sat_files = [f for f in files if f not in meta_files and f not in era5_files]

    meta = (pd.concat([pd.read_csv(f) for f in meta_files
                       if Path(f).stat().st_size > 10], ignore_index=True)
            if meta_files else pd.DataFrame())
    sat = _read_many(sat_files, "anon_polygon_id")
    era5 = _read_many(era5_files, "cell_id")
    print(f"файлов: паспорт {len(meta_files)}, спутники {len(sat_files)}, ERA5 {len(era5_files)}")
    return sat, era5, meta


def daily_grid(polygons: list[str], years: list[int]) -> pd.DataFrame:
    """Суточная сетка сезона: 1 апреля - 30 октября, 213 строк на полигон-сезон."""
    idx = []
    for year in years:
        idx.append(pd.date_range(f"{year}-{SEASON_START[0]:02d}-{SEASON_START[1]:02d}",
                                 f"{year}-{SEASON_END[0]:02d}-{SEASON_END[1]:02d}", freq="D"))
    dates = pd.DatetimeIndex(np.concatenate([i.values for i in idx]))
    return pd.MultiIndex.from_product([polygons, dates],
                                      names=["anon_polygon_id", "date"]).to_frame(index=False)


def build(sat: pd.DataFrame, era5: pd.DataFrame, meta: pd.DataFrame,
          clip_physical: bool = True) -> pd.DataFrame:
    polygons = sorted(set(sat["anon_polygon_id"]) | set(meta.get("anon_polygon_id", [])))
    years = sorted(sat["date"].dt.year.unique()) if len(sat) else []
    if not polygons or not years:
        raise SystemExit("не из чего собирать: нет полигонов или дат")

    df = daily_grid(polygons, years).merge(sat, on=["anon_polygon_id", "date"], how="left")

    # погода: пришиваем по ячейке из паспорта
    if len(era5) and "cell_id" in meta.columns:
        df = df.merge(meta[["anon_polygon_id", "cell_id"]], on="anon_polygon_id", how="left")
        df = df.merge(era5, on=["cell_id", "date"], how="left")
    else:
        print("  ВНИМАНИЕ: ERA5 не пришита (нет паспорта или файлов era5)")
        for c in ERA5_COLS:
            df[c] = np.nan

    for col in SENSOR_COLS + ERA5_COLS:
        if col not in df:
            df[col] = np.nan

    if clip_physical:
        # у организаторов Landsat даёт значения вне [-1, 1]; у себя чиним:
        # такие строки только портят обучение, а совместимости не ломают
        for col in ("s2_ndvi", "landsat_ndvi", "modis_ndvi"):
            df.loc[(df[col] < -1) | (df[col] > 1), col] = np.nan

    # приоритет сенсоров ровно как у организаторов
    df["primary_ndvi"] = df["s2_ndvi"].fillna(df["landsat_ndvi"]).fillna(df["modis_ndvi"])
    df["year"] = df["date"].dt.year.astype(np.int32)
    df["doy"] = df["date"].dt.dayofyear.astype(np.int32)
    # культура: из паспорта, если gee_rostov.py её разметил по WorldCereal
    if "crop_type" in meta.columns:
        cmap = dict(zip(meta["anon_polygon_id"], meta["crop_type"]))
        df["crop_type"] = df["anon_polygon_id"].map(cmap).fillna("неизвестно")
    else:
        df["crop_type"] = "неизвестно"
    df["source"] = "external"
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    keep = (["anon_polygon_id", "date"] + SENSOR_COLS + ERA5_COLS
            + ["year", "doy", "primary_ndvi", "crop_type", "source"])
    return df[keep].sort_values(["anon_polygon_id", "date"]).reset_index(drop=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True, help="каталог с выгрузками из Drive")
    ap.add_argument("--out", default="external_train.csv")
    ap.add_argument("--no-clip", action="store_true")
    a = ap.parse_args()

    sat, era5, meta = load_raw(a.raw)
    out = build(sat, era5, meta, clip_physical=not a.no_clip)
    out.to_csv(a.out, index=False, encoding="utf-8")

    obs = int(out["primary_ndvi"].notna().sum())
    per = out.groupby(["anon_polygon_id", "year"])["primary_ndvi"].count()
    print(f"\n{a.out}: {len(out)} строк, {out.anon_polygon_id.nunique()} полигонов, "
          f"{out.year.nunique()} сезонов")
    print(f"наблюдений: {obs} ({obs / max(len(out), 1):.1%} суточной сетки)")
    print(f"на полигон-сезон: медиана {per.median():.0f} (у организаторов около 49)")
    print(f"погода заполнена: {out.era5_temp_c.notna().mean():.1%} строк")
    src = pd.DataFrame({
        "S2": out.s2_ndvi.notna().sum(),
        "Landsat": out.landsat_ndvi.notna().sum(),
        "MODIS": out.modis_ndvi.notna().sum(),
    }, index=["наблюдений"]).T
    print(src.to_string())


if __name__ == "__main__":
    main()
