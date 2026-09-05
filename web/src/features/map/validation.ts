import { RegionBox } from '../../types/domain';
import { formatArea } from '../../lib/formatters';

export interface ValidationResult {
  valid: boolean;
  areaHa: number;
  error?: string;
  warning?: string;
  isOutsideRegion: boolean;
}

type Ring = [number, number][];

function getRings(geometry: GeoJSON.Geometry | GeoJSON.Feature): Ring[] {
  const geom = (geometry as GeoJSON.Feature).type === 'Feature'
    ? (geometry as GeoJSON.Feature).geometry
    : geometry as GeoJSON.Geometry;

  if (!geom) return [];

  if (geom.type === 'Polygon') {
    return [(geom as GeoJSON.Polygon).coordinates[0] as Ring];
  }

  if (geom.type === 'MultiPolygon') {
    return (geom as GeoJSON.MultiPolygon).coordinates.map((p) => p[0] as Ring);
  }

  return [];
}

/**
 * Расчёт площади в гектарах по точной формуле бэкенда (gee_fetch.py).
 */
export function calculateAreaHa(geometry: GeoJSON.Geometry | GeoJSON.Feature): number {
  const rings = getRings(geometry);
  if (rings.length === 0) return 0;

  let totalHa = 0;

  for (const ring of rings) {
    if (!ring || ring.length < 3) continue;

    let sumLat = 0;
    for (const p of ring) {
      sumLat += p[1];
    }
    const lat0 = (sumLat / ring.length) * (Math.PI / 180);
    const kx = 111320 * Math.cos(lat0);
    const ky = 110540;

    let s = 0.0;
    for (let i = 0; i < ring.length; i++) {
      const p1 = ring[i];
      const p2 = ring[(i + 1) % ring.length];
      if (!p1 || !p2) continue;

      s += (p1[0] * kx) * (p2[1] * ky) - (p2[0] * kx) * (p1[1] * ky);
    }
    totalHa += Math.abs(s) / 2 / 10000;
  }

  return Math.round(totalHa * 10) / 10;
}

/**
 * Валидация геометрии поля перед отправкой на анализ (§4, §8.1).
 */
export function validateGeometry(
  geometry: GeoJSON.Geometry | GeoJSON.Feature | null,
  regionBox: RegionBox,
  maxAreaHa = 5000
): ValidationResult {
  if (!geometry) {
    return {
      valid: false,
      areaHa: 0,
      error: 'Обведите поле на карте или загрузите GeoJSON',
      isOutsideRegion: false,
    };
  }

  const rings = getRings(geometry);
  if (rings.length === 0) {
    return {
      valid: false,
      areaHa: 0,
      error: 'Нужен GeoJSON Polygon или MultiPolygon',
      isOutsideRegion: false,
    };
  }

  let minLon = Infinity;
  let maxLon = -Infinity;
  let minLat = Infinity;
  let maxLat = -Infinity;

  for (const ring of rings) {
    for (const p of ring) {
      if (p[0] < minLon) minLon = p[0];
      if (p[0] > maxLon) maxLon = p[0];
      if (p[1] < minLat) minLat = p[1];
      if (p[1] > maxLat) maxLat = p[1];
    }
  }

  const isOutside =
    minLon < regionBox.min_lon ||
    maxLon > regionBox.max_lon ||
    minLat < regionBox.min_lat ||
    maxLat > regionBox.max_lat;

  const areaHa = calculateAreaHa(geometry);

  if (areaHa > maxAreaHa) {
    return {
      valid: false,
      areaHa,
      error: `Область ${formatArea(areaHa)} больше предела ${formatArea(maxAreaHa)}: обведите поле, а не район`,
      isOutsideRegion: isOutside,
    };
  }

  // Регион обучения ограничивает не выбор, а достоверность: модель на нём
  // училась, за его пределами культуры и климатнорма другие. Считать всё
  // равно даём — иначе решение намертво привязано к одной области.
  const warnings: string[] = [];

  if (isOutside) {
    warnings.push(
      `Область выходит за регион обучения (${regionBox.min_lon}°–${regionBox.max_lon}° E, ` +
        `${regionBox.min_lat}°–${regionBox.max_lat}° N). Восстановление ряда работает везде, ` +
        'но климатнорма и причины аномалий откалиброваны на Ростовской области: ' +
        'к выводам за её пределами относитесь осторожнее.'
    );
  }

  if (areaHa < 0.5) {
    warnings.push(
      'Площадь меньше 0.5 га: пиксель Sentinel-2 составляет 10 м, на маленькой области усреднять нечего'
    );
  }

  return {
    valid: true,
    areaHa,
    warning: warnings.length > 0 ? warnings.join(' ') : undefined,
    isOutsideRegion: isOutside,
  };
}
