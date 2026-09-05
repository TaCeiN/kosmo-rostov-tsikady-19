import { SeriesView } from '../../adapters/series';
import { AnomalyRecord, FieldDigest } from '../../types/domain';

/**
 * Сжимает разбор поля до того, что нужно модели.
 *
 * Целиком ряд отправлять нельзя: 16 сезонов суточной сетки — это больше двух
 * тысяч точек на поле, они и в контекст не влезут, и стоить будут дорого.
 * По сезонным агрегатам плюс список аномалий модель рассуждает не хуже:
 * ей важны уровень вегетации, пики, глубина просадок и погода вокруг них,
 * а не отдельные сутки.
 */

function mean(values: Array<number | null | undefined>): number | null {
  const nums = values.filter((v): v is number => typeof v === 'number' && !Number.isNaN(v));
  if (nums.length === 0) return null;
  return nums.reduce((sum, v) => sum + v, 0) / nums.length;
}

function round(value: number | null, digits = 3): number | null {
  if (value === null) return null;
  const k = 10 ** digits;
  return Math.round(value * k) / k;
}

export function buildFieldDigest(
  series: SeriesView,
  anomalies: AnomalyRecord[],
  opts: {
    name: string;
    areaHa?: number | null;
    outsideRegion?: boolean;
    observedPct?: number | null;
    reconstructed?: number | null;
  }
): FieldDigest {
  // Раскладываем индексы дат по годам одним проходом: дат тут тысячи,
  // фильтровать массив на каждый сезон заметно дороже
  const byYear = new Map<number, number[]>();
  series.date.forEach((d, i) => {
    const year = Number(d.slice(0, 4));
    if (!Number.isFinite(year)) return;
    const bucket = byYear.get(year);
    if (bucket) bucket.push(i);
    else byYear.set(year, [i]);
  });

  const seasons = [...byYear.keys()]
    .sort((a, b) => a - b)
    .map((year) => {
      const idx = byYear.get(year) ?? [];

      let peak: number | null = null;
      let peakDate: string | null = null;
      let belowNorm = 0;

      for (const i of idx) {
        const smooth = series.ndviSmooth[i];
        if (typeof smooth === 'number' && (peak === null || smooth > peak)) {
          peak = smooth;
          peakDate = series.date[i] ?? null;
        }

        // «Ниже нормы» считаем по z: он уже учитывает разброс климатнормы,
        // а голое сравнение с средним ловило бы обычный шум
        const z = series.z[i];
        if (typeof z === 'number' && z < -1) belowNorm++;
      }

      return {
        year,
        ndvi_mean: round(mean(idx.map((i) => series.ndviSmooth[i]))),
        ndvi_peak: round(peak),
        peak_date: peakDate,
        days_below_norm: belowNorm,
        precip_mean_30d: round(mean(idx.map((i) => series.precip30d[i])), 1),
        temp_mean_30d: round(mean(idx.map((i) => series.temp30d[i])), 1),
      };
    });

  return {
    name: opts.name,
    area_ha: opts.areaHa ?? null,
    crop_type: series.cropType,
    years: series.years,
    outside_region: Boolean(opts.outsideRegion),
    observed_pct: opts.observedPct ?? null,
    reconstructed: opts.reconstructed ?? null,
    seasons,
    anomalies: anomalies.map((a) => ({
      start: a.start,
      end: a.end,
      days: a.days,
      z_min: round(a.z_min, 2),
      // drop_vs_norm приходит долей: в процентах модель читает его вернее
      drop_pct: round(a.drop_vs_norm * 100, 1),
      cause: a.cause,
      status: a.severity,
    })),
  };
}
