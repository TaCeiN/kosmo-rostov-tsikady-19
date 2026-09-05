#!/usr/bin/env python3
"""Сбор датасета по всей Ростовской области из Google Earth Engine — в один заход.

    pip install earthengine-api
    earthengine authenticate                  # один раз
    python data_collection/gee_rostov.py --project МОЙ-GEE-ПРОЕКТ --fields 500 --merge

Отличия от gee_collect.py (тот остаётся как запасной путь через Drive):

  * регион — настоящая граница области из FAO GAUL, а не прямоугольник.
    Прямоугольник либо резал продуктивный запад, либо цеплял сухую степь
    за границей — и то и другое смещало распределение NDVI;
  * отбор полей идёт по тайлам параллельно, квоты раздаются в Python.
    Один stratifiedSample на всю область упирается в память GEE, а квоты
    внутри GEE не дают развести поля по территории равномерно;
  * выгрузка не через Drive, а прямыми запросами getDownloadURL пулом
    потоков сразу в каталог на диске. Экспорт в Drive стоит часы ожидания
    и ручное скачивание 65 файлов; здесь всё доезжает за десятки минут;
  * геометрия полей считается ОДИН раз и кэшируется в fields.geojson.
    В экспортных задачах цепочка отбора пересчитывалась заново на каждую
    задачу — это и было основной платой за время;
  * прогон резюмируемый: готовый кусок не пересчитывается, упавший режется
    пополам и повторяется. Ctrl+C и повторный запуск продолжают с места.

Формат файлов на выходе тот же, что у gee_collect.py, поэтому дальше всё
работает без изменений:

    python run_external.py --raw rostov_raw/

Рецепт сбора (коллекции, приоритет сенсоров, окно, формулы) — RECIPE.md.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import random
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

# Консоль Windows живёт в cp1251/cp866 и роняет процесс на любом символе вне
# кодировки. Прогон eval_halfsplit.py уже потерял пятнадцать минут счёта,
# упав на печати «ΔRMSE» перед самым сохранением результата.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

try:
    import ee
except ImportError:  # pragma: no cover
    sys.exit("нет earthengine-api: pip install earthengine-api")

# ------------------------------------------------------------------ настройки

# Запасная рамка на случай, если граница области не нашлась в GAUL.
# Продуктивная часть; ею жил gee_collect.py.
FALLBACK_BOX = (38.3, 46.8, 41.3, 49.3)

CELL_M = 250          # сторона участка, м (6 га)
MAX_NDVI_STD = 0.08   # порог однородности: выше — квадрат сидит на двух полях
MIN_PEAK_NDVI = 0.25  # нижний пол: вода, голая почва, застройка

# Квоты по пиковому NDVI — доли ровно как у организаторов (39 полей, пик =
# медиана по годам от медианы NDVI за май-июнь). Порогом вместо квот выборка
# уезжает в сочные поля: замер дал медиану 0.796 против 0.618 у организаторов.
TARGET_BINS = (
    (0.00, 0.35, 0.026),
    (0.35, 0.45, 0.103),
    (0.45, 0.55, 0.179),
    (0.55, 0.65, 0.256),
    (0.65, 0.75, 0.410),
    (0.75, 2.00, 0.026),
)

CANDIDATES_PER_FIELD = 20   # точек-кандидатов на одно нужное поле
HOMO_YEAR = 2023            # год проверки однородности и пика (нужен Sentinel-2)
SEASON = ("04-01", "10-31")  # 1 апреля — 30 октября, 213 суток
TILE_DEG = 0.75             # сторона тайла отбора; на всю область один запрос
                            # не влезает в память GEE

S2 = "COPERNICUS/S2_SR_HARMONIZED"
LANDSAT_OLD = ("LANDSAT/LT05/C02/T1_L2", "LANDSAT/LE07/C02/T1_L2")
LANDSAT_NEW = ("LANDSAT/LC08/C02/T1_L2", "LANDSAT/LC09/C02/T1_L2")
MODIS = "MODIS/061/MOD13Q1"
ERA5 = "ECMWF/ERA5_LAND/HOURLY"
WORLDCEREAL = "ESA/WorldCereal/2021/MODELS/v100"

BANDS_OLD = ["SR_B4", "SR_B3", "SR_B1", "SR_B2"]   # NIR RED BLUE GREEN у L5/L7
BANDS_NEW = ["SR_B5", "SR_B4", "SR_B2", "SR_B3"]   # у L8/L9 нумерация сдвинута

S2_FIRST_YEAR = 2017        # раньше в этом регионе S2_SR_HARMONIZED пуст;
                            # годы до него не запрашиваем вовсе

# Полей в одном запросе. Разное по источникам: Landsat тянет четыре миссии
# и упирается во время раньше остальных, MODIS — 13 снимков за сезон и дешёвый.
BLOCK = {"s2": 60, "landsat": 40, "modis": 250}
MIN_BLOCK = 5               # мельче не режем: значит, дело не в размере


# ------------------------------------------------------------------ регион

def rostov_geometry() -> tuple[ee.Geometry, str]:
    """Граница Ростовской области. GAUL, с откатом на прямоугольник."""
    for asset in ("FAO/GAUL_SIMPLIFIED_500m/2015/level1", "FAO/GAUL/2015/level1"):
        try:
            fc = (ee.FeatureCollection(asset)
                  .filter(ee.Filter.stringContains("ADM1_NAME", "Rostov")))
            if fc.size().getInfo():
                return fc.geometry(), asset
        except ee.EEException:
            continue
    print("  граница в GAUL не нашлась, беру прямоугольник", FALLBACK_BOX)
    return ee.Geometry.Rectangle(list(FALLBACK_BOX)), "fallback box"


def tiles(bounds: list[float], step: float = TILE_DEG) -> list[list[float]]:
    """Режем рамку области на тайлы: отбор в каждом считается отдельным запросом."""
    x0, y0, x1, y1 = bounds
    out = []
    x = x0
    while x < x1:
        y = y0
        while y < y1:
            out.append([x, y, min(x + step, x1), min(y + step, y1)])
            y += step
        x += step
    return out


# ------------------------------------------------------------------ маски

def mask_s2(img):
    """SCL: 4 растительность, 5 голая почва, 6 вода, 7 низкая вероятность облака, 11 снег."""
    scl = img.select("SCL")
    keep = scl.eq(4).Or(scl.eq(5)).Or(scl.eq(6)).Or(scl.eq(7)).Or(scl.eq(11))
    return img.updateMask(keep)


def mask_landsat(img):
    """QA_PIXEL: бит 3 — облако, бит 4 — тень, оба должны быть нулевыми."""
    qa = img.select("QA_PIXEL")
    return img.updateMask(qa.bitwiseAnd(8).eq(0).And(qa.bitwiseAnd(16).eq(0)))


# ------------------------------------------------------------------ индексы

def indices(img, bands, prefix, scale, offset):
    """NDVI/EVI/NDWI одной формулой для всех сенсоров — как у организаторов.

    EVI намеренно не обрезается: в исходных данных он тоже улетает до 1e11,
    когда знаменатель уходит в ноль. NDWI — Макфитерс через зелёный канал.
    """
    b = (img.select(bands, ["NIR", "RED", "BLUE", "GREEN"])
            .multiply(scale).add(offset))
    ndvi = b.normalizedDifference(["NIR", "RED"]).rename(f"{prefix}_ndvi")
    evi = b.expression(
        "2.5 * (NIR - RED) / (NIR + 6 * RED - 7.5 * BLUE + 1)",
        {"NIR": b.select("NIR"), "RED": b.select("RED"), "BLUE": b.select("BLUE")},
    ).rename(f"{prefix}_evi")
    ndwi = b.normalizedDifference(["GREEN", "NIR"]).rename(f"{prefix}_ndwi")
    return ee.Image.cat([ndvi, evi, ndwi]).copyProperties(img, ["system:time_start"])


def season_filter(year: int):
    return ee.Filter.date(f"{year}-{SEASON[0]}", f"{year}-{SEASON[1]}")


def s2_coll(region, year):
    return (ee.ImageCollection(S2).filterBounds(region).filter(season_filter(year))
            .map(lambda im: indices(mask_s2(im), ["B8", "B4", "B2", "B3"], "s2", 1e-4, 0.0)))


def landsat_coll(region, year):
    """Все миссии сразу: провал 2012 у организаторов — промежуток между L5 и L8."""
    parts = []
    for cid in LANDSAT_OLD:
        parts.append(ee.ImageCollection(cid).filterBounds(region).map(
            lambda im: indices(mask_landsat(im), BANDS_OLD, "landsat", 2.75e-5, -0.2)))
    for cid in LANDSAT_NEW:
        parts.append(ee.ImageCollection(cid).filterBounds(region).map(
            lambda im: indices(mask_landsat(im), BANDS_NEW, "landsat", 2.75e-5, -0.2)))
    merged = parts[0]
    for p in parts[1:]:
        merged = merged.merge(p)
    return merged.filter(season_filter(year))


def modis_coll(region, year):
    return (ee.ImageCollection(MODIS).filterBounds(region).filter(season_filter(year))
            .map(lambda im: im.select(["NDVI", "EVI"], ["modis_ndvi", "modis_evi"])
                 .multiply(1e-4).copyProperties(im, ["system:time_start"])))


def era5_coll(region, year):
    """Среднесуточная температура и суточная сумма осадков — ровно как в данных."""
    hourly = ee.ImageCollection(ERA5).filterBounds(region).filter(season_filter(year))
    start = ee.Date(f"{year}-{SEASON[0]}")

    def one_day(offset):
        d0 = start.advance(ee.Number(offset), "day")
        day = hourly.filterDate(d0, d0.advance(1, "day"))
        t = day.select("temperature_2m").mean().subtract(273.15).rename("era5_temp_c")
        p = (day.select("total_precipitation_hourly").sum()
             .multiply(1000).rename("era5_precip_mm"))
        return ee.Image.cat([t, p]).set("system:time_start", d0.millis())

    return ee.ImageCollection(ee.List.sequence(0, 212).map(one_day))


SOURCES = {
    "s2": (s2_coll, 20, ["s2_ndvi", "s2_evi", "s2_ndwi"]),
    "landsat": (landsat_coll, 30, ["landsat_ndvi", "landsat_evi", "landsat_ndwi"]),
    "modis": (modis_coll, 250, ["modis_ndvi", "modis_evi"]),
}


# ------------------------------------------------------------------ отбор полей

def tile_candidates(tile: list[float], want: int, seed: int, prefix: str,
                    candidates_per_field: int):
    """Три фильтра подряд внутри одного тайла. Возвращает готовый к getInfo набор.

    Регулярную сетку на весь тайл строить нельзя: reproject на 250 м даёт
    массив в десятки тысяч пикселей по стороне. Поэтому случайные точки по
    маске пашни, а квадраты уже вокруг них.
    """
    region = ee.Geometry.Rectangle(tile)
    cropland = (ee.ImageCollection("ESA/WorldCover/v200").first()
                .select("Map").eq(40).rename("crop").toByte())

    points = cropland.selfMask().stratifiedSample(
        numPoints=want * candidates_per_field, classBand="crop", region=region,
        scale=100, seed=seed, geometries=True, tileScale=4)

    def to_box(f):
        # cell_id — ячейка ERA5-Land 0.1°. Погода внутри 10 км одинакова,
        # поэтому её выгружаем по ячейкам, а не по полям, и сшиваем по id.
        c = f.geometry().centroid(1).coordinates()
        clon = ee.Number(c.get(0)).multiply(10).round().divide(10)
        clat = ee.Number(c.get(1)).multiply(10).round().divide(10)
        return (ee.Feature(f.geometry().buffer(CELL_M / 2).bounds())
                .set("anon_polygon_id",
                     ee.String(prefix).cat(ee.String(f.get("system:index"))))
                .set("cell_lon", clon).set("cell_lat", clat)
                .set("cell_id", clon.format("%.1f").cat("_").cat(clat.format("%.1f"))))

    boxes = points.map(to_box)

    # Фильтр 1: доля пашни внутри квадрата. Квадрат не должен залезать
    # на дорогу, лесополосу или застройку.
    scored = (cropland.reduceRegions(collection=boxes, reducer=ee.Reducer.mean(),
                                     scale=10, tileScale=4)
              .map(lambda f: f.set("cropland_frac", f.get("mean"))))
    pure = scored.filter(ee.Filter.gte("cropland_frac", 0.95))

    # Фильтр 2: однородность. Маска пашни не отличает одно поле от двух соседних,
    # а квадрат на границе даёт средний NDVI как смесь двух культур — кривую,
    # которой в природе не существует. Летний разброс внутри квадрата это ловит.
    summer = (ee.ImageCollection(S2).filterBounds(region)
              .filterDate(f"{HOMO_YEAR}-06-01", f"{HOMO_YEAR}-08-01").map(mask_s2)
              .map(lambda im: im.normalizedDifference(["B8", "B4"]).rename("ndvi")).median())
    homo = (summer.reduceRegions(collection=pure, reducer=ee.Reducer.stdDev(),
                                 scale=10, tileScale=4)
            .map(lambda f: f.set("ndvi_std", f.get("stdDev"))))
    homogeneous = homo.filter(ee.Filter.lte("ndvi_std", MAX_NDVI_STD))

    # Фильтр 3: пиковый NDVI — медиана за май-июнь. Он же характеристика поля,
    # по которой дальше раздаются квоты.
    peak = (ee.ImageCollection(S2).filterBounds(region)
            .filterDate(f"{HOMO_YEAR}-05-01", f"{HOMO_YEAR}-06-30").map(mask_s2)
            .map(lambda im: im.normalizedDifference(["B8", "B4"]).rename("ndvi")).median())
    pool = (peak.reduceRegions(collection=homogeneous, reducer=ee.Reducer.mean(),
                               scale=10, tileScale=4)
            .map(lambda f: f.set("peak_ndvi", f.get("mean")))
            .filter(ee.Filter.gte("peak_ndvi", MIN_PEAK_NDVI)))

    keep = ["anon_polygon_id", "cell_id", "cell_lon", "cell_lat",
            "cropland_frac", "ndvi_std", "peak_ndvi"]
    return pool.select(keep, keep, True)


def collect_pool(region, region_tiles, n_fields, seed, prefix, candidates,
                 workers, verbose=True):
    """Кандидаты со всех тайлов, каждый тайл — свой параллельный запрос."""
    inside = [t for t in region_tiles]
    per_tile = max(4, int(round(n_fields * 2.0 / max(len(inside), 1))))
    pool, lock = [], threading.Lock()
    done = [0]

    def one(idx_tile):
        idx, tile = idx_tile
        fc = tile_candidates(tile, per_tile, seed + idx, prefix,
                             candidates).filterBounds(region)
        for attempt in range(3):
            try:
                feats = fc.getInfo()["features"]
                break
            except (ee.EEException, OSError) as e:
                if attempt == 2:
                    with lock:
                        done[0] += 1
                        print(f"  тайл {idx}: не отобрался ({e})", flush=True)
                    return []
                time.sleep(5 * (attempt + 1))
        out = []
        for f in feats:
            p = f["properties"]
            out.append({"id": f"{prefix}{idx:02d}-{len(out):04d}",
                        "geom": f["geometry"], "tile": idx,
                        "cell_id": p.get("cell_id"),
                        "cell_lon": p.get("cell_lon"), "cell_lat": p.get("cell_lat"),
                        "cropland_frac": p.get("cropland_frac"),
                        "ndvi_std": p.get("ndvi_std"), "peak_ndvi": p.get("peak_ndvi")})
        with lock:
            done[0] += 1
            if verbose:
                print(f"  тайл {idx + 1}/{len(inside)}: {len(out)} кандидатов "
                      f"(готово {done[0]})", flush=True)
        return out

    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        for res in ex.map(one, list(enumerate(inside))):
            pool.extend(res)
    return pool


def apply_quotas(pool, n_fields, rng):
    """Раздаём квоты по пиковому NDVI, внутри бина — по кругу между тайлами.

    Круг по тайлам важен: без него весь бин уедет в те тайлы, где кандидатов
    оказалось больше, и «вся область» превратится в пару районов.
    """
    chosen, report = [], []
    for lo, hi, share in TARGET_BINS:
        quota = max(1, round(n_fields * share))
        got = [f for f in pool
               if f["peak_ndvi"] is not None and lo <= f["peak_ndvi"] < hi]
        by_tile: dict[int, list] = {}
        for f in got:
            by_tile.setdefault(f["tile"], []).append(f)
        for lst in by_tile.values():
            rng.shuffle(lst)
        picked, order = [], sorted(by_tile)
        while len(picked) < quota and any(by_tile[t] for t in order):
            for t in order:
                if by_tile[t] and len(picked) < quota:
                    picked.append(by_tile[t].pop())
        chosen.extend(picked)
        report.append((f"[{lo:.2f},{hi:.2f})", quota, len(got), len(picked)))
    return chosen, report


def label_crops(fields):
    """Культура из ESA WorldCereal — по маскам озимых, яровых и кукурузы.

    Подсолнечника в WorldCereal нет, поэтому часть полей останется
    «неизвестно». Модель это переживает: культура — не главный признак.
    """
    products = {"wintercereals": "озимая пшеница",
                "springcereals": "зерновые",
                "maize": "зерновые"}
    labels = {f["id"]: "неизвестно" for f in fields}
    for product, name in products.items():
        try:
            img = (ee.ImageCollection(WORLDCEREAL)
                   .filter(ee.Filter.eq("product", product))
                   .select("classification").mosaic())
        except ee.EEException as e:
            print(f"  WorldCereal {product}: недоступен ({e})")
            continue
        for part in chunks(fields, 200):
            fc = ee.FeatureCollection([
                ee.Feature(ee.Geometry(f["geom"]), {"anon_polygon_id": f["id"]})
                for f in part])
            try:
                res = (img.reduceRegions(collection=fc, reducer=ee.Reducer.mean(),
                                         scale=10, tileScale=4)
                       .select(["anon_polygon_id", "mean"], None, False).getInfo())
            except (ee.EEException, OSError) as e:
                print(f"  WorldCereal {product}: кусок не посчитался ({e})")
                continue
            for f in res["features"]:
                p = f["properties"]
                if p.get("mean") is not None and p["mean"] >= 50:
                    labels[p["anon_polygon_id"]] = name
    return labels


# ------------------------------------------------------------------ выгрузка

def chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def block_fc(recs):
    """FeatureCollection из уже посчитанной геометрии — без пересчёта отбора."""
    return ee.FeatureCollection([
        ee.Feature(ee.Geometry(r["geom"]), {"anon_polygon_id": r["id"]}) for r in recs])


def reduce_coll(coll, targets, id_prop: str, scale: int, bands: list[str]):
    """Среднее по участку на каждый снимок: строка = участок + дата.

    Снимок, целиком закрытый облаком над участком, не даёт свойств для
    замаскированных каналов — такие строки выкидываем до сборки таблицы.
    """
    def per_image(img):
        date = ee.Date(img.get("system:time_start")).format("YYYY-MM-dd")

        def strip(f):
            out = {"date": date, id_prop: f.get(id_prop)}
            for b in bands:
                out[b] = f.get(b)
            return ee.Feature(None, out)

        stats = img.reduceRegions(collection=targets, reducer=ee.Reducer.mean(),
                                  scale=scale, tileScale=4)
        return stats.filter(ee.Filter.notNull([bands[0]])).map(strip)

    return coll.map(per_image).flatten()


def download(fc, cols, path: Path, timeout: int) -> int:
    """Считает таблицу интерактивно и кладёт CSV на диск. Возвращает число строк."""
    url = fc.getDownloadURL(filetype="CSV", selectors=cols,
                            filename=path.stem)
    tmp = path.with_suffix(".part")
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r, open(tmp, "wb") as out:
            shutil.copyfileobj(r, out)
        with open(tmp, "rb") as f:
            rows = max(sum(1 for _ in f) - 1, 0)
        tmp.replace(path)
        return rows
    except BaseException:
        tmp.unlink(missing_ok=True)   # недокачанный кусок нельзя оставлять:
        raise                         # он выглядел бы как готовый при резюме


# Отказ по частоте запросов. Резать блок в ответ на него нельзя: деление даёт
# ВДВОЕ больше запросов, то есть ровно то, на что сервер и жалуется. Только
# пауза. Первый прогон 8 потоками словил 429 на трёх кусках из четырёх и потерял
# три файла именно потому, что 429 лежал в общем списке «тяжело, режем».
RATE_LIMIT = ("429", "Too Many", "Too many", "rate limit", "Rate Limit",
              "quota", "Quota", "RESOURCE_EXHAUSTED")

# Отказ по весу вычисления. Вот на него деление и рассчитано.
HEAVY = ("timed out", "Timed out", "memory", "Computation", "internal error",
         "500", "502", "503")

RATE_TRIES = 7          # попыток пробиться сквозь лимит частоты
BACKOFF_BASE = 8.0      # первая пауза, дальше удвоение до потолка
BACKOFF_MAX = 180.0


class Throttle:
    """Общий тормоз на все потоки: 429 у одного — пауза у всех.

    Иначе остальные потоки продолжают долбить в ту же секунду и держат
    лимит открытым; отступать надо всем сразу.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._until = 0.0
        self.hits = 0

    def wait(self):
        while True:
            with self._lock:
                left = self._until - time.time()
            if left <= 0:
                return
            time.sleep(min(left, 2.0))

    def hit(self, seconds: float):
        with self._lock:
            self.hits += 1
            self._until = max(self._until, time.time() + seconds)


THROTTLE = Throttle()


def _kind(msg: str) -> str:
    if any(k in msg for k in RATE_LIMIT):
        return "rate"
    if any(k in msg for k in HEAVY):
        return "heavy"
    return "fatal"


def fetch_chunk(job, outdir: Path, region, timeout: int, log) -> tuple[int, int]:
    """Один кусок: источник × год × блок полей. Падает — режется пополам.

    Возвращает (успешных файлов, строк). Готовый файл не пересчитывается,
    поэтому повторный запуск скрипта продолжает с места обрыва.
    """
    source, year, recs, tag = job
    path = outdir / f"ndvi_{source}_{year}_{tag}.csv"
    if path.exists():
        return 1, -1
    if source == "era5":
        cells = recs
        fc = ee.FeatureCollection([
            ee.Feature(ee.Geometry.Point([c["lon"], c["lat"]]), {"cell_id": c["id"]})
            for c in cells])
        table = reduce_coll(era5_coll(region, year), fc, "cell_id", 1000,
                            ["era5_temp_c", "era5_precip_mm"])
        cols = ["cell_id", "date", "era5_temp_c", "era5_precip_mm"]
    else:
        maker, scale, bands = SOURCES[source]
        fc = block_fc(recs)
        table = reduce_coll(maker(fc.geometry(), year), fc, "anon_polygon_id",
                            scale, bands)
        cols = ["anon_polygon_id", "date"] + bands

    for attempt in range(RATE_TRIES):
        THROTTLE.wait()
        try:
            rows = download(table, cols, path, timeout)
            log(f"  {path.name}: {rows} строк")
            return 1, rows
        except (ee.EEException, urllib.error.URLError, OSError, TimeoutError) as e:
            msg = str(e)
            kind = _kind(msg)

            if kind == "rate":
                # Ждём и повторяем ТОТ ЖЕ кусок. Пауза общая на все потоки,
                # джиттер — чтобы они не проснулись одновременно и не легли снова.
                pause = min(BACKOFF_BASE * 2 ** attempt, BACKOFF_MAX)
                pause += random.uniform(0, pause * 0.3)
                THROTTLE.hit(pause)
                log(f"  {path.name}: лимит запросов, пауза {pause:.0f} с "
                    f"(попытка {attempt + 1}/{RATE_TRIES})")
                time.sleep(pause)
                continue

            if kind == "heavy" and len(recs) > MIN_BLOCK:
                half = len(recs) // 2
                log(f"  {path.name}: тяжело ({msg[:80]}), "
                    f"режу на {half} + {len(recs) - half}")
                ok = rows = 0
                for i, part in enumerate((recs[:half], recs[half:])):
                    o, r = fetch_chunk((source, year, part, f"{tag}{chr(97 + i)}"),
                                       outdir, region, timeout, log)
                    ok += o
                    rows += max(r, 0)
                return ok, rows

            log(f"  ОШИБКА {path.name}: {msg[:160]}")
            return 0, 0

    log(f"  ОШИБКА {path.name}: не пробился сквозь лимит запросов за "
        f"{RATE_TRIES} попыток — снизь --workers")
    return 0, 0


def build_jobs(fields, cells, years, batch, block_mult):
    jobs = []
    for source in ("s2", "landsat", "modis"):
        size = max(MIN_BLOCK, int(BLOCK[source] * block_mult))
        for year in years:
            if source == "s2" and year < S2_FIRST_YEAR:
                continue          # до 2017 коллекция здесь пуста, запрос впустую
            for k, part in enumerate(chunks(fields, size)):
                jobs.append((source, year, part, f"b{batch}_p{k:02d}"))
    for year in years:
        jobs.append(("era5", year, cells, f"b{batch}"))
    # Тяжёлое вперёд: длинный хвост коротких задач в конце лучше, чем наоборот
    order = {"landsat": 0, "s2": 1, "era5": 2, "modis": 3}
    jobs.sort(key=lambda j: (order[j[0]], j[1]))
    return jobs


# ------------------------------------------------------------------ паспорт

def write_meta(fields, crops, path: Path):
    cols = ["anon_polygon_id", "cell_id", "cell_lon", "cell_lat",
            "cropland_frac", "ndvi_std", "peak_ndvi", "crop_type", "tile"]
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(",".join(cols) + "\n")
        for r in fields:
            row = [r["id"], r["cell_id"], r["cell_lon"], r["cell_lat"],
                   r["cropland_frac"], r["ndvi_std"], r["peak_ndvi"],
                   crops.get(r["id"], "неизвестно"), r["tile"]]
            f.write(",".join("" if v is None else str(v) for v in row) + "\n")


def save_fields(fields, path: Path):
    path.write_text(json.dumps(
        {"type": "FeatureCollection",
         "features": [{"type": "Feature", "geometry": r["geom"],
                       "properties": {k: v for k, v in r.items() if k != "geom"}}
                      for r in fields]}, ensure_ascii=False), encoding="utf-8")


def load_fields(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for f in data["features"]:
        r = dict(f["properties"])
        r["geom"] = f["geometry"]
        out.append(r)
    return out


def summarize(fields):
    import statistics as st
    peaks = [f["peak_ndvi"] for f in fields if f["peak_ndvi"] is not None]
    if not peaks:
        return
    def q(xs, p):
        return sorted(xs)[min(int(p * len(xs)), len(xs) - 1)]
    print(f"\nотобрано полей: {len(fields)}, тайлов задействовано "
          f"{len({f['tile'] for f in fields})}, ячеек погоды "
          f"{len({f['cell_id'] for f in fields})}")
    print(f"пик NDVI: медиана {st.median(peaks):.3f}, 10% {q(peaks, .1):.3f}, "
          f"90% {q(peaks, .9):.3f}")
    print("эталон организаторов: медиана 0.618, 10% 0.402, 90% 0.724")
    d = st.median(peaks) - 0.618
    verdict = ("распределение сходится" if abs(d) <= 0.06
               else "РАСХОЖДЕНИЕ: поля живут не в том распределении")
    print(f"расхождение медиан: {d:+.3f} — {verdict}")


# ------------------------------------------------------------------ main

def main():
    ap = argparse.ArgumentParser(
        description="сбор датасета по всей Ростовской области из GEE")
    ap.add_argument("--project", default=None, help="GEE cloud project (обычно нужен)")
    ap.add_argument("--fields", type=int, default=500, help="сколько полей собрать")
    ap.add_argument("--years", default="2010-2025")
    ap.add_argument("--outdir", default="rostov_raw", help="куда класть CSV")
    ap.add_argument("--batch", type=int, default=1,
                    help="номер партии: меняет сид отбора и префикс id, "
                         "чтобы вторая партия не пересекалась с первой")
    ap.add_argument("--workers", type=int, default=4,
                    help="параллельных запросов к GEE. Больше 6 упирается в "
                         "лимит частоты (429): скрипт переживает его паузами, "
                         "но общее время от этого не падает")
    ap.add_argument("--timeout", type=int, default=900, help="таймаут запроса, с")
    ap.add_argument("--tile", type=float, default=TILE_DEG,
                    help="сторона тайла отбора в градусах")
    ap.add_argument("--candidates", type=int, default=CANDIDATES_PER_FIELD,
                    help="точек-кандидатов на одно нужное поле")
    ap.add_argument("--block-mult", type=float, default=1.0,
                    help="множитель размера блока полей в запросе: <1 при "
                         "падениях по времени, >1 если всё летает")
    ap.add_argument("--no-crops", action="store_true",
                    help="не размечать культуру по ESA WorldCereal")
    ap.add_argument("--reselect", action="store_true",
                    help="пересобрать отбор полей, даже если fields.geojson готов")
    ap.add_argument("--select-only", action="store_true",
                    help="только отбор полей и его сводка, без выгрузки")
    ap.add_argument("--merge", action="store_true",
                    help="в конце свести в схему организаторов и сверить "
                         "распределения (merge_external + validate_external)")
    ap.add_argument("--train", default="train_dataset.csv",
                    help="эталон для сверки распределений при --merge")
    ap.add_argument("--out", default="external_train.csv",
                    help="куда писать сведённый датасет при --merge")
    a = ap.parse_args()

    if a.project and not a.project.isascii():
        sys.exit(f"--project {a.project!r}: id проекта не может быть кириллицей.\n"
                 "Подставь настоящий id Cloud-проекта — он в правом верхнем углу\n"
                 "https://code.earthengine.google.com. Выглядит как ee-nikolay.")
    try:
        ee.Initialize(project=a.project) if a.project else ee.Initialize()
    except ee.EEException as e:
        sys.exit(f"Earth Engine не поднялся: {e}\n"
                 "Проверь: earthengine authenticate выполнен, проект зарегистрирован\n"
                 "в Earth Engine (https://code.earthengine.google.com/register).")

    y0, y1 = (int(x) for x in a.years.split("-"))
    years = list(range(y0, y1 + 1))
    outdir = Path(a.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    fields_path = outdir / f"fields_b{a.batch}.geojson"
    rng = random.Random(42 + a.batch * 1000)
    prefix = f"ROS{a.batch}-"

    print(f"регион: Ростовская область целиком, полей {a.fields}, "
          f"годы {y0}-{y1}, партия b{a.batch}")
    region, src = rostov_geometry()
    bounds = region.bounds().coordinates().getInfo()[0]
    xs = [p[0] for p in bounds]
    ys = [p[1] for p in bounds]
    box = [min(xs), min(ys), max(xs), max(ys)]
    grid = tiles(box, a.tile)
    print(f"граница: {src}, рамка {tuple(round(v, 2) for v in box)}, "
          f"тайлов {len(grid)}")

    # --- отбор полей: считается один раз и кэшируется
    if fields_path.exists() and not a.reselect:
        fields = load_fields(fields_path)
        print(f"отбор взят из {fields_path}: {len(fields)} полей "
              f"(--reselect пересоберёт)")
    else:
        print(f"отбор полей по тайлам, {a.workers} потоков...", flush=True)
        t0 = time.time()
        pool = collect_pool(region, grid, a.fields, 42 + a.batch * 1000, prefix,
                            a.candidates, a.workers)
        print(f"пул кандидатов: {len(pool)} за {time.time() - t0:.0f} с")
        if not pool:
            sys.exit("пул пуст: подними --candidates или проверь доступ к WorldCover")
        fields, report = apply_quotas(pool, a.fields, rng)
        print("\nквоты по пиковому NDVI (доли как у организаторов):")
        for name, quota, have, took in report:
            mark = "" if took >= quota else f"  НЕ ХВАТАЕТ ещё {quota - took}"
            print(f"  {name}: квота {quota:>3}, в пуле {have:>5}, взято {took:>3}{mark}")
        if len(fields) < a.fields * 0.8:
            print(f"\nвзято {len(fields)} из {a.fields}: подними --candidates "
                  f"(сейчас {a.candidates}) и запусти с --reselect")
        save_fields(fields, fields_path)

    summarize(fields)

    crops = {}
    if not a.no_crops:
        print("\nразметка культуры по ESA WorldCereal...", flush=True)
        crops = label_crops(fields)
        counts: dict[str, int] = {}
        for v in crops.values():
            counts[v] = counts.get(v, 0) + 1
        print("  " + ", ".join(f"{k}: {v}" for k, v in sorted(counts.items())))

    meta_path = outdir / f"ndvi_fields_meta_b{a.batch}.csv"
    write_meta(fields, crops, meta_path)
    print(f"паспорт участков: {meta_path}")

    if a.select_only:
        print("\n--select-only: выгрузку не запускаю. "
              "Тот же запуск без флага пойдёт дальше по кэшу отбора.")
        return

    # --- выгрузка
    cells = {}
    for f in fields:
        cells[f["cell_id"]] = {"id": f["cell_id"], "lon": f["cell_lon"],
                               "lat": f["cell_lat"]}
    cell_list = sorted(cells.values(), key=lambda c: c["id"])

    jobs = build_jobs(fields, cell_list, years, a.batch, a.block_mult)
    ready = sum(1 for j in jobs
                if (outdir / f"ndvi_{j[0]}_{j[1]}_{j[3]}.csv").exists())
    print(f"\nкусков к выгрузке: {len(jobs)} (готово с прошлого раза {ready}), "
          f"ячеек погоды {len(cell_list)}, потоков {a.workers}")
    print(f"пишу в {outdir.resolve()}, Ctrl+C можно — повторный запуск продолжит")

    lock = threading.Lock()
    counter = [0]

    def log(msg):
        # Счётчик без знаменателя: деление тяжёлых кусков рождает новые файлы,
        # и «18 из 4» в прошлой версии выглядело как ошибка.
        with lock:
            counter[0] += 1
            print(f"[{counter[0]:>3}]{msg}", flush=True)

    t0 = time.time()
    ok = rows = 0
    with cf.ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = [ex.submit(fetch_chunk, j, outdir, region, a.timeout, log)
                for j in jobs]
        try:
            for fut in cf.as_completed(futs):
                o, r = fut.result()
                ok += o
                rows += max(r, 0)
        except KeyboardInterrupt:
            print("\nпрерывание: доделываю запущенные куски и выхожу")
            for fut in futs:
                fut.cancel()
            raise

    dt = time.time() - t0
    files = len(list(outdir.glob("ndvi_*_*.csv")))
    print(f"\nготово: кусков {ok} из {len(jobs)} запланированных, файлов в "
          f"каталоге {files}, новых строк {rows}, {dt / 60:.1f} мин")
    if THROTTLE.hits:
        print(f"лимит частоты срабатывал {THROTTLE.hits} раз. "
              f"Следующий прогон — с --workers {max(2, a.workers // 2)}")
    if ok < len(jobs):
        print(f"не доехало {len(jobs) - ok} кусков. Запусти ту же команду ещё раз — "
              f"готовое пропустится. Падает по времени — --block-mult 0.5, "
              f"по лимиту запросов — меньше --workers")

    if a.merge:
        here = Path(__file__).parent
        run = [sys.executable, "-W", "ignore"]
        print("\n" + "=" * 70 + "\nсведение в схему организаторов\n" + "=" * 70)
        subprocess.run(run + [str(here / "merge_external.py"), "--raw", str(outdir),
                              "--out", a.out], check=True)
        if Path(a.train).exists():
            print("\n" + "=" * 70 + "\nсверка распределений\n" + "=" * 70)
            subprocess.run(run + [str(here / "validate_external.py"),
                                  "--external", a.out, "--reference", a.train])
        print(f"\nдальше: python run_experiment.py --train {a.train} "
              f"--test test2_features.csv --extra {a.out} --rounds 15")
    else:
        print(f"\nдальше: python run_external.py --raw {outdir}")


if __name__ == "__main__":
    main()
