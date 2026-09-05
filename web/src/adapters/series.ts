import { ApiSeriesRow, StaticSeries } from '../types/domain';

export type SeriesView = {
  id: string;
  cropType: string;
  years: number[];
  n: number;
  date: string[];            // всегда массивы: график ест их напрямую
  ndviObs: (number | null)[];
  ndviFilled: (number | null)[];
  ndviSmooth: (number | null)[];
  climMean: (number | null)[];
  climStd: (number | null)[];
  z: (number | null)[];
  status: string[];
  precip30d: (number | null)[];
  temp30d: (number | null)[];
  precip30dNorm?: (number | null)[];   // только из API
  temp30dNorm?: (number | null)[];
  tempAnom?: (number | null)[];
  isControlPoint?: boolean[];        // только из демо
  hasClimateNorm: boolean;           // false, если climMean весь null
};

/**
 * Разбивает индексы дат на непрерывные сегменты.
 * Разрыв происходит везде, где между соседними датами больше 1 суток.
 * Это решает проблему зимы и разреженных рядов (например, AOI-0008).
 */
export function segments(dates: string[]): Array<[number, number]> {
  if (dates.length === 0) {
    return [];
  }

  const result: Array<[number, number]> = [];
  let startIdx = 0;

  for (let i = 1; i < dates.length; i++) {
    const prevDateStr = dates[i - 1];
    const currDateStr = dates[i];

    if (!prevDateStr || !currDateStr) {
      continue;
    }

    const prevDate = new Date(prevDateStr + 'T00:00:00Z').getTime();
    const currDate = new Date(currDateStr + 'T00:00:00Z').getTime();
    const diffDays = Math.round((currDate - prevDate) / (1000 * 60 * 60 * 24));

    if (diffDays > 1) {
      result.push([startIdx, i - 1]);
      startIdx = i;
    }
  }

  result.push([startIdx, dates.length - 1]);
  return result;
}

/**
 * Адаптер для статического ряда полигона из data/series/<id>.json
 */
export function fromStaticSeries(raw: StaticSeries): SeriesView {
  const hasClimateNorm = raw.clim_mean.some((val) => val !== null && !Number.isNaN(val));

  return {
    id: raw.id,
    cropType: raw.crop_type,
    years: raw.years,
    n: raw.date.length,
    date: raw.date,
    ndviObs: raw.ndvi_obs,
    ndviFilled: raw.ndvi_filled,
    ndviSmooth: raw.ndvi_smooth,
    climMean: raw.clim_mean,
    climStd: raw.clim_std,
    z: raw.z,
    status: raw.status.map((s) => s ?? 'нет данных'),
    precip30d: raw.precip_30d,
    temp30d: raw.temp_30d,
    isControlPoint: raw.is_control_point,
    hasClimateNorm,
  };
}

/**
 * Адаптер для массива объектов из ответа API (result.series)
 */
export function fromApiSeries(
  rows: ApiSeriesRow[],
  meta?: { id?: string; cropType?: string; years?: number[] }
): SeriesView {
  const n = rows.length;
  const firstRow = rows[0];

  const date: string[] = new Array(n);
  const ndviObs: (number | null)[] = new Array(n);
  const ndviFilled: (number | null)[] = new Array(n);
  const ndviSmooth: (number | null)[] = new Array(n);
  const climMean: (number | null)[] = new Array(n);
  const climStd: (number | null)[] = new Array(n);
  const z: (number | null)[] = new Array(n);
  const status: string[] = new Array(n);
  const precip30d: (number | null)[] = new Array(n);
  const temp30d: (number | null)[] = new Array(n);
  const precip30dNorm: (number | null)[] = new Array(n);
  const temp30dNorm: (number | null)[] = new Array(n);
  const tempAnom: (number | null)[] = new Array(n);

  let hasClimateNorm = false;
  const yearsSet = new Set<number>();

  for (let i = 0; i < n; i++) {
    const r = rows[i];
    if (!r) continue;

    date[i] = r.date;
    ndviObs[i] = r.ndvi_obs;
    ndviFilled[i] = r.ndvi_filled;
    ndviSmooth[i] = r.ndvi_smooth;
    climMean[i] = r.clim_mean;
    climStd[i] = r.clim_std;
    z[i] = r.z;
    status[i] = r.status_pred || 'нет данных';
    precip30d[i] = r.precip_30d;
    temp30d[i] = r.temp_30d;
    precip30dNorm[i] = r.precip_30d_norm ?? null;
    temp30dNorm[i] = r.temp_30d_norm ?? null;
    tempAnom[i] = r.temp_anom ?? null;

    if (r.clim_mean !== null && !Number.isNaN(r.clim_mean)) {
      hasClimateNorm = true;
    }

    if (r.year) {
      yearsSet.add(r.year);
    }
  }

  const id = meta?.id ?? firstRow?.anon_polygon_id ?? 'USER-AREA';
  const cropType = meta?.cropType ?? firstRow?.crop_type ?? 'неизвестно';
  const years = meta?.years ?? Array.from(yearsSet).sort((a, b) => a - b);

  return {
    id,
    cropType,
    years,
    n,
    date,
    ndviObs,
    ndviFilled,
    ndviSmooth,
    climMean,
    climStd,
    z,
    status,
    precip30d,
    temp30d,
    precip30dNorm,
    temp30dNorm,
    tempAnom,
    hasClimateNorm,
  };
}
