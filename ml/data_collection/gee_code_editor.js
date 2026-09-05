/**
 * Сбор дополнительных полигонов в схеме организаторов.
 * Вставить целиком в https://code.earthengine.google.com, нажать Run,
 * затем на вкладке Tasks запустить все задачи.
 *
 * Повторяет рецепт организаторов (см. RECIPE.md):
 *   primary_ndvi = S2 -> Landsat -> MODIS, сезон 1 апреля - 30 октября,
 *   NDWI по формуле Макфитерса, ERA5: среднесуточная температура и сумма осадков.
 *
 * ПОРЯДОК РАБОТЫ:
 *   1) N_FIELDS = 5, YEARS = [2024] -> проверить, что считается и выгружается;
 *   2) N_FIELDS = 200 -> посмотреть в Overview, сколько съело EECU-часов;
 *   3) остальное партиями, меняя BATCH (см. ниже).
 */

// ============================ НАСТРОЙКИ ============================
var N_FIELDS = 5;            // сколько полей собрать; для боевого сбора 800
var PREVIEW = true;          // печатать статистику и рисовать карту.
                             // ВАЖНО: при большом N_FIELDS ставить false, иначе
                             // редактор пытается посчитать отбор интерактивно
                             // и виснет на пятиминутном лимите браузера.
var BATCH = 1;               // номер партии: меняет и сид выборки, и префикс id
var YEARS = [2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025];
// Продуктивная часть Ростовской области. Первая версия рамки уходила на
// юго-восток в сухую степь у границы с Калмыкией: собранные там поля дали
// NDVI на 0.10 ниже, чем у организаторов. Восточную границу сдвинули с 42.5
// до 41.3, южную с 46.0 до 46.8.
var REGION = ee.Geometry.Rectangle([38.3, 46.8, 41.3, 49.3]);
var CELL_M = 250;            // сторона участка в метрах (6 га)
var MAX_NDVI_STD = 0.08;     // порог однородности: выше — квадрат сидит на двух полях
var HOMO_YEAR = 2023;        // год проверки однородности (нужен Sentinel-2)
var MIN_PEAK_NDVI = 0.40;    // порог продуктивности: отсекает пастбища и залежь.
                             // У организаторов этот порог проходят 33 поля из 39.
var DRIVE_FOLDER = 'ndvi_external';
// ==================================================================

var SEED = 42 + BATCH * 1000;
var PREFIX = 'EXT' + BATCH + '-';

function maskS2(img) {
  var scl = img.select('SCL');
  return img.updateMask(scl.eq(4).or(scl.eq(5)).or(scl.eq(6)).or(scl.eq(7)).or(scl.eq(11)));
}

function maskLandsat(img) {
  var qa = img.select('QA_PIXEL');
  return img.updateMask(qa.bitwiseAnd(8).eq(0).and(qa.bitwiseAnd(16).eq(0)));
}

// --- 1. Кандидаты: случайные точки по маске пашни
// Регулярную сетку на весь регион строить нельзя: reproject на 250 м по области
// даёт массив в десятки тысяч пикселей по стороне, и GEE его не считает.
var cropland = ee.ImageCollection('ESA/WorldCover/v200').first()
                 .select('Map').eq(40).rename('crop').toByte();

var points = cropland.selfMask().stratifiedSample({
  numPoints: N_FIELDS * 20,     // три фильтра подряд, кандидатов нужно много
  classBand: 'crop',
  region: REGION,
  scale: 100,
  seed: SEED,
  geometries: true,
  tileScale: 4
});

var boxes = points.map(function (f) {
  return ee.Feature(f.geometry().buffer(CELL_M / 2).bounds())
           .set('anon_polygon_id', ee.String(PREFIX).cat(ee.String(f.get('system:index'))));
});

// --- 2. Фильтр 1: доля пашни внутри квадрата
var scored = cropland.reduceRegions({
  collection: boxes, reducer: ee.Reducer.mean(), scale: 10, tileScale: 4
});
var pureBoxes = scored.filter(ee.Filter.gte('mean', 0.95));

// --- 3. Фильтр 2: однородность.
// Маска пашни не отличает одно поле от двух соседних. Квадрат на границе даёт
// средний NDVI как смесь двух культур — кривую, которой в природе не существует.
// Летний разброс NDVI внутри квадрата это ловит: у одного поля он мал, у двух велик.
var summerNdvi = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
  .filterBounds(REGION)
  .filterDate(HOMO_YEAR + '-06-01', HOMO_YEAR + '-08-01')
  .map(maskS2)
  .map(function (im) { return im.normalizedDifference(['B8', 'B4']).rename('ndvi'); })
  .median();

var homo = summerNdvi.reduceRegions({
  collection: pureBoxes, reducer: ee.Reducer.stdDev(), scale: 10, tileScale: 4
});

// --- 4. Привязка к ячейке ERA5 (0.1 градуса).
// Погода одинакова для всех полей внутри ячейки, поэтому выгружать её на каждое
// поле — значит раздуть выгрузку в десятки раз без единого нового бита информации.
var homogeneous = homo.filter(ee.Filter.lte('stdDev', MAX_NDVI_STD));

// --- 3b. Фильтр 3: продуктивность.
// Маска пашни включает пастбища и залежь, у которых NDVI круглый год низкий.
// У организаторов таких почти нет: медиана пикового NDVI по их полям 0.60,
// а первая наша выборка дала 0.38 — отсюда и расхождение сезонного хода.
// Порог по пиковому NDVI (медиана за май-июнь) выравнивает выборку.
var peakNdvi = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
  .filterBounds(REGION)
  .filterDate(HOMO_YEAR + '-05-01', HOMO_YEAR + '-06-30')
  .map(maskS2)
  .map(function (im) { return im.normalizedDifference(['B8', 'B4']).rename('ndvi'); })
  .median();

var productive = peakNdvi.reduceRegions({
  collection: homogeneous, reducer: ee.Reducer.mean(), scale: 10, tileScale: 4
});

var fields = productive.filter(ee.Filter.gte('mean', MIN_PEAK_NDVI)).limit(N_FIELDS)
var cells = fields.distinct(['cell_id']).map(function (f) {
  return ee.Feature(ee.Geometry.Point([f.getNumber('cell_lon'), f.getNumber('cell_lat')]))
           .set('cell_id', f.get('cell_id'));
});

if (PREVIEW) {
  print('Участков отобрано:', fields.size());
  print('Ячеек погоды:', cells.size());
  print('Кандидатов было:', points.size(), '| чистая пашня:', pureBoxes.size(),
        '| однородные:', homogeneous.size());
  print('Пиковый NDVI отобранных:', fields.aggregate_array('mean'));
  Map.centerObject(fields.first(), 14);
  Map.addLayer(fields, {color: 'red'}, 'участки');
}

// --- 5. Индексы: одна формула для всех сенсоров
function indices(img, nir, red, blue, green, prefix, scale, offset) {
  var b = img.select([nir, red, blue, green], ['NIR', 'RED', 'BLUE', 'GREEN'])
             .multiply(scale).add(offset);
  var ndvi = b.normalizedDifference(['NIR', 'RED']).rename(prefix + '_ndvi');
  var evi = b.expression(
    '2.5 * (NIR - RED) / (NIR + 6 * RED - 7.5 * BLUE + 1)',
    {NIR: b.select('NIR'), RED: b.select('RED'), BLUE: b.select('BLUE')}
  ).rename(prefix + '_evi');
  var ndwi = b.normalizedDifference(['GREEN', 'NIR']).rename(prefix + '_ndwi');
  return ee.Image.cat([ndvi, evi, ndwi]).copyProperties(img, ['system:time_start']);
}

function season(year) { return ee.Filter.date(year + '-04-01', year + '-10-31'); }

function s2Coll(year) {
  return ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
    .filterBounds(REGION).filter(season(year))
    .map(function (im) { return indices(maskS2(im), 'B8', 'B4', 'B2', 'B3', 's2', 0.0001, 0); });
}

function landsatPart(id, bands) {
  return ee.ImageCollection(id).filterBounds(REGION).map(function (im) {
    return indices(maskLandsat(im), bands[0], bands[1], bands[2], bands[3],
                   'landsat', 0.0000275, -0.2);
  });
}

function landsatColl(year) {
  // все миссии сразу: провал 2012 у организаторов — ровно промежуток между L5 и L8
  var old = ['SR_B4', 'SR_B3', 'SR_B1', 'SR_B2'];
  var neu = ['SR_B5', 'SR_B4', 'SR_B2', 'SR_B3'];
  return landsatPart('LANDSAT/LT05/C02/T1_L2', old)
    .merge(landsatPart('LANDSAT/LE07/C02/T1_L2', old))
    .merge(landsatPart('LANDSAT/LC08/C02/T1_L2', neu))
    .merge(landsatPart('LANDSAT/LC09/C02/T1_L2', neu))
    .filter(season(year));
}

function modisColl(year) {
  return ee.ImageCollection('MODIS/061/MOD13Q1')
    .filterBounds(REGION).filter(season(year))
    .map(function (im) {
      return im.select(['NDVI', 'EVI'], ['modis_ndvi', 'modis_evi'])
               .multiply(0.0001).copyProperties(im, ['system:time_start']);
    });
}

function era5Coll(year) {
  var hourly = ee.ImageCollection('ECMWF/ERA5_LAND/HOURLY')
    .filterBounds(REGION).filter(season(year));
  var start = ee.Date(year + '-04-01');
  return ee.ImageCollection(ee.List.sequence(0, 212).map(function (d) {
    var d0 = start.advance(ee.Number(d), 'day');
    var day = hourly.filterDate(d0, d0.advance(1, 'day'));
    var t = day.select('temperature_2m').mean().subtract(273.15).rename('era5_temp_c');
    var p = day.select('total_precipitation_hourly').sum().multiply(1000).rename('era5_precip_mm');
    return ee.Image.cat([t, p]).set('system:time_start', d0.millis());
  }));
}

// --- 6. Среднее по участку на каждый снимок: строка = участок + дата
function reduceColl(coll, targets, idProp, scale, bands) {
  var tables = coll.map(function (img) {
    var date = ee.Date(img.get('system:time_start')).format('YYYY-MM-dd');
    var stats = img.reduceRegions({
      collection: targets, reducer: ee.Reducer.mean(), scale: scale, tileScale: 4
    });
    // Если снимок над участком целиком под облаком, reduceRegions не создаёт
    // свойств для замаскированных каналов — у фичи остаются только id и дата.
    // Такие строки бесполезны, выкидываем их до сборки таблицы.
    return stats.filter(ee.Filter.notNull([bands[0]])).map(function (f) {
      var out = {date: date};
      out[idProp] = f.get(idProp);
      bands.forEach(function (b) { out[b] = f.get(b); });
      return ee.Feature(null, out);   // null-геометрия: в CSV не будет колонки .geo
    });
  }).flatten();
  return tables;
}

// --- 7. Задачи экспорта
// Паспорт участков: id, ячейка погоды, чистота пашни, однородность.
// Нужен и для сшивки с ERA5, и для отчёта о происхождении данных.
Export.table.toDrive({
  collection: fields.select(['anon_polygon_id', 'cell_id', 'mean', 'stdDev'],
                            ['anon_polygon_id', 'cell_id', 'peak_ndvi', 'ndvi_std'], false),
  description: 'ndvi_fields_meta_b' + BATCH, folder: DRIVE_FOLDER, fileFormat: 'CSV'
});

YEARS.forEach(function (year) {
  Export.table.toDrive({
    collection: reduceColl(s2Coll(year), fields, 'anon_polygon_id', 20,
                           ['s2_ndvi', 's2_evi', 's2_ndwi']),
    description: 'ndvi_s2_' + year + '_b' + BATCH, folder: DRIVE_FOLDER, fileFormat: 'CSV'
  });
  Export.table.toDrive({
    collection: reduceColl(landsatColl(year), fields, 'anon_polygon_id', 30,
                           ['landsat_ndvi', 'landsat_evi', 'landsat_ndwi']),
    description: 'ndvi_landsat_' + year + '_b' + BATCH, folder: DRIVE_FOLDER, fileFormat: 'CSV'
  });
  Export.table.toDrive({
    collection: reduceColl(modisColl(year), fields, 'anon_polygon_id', 250,
                           ['modis_ndvi', 'modis_evi']),
    description: 'ndvi_modis_' + year + '_b' + BATCH, folder: DRIVE_FOLDER, fileFormat: 'CSV'
  });
  // ERA5 — по ячейкам, а не по полям: погода внутри 10 км одинакова
  Export.table.toDrive({
    collection: reduceColl(era5Coll(year), cells, 'cell_id', 1000,
                           ['era5_temp_c', 'era5_precip_mm']),
    description: 'ndvi_era5_' + year + '_b' + BATCH, folder: DRIVE_FOLDER, fileFormat: 'CSV'
  });
});

print('Задач поставлено: ' + (YEARS.length * 4 + 1) + '. Открой вкладку Tasks и запусти их.');
