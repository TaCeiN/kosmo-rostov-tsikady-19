"""Данные по произвольной области из Google Earth Engine — в схему организаторов.

Это звено между картой и моделью: пользователь обвёл поле, сюда приезжает
GeoJSON, отсюда уезжает DataFrame ровно той формы, которую ждёт NdviPipeline.

    from ndvi_ml.gee_fetch import init_ee, fetch_area
    init_ee()
    df = fetch_area(geojson_polygon, years=range(2015, 2026))

Повторяет рецепт организаторов (data_collection/RECIPE.md): те же коллекции,
приоритет S2 -> Landsat -> MODIS, сезон 1 апреля — 30 октября, суточная сетка.

Здесь же живут строители коллекций, которыми пользуется и пакетный сбор
(data_collection/gee_collect.py) — чтобы живой сервис и офлайн-выгрузка не
разъехались по формулам.

Одно отличие от пакетного пути: ERA5 берётся из суточного агрегата
ECMWF/ERA5_LAND/DAILY_AGGR, а не собирается из почасового. Значения те же
(среднесуточная температура, суточная сумма осадков), но почасовая сборка —
это 24 снимка на каждый из 3408 дней, и интерактивный запрос в неё упирается.
Для пакетной задачи, которая считается часами, разницы нет, для запроса из
браузера — принципиальная.
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd

SEASON_START_MD = (4, 1)
SEASON_END_MD = (10, 30)

S2 = "COPERNICUS/S2_SR_HARMONIZED"
LANDSAT_OLD = ("LANDSAT/LT05/C02/T1_L2", "LANDSAT/LE07/C02/T1_L2")
LANDSAT_NEW = ("LANDSAT/LC08/C02/T1_L2", "LANDSAT/LC09/C02/T1_L2")
MODIS = "MODIS/061/MOD13Q1"
ERA5_HOURLY = "ECMWF/ERA5_LAND/HOURLY"
ERA5_DAILY = "ECMWF/ERA5_LAND/DAILY_AGGR"

BANDS_OLD = ["SR_B4", "SR_B3", "SR_B1", "SR_B2"]   # NIR RED BLUE GREEN у L5/L7
BANDS_NEW = ["SR_B5", "SR_B4", "SR_B2", "SR_B3"]   # у L8/L9 нумерация сдвинута

SENSOR_COLS = ["s2_ndvi", "s2_evi", "s2_ndwi", "landsat_ndvi", "landsat_evi",
               "landsat_ndwi", "modis_ndvi", "modis_evi"]
ERA5_COLS = ["era5_temp_c", "era5_precip_mm"]

MAX_AREA_HA = 5000.0     # выше — интерактивный запрос не укладывается в таймаут
MAX_YEARS = 20


class GeeUnavailable(RuntimeError):
    """Earth Engine не настроен или не отвечает."""


# ------------------------------------------------------------------ инициализация

_inited = False


def init_ee(project: str | None = None) -> None:
    """Поднимает Earth Engine. Идемпотентна.

    Два способа авторизации, в порядке приоритета:

      1. сервисный аккаунт — путь к JSON-ключу в GEE_SERVICE_ACCOUNT_KEY.
         Так надо в проде: не привязано к живому человеку и не протухает;
      2. пользовательские креды от `earthengine authenticate` — так удобно
         на машине разработчика.

    Проект берётся из аргумента или из GEE_PROJECT.
    """
    global _inited
    if _inited:
        return
    try:
        import ee
    except ImportError as e:
        raise GeeUnavailable("не установлен earthengine-api: "
                             "pip install earthengine-api") from e

    project = project or os.environ.get("GEE_PROJECT")
    key = os.environ.get("GEE_SERVICE_ACCOUNT_KEY")
    try:
        if key:
            import json
            with open(key, encoding="utf-8") as f:
                email = json.load(f).get("client_email")
            creds = ee.ServiceAccountCredentials(email, key)
            ee.Initialize(creds, project=project)
        else:
            ee.Initialize(project=project) if project else ee.Initialize()
    except Exception as e:  # noqa: BLE001 — наружу отдаём одну понятную ошибку
        raise GeeUnavailable(
            f"Earth Engine не поднялся: {e}. Нужен либо GEE_SERVICE_ACCOUNT_KEY "
            f"с путём к JSON-ключу сервисного аккаунта, либо выполненный "
            f"`earthengine authenticate`. Проект: GEE_PROJECT.") from e
    _inited = True


def available() -> bool:
    try:
        init_ee()
        return True
    except GeeUnavailable:
        return False


# ------------------------------------------------------------------ маски и индексы

def mask_s2(img):
    """SCL: 4 растительность, 5 голая почва, 6 вода, 7 низкая вероятность облака, 11 снег."""
    import ee
    scl = img.select("SCL")
    keep = scl.eq(4).Or(scl.eq(5)).Or(scl.eq(6)).Or(scl.eq(7)).Or(scl.eq(11))
    return img.updateMask(keep)


def mask_landsat(img):
    """QA_PIXEL: бит 3 — облако, бит 4 — тень, оба должны быть нулевыми."""
    qa = img.select("QA_PIXEL")
    return img.updateMask(qa.bitwiseAnd(8).eq(0).And(qa.bitwiseAnd(16).eq(0)))


def indices(img, bands, prefix, scale, offset):
    """NDVI/EVI/NDWI одной формулой для всех сенсоров — как у организаторов.

    EVI намеренно не обрезается: в исходных данных он тоже улетает, когда
    знаменатель уходит в ноль. NDWI — Макфитерс через зелёный канал.
    """
    import ee
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
    import ee
    return ee.Filter.date(f"{year}-{SEASON_START_MD[0]:02d}-{SEASON_START_MD[1]:02d}",
                          f"{year}-{SEASON_END_MD[0]:02d}-{SEASON_END_MD[1]+1:02d}")


def _seasons_filter(years):
    import ee
    f = season_filter(years[0])
    for y in years[1:]:
        f = ee.Filter.Or(f, season_filter(y))
    return f


def s2_coll(region, years):
    import ee
    return (ee.ImageCollection(S2).filterBounds(region).filter(_seasons_filter(years))
            .map(lambda im: indices(mask_s2(im), ["B8", "B4", "B2", "B3"], "s2", 1e-4, 0.0)))


def landsat_coll(region, years):
    """Все миссии сразу: провал 2012 у организаторов — промежуток между L5 и L8."""
    import ee
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
    return merged.filter(_seasons_filter(years))


def modis_coll(region, years):
    import ee
    return (ee.ImageCollection(MODIS).filterBounds(region).filter(_seasons_filter(years))
            .map(lambda im: im.select(["NDVI", "EVI"], ["modis_ndvi", "modis_evi"])
                 .multiply(1e-4).copyProperties(im, ["system:time_start"])))


def era5_coll(region, years):
    """Суточный агрегат: среднесуточная температура и суточная сумма осадков."""
    import ee
    return (ee.ImageCollection(ERA5_DAILY).filterBounds(region)
            .filter(_seasons_filter(years))
            .map(lambda im: ee.Image.cat([
                im.select("temperature_2m").subtract(273.15).rename("era5_temp_c"),
                im.select("total_precipitation_sum").multiply(1000).rename("era5_precip_mm"),
            ]).copyProperties(im, ["system:time_start"])))


# ------------------------------------------------------------------ выборка

def _table(coll, region, scale: int, bands: list[str]):
    """Среднее по области на каждый снимок -> список словарей.

    Снимок, целиком закрытый облаком над областью, не даёт свойств для
    замаскированных каналов — такие строки отсеиваются до передачи.
    """
    import ee

    def per_image(img):
        date = ee.Date(img.get("system:time_start")).format("YYYY-MM-dd")
        stats = img.reduceRegion(reducer=ee.Reducer.mean(), geometry=region,
                                 scale=scale, maxPixels=1e9, bestEffort=True)
        return ee.Feature(None, stats.set("date", date))

    fc = ee.FeatureCollection(coll.map(per_image)).filter(
        ee.Filter.notNull([bands[0]]))
    rows = fc.getInfo().get("features", [])
    return [f["properties"] for f in rows]


def _to_frame(rows: list[dict], cols: list[str]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=["date"] + cols)
    d = pd.DataFrame(rows)
    for c in cols:
        if c not in d:
            d[c] = np.nan
    d = d[["date"] + cols]
    d["date"] = pd.to_datetime(d["date"])
    # два пролёта в сутки усредняем: одна строка на дату
    return d.groupby("date", as_index=False).mean(numeric_only=True)


def daily_grid(years, polygon_id: str) -> pd.DataFrame:
    """Суточная сетка сезона. Признаки считаются по ней, а не по датам съёмок."""
    idx = []
    for y in years:
        idx.append(pd.date_range(f"{y}-{SEASON_START_MD[0]:02d}-{SEASON_START_MD[1]:02d}",
                                 f"{y}-{SEASON_END_MD[0]:02d}-{SEASON_END_MD[1]:02d}",
                                 freq="D"))
    dates = pd.DatetimeIndex(np.concatenate([i.values for i in idx]))
    return pd.DataFrame({"anon_polygon_id": polygon_id, "date": dates})


def area_ha(geometry: dict) -> float:
    """Площадь в гектарах. Считается локально, без обращения к GEE."""
    import math
    def ring_ha(ring):
        lat0 = math.radians(sum(p[1] for p in ring) / len(ring))
        kx = 111_320 * math.cos(lat0)
        ky = 110_540
        s = 0.0
        for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
            s += (x1 * kx) * (y2 * ky) - (x2 * kx) * (y1 * ky)
        return abs(s) / 2 / 10_000

    t = geometry.get("type")
    coords = geometry.get("coordinates", [])
    if t == "Polygon":
        return ring_ha(coords[0])
    if t == "MultiPolygon":
        return sum(ring_ha(p[0]) for p in coords)
    raise ValueError(f"поддерживаются Polygon и MultiPolygon, пришло {t}")


def fetch_area(geometry: dict, years, polygon_id: str = "USER-AREA",
               crop_type: str = "неизвестно", scale: int = 20,
               clip_physical: bool = True) -> pd.DataFrame:
    """Спутники и погода по области -> DataFrame в схеме организаторов.

    geometry — GeoJSON Polygon или MultiPolygon в WGS84.
    years — какие сезоны тянуть. Чем больше, тем лучше: климатнорма считается
    leave-one-year-out, и на одном-двух сезонах аномалии не найдутся.

    Возвращает суточную сетку со всеми колонками, которые ждёт пайплайн.
    primary_ndvi собирается по приоритету S2 -> Landsat -> MODIS.
    """
    import ee
    init_ee()

    years = sorted(int(y) for y in years)
    if not years:
        raise ValueError("не указано ни одного года")
    if len(years) > MAX_YEARS:
        raise ValueError(f"слишком много лет: {len(years)}, максимум {MAX_YEARS}")
    ha = area_ha(geometry)
    if ha > MAX_AREA_HA:
        raise ValueError(f"область {ha:.0f} га больше предела {MAX_AREA_HA:.0f} га: "
                         "интерактивный запрос в неё не уложится, обведи поле, "
                         "а не район")

    region = ee.Geometry(geometry)
    s2 = _to_frame(_table(s2_coll(region, years), region, scale,
                          ["s2_ndvi", "s2_evi", "s2_ndwi"]),
                   ["s2_ndvi", "s2_evi", "s2_ndwi"])
    ls = _to_frame(_table(landsat_coll(region, years), region, 30,
                          ["landsat_ndvi", "landsat_evi", "landsat_ndwi"]),
                   ["landsat_ndvi", "landsat_evi", "landsat_ndwi"])
    md = _to_frame(_table(modis_coll(region, years), region, 250,
                          ["modis_ndvi", "modis_evi"]),
                   ["modis_ndvi", "modis_evi"])
    er = _to_frame(_table(era5_coll(region, years), region, 1000, ERA5_COLS),
                   ERA5_COLS)

    df = daily_grid(years, polygon_id)
    for part in (s2, ls, md, er):
        if len(part):
            df = df.merge(part, on="date", how="left")
    for c in SENSOR_COLS + ERA5_COLS:
        if c not in df:
            df[c] = np.nan

    if clip_physical:
        # Landsat изредка отдаёт значения вне физического диапазона; у себя
        # чиним — такие строки только портят вход модели
        for c in ("s2_ndvi", "landsat_ndvi", "modis_ndvi"):
            df.loc[(df[c] < -1) | (df[c] > 1), c] = np.nan

    df["primary_ndvi"] = df["s2_ndvi"].fillna(df["landsat_ndvi"]).fillna(df["modis_ndvi"])
    df["crop_type"] = crop_type
    df["year"] = df["date"].dt.year.astype(np.int32)
    df["doy"] = df["date"].dt.dayofyear.astype(np.int32)
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    keep = (["anon_polygon_id", "date"] + SENSOR_COLS + ERA5_COLS
            + ["year", "doy", "primary_ndvi", "crop_type"])
    return df[keep].sort_values(["anon_polygon_id", "date"]).reset_index(drop=True)


def fetch_stats(df: pd.DataFrame) -> dict:
    """Что удалось достать — для показа пользователю до разбора результата."""
    obs = int(df["primary_ndvi"].notna().sum())
    return {
        "days": len(df),
        "observed": obs,
        "coverage_%": round(100 * obs / max(len(df), 1), 1),
        "years": sorted(int(y) for y in df["year"].unique()),
        "by_sensor": {
            "S2": int(df["s2_ndvi"].notna().sum()),
            "Landsat": int(df["landsat_ndvi"].notna().sum()),
            "MODIS": int(df["modis_ndvi"].notna().sum()),
        },
        "weather_filled_%": round(100 * float(df["era5_temp_c"].notna().mean()), 1),
    }
