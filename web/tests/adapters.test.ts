import { describe, it, expect } from 'vitest';
import fs from 'fs';
import path from 'path';
import { segments, fromStaticSeries, fromApiSeries, SeriesView } from '../src/adapters/series';
import { StaticSeries } from '../src/types/domain';

describe('Series Segments', () => {
  it('handles empty array', () => {
    expect(segments([])).toEqual([]);
  });

  it('handles single element', () => {
    expect(segments(['2020-04-01'])).toEqual([[0, 0]]);
  });

  it('handles continuous days', () => {
    expect(segments(['2020-04-01', '2020-04-02', '2020-04-03'])).toEqual([[0, 2]]);
  });

  it('breaks line across winter gap (Oct 30 to Apr 1)', () => {
    const dates = [
      '2020-10-29',
      '2020-10-30',
      '2021-04-01',
      '2021-04-02',
    ];
    const segs = segments(dates);
    expect(segs).toEqual([
      [0, 1],
      [2, 3],
    ]);
  });

  it('handles sparse series like AOI-0008 where dates jump by > 1 day', () => {
    const filePath = path.resolve(__dirname, '../../data/series/AOI-0008.json');
    const raw: StaticSeries = JSON.parse(fs.readFileSync(filePath, 'utf-8'));
    const segs = segments(raw.date);

    expect(segs.length).toBeGreaterThan(1);
    // Every segment must have valid start and end indices
    for (const [start, end] of segs) {
      expect(start).toBeLessThanOrEqual(end);
      expect(start).toBeGreaterThanOrEqual(0);
      expect(end).toBeLessThan(raw.date.length);
    }
  });

  it('handles single season series AOI-0006', () => {
    const filePath = path.resolve(__dirname, '../../data/series/AOI-0006.json');
    const raw: StaticSeries = JSON.parse(fs.readFileSync(filePath, 'utf-8'));
    const segs = segments(raw.date);

    expect(segs.length).toBeGreaterThanOrEqual(1);
    expect(raw.years).toEqual([2025]);
  });
});

describe('Adapters fromStaticSeries & fromApiSeries', () => {
  it('converts static series AOI-0001 into SeriesView', () => {
    const filePath = path.resolve(__dirname, '../../data/series/AOI-0001.json');
    const raw: StaticSeries = JSON.parse(fs.readFileSync(filePath, 'utf-8'));
    const view: SeriesView = fromStaticSeries(raw);

    expect(view.id).toBe('AOI-0001');
    expect(view.cropType).toBe('озимая пшеница');
    expect(view.n).toBe(3408);
    expect(view.date.length).toBe(view.n);
    expect(view.ndviObs.length).toBe(view.n);
    expect(view.ndviFilled.length).toBe(view.n);
    expect(view.ndviSmooth.length).toBe(view.n);
    expect(view.climMean.length).toBe(view.n);
    expect(view.climStd.length).toBe(view.n);
    expect(view.z.length).toBe(view.n);
    expect(view.status.length).toBe(view.n);
    expect(view.precip30d.length).toBe(view.n);
    expect(view.temp30d.length).toBe(view.n);
    expect(view.isControlPoint?.length).toBe(view.n);
    expect(view.hasClimateNorm).toBe(true);
  });

  it('correctly sets hasClimateNorm = false for AOI-0006 (< 3 seasons)', () => {
    const filePath = path.resolve(__dirname, '../../data/series/AOI-0006.json');
    const raw: StaticSeries = JSON.parse(fs.readFileSync(filePath, 'utf-8'));
    const view = fromStaticSeries(raw);

    expect(view.hasClimateNorm).toBe(false);
  });

  it('converts api series from analyze_response.json into SeriesView', () => {
    const filePath = path.resolve(__dirname, '../../samples/analyze_response.json');
    const apiResponse = JSON.parse(fs.readFileSync(filePath, 'utf-8'));
    const view: SeriesView = fromApiSeries(apiResponse.result.series, {
      id: 'USER-AREA',
      cropType: 'озимая пшеница',
    });

    expect(view.id).toBe('USER-AREA');
    expect(view.cropType).toBe('озимая пшеница');
    expect(view.n).toBe(2130);
    expect(view.date.length).toBe(view.n);
    expect(view.ndviObs.length).toBe(view.n);
    expect(view.ndviFilled.length).toBe(view.n);
    expect(view.ndviSmooth.length).toBe(view.n);
    expect(view.climMean.length).toBe(view.n);
    expect(view.climStd.length).toBe(view.n);
    expect(view.z.length).toBe(view.n);
    expect(view.status.length).toBe(view.n);
    expect(view.precip30d.length).toBe(view.n);
    expect(view.temp30d.length).toBe(view.n);
    expect(view.precip30dNorm?.length).toBe(view.n);
    expect(view.temp30dNorm?.length).toBe(view.n);
    expect(view.tempAnom?.length).toBe(view.n);
    expect(view.hasClimateNorm).toBe(true);
  });
});
