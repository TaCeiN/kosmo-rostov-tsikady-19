/**
 * Утилиты форматирования чисел и дат для русской локали по стандартам ТЗ (§10, §11).
 */

export function formatNumber(val: number | null | undefined, fractionDigits = 2): string {
  if (val === null || val === undefined || Number.isNaN(val)) {
    return '—';
  }
  return new Intl.NumberFormat('ru-RU', {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  }).format(val);
}

export function formatNdvi(val: number | null | undefined): string {
  return formatNumber(val, 3);
}

export function formatZScore(val: number | null | undefined): string {
  if (val === null || val === undefined || Number.isNaN(val)) {
    return '—';
  }
  return formatNumber(val, 2);
}

export function formatArea(ha: number | null | undefined): string {
  if (ha === null || ha === undefined || Number.isNaN(ha)) {
    return '— га';
  }
  return `${new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 1 }).format(ha)} га`;
}

export function formatPrecip(mm: number | null | undefined): string {
  if (mm === null || mm === undefined || Number.isNaN(mm)) {
    return '— мм';
  }
  return `${new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 1 }).format(mm)} мм`;
}

export function formatTemp(c: number | null | undefined): string {
  if (c === null || c === undefined || Number.isNaN(c)) {
    return '— °C';
  }
  const sign = c > 0 ? '+' : '';
  return `${sign}${new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 1 }).format(c)} °C`;
}

export function formatPercent(val: number | null | undefined, fractionDigits = 1): string {
  if (val === null || val === undefined || Number.isNaN(val)) {
    return '—%';
  }
  return `${new Intl.NumberFormat('ru-RU', {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  }).format(val)}%`;
}

export function formatInteger(val: number | null | undefined): string {
  if (val === null || val === undefined || Number.isNaN(val)) {
    return '—';
  }
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 }).format(val);
}

/**
 * Форматирование одной даты: "2019-04-05" -> "5 апреля 2019"
 */
export function formatDateRu(dateStr: string | null | undefined): string {
  if (!dateStr) return '—';
  const parts = dateStr.split('-');
  if (parts.length !== 3) return dateStr;
  const year = parseInt(parts[0] ?? '0', 10);
  const month = parseInt(parts[1] ?? '0', 10) - 1;
  const day = parseInt(parts[2] ?? '0', 10);
  const d = new Date(Date.UTC(year, month, day));

  return new Intl.DateTimeFormat('ru-RU', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(d);
}

/**
 * Форматирование диапазона дат: "5 апреля — 12 июня 2019"
 */
export function formatDateRange(startStr: string, endStr: string): string {
  if (!startStr || !endStr) return '—';
  const startParts = startStr.split('-');
  const endParts = endStr.split('-');
  if (startParts.length !== 3 || endParts.length !== 3) {
    return `${startStr} — ${endStr}`;
  }

  const sYear = parseInt(startParts[0] ?? '0', 10);
  const sMonth = parseInt(startParts[1] ?? '0', 10) - 1;
  const sDay = parseInt(startParts[2] ?? '0', 10);

  const eYear = parseInt(endParts[0] ?? '0', 10);
  const eMonth = parseInt(endParts[1] ?? '0', 10) - 1;
  const eDay = parseInt(endParts[2] ?? '0', 10);

  const startD = new Date(Date.UTC(sYear, sMonth, sDay));
  const endD = new Date(Date.UTC(eYear, eMonth, eDay));

  if (sYear === eYear) {
    const sDayMonth = new Intl.DateTimeFormat('ru-RU', {
      day: 'numeric',
      month: 'long',
      timeZone: 'UTC',
    }).format(startD);

    const eDayMonth = new Intl.DateTimeFormat('ru-RU', {
      day: 'numeric',
      month: 'long',
      timeZone: 'UTC',
    }).format(endD);

    if (sMonth === eMonth) {
      return `${sDay}–${eDayMonth} ${eYear}`;
    }
    return `${sDayMonth} — ${eDayMonth} ${eYear}`;
  }

  return `${formatDateRu(startStr)} — ${formatDateRu(endStr)}`;
}
