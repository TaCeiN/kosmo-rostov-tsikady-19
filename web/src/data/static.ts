import { AnomalyRecord, StaticMeta, StaticMetrics, StaticSeries } from '../types/domain';

let cachedMeta: StaticMeta | null = null;
let cachedAnomaliesByPolygon: Record<string, AnomalyRecord[]> | null = null;
let cachedMetrics: StaticMetrics | null = null;

/**
 * Загружает общую метаинформацию data/meta.json
 */
export async function getStaticMeta(): Promise<StaticMeta> {
  if (cachedMeta) {
    return cachedMeta;
  }
  const res = await fetch('/data/meta.json');
  if (!res.ok) {
    throw new Error(`Ошибка загрузки meta.json: HTTP ${res.status}`);
  }
  cachedMeta = (await res.json()) as StaticMeta;
  return cachedMeta;
}

/**
 * Загружает ряд конкретного полигона data/series/<id>.json
 */
export async function getStaticSeries(id: string): Promise<StaticSeries> {
  const res = await fetch(`/data/series/${id}.json`);
  if (!res.ok) {
    throw new Error(`Ошибка загрузки серии ${id}: HTTP ${res.status}`);
  }
  return (await res.json()) as StaticSeries;
}

/**
 * Лениво загружает data/anomalies.json (один раз) и группирует по anon_polygon_id
 */
export async function getStaticAnomalies(): Promise<Record<string, AnomalyRecord[]>> {
  if (cachedAnomaliesByPolygon) {
    return cachedAnomaliesByPolygon;
  }
  const res = await fetch('/data/anomalies.json');
  if (!res.ok) {
    throw new Error(`Ошибка загрузки anomalies.json: HTTP ${res.status}`);
  }
  const allAnomalies = (await res.json()) as AnomalyRecord[];
  const map: Record<string, AnomalyRecord[]> = {};

  for (const anom of allAnomalies) {
    const list = map[anom.anon_polygon_id] ?? [];
    list.push(anom);
    map[anom.anon_polygon_id] = list;
  }

  cachedAnomaliesByPolygon = map;
  return cachedAnomaliesByPolygon;
}

/**
 * Плоский список всех аномалий по всем полигонам (для сводных разрезов)
 */
export async function getStaticAnomaliesFlat(): Promise<AnomalyRecord[]> {
  const map = await getStaticAnomalies();
  return Object.values(map).flat();
}

/**
 * Получить аномалии конкретного полигона
 */
export async function getStaticAnomaliesForPolygon(id: string): Promise<AnomalyRecord[]> {
  const map = await getStaticAnomalies();
  return map[id] ?? [];
}

/**
 * Загружает метрики модели data/metrics.json
 */
export async function getStaticMetrics(): Promise<StaticMetrics> {
  if (cachedMetrics) {
    return cachedMetrics;
  }
  const res = await fetch('/data/metrics.json');
  if (!res.ok) {
    throw new Error(`Ошибка загрузки metrics.json: HTTP ${res.status}`);
  }
  cachedMetrics = (await res.json()) as StaticMetrics;
  return cachedMetrics;
}
