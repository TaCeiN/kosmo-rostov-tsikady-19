import { AnalysisResult } from '../../types/domain';
import { calculateAreaHa } from './validation';

/**
 * Краткая карточка сохранённого разбора. Лежит рядом с участком в общем
 * списке, поэтому держим её маленькой: сам результат весит сотни килобайт
 * и хранится отдельным ключом.
 */
export interface SavedAnalysisMeta {
  savedAt: number;
  years: number[];
  cropType: string;
  anomalyCount: number;
  daysCount: number;
}

/** Полный разбор поля: его хватает, чтобы восстановить экран без пересчёта. */
export interface SavedAnalysisPayload {
  years: number[];
  cropType: string;
  result: AnalysisResult;
}

/**
 * Участок, сохранённый пользователем. Живёт в localStorage браузера:
 * набор полей у каждого свой, а поднимать под это хранилище на сервере
 * незачем — данные не общие и не переживают смену рабочего места.
 */
export interface SavedPolygon {
  id: string;
  name: string;
  geometry: GeoJSON.Polygon;
  areaHa: number;
  createdAt: number;
  /** Заполнено, если к участку сохранён готовый разбор. */
  analysis?: SavedAnalysisMeta;
}

const STORAGE_KEY = 'ndvi.savedPolygons.v1';

/** Разборы лежат по одному ключу на участок: список остаётся лёгким. */
const ANALYSIS_KEY_PREFIX = 'ndvi.savedAnalysis.v1.';

function analysisKey(id: string): string {
  return `${ANALYSIS_KEY_PREFIX}${id}`;
}

/** Достаёт полигональное кольцо из Geometry или Feature. */
export function toPolygon(
  geometry: GeoJSON.Geometry | GeoJSON.Feature | null
): GeoJSON.Polygon | null {
  if (!geometry) return null;

  const geom =
    (geometry as GeoJSON.Feature).type === 'Feature'
      ? (geometry as GeoJSON.Feature).geometry
      : (geometry as GeoJSON.Geometry);

  if (!geom) return null;

  if (geom.type === 'Polygon') {
    return geom as GeoJSON.Polygon;
  }

  // MultiPolygon сводим к первому контуру: анализ считается по одному участку
  if (geom.type === 'MultiPolygon') {
    const first = (geom as GeoJSON.MultiPolygon).coordinates[0];
    if (!first) return null;
    return { type: 'Polygon', coordinates: first };
  }

  return null;
}

/**
 * Читает список участков. localStorage может быть недоступен (приватное окно,
 * запрет на данные сайта) или содержать мусор от старой версии — в обоих
 * случаях возвращаем пустой список, а не роняем страницу.
 */
export function loadSavedPolygons(): SavedPolygon[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];

    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];

    const list = parsed.filter(
      (p): p is SavedPolygon =>
        p &&
        typeof p.id === 'string' &&
        typeof p.name === 'string' &&
        p.geometry &&
        p.geometry.type === 'Polygon'
    );

    // Разбор мог не пережить чистку хранилища: пометку без данных снимаем,
    // иначе закладка обещает готовый результат и открывается пустой.
    for (const entry of list) {
      if (entry.analysis && localStorage.getItem(analysisKey(entry.id)) === null) {
        delete entry.analysis;
      }
    }

    return list;
  } catch {
    return [];
  }
}

function persist(list: SavedPolygon[]): SavedPolygon[] {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(list));
  } catch {
    // Квота исчерпана или запись запрещена: список остаётся жить в памяти
    // до перезагрузки страницы, терять текущую работу из-за этого не стоит.
  }
  return list;
}

/** Добавляет участок в список. Имя по умолчанию — по порядковому номеру. */
export function addSavedPolygon(
  list: SavedPolygon[],
  geometry: GeoJSON.Geometry | GeoJSON.Feature,
  name?: string
): SavedPolygon[] {
  const polygon = toPolygon(geometry);
  if (!polygon) return list;

  const entry: SavedPolygon = {
    id: `poly-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    name: name?.trim() || `Участок ${list.length + 1}`,
    geometry: polygon,
    areaHa: calculateAreaHa(polygon),
    createdAt: Date.now(),
  };

  return persist([...list, entry]);
}

export function removeSavedPolygon(list: SavedPolygon[], id: string): SavedPolygon[] {
  dropAnalysis(id);
  return persist(list.filter((p) => p.id !== id));
}

/** Читает сохранённый разбор участка. Нет разбора или мусор — вернём null. */
export function loadAnalysis(id: string): SavedAnalysisPayload | null {
  try {
    const raw = localStorage.getItem(analysisKey(id));
    if (!raw) return null;

    const parsed = JSON.parse(raw) as SavedAnalysisPayload;
    if (!parsed?.result || !Array.isArray(parsed.result.series)) return null;

    return parsed;
  } catch {
    return null;
  }
}

/** Убирает разбор, оставляя сам участок. */
export function dropAnalysis(id: string): void {
  try {
    localStorage.removeItem(analysisKey(id));
  } catch {
    // Хранилище недоступно — освобождать нечего
  }
}

function isQuotaError(err: unknown): boolean {
  return (
    err instanceof DOMException &&
    (err.name === 'QuotaExceededError' || err.name === 'NS_ERROR_DOM_QUOTA_REACHED')
  );
}

/**
 * Пишет разбор, освобождая место под него. Один разбор за 16 сезонов — это
 * сотни килобайт, а localStorage даёт около пяти мегабайт на домен: без
 * вытеснения третья-четвёртая закладка молча не сохранилась бы.
 */
function writeAnalysis(
  list: SavedPolygon[],
  id: string,
  payload: SavedAnalysisPayload
): boolean {
  const serialized = JSON.stringify(payload);

  // Кандидаты на вытеснение: чужие разборы, начиная с самого старого
  const victims = list
    .filter((p) => p.id !== id && p.analysis)
    .sort((a, b) => (a.analysis?.savedAt ?? 0) - (b.analysis?.savedAt ?? 0));

  for (let attempt = 0; attempt <= victims.length; attempt++) {
    try {
      localStorage.setItem(analysisKey(id), serialized);
      return true;
    } catch (err) {
      if (!isQuotaError(err)) return false;

      const victim = victims[attempt];
      if (!victim) return false;

      dropAnalysis(victim.id);
      delete victim.analysis;
    }
  }

  return false;
}

/** Совпадают ли контуры: сравниваем кольца, имена и площади здесь ни при чём. */
export function sameRing(a: GeoJSON.Polygon, b: GeoJSON.Polygon): boolean {
  return JSON.stringify(a.coordinates) === JSON.stringify(b.coordinates);
}

export interface SaveAnalysisOutcome {
  list: SavedPolygon[];
  entry: SavedPolygon | null;
  /** false — контур сохранён, а разбор в хранилище не поместился. */
  stored: boolean;
}

/**
 * Кладёт разбор в закладки. Если участок с таким же контуром уже сохранён,
 * дополняет его, а не плодит дубль: пользователь обводит поле один раз,
 * а считает по нему несколько раз.
 */
export function saveAnalysisFor(
  list: SavedPolygon[],
  geometry: GeoJSON.Geometry | GeoJSON.Feature,
  payload: SavedAnalysisPayload,
  name?: string
): SaveAnalysisOutcome {
  const polygon = toPolygon(geometry);
  if (!polygon) return { list, entry: null, stored: false };

  const existing = list.find((p) => sameRing(p.geometry, polygon));

  const entry: SavedPolygon = existing ?? {
    id: `poly-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    name: name?.trim() || `Разбор ${list.length + 1}`,
    geometry: polygon,
    areaHa: calculateAreaHa(polygon),
    createdAt: Date.now(),
  };

  // Копии списка: вытеснение чужих разборов правит поле analysis у соседей
  const next = existing
    ? list.map((p) => (p.id === entry.id ? { ...entry } : { ...p }))
    : [...list.map((p) => ({ ...p })), { ...entry }];

  const target = next.find((p) => p.id === entry.id);
  if (!target) return { list, entry: null, stored: false };

  const stored = writeAnalysis(next, entry.id, payload);

  if (stored) {
    target.analysis = {
      savedAt: Date.now(),
      years: payload.years,
      cropType: payload.cropType,
      anomalyCount: payload.result.anomalies?.length ?? 0,
      daysCount: payload.result.series?.length ?? 0,
    };
  } else {
    delete target.analysis;
  }

  return { list: persist(next), entry: target, stored };
}

export function renameSavedPolygon(
  list: SavedPolygon[],
  id: string,
  name: string
): SavedPolygon[] {
  const trimmed = name.trim();
  if (!trimmed) return list;
  return persist(list.map((p) => (p.id === id ? { ...p, name: trimmed } : p)));
}

export function clearSavedPolygons(list: SavedPolygon[] = []): SavedPolygon[] {
  for (const entry of list) dropAnalysis(entry.id);
  return persist([]);
}

/** Собирает участки в FeatureCollection — формат для выгрузки наружу. */
export function toFeatureCollection(list: SavedPolygon[]): GeoJSON.FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: list.map((p) => ({
      type: 'Feature',
      geometry: p.geometry,
      properties: { name: p.name, area_ha: p.areaHa, created_at: p.createdAt },
    })),
  };
}

/**
 * Разбирает загруженный GeoJSON: принимаем и одиночную геометрию, и Feature,
 * и FeatureCollection — руками собранные файлы приходят во всех трёх видах.
 */
export function parseGeoJsonUpload(raw: unknown): SavedPolygon[] {
  const found: Array<{ geometry: GeoJSON.Polygon; name?: string }> = [];

  const pushGeometry = (geom: unknown, name?: string) => {
    const polygon = toPolygon(geom as GeoJSON.Geometry);
    if (polygon) found.push({ geometry: polygon, name });
  };

  const obj = raw as { type?: string; features?: unknown[]; properties?: Record<string, unknown> };

  if (obj?.type === 'FeatureCollection' && Array.isArray(obj.features)) {
    for (const f of obj.features) {
      const feature = f as GeoJSON.Feature;
      const props = (feature.properties ?? {}) as Record<string, unknown>;
      const name = typeof props.name === 'string' ? props.name : undefined;
      pushGeometry(feature.geometry, name);
    }
  } else if (obj?.type === 'Feature') {
    const props = (obj.properties ?? {}) as Record<string, unknown>;
    pushGeometry((obj as unknown as GeoJSON.Feature).geometry,
      typeof props.name === 'string' ? props.name : undefined);
  } else {
    pushGeometry(raw);
  }

  return found.map((item, i) => ({
    id: `poly-${Date.now()}-${i}-${Math.random().toString(36).slice(2, 7)}`,
    name: item.name || `Загружено ${i + 1}`,
    geometry: item.geometry,
    areaHa: calculateAreaHa(item.geometry),
    createdAt: Date.now(),
  }));
}

/** Дописывает разобранные участки к списку и сохраняет. */
export function appendSavedPolygons(
  list: SavedPolygon[],
  incoming: SavedPolygon[]
): SavedPolygon[] {
  return persist([...list, ...incoming]);
}
