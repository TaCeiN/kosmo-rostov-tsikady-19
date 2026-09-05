#!/usr/bin/env python3
"""Собирает один файл для --extra из любого числа внешних наборов.

    python build_training_set.py --out extra_all.csv \
        govno_dataset/*.csv extra_govno_dataset/train_2013_2019.csv ...

Задача не «склеить», а **отсеять**. По ходу хакатона набралось несколько
«дополнительных» датасетов, и большинство оказалось пересборкой того, что уже
лежит в train и test. Подмешать такой файл не просто бесполезно — вредно:

  * load_raw в конце делает drop_duplicates по (полигон, дата) с сортировкой
    по source, а "external" < "train" по алфавиту. Копия строки организаторов,
    приехавшая как external, ВЫТЕСНЯЕТ оригинал;
  * вытесненные строки исчезают из валидации: все три сценария исключают
    source == "external". Метрика перестаёт быть сравнимой с прошлыми прогонами,
    причём молча.

Отсюда правило отбора. Для каждого набора смотрим пары (полигон, дата),
которых нет в базе. Если новых пар нет вовсе — это копия, набор отбрасывается.
Если пары пересекаются, но ЗНАЧЕНИЯ на них другие — значит, id совпали
случайно (два источника независимо назвали поля AOI-0001), набор берётся
целиком с префиксом. Разделить эти два случая по именам файлов нельзя,
только по содержимому.

Что делается с принятыми наборами: префикс полигонов, культура на классы
организаторов, отсечение NDVI вне [-1, 1], пересборка primary_ndvi по
приоритету S2 -> Landsat -> MODIS, выброс колонок задачи 2.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

SENSOR_COLS = ["s2_ndvi", "s2_evi", "s2_ndwi", "landsat_ndvi", "landsat_evi",
               "landsat_ndwi", "modis_ndvi", "modis_evi"]
ERA5_COLS = ["era5_temp_c", "era5_precip_mm"]
CLIM_COLS = ["ndvi_climatology_mean", "ndvi_climatology_std", "n_reference_years"]
DROP_COLS = ["ndvi_zscore", "status", "is_synthetic_gap", "source", "primary_ndvi_true"]

CROP_MAP = {
    "wheat": "озимая пшеница", "winter_wheat": "озимая пшеница",
    "wintercereals": "озимая пшеница",
    "sunflower": "подсолнечник",
    "maize": "зерновые", "corn": "зерновые", "barley": "зерновые",
    "cereals": "зерновые", "springcereals": "зерновые",
    "farmland": "зерновые", "cropland": "зерновые",
    "pasture": "пастбища/зерновые", "grassland": "пастбища/зерновые",
}
KNOWN_CROPS = {"озимая пшеница", "зерновые", "подсолнечник", "пастбища/зерновые"}

SAME_VALUE_TOL = 1e-6      # значения считаем одинаковыми с точностью до вывода в CSV
COPY_SHARE = 0.98          # доля совпавших значений, после которой набор — копия


def map_crop(v) -> str:
    if not isinstance(v, str) or not v.strip():
        return "зерновые"
    s = v.strip()
    if s in KNOWN_CROPS:
        return s
    return CROP_MAP.get(s.lower().replace(" ", "_"), "зерновые")


def load_keys(paths: list[str]) -> tuple[set, pd.DataFrame]:
    """Пары (полигон, дата) и значения базы — того, что уже участвует в обучении."""
    frames = []
    for p in paths:
        if not Path(p).exists():
            print(f"  базы {p} нет, пропускаю")
            continue
        d = pd.read_csv(p, usecols=lambda c: c in ("anon_polygon_id", "date",
                                                   "primary_ndvi"))
        if "primary_ndvi" not in d.columns:
            d["primary_ndvi"] = np.nan
        frames.append(d)
        print(f"  база {Path(p).name}: {len(d)} строк")
    if not frames:
        sys.exit("база пуста: нужен хотя бы train_dataset.csv")
    base = pd.concat(frames, ignore_index=True)
    base = base.drop_duplicates(["anon_polygon_id", "date"], keep="first")
    return set(zip(base.anon_polygon_id, base.date)), base


def classify(df: pd.DataFrame, base_keys: set, base: pd.DataFrame) -> tuple[str, dict]:
    """Копия базы, независимый источник или частично новое. Решает содержимое."""
    keys = set(zip(df.anon_polygon_id, df.date))
    new = keys - base_keys
    overlap = keys & base_keys
    info = {"строк": len(df), "новых пар": len(new), "пересечений": len(overlap)}

    if not overlap:
        return "новый", info

    # Сравниваем значения на пересечении: одинаковые — копия, разные — совпали id
    m = df[["anon_polygon_id", "date", "primary_ndvi"]].merge(
        base, on=["anon_polygon_id", "date"], suffixes=("_new", "_base"))
    both = m.dropna(subset=["primary_ndvi_new", "primary_ndvi_base"])
    if len(both) == 0:
        same = 0.0
    else:
        same = float((both.primary_ndvi_new.sub(both.primary_ndvi_base).abs()
                      < SAME_VALUE_TOL).mean())
    info["сравнимых значений"] = len(both)
    info["совпало значений"] = f"{same:.1%}"

    if same >= COPY_SHARE and len(new) == 0:
        return "копия", info
    if same >= COPY_SHARE:
        return "частичная копия", info
    return "независимый", info


def normalize(df: pd.DataFrame, prefix: str, clip: bool) -> pd.DataFrame:
    df = df.copy()
    df["anon_polygon_id"] = prefix + df["anon_polygon_id"].astype(str)

    if "crop_type" in df.columns:
        df["crop_type"] = df["crop_type"].map(map_crop)
    else:
        df["crop_type"] = "зерновые"

    for col in SENSOR_COLS + ERA5_COLS:
        if col not in df.columns:
            df[col] = np.nan
        df[col] = pd.to_numeric(df[col], errors="coerce")

    if clip:
        for col in ("s2_ndvi", "landsat_ndvi", "modis_ndvi", "primary_ndvi"):
            if col in df.columns:
                df.loc[(df[col] < -1) | (df[col] > 1), col] = np.nan

    if "primary_ndvi" not in df.columns or df["primary_ndvi"].isna().all():
        df["primary_ndvi"] = (df["s2_ndvi"].fillna(df["landsat_ndvi"])
                              .fillna(df["modis_ndvi"]))

    df["date"] = pd.to_datetime(df["date"])
    df["year"] = df["date"].dt.year.astype(np.int32)
    df["doy"] = df["date"].dt.dayofyear.astype(np.int32)
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    df = df.drop(columns=[c for c in DROP_COLS if c in df.columns], errors="ignore")

    keep = (["anon_polygon_id", "date"] + SENSOR_COLS + ERA5_COLS
            + [c for c in CLIM_COLS if c in df.columns]
            + ["year", "doy", "primary_ndvi", "crop_type"])
    return df[keep]


def profile(df: pd.DataFrame, name: str, ref_med: float | None) -> None:
    obs = df["primary_ndvi"].notna()
    per = df[obs].groupby(["anon_polygon_id", "year"]).size()
    med = float(df.loc[obs, "primary_ndvi"].median()) if obs.any() else float("nan")
    line = (f"    {name}: {len(df)} строк, {df.anon_polygon_id.nunique()} полигонов, "
            f"наблюдений {int(obs.sum())} ({obs.mean():.1%}), "
            f"на полигон-сезон {per.median():.0f}, медиана NDVI {med:.3f}")
    if ref_med is not None and not np.isnan(med):
        d = med - ref_med
        line += f", расхождение {d:+.3f}"
        if abs(d) > 0.06:
            line += " — ДРУГОЕ РАСПРЕДЕЛЕНИЕ"
    print(line)


def main():
    ap = argparse.ArgumentParser(
        description="отбор и нормализация внешних наборов под --extra")
    ap.add_argument("sources", nargs="+", help="файлы-кандидаты")
    ap.add_argument("--out", default="extra_all.csv")
    ap.add_argument("--base", nargs="*",
                    default=["train_dataset.csv", "test_features.csv",
                             "labeled_test1.csv"],
                    help="что уже участвует в обучении: с этим и сверяем")
    ap.add_argument("--keep-copies", action="store_true",
                    help="не отбрасывать наборы, оказавшиеся копиями базы "
                         "(нужно только для отладки: они вытесняют оригиналы)")
    ap.add_argument("--no-clip", action="store_true")
    a = ap.parse_args()

    print("база (то, что уже идёт в обучение):")
    base_keys, base = load_keys(a.base)
    ref_med = float(base["primary_ndvi"].median())
    print(f"  всего уникальных пар: {len(base_keys)}, медиана NDVI {ref_med:.3f}\n")

    accepted, kept_keys = [], set(base_keys)
    for i, src in enumerate(a.sources):
        p = Path(src)
        print(f"[{i + 1}/{len(a.sources)}] {p}")
        if not p.exists():
            print("    нет файла, пропускаю")
            continue
        df = pd.read_csv(p)
        if not {"anon_polygon_id", "date"} <= set(df.columns):
            print("    нет anon_polygon_id/date — это не датасет в схеме "
                  "организаторов, пропускаю")
            continue
        if "primary_ndvi" not in df.columns:
            df["primary_ndvi"] = np.nan

        verdict, info = classify(df, kept_keys, base)
        print("    " + ", ".join(f"{k}: {v}" for k, v in info.items()))

        if verdict in ("копия", "частичная копия") and not a.keep_copies:
            print(f"    ВЕРДИКТ: {verdict} того, что уже есть -> отбрасываю. "
                  f"Подмешивание вытеснило бы строки организаторов "
                  f"и выбило их из валидации")
            continue

        prefix = f"X{i + 1}-"
        norm = normalize(df, prefix, clip=not a.no_clip)
        print(f"    ВЕРДИКТ: {verdict} -> беру, префикс {prefix}")
        profile(norm, "после нормализации", ref_med)
        accepted.append(norm)
        kept_keys |= set(zip(df.anon_polygon_id, df.date))

    if not accepted:
        print("\nНичего не принято: все кандидаты — пересборка уже имеющегося.")
        print("Учись на том, что есть: --extra labeled_test1.csv")
        return

    out = pd.concat(accepted, ignore_index=True)
    out = (out.sort_values(["anon_polygon_id", "date"])
              .drop_duplicates(["anon_polygon_id", "date"], keep="first")
              .reset_index(drop=True))
    out["source"] = "external"
    out.to_csv(a.out, index=False, encoding="utf-8")

    print(f"\n{a.out}: {len(out)} строк, {out.anon_polygon_id.nunique()} полигонов")
    profile(out, "итог", ref_med)
    print(f"\nдальше: --extra labeled_test1.csv {a.out}")


if __name__ == "__main__":
    main()
