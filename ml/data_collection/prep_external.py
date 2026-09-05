#!/usr/bin/env python3
"""Приводит любой внешний CSV к схеме организаторов — перед подачей в --extra.

    python data_collection/prep_external.py --src "govno_dataset/sample.csv" --out ext_ready.csv

Три вещи, без которых внешний файл ломает обучение молча:

1. **Префикс полигонов.** load_raw в конце делает drop_duplicates по
   (anon_polygon_id, date) с сортировкой по source, а "external" < "train"
   по алфавиту. Значит, при совпадении id внешняя строка ВЫТЕСНЯЕТ строку
   организаторов. Файл с id вида AOI-0001 перекрывает train почти целиком:
   девять полигонов на пятнадцать сезонов — под тридцать тысяч подменённых
   строк, и ни одного предупреждения в логе.

2. **Культура.** crop_type — категориальный признак и ключ группировки
   статистик (features._loo_stat по crop). Английские классы дают лишние
   уровни категории и отдельные группы, которые не пересекаются с полями
   организаторов.

3. **Битые NDVI.** У организаторов в landsat_ndvi лежат значения до 1.19 и
   до −2.13; во внешних данных такие только портят обучение, совместимости
   не ломает их отрезать (см. RECIPE.md).

Диагностика печатается всегда: сколько строк, полигонов, какое покрытие
наблюдениями и как оно соотносится с эталоном.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Консоль Windows живёт в cp1251/cp866 и роняет процесс на любом символе вне
# кодировки. Прогон eval_halfsplit.py уже потерял пятнадцать минут счёта,
# упав на печати «ΔRMSE» перед самым сохранением результата.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

SENSOR_COLS = ["s2_ndvi", "s2_evi", "s2_ndwi", "landsat_ndvi", "landsat_evi",
               "landsat_ndwi", "modis_ndvi", "modis_evi"]
ERA5_COLS = ["era5_temp_c", "era5_precip_mm"]

# Классы организаторов: озимая пшеница, зерновые, подсолнечник, пастбища/зерновые.
# Английские подписи внешних наборов кладём на них; всё незнакомое — в «зерновые»
# как самый общий класс, а не в новый уровень категории.
CROP_MAP = {
    "wheat": "озимая пшеница",
    "winter_wheat": "озимая пшеница",
    "winterwheat": "озимая пшеница",
    "sunflower": "подсолнечник",
    "maize": "зерновые",
    "corn": "зерновые",
    "barley": "зерновые",
    "cereals": "зерновые",
    "springcereals": "зерновые",
    "wintercereals": "озимая пшеница",
    "farmland": "зерновые",
    "cropland": "зерновые",
    "pasture": "пастбища/зерновые",
    "grassland": "пастбища/зерновые",
}
KNOWN = {"озимая пшеница", "зерновые", "подсолнечник", "пастбища/зерновые"}


def map_crop(v) -> str:
    if not isinstance(v, str) or not v.strip():
        return "зерновые"
    s = v.strip()
    if s in KNOWN:
        return s
    return CROP_MAP.get(s.lower().replace(" ", "_"), "зерновые")


def main():
    ap = argparse.ArgumentParser(description="нормализация внешнего CSV под --extra")
    ap.add_argument("--src", required=True, help="исходный файл")
    ap.add_argument("--out", required=True, help="куда писать нормализованный")
    ap.add_argument("--prefix", default="EXT-",
                    help="префикс id полигонов; должен быть уникальным для "
                         "каждого внешнего источника")
    ap.add_argument("--reference", default="train_dataset.csv",
                    help="эталон для сверки покрытия")
    ap.add_argument("--no-clip", action="store_true",
                    help="не отрезать NDVI вне [-1, 1]")
    a = ap.parse_args()

    src = Path(a.src)
    if not src.exists():
        sys.exit(f"нет файла {src}")
    df = pd.read_csv(src)
    print(f"{src.name}: {len(df)} строк, {df.shape[1]} колонок")

    need = {"anon_polygon_id", "date"}
    miss = need - set(df.columns)
    if miss:
        sys.exit(f"нет обязательных колонок: {sorted(miss)}")

    # 1. префикс — иначе внешние строки вытеснят строки организаторов
    old_ids = df["anon_polygon_id"].astype(str)
    df["anon_polygon_id"] = a.prefix + old_ids
    print(f"полигоны: {old_ids.nunique()} шт., переименованы в "
          f"{a.prefix}* (пример: {df.anon_polygon_id.iloc[0]})")

    # 2. культура
    if "crop_type" in df.columns:
        before = df["crop_type"].astype(str).value_counts().to_dict()
        df["crop_type"] = df["crop_type"].map(map_crop)
        after = df["crop_type"].value_counts().to_dict()
        print(f"crop_type: {before}")
        print(f"        -> {after}")
    else:
        df["crop_type"] = "зерновые"
        print("crop_type: колонки не было, поставил «зерновые»")

    # недостающие колонки схемы — пустыми, иначе load_raw создаст их сам,
    # но уже после конкатенации, и типы разъедутся
    for col in SENSOR_COLS + ERA5_COLS:
        if col not in df.columns:
            df[col] = np.nan
            print(f"  нет колонки {col}, добавил пустой")
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # 3. битые NDVI
    if not a.no_clip:
        n = 0
        for col in ("s2_ndvi", "landsat_ndvi", "modis_ndvi", "primary_ndvi"):
            if col in df.columns:
                bad = (df[col] < -1) | (df[col] > 1)
                n += int(bad.sum())
                df.loc[bad, col] = np.nan
        if n:
            print(f"вне [-1, 1]: обнулено {n} значений")

    # primary_ndvi по приоритету организаторов: S2 -> Landsat -> MODIS
    if "primary_ndvi" not in df.columns or df["primary_ndvi"].isna().all():
        df["primary_ndvi"] = (df["s2_ndvi"].fillna(df["landsat_ndvi"])
                              .fillna(df["modis_ndvi"]))
        print("primary_ndvi пересобран по приоритету S2 -> Landsat -> MODIS")

    df["date"] = pd.to_datetime(df["date"])
    df["year"] = df["date"].dt.year.astype(np.int32)
    df["doy"] = df["date"].dt.dayofyear.astype(np.int32)
    df["source"] = "external"
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")

    # ndvi_zscore и status — колонки задачи 2, load_raw их и так выбрасывает;
    # is_synthetic_gap во внешних данных быть не должно
    df = df.drop(columns=[c for c in ("ndvi_zscore", "status", "is_synthetic_gap")
                          if c in df.columns], errors="ignore")

    keep = (["anon_polygon_id", "date"] + SENSOR_COLS + ERA5_COLS
            + [c for c in ("ndvi_climatology_mean", "ndvi_climatology_std",
                           "n_reference_years") if c in df.columns]
            + ["year", "doy", "primary_ndvi", "crop_type", "source"])
    out = df[keep].sort_values(["anon_polygon_id", "date"]).reset_index(drop=True)
    out.to_csv(a.out, index=False, encoding="utf-8")

    # --- сводка
    obs = int(out["primary_ndvi"].notna().sum())
    per = out.groupby(["anon_polygon_id", "year"])["primary_ndvi"].count()
    print(f"\n{a.out}: {len(out)} строк, {out.anon_polygon_id.nunique()} полигонов, "
          f"{out.year.nunique()} сезонов")
    print(f"наблюдений: {obs} ({obs / max(len(out), 1):.1%} суточной сетки)")
    print(f"на полигон-сезон: медиана {per.median():.0f}")
    print(f"погода заполнена: {out.era5_temp_c.notna().mean():.1%}")

    ref = Path(a.reference)
    if ref.exists():
        r = pd.read_csv(ref, usecols=["anon_polygon_id", "date", "primary_ndvi"])
        r["year"] = pd.to_datetime(r["date"]).dt.year
        rper = r.groupby(["anon_polygon_id", "year"])["primary_ndvi"].count()
        rmed = float(r["primary_ndvi"].median())
        omed = float(out["primary_ndvi"].median())
        print(f"\nэталон {ref.name}: на полигон-сезон медиана {rper.median():.0f}, "
              f"медиана NDVI {rmed:.3f}")
        print(f"здесь:              на полигон-сезон медиана {per.median():.0f}, "
              f"медиана NDVI {omed:.3f}")
        d = omed - rmed
        print(f"расхождение медиан NDVI: {d:+.3f} — "
              + ("сходится" if abs(d) <= 0.06
                 else "РАСХОЖДЕНИЕ, эти поля живут в другом распределении"))
        if per.median() < rper.median() * 0.6:
            print("наблюдений заметно меньше эталона: ряды дырявее, "
                  "польза от них ниже, но вреда сами по себе не несут")

    print(f"\nдальше: ... --extra {a.out}")


if __name__ == "__main__":
    main()
