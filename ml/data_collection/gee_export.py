#!/usr/bin/env python3
"""Сбор датасета в схеме организаторов через Google Earth Engine.

Повторяет рецепт из RECIPE.md: те же коллекции, тот же приоритет сенсоров
(S2 -> Landsat -> MODIS), то же окно сезона и та же суточная сетка.

    earthengine authenticate          # один раз
    python data_collection/gee_export.py --fields fields.geojson \
        --years 2010-2025 --out gs://<bucket>/ndvi_external --scale 20

Экспорт идёт в задачи GEE (в Drive или GCS): выгрузка сотен полигонов за
16 сезонов — это часы, и синхронно её тянуть нельзя. Скрипт ставит задачи и
печатает их id; следить за ними в https://code.earthengine.google.com/tasks

ВАЖНО: скрипт не проверялся против живого API — на машине сборки нет доступа
к Earth Engine. Логика и идентификаторы коллекций выверены по документации и
по восстановленному рецепту, но первый запуск делай на 2-3 полигонах и одном
сезоне, сверь результат с `validate_external.py`, и только потом запускай всё.
"""

from __future__ import annotations

import argparse
import json

import ee

SEASON_START_MD = (4, 1)    # 1 апреля
SEASON_END_MD = (10, 30)    # 30 октября

# --- коллекции ровно те, что перечислены в постановке
S2 = "COPERNICUS/S2_SR_HARMONIZED"
L5, L7, L8, L9 = ("LANDSAT/LT05/C02/T1_L2", "LANDSAT/LE07/C02/T1_L2",
                  "LANDSAT/LC08/C02/T1_L2", "LANDSAT/LC09/C02/T1_L2")
MODIS = "MODIS/061/MOD13Q1"
ERA5 = "ECMWF/ERA5_LAND/HOURLY"


# ---------------------------------------------------------------- маскирование

def mask_s2(img: ee.Image) -> ee.Image:
    """Облака и тени по SCL. Классы 4,5,6,7 — растительность, почва, вода, низкая вероятность облака."""
    scl = img.select("SCL")
    good = scl.remap([4, 5, 6, 7, 11], [1, 1, 1, 1, 1], 0)
    return img.updateMask(good)


def mask_landsat(img: ee.Image) -> ee.Image:
    """QA_PIXEL: биты 3 (облако) и 4 (тень) должны быть нулевыми."""
    qa = img.select("QA_PIXEL")
    clear = qa.bitwiseAnd(1 << 3).eq(0).And(qa.bitwiseAnd(1 << 4).eq(0))
    return img.updateMask(clear)


# ---------------------------------------------------------------- индексы

def indices_from(img: ee.Image, nir: str, red: str, blue: str, green: str,
                 prefix: str, scale: float, offset: float) -> ee.Image:
    """NDVI/EVI/NDWI по одной формуле для всех сенсоров — как у организаторов.

    scale/offset приводят целочисленные значения коллекции к отражению.
    EVI намеренно НЕ обрезается: в исходных данных он тоже улетает.
    """
    b = img.select([nir, red, blue, green], ["NIR", "RED", "BLUE", "GREEN"]) \
           .multiply(scale).add(offset)
    ndvi = b.normalizedDifference(["NIR", "RED"]).rename(f"{prefix}_ndvi")
    evi = b.expression(
        "2.5 * (NIR - RED) / (NIR + 6 * RED - 7.5 * BLUE + 1)",
        {"NIR": b.select("NIR"), "RED": b.select("RED"), "BLUE": b.select("BLUE")}
    ).rename(f"{prefix}_evi")
    # NDWI Макфитерса: (GREEN - NIR) / (GREEN + NIR) — именно он даёт медиану -0.37
    ndwi = b.normalizedDifference(["GREEN", "NIR"]).rename(f"{prefix}_ndwi")
    return ee.Image.cat([ndvi, evi, ndwi]).copyProperties(img, ["system:time_start"])


def s2_indices(img):
    return indices_from(mask_s2(img), "B8", "B4", "B2", "B3", "s2", 1e-4, 0.0)


def landsat_indices(img, sensor: str):
    # у L8/L9 другие номера каналов, чем у L5/L7
    bands = (["SR_B5", "SR_B4", "SR_B2", "SR_B3"] if sensor in ("L8", "L9")
             else ["SR_B4", "SR_B3", "SR_B1", "SR_B2"])
    return indices_from(mask_landsat(img), *bands, "landsat", 2.75e-5, -0.2)


# ---------------------------------------------------------------- сбор по полигонам

def season_filter(year: int) -> ee.Filter:
    return ee.Filter.date(f"{year}-{SEASON_START_MD[0]:02d}-{SEASON_START_MD[1]:02d}",
                          f"{year}-{SEASON_END_MD[0]:02d}-{SEASON_END_MD[1]+1:02d}")


def reduce_over(fc: ee.FeatureCollection, coll: ee.ImageCollection, scale: int,
                bands: list[str] | None = None) -> ee.FeatureCollection:
    """Среднее по полигону для каждого снимка. Одна строка = полигон + дата.

    Снимки, целиком закрытые облаком над полигоном, отсеиваются: reduceRegions
    не создаёт для них свойств замаскированных каналов, и такая строка всё равно пуста.
    """
    def per_image(img):
        stats = img.reduceRegions(collection=fc, reducer=ee.Reducer.mean(),
                                  scale=scale, tileScale=4)
        date = ee.Date(img.get("system:time_start")).format("YYYY-MM-dd")
        if bands:
            stats = stats.filter(ee.Filter.notNull([bands[0]]))
        return stats.map(lambda f: f.set("date", date))
    return coll.map(per_image).flatten()


def build_landsat(region: ee.Geometry, year: int) -> ee.ImageCollection:
    """Все миссии Landsat разом — именно так получаются 20-35 наблюдений за сезон."""
    parts = []
    for cid, sensor in ((L5, "L5"), (L7, "L7"), (L8, "L8"), (L9, "L9")):
        c = (ee.ImageCollection(cid).filterBounds(region).filter(season_filter(year))
             .map(lambda im, s=sensor: landsat_indices(im, s)))
        parts.append(c)
    return ee.ImageCollection(parts[0].merge(parts[1]).merge(parts[2]).merge(parts[3]))


def era5_daily(region: ee.Geometry, year: int) -> ee.ImageCollection:
    """Среднесуточная температура и суточная сумма осадков — как в исходных данных."""
    hourly = ee.ImageCollection(ERA5).filterBounds(region).filter(season_filter(year))
    start = ee.Date(f"{year}-{SEASON_START_MD[0]:02d}-{SEASON_START_MD[1]:02d}")
    n_days = ee.Date(f"{year}-{SEASON_END_MD[0]:02d}-{SEASON_END_MD[1]:02d}").difference(start, "day")

    def one_day(offset):
        d0 = start.advance(ee.Number(offset), "day")
        day = hourly.filterDate(d0, d0.advance(1, "day"))
        temp = day.select("temperature_2m").mean().subtract(273.15).rename("era5_temp_c")
        precip = day.select("total_precipitation_hourly").sum().multiply(1000).rename("era5_precip_mm")
        return ee.Image.cat([temp, precip]).set("system:time_start", d0.millis())

    return ee.ImageCollection(ee.List.sequence(0, n_days).map(one_day))


def export_year(fields: ee.FeatureCollection, year: int, out_prefix: str,
                scale: int, to_drive: bool):
    region = fields.geometry()
    tasks = []
    sources = {
        "s2": ee.ImageCollection(S2).filterBounds(region).filter(season_filter(year)).map(s2_indices),
        "landsat": build_landsat(region, year),
        "modis": (ee.ImageCollection(MODIS).filterBounds(region).filter(season_filter(year))
                  .map(lambda im: im.select(["NDVI", "EVI"], ["modis_ndvi", "modis_evi"])
                       .multiply(1e-4).copyProperties(im, ["system:time_start"]))),
        "era5": era5_daily(region, year),
    }
    for name, coll in sources.items():
        table = reduce_over(fields, coll, scale if name != "modis" else 250)
        desc = f"{out_prefix}_{name}_{year}"
        task = (ee.batch.Export.table.toDrive(collection=table, description=desc,
                                              fileFormat="CSV", folder="ndvi_external")
                if to_drive else
                ee.batch.Export.table.toCloudStorage(collection=table, description=desc,
                                                     bucket=out_prefix.split("/")[2],
                                                     fileFormat="CSV"))
        task.start()
        tasks.append(desc)
    return tasks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fields", required=True, help="GeoJSON с контурами полей")
    ap.add_argument("--years", default="2010-2025")
    ap.add_argument("--out", default="ndvi_external", help="префикс задач или gs://bucket/prefix")
    ap.add_argument("--scale", type=int, default=20, help="метров на пиксель для S2/Landsat")
    ap.add_argument("--project", default=None, help="GEE cloud project")
    a = ap.parse_args()

    ee.Initialize(project=a.project) if a.project else ee.Initialize()
    with open(a.fields, encoding="utf-8") as f:
        fields = ee.FeatureCollection(json.load(f))
    y0, y1 = (int(x) for x in a.years.split("-"))

    all_tasks = []
    for year in range(y0, y1 + 1):
        all_tasks += export_year(fields, year, a.out, a.scale, not a.out.startswith("gs://"))
        print(f"{year}: задачи поставлены", flush=True)
    print(f"\nвсего задач: {len(all_tasks)}")
    print("следить: https://code.earthengine.google.com/tasks")


if __name__ == "__main__":
    main()
