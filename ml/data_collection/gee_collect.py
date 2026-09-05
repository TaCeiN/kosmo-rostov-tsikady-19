#!/usr/bin/env python3
"""Сбор дополнительных полей через Google Earth Engine — одной командой.

    pip install earthengine-api
    earthengine authenticate                       # один раз
    python data_collection/gee_collect.py --project МОЙ-GEE-ПРОЕКТ --fields 300 --watch

Скрипт сам отбирает поля внутри GEE, сам ставит задачи экспорта и сам за ними
следит. Вкладку Tasks в браузере открывать не нужно — 65 задач руками не жмут.

Отличия от gee_code_editor.js (тот остаётся как запасной путь через браузер):

  * присваивается cell_id/cell_lon/cell_lat. В JS блок привязки к ячейке ERA5
    состоит из одного комментария, а cells их читает — погода не сшивается;
  * в паспорт полей едут все три метрики отбора, а не только последняя:
    у reduceRegions выход всегда называется mean, и цепочка фильтров затирает
    предыдущий mean следующим;
  * задачи стартуют из скрипта, состояние опрашивается до конца.

Рецепт сбора — data_collection/RECIPE.md, отбор полей — три фильтра подряд
(чистота пашни, однородность, продуктивность), см. комментарии по месту.
"""

from __future__ import annotations

import argparse
import sys
import time

try:
    import ee
except ImportError:  # pragma: no cover
    sys.exit("нет earthengine-api: pip install earthengine-api")

# ------------------------------------------------------------------ настройки

# Продуктивная часть Ростовской области. Первая рамка уходила на юго-восток
# в сухую степь у границы с Калмыкией: собранные там поля дали NDVI на 0.10
# ниже, чем у организаторов. Партия b1 собрана именно по ней — она непригодна.
REGION_BOX = (38.3, 46.8, 41.3, 49.3)

CELL_M = 250          # сторона участка, м (6 га)
MAX_NDVI_STD = 0.08   # порог однородности: выше — квадрат сидит на двух полях
MIN_PEAK_NDVI = 0.25  # нижний пол: вода, голая почва, застройка. Не фильтр
                      # продуктивности — за распределение отвечают квоты ниже.

# Квоты по пиковому NDVI. Одного нижнего порога мало: фильтры чистоты пашни и
# однородности сами по себе отбирают крупные ухоженные поля, и выборка уезжает
# в сочные. Замер на 231 отобранном участке дал медиану пика 0.796 против 0.618
# у организаторов, причём больше половины падало в бин, которому положено 2.6%.
# Поэтому берём поля не по порогу, а долями — ровно в той пропорции, в какой
# они лежат у организаторов (39 полей, пик = медиана по годам от медианы NDVI
# за май-июнь). Иначе внешние поля живут в другом распределении и тянут модель.
TARGET_BINS = (
    (0.00, 0.35, 0.026),
    (0.35, 0.45, 0.103),
    (0.45, 0.55, 0.179),
    (0.55, 0.65, 0.256),
    (0.65, 0.75, 0.410),
    (0.75, 2.00, 0.026),
)

CANDIDATES_PER_FIELD = 20   # сколько точек-кандидатов на одно нужное поле;
                            # подбирается по воронке, см. --dry-run
HOMO_YEAR = 2023      # год проверки однородности и пика (нужен Sentinel-2)
SEASON = ("04-01", "10-31")   # 1 апреля — 30 октября, 213 суток
DRIVE_FOLDER = "ndvi_external"

S2 = "COPERNICUS/S2_SR_HARMONIZED"
LANDSAT_OLD = ("LANDSAT/LT05/C02/T1_L2", "LANDSAT/LE07/C02/T1_L2")
LANDSAT_NEW = ("LANDSAT/LC08/C02/T1_L2", "LANDSAT/LC09/C02/T1_L2")
MODIS = "MODIS/061/MOD13Q1"
ERA5 = "ECMWF/ERA5_LAND/HOURLY"

BANDS_OLD = ["SR_B4", "SR_B3", "SR_B1", "SR_B2"]   # NIR RED BLUE GREEN у L5/L7
BANDS_NEW = ["SR_B5", "SR_B4", "SR_B2", "SR_B3"]   # у L8/L9 нумерация сдвинута


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


# ------------------------------------------------------------------ отбор полей

def select_fields(region, n_fields: int, seed: int, prefix: str,
                  candidates_per_field: int = CANDIDATES_PER_FIELD):
    """Три фильтра подряд. Возвращает (участки, ячейки погоды, стадии воронки).

    Регулярную сетку на весь регион строить нельзя: reproject на 250 м даёт
    массив в десятки тысяч пикселей по стороне, GEE его не считает. Поэтому
    случайные точки по маске пашни, а квадраты уже вокруг них.
    """
    cropland = (ee.ImageCollection("ESA/WorldCover/v200").first()
                .select("Map").eq(40).rename("crop").toByte())

    points = cropland.selfMask().stratifiedSample(
        numPoints=n_fields * candidates_per_field,   # три фильтра съедают кандидатов
        classBand="crop", region=region, scale=100, seed=seed,
        geometries=True, tileScale=4)

    def to_box(f):
        # cell_id — ячейка ERA5-Land 0.1°. Погода внутри 10 км одинакова,
        # поэтому её выгружаем по ячейкам, а не по полям, и сшиваем по этому id.
        c = f.geometry().centroid(1).coordinates()
        clon = ee.Number(c.get(0)).multiply(10).round().divide(10)
        clat = ee.Number(c.get(1)).multiply(10).round().divide(10)
        return (ee.Feature(f.geometry().buffer(CELL_M / 2).bounds())
                .set("anon_polygon_id", ee.String(prefix).cat(ee.String(f.get("system:index"))))
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

    # Шаг 3: пиковый NDVI — медиана за май-июнь. Он же характеристика поля,
    # по которой дальше раздаются квоты.
    peak = (ee.ImageCollection(S2).filterBounds(region)
            .filterDate(f"{HOMO_YEAR}-05-01", f"{HOMO_YEAR}-06-30").map(mask_s2)
            .map(lambda im: im.normalizedDifference(["B8", "B4"]).rename("ndvi")).median())
    scored3 = (peak.reduceRegions(collection=homogeneous, reducer=ee.Reducer.mean(),
                                  scale=10, tileScale=4)
               .map(lambda f: f.set("peak_ndvi", f.get("mean"))))
    pool = scored3.filter(ee.Filter.gte("peak_ndvi", MIN_PEAK_NDVI))

    # Квоты: из каждого бина берём столько полей, сколько положено по доле
    # у организаторов. Порог вместо квот дал бы медиану 0.796 вместо 0.618.
    bins, parts = {}, []
    for lo, hi, share in TARGET_BINS:
        b = pool.filter(ee.Filter.And(ee.Filter.gte("peak_ndvi", lo),
                                      ee.Filter.lt("peak_ndvi", hi)))
        bins[f"[{lo:.2f},{hi:.2f})"] = (b, max(1, round(n_fields * share)))
        parts.append(b.limit(max(1, round(n_fields * share))))
    fields = parts[0]
    for p in parts[1:]:
        fields = fields.merge(p)

    cells = fields.distinct(["cell_id"]).map(
        lambda f: ee.Feature(ee.Geometry.Point([f.getNumber("cell_lon"),
                                                f.getNumber("cell_lat")]))
                    .set("cell_id", f.get("cell_id")))
    stages = {"кандидаты": points, "чистая пашня": pure,
              "однородные": homogeneous, "пул после пола": pool}
    return fields, cells, stages, bins


# ------------------------------------------------------------------ таблицы

def reduce_coll(coll, targets, id_prop: str, scale: int, bands: list[str]):
    """Среднее по участку на каждый снимок: строка = участок + дата.

    Снимок, целиком закрытый облаком над участком, не даёт свойств для
    замаскированных каналов — такие строки выкидываем до сборки таблицы.
    Геометрия обнуляется, иначе в CSV приезжает бесполезная колонка .geo.
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


def start_exports(region, fields, cells, years, batch: int, folder: str):
    tasks = []

    def add(collection, desc):
        t = ee.batch.Export.table.toDrive(collection=collection, description=desc,
                                          folder=folder, fileFormat="CSV")
        t.start()
        tasks.append((desc, t))

    # Паспорт участков. Без него ERA5 не пришьётся — файл терять нельзя.
    meta_cols = ["anon_polygon_id", "cell_id", "cropland_frac", "ndvi_std", "peak_ndvi"]
    add(fields.select(meta_cols, meta_cols, False), f"ndvi_fields_meta_b{batch}")

    for year in years:
        add(reduce_coll(s2_coll(region, year), fields, "anon_polygon_id", 20,
                        ["s2_ndvi", "s2_evi", "s2_ndwi"]), f"ndvi_s2_{year}_b{batch}")
        add(reduce_coll(landsat_coll(region, year), fields, "anon_polygon_id", 30,
                        ["landsat_ndvi", "landsat_evi", "landsat_ndwi"]),
            f"ndvi_landsat_{year}_b{batch}")
        add(reduce_coll(modis_coll(region, year), fields, "anon_polygon_id", 250,
                        ["modis_ndvi", "modis_evi"]), f"ndvi_modis_{year}_b{batch}")
        add(reduce_coll(era5_coll(region, year), cells, "cell_id", 1000,
                        ["era5_temp_c", "era5_precip_mm"]), f"ndvi_era5_{year}_b{batch}")
        print(f"  {year}: задачи поставлены", flush=True)
    return tasks


def watch(tasks, poll: int = 60):
    """Опрашивает задачи до конца. Возвращает True, если всё доехало."""
    pending = {desc: t for desc, t in tasks}
    done, failed = {}, {}
    print(f"\nслежу за {len(pending)} задачами, опрос раз в {poll} с. Ctrl+C — выйти,"
          f" задачи продолжат считаться на серверах Google")
    while pending:
        time.sleep(poll)
        for desc in list(pending):
            try:
                state = pending[desc].status().get("state", "UNKNOWN")
            except Exception as e:            # сеть моргнула — не роняем слежение
                print(f"  {desc}: опрос не удался ({e})")
                continue
            if state == "COMPLETED":
                done[desc] = state
                del pending[desc]
            elif state in ("FAILED", "CANCELLED"):
                msg = pending[desc].status().get("error_message", "")
                failed[desc] = msg
                print(f"  ОШИБКА {desc}: {msg}")
                del pending[desc]
        print(f"  готово {len(done)}, в работе {len(pending)}, упало {len(failed)}",
              flush=True)
    print(f"\nвсё: успешно {len(done)}, упало {len(failed)}")
    if failed:
        print("упавшие задачи (перезапусти их с меньшим --fields или по частям лет):")
        for d, m in failed.items():
            print(f"  {d}: {m}")
    return not failed


def main():
    ap = argparse.ArgumentParser(description="сбор внешних полей через GEE")
    ap.add_argument("--project", default=None, help="GEE cloud project (обычно нужен)")
    ap.add_argument("--fields", type=int, default=300, help="сколько полей собрать")
    ap.add_argument("--years", default="2010-2025")
    ap.add_argument("--batch", type=int, default=2,
                    help="номер партии: меняет сид выборки и префикс id. b1 занята "
                         "старой рамкой, начинать с 2")
    ap.add_argument("--folder", default=DRIVE_FOLDER, help="папка в Google Drive")
    ap.add_argument("--watch", action="store_true", help="следить до конца")
    ap.add_argument("--poll", type=int, default=60, help="период опроса, с")
    ap.add_argument("--candidates", type=int, default=CANDIDATES_PER_FIELD,
                    help="точек-кандидатов на одно нужное поле: мало — недоберёшь "
                         "полей, много — дороже отбор. Подбирается по --dry-run")
    ap.add_argument("--dry-run", action="store_true",
                    help="только показать, сколько полей отобралось, без экспорта")
    a = ap.parse_args()

    if a.project and not a.project.isascii():
        sys.exit(f"--project {a.project!r}: id проекта не может быть кириллицей.\n"
                 "Это плейсхолдер из инструкции, подставь настоящий id Cloud-проекта —\n"
                 "он в правом верхнем углу https://code.earthengine.google.com\n"
                 "или в https://console.cloud.google.com, поле «ID проекта».\n"
                 "Выглядит как ee-nikolay или ndvi-hack-471203.")

    try:
        ee.Initialize(project=a.project) if a.project else ee.Initialize()
    except ee.EEException as e:
        sys.exit(f"Earth Engine не поднялся: {e}\n"
                 "Проверь: earthengine authenticate выполнен, проект зарегистрирован\n"
                 "в Earth Engine (https://code.earthengine.google.com/register).")

    y0, y1 = (int(x) for x in a.years.split("-"))
    years = list(range(y0, y1 + 1))
    region = ee.Geometry.Rectangle(list(REGION_BOX))
    seed = 42 + a.batch * 1000
    prefix = f"EXT{a.batch}-"

    print(f"регион {REGION_BOX}, полей {a.fields}, годы {y0}-{y1}, партия b{a.batch}")
    fields, cells, stages, bins = select_fields(region, a.fields, seed, prefix,
                                                a.candidates)

    if a.dry_run:
        # getInfo считает отбор интерактивно; на больших наборах это долго,
        # поэтому только в dry-run и никогда в боевом прогоне
        import statistics as st
        print("считаю отбор (может занять минуты)...", flush=True)

        sizes, prev = {}, None
        for name, fc in stages.items():
            sizes[name] = fc.size().getInfo()
            share = "" if prev is None else f"  ({sizes[name] / max(prev, 1):.0%} от прошлой)"
            print(f"  {name:>14}: {sizes[name]:>6}{share}", flush=True)
            prev = sizes[name]

        print("\nквоты по пиковому NDVI (доли как у организаторов):")
        short, quota_sum = [], 0
        for name, (fc, quota) in bins.items():
            have = fc.size().getInfo()
            quota_sum += quota
            mark = "" if have >= quota else f"  НЕ ХВАТАЕТ, нужно ещё {quota - have}"
            print(f"  {name}: квота {quota:>3}, в пуле {have:>4}{mark}", flush=True)
            if have < quota:
                short.append((name, quota / max(have, 1)))
        print(f"  итого квот: {quota_sum}")

        # кандидатов на одно поле — по самому дефицитному бину, а не по среднему:
        # добор полей упирается именно в него
        worst = max((r for _, r in short), default=1.0)
        need = a.candidates * max(worst, quota_sum / max(sizes["пул после пола"], 1))
        print(f"\nвыход воронки: {sizes['пул после пола'] / max(sizes['кандидаты'], 1):.1%}"
              f" от кандидатов")
        if short:
            print(f"дефицит в бинах: {', '.join(n for n, _ in short)}")
            print(f"  -> запускай с --candidates {int(need * 1.3) + 1}")
        else:
            print(f"кандидатов хватает (сейчас --candidates {a.candidates})")

        peaks = fields.aggregate_array("peak_ndvi").getInfo()
        stds = fields.aggregate_array("ndvi_std").getInfo()
        if peaks:
            def q(xs, p):
                return sorted(xs)[min(int(p * len(xs)), len(xs) - 1)]
            print(f"\nпик NDVI отобранных: медиана {st.median(peaks):.3f}, "
                  f"10% {q(peaks, .1):.3f}, 90% {q(peaks, .9):.3f}, "
                  f"мин {min(peaks):.3f}, макс {max(peaks):.3f}")
            print("эталон организаторов:  медиана 0.618, 10% 0.402, 90% 0.724, "
                  "мин 0.332, макс 0.772")
            d = st.median(peaks) - 0.618
            tail = ("распределение сходится" if abs(d) <= 0.06
                    else "РАСХОЖДЕНИЕ: поля живут не в том распределении")
            print(f"расхождение медиан: {d:+.3f} — {tail}")
            print(f"разброс NDVI внутри участка: медиана {st.median(stds):.3f} "
                  f"(порог {MAX_NDVI_STD})")
        print("\nустраивает? тот же запуск без --dry-run поставит задачи")
        return

    n_tasks = len(years) * 4 + 1
    print(f"ставлю {n_tasks} задач, выгрузка в Google Drive / {a.folder}")
    tasks = start_exports(region, fields, cells, years, a.batch, a.folder)
    print(f"\nпоставлено задач: {len(tasks)}")
    print("следить можно и тут: https://code.earthengine.google.com/tasks")

    if a.watch:
        ok = watch(tasks, a.poll)
        print("\nдальше: скачать папку из Google Drive и прогнать")
        print(f"  python run_external.py --raw <распакованная_папка>")
        sys.exit(0 if ok else 1)
    else:
        print("\nзадачи считаются на серверах Google, скрипт можно закрыть.")
        print("когда доедут — скачать папку из Drive и прогнать:")
        print("  python run_external.py --raw <распакованная_папка>")


if __name__ == "__main__":
    main()
