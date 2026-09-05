import { describe, it, expect } from 'vitest';
import fs from 'fs';
import path from 'path';
import { AnomalyRecord } from '../src/types/domain';

describe('Anomalies Grouping & Data Integrity', () => {
  it('loads and groups 782 anomalies by anon_polygon_id', () => {
    const filePath = path.resolve(__dirname, '../../data/anomalies.json');
    const all: AnomalyRecord[] = JSON.parse(fs.readFileSync(filePath, 'utf-8'));

    expect(all.length).toBe(782);

    const map: Record<string, AnomalyRecord[]> = {};
    for (const anom of all) {
      const list = map[anom.anon_polygon_id] ?? [];
      list.push(anom);
      map[anom.anon_polygon_id] = list;
    }

    // Check specific known polygon anomaly counts from meta.json
    expect(map['AOI-0001']?.length).toBe(15);
    expect(map['AOI-0002']?.length).toBe(19);
    expect(map['AOI-0004']?.length).toBe(22);
    // Polygons with 0 anomalies should be undefined in map or empty
    expect(map['AOI-0005']).toBeUndefined();
    expect(map['AOI-0006']).toBeUndefined();

    // Verify all anomalies have severity and cause
    for (const anom of all) {
      expect(anom.severity).toBeTruthy();
      expect(anom.cause).toBeTruthy();
      expect(anom.comment).toBeTruthy();
      expect(anom.z_min).toBeLessThanOrEqual(0);
      expect(anom.days).toBeGreaterThan(0);
    }
  });
});
