import { describe, it, expect } from 'vitest';
import { calculateAreaHa, validateGeometry } from '../src/features/map/validation';
import { RegionBox } from '../src/types/domain';

const regionBox: RegionBox = {
  min_lon: 38.3,
  min_lat: 46.8,
  max_lon: 41.3,
  max_lat: 49.3,
};

describe('Geometry Validation & Area', () => {
  it('calculates area accurately for a sample polygon', () => {
    // A small rectangle: lon ~ 39.8408 to 39.8441, lat ~ 48.0056 to 48.0079 (~6.2 ha)
    const polygon: GeoJSON.Polygon = {
      type: 'Polygon',
      coordinates: [
        [
          [39.8408, 48.0056],
          [39.8441, 48.0056],
          [39.8441, 48.0079],
          [39.8408, 48.0079],
          [39.8408, 48.0056],
        ],
      ],
    };

    const ha = calculateAreaHa(polygon);
    expect(ha).toBeCloseTo(6.2, 0.5);
  });

  it('validates polygon inside region box with valid area', () => {
    const polygon: GeoJSON.Polygon = {
      type: 'Polygon',
      coordinates: [
        [
          [39.8408, 48.0056],
          [39.8441, 48.0056],
          [39.8441, 48.0079],
          [39.8408, 48.0079],
          [39.8408, 48.0056],
        ],
      ],
    };

    const res = validateGeometry(polygon, regionBox, 5000);
    expect(res.valid).toBe(true);
    expect(res.isOutsideRegion).toBe(false);
    expect(res.error).toBeUndefined();
  });

  // Область вне региона обучения больше не отклоняется: расчёт разрешён,
  // но помечен как менее достоверный. Жёсткий отказ намертво привязывал
  // сервис к одной области.
  it('allows polygon outside region box but marks it as less reliable', () => {
    const outsidePolygon: GeoJSON.Polygon = {
      type: 'Polygon',
      coordinates: [
        [
          [37.0, 48.0],
          [37.01, 48.0],
          [37.01, 48.01],
          [37.0, 48.01],
          [37.0, 48.0],
        ],
      ],
    };

    const res = validateGeometry(outsidePolygon, regionBox, 5000);
    expect(res.valid).toBe(true);
    expect(res.isOutsideRegion).toBe(true);
    expect(res.warning).toContain('за регион обучения');
  });

  it('still reports the region flag when an outside polygon is also too large', () => {
    const hugeOutsidePolygon: GeoJSON.Polygon = {
      type: 'Polygon',
      coordinates: [
        [
          [37.0, 48.0],
          [37.1, 48.0],
          [37.1, 48.1],
          [37.0, 48.1],
          [37.0, 48.0],
        ],
      ],
    };

    const res = validateGeometry(hugeOutsidePolygon, regionBox, 5000);
    expect(res.valid).toBe(false);
    expect(res.isOutsideRegion).toBe(true);
    expect(res.error).toContain('больше предела');
  });

  it('rejects polygon exceeding max_area_ha', () => {
    // Large box ~100 km x 100 km (~1,000,000 ha)
    const largePolygon: GeoJSON.Polygon = {
      type: 'Polygon',
      coordinates: [
        [
          [39.0, 47.0],
          [40.0, 47.0],
          [40.0, 48.0],
          [39.0, 48.0],
          [39.0, 47.0],
        ],
      ],
    };

    const res = validateGeometry(largePolygon, regionBox, 5000);
    expect(res.valid).toBe(false);
    expect(res.error).toContain('больше предела');
  });

  it('warns when area is less than 0.5 ha', () => {
    // Tiny box ~10m x 10m (~0.01 ha)
    const tinyPolygon: GeoJSON.Polygon = {
      type: 'Polygon',
      coordinates: [
        [
          [39.8408, 48.0056],
          [39.8409, 48.0056],
          [39.8409, 48.0057],
          [39.8408, 48.0057],
          [39.8408, 48.0056],
        ],
      ],
    };

    const res = validateGeometry(tinyPolygon, regionBox, 5000);
    expect(res.valid).toBe(true);
    expect(res.warning).toContain('меньше 0.5 га');
  });
});
