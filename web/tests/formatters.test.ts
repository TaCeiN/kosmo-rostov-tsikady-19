import { describe, it, expect } from 'vitest';
import {
  formatArea,
  formatDateRange,
  formatDateRu,
  formatNdvi,
  formatPrecip,
  formatTemp,
  formatZScore,
} from '../src/lib/formatters';

describe('Formatters (Russian Locale)', () => {
  it('formats NDVI with 3 decimals and comma', () => {
    expect(formatNdvi(0.2314)).toBe('0,231');
    expect(formatNdvi(-0.085)).toBe('-0,085');
    expect(formatNdvi(null)).toBe('—');
  });

  it('formats z-score with 2 decimals and handles null as dash', () => {
    expect(formatZScore(-2.5196)).toBe('-2,52');
    expect(formatZScore(1.456)).toBe('1,46');
    expect(formatZScore(null)).toBe('—');
    expect(formatZScore(undefined)).toBe('—');
  });

  it('formats area in hectares', () => {
    expect(formatArea(6.2)).toBe('6,2 га');
    expect(formatArea(1500)).toBe('1\u00A0500 га'); // non-breaking space
  });

  it('formats precipitation and temperature with units', () => {
    expect(formatPrecip(12.4)).toBe('12,4 мм');
    expect(formatPrecip(null)).toBe('— мм');

    expect(formatTemp(1.2)).toBe('+1,2 °C');
    expect(formatTemp(-0.2)).toBe('-0,2 °C');
    expect(formatTemp(null)).toBe('— °C');
  });

  it('formats single dates in Russian', () => {
    const formatted = formatDateRu('2019-04-05');
    expect(formatted).toContain('5');
    expect(formatted).toContain('апреля');
    expect(formatted).toContain('2019');
  });

  it('formats date ranges in Russian', () => {
    const range = formatDateRange('2019-04-05', '2019-06-12');
    expect(range).toContain('5 апреля');
    expect(range).toContain('12 июня');
    expect(range).toContain('2019');
  });
});
