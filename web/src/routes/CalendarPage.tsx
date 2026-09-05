import React, { useEffect, useMemo, useState } from 'react';
import ReactECharts from 'echarts-for-react';
import { getStaticAnomaliesFlat, getStaticMeta } from '../data/static';
import { AnomalyRecord, StaticMeta } from '../types/domain';
import { formatDateRange, formatInteger, formatNdvi, formatZScore } from '../lib/formatters';
import { getCauseMeta, getSeverityMeta } from '../lib/constants';
import { CalendarDays, Filter, RotateCcw } from 'lucide-react';

const MONTH_LABELS = [
  'Янв',
  'Фев',
  'Мар',
  'Апр',
  'Май',
  'Июн',
  'Июл',
  'Авг',
  'Сен',
  'Окт',
  'Ноя',
  'Дек',
];

/**
 * Разносит один аномальный период по месяцам, в которые он попадает.
 * Считаем именно сутки, а не сами периоды: аномалия на стыке месяцев
 * иначе целиком уехала бы в месяц своего начала.
 */
function daysByMonth(anom: AnomalyRecord): Map<string, number> {
  const buckets = new Map<string, number>();
  const start = new Date(anom.start + 'T00:00:00Z');
  const end = new Date(anom.end + 'T00:00:00Z');

  if (isNaN(start.getTime()) || isNaN(end.getTime()) || end < start) {
    return buckets;
  }

  const cursor = new Date(start);
  while (cursor <= end) {
    const key = `${cursor.getUTCFullYear()}-${cursor.getUTCMonth()}`;
    buckets.set(key, (buckets.get(key) ?? 0) + 1);
    cursor.setUTCDate(cursor.getUTCDate() + 1);
  }

  return buckets;
}

export const CalendarPage: React.FC = () => {
  const [anomalies, setAnomalies] = useState<AnomalyRecord[] | null>(null);
  const [meta, setMeta] = useState<StaticMeta | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Фильтры
  const [selectedCrop, setSelectedCrop] = useState<string>('all');
  const [selectedSeverity, setSelectedSeverity] = useState<string>('all');

  // Раскрытая ячейка: [год, номер месяца]
  const [selectedCell, setSelectedCell] = useState<[number, number] | null>(null);

  useEffect(() => {
    let cancelled = false;

    Promise.all([getStaticAnomaliesFlat(), getStaticMeta()])
      .then(([anoms, m]) => {
        if (cancelled) return;
        setAnomalies(anoms);
        setMeta(m);
        setLoading(false);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : String(err));
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const filtered = useMemo(() => {
    if (!anomalies) return [];
    return anomalies.filter((a) => {
      if (selectedCrop !== 'all' && a.crop_type !== selectedCrop) return false;
      if (selectedSeverity !== 'all' && a.severity !== selectedSeverity) return false;
      return true;
    });
  }, [anomalies, selectedCrop, selectedSeverity]);

  // Ось лет: только те годы, которых аномалии действительно коснулись
  const years = useMemo(() => {
    const set = new Set<number>();
    for (const a of filtered) {
      for (const key of daysByMonth(a).keys()) {
        set.add(Number(key.split('-')[0]));
      }
    }
    return [...set].sort((x, y) => x - y);
  }, [filtered]);

  // Ячейки теплокарты: [месяц, год, аномальных суток] плюс число периодов для подсказки
  const { cells, periodCounts, maxDays } = useMemo(() => {
    const dayMap = new Map<string, number>();
    const periodMap = new Map<string, number>();

    for (const a of filtered) {
      for (const [key, days] of daysByMonth(a)) {
        dayMap.set(key, (dayMap.get(key) ?? 0) + days);
        periodMap.set(key, (periodMap.get(key) ?? 0) + 1);
      }
    }

    const out: Array<[number, number, number]> = [];
    let max = 0;

    years.forEach((year, yIdx) => {
      for (let month = 0; month < 12; month++) {
        const days = dayMap.get(`${year}-${month}`) ?? 0;
        out.push([month, yIdx, days]);
        if (days > max) max = days;
      }
    });

    return { cells: out, periodCounts: periodMap, maxDays: max };
  }, [filtered, years]);

  // Аномалии, попадающие в выбранную ячейку
  const cellAnomalies = useMemo(() => {
    if (!selectedCell) return [];
    const [year, month] = selectedCell;
    const key = `${year}-${month}`;
    return filtered
      .filter((a) => daysByMonth(a).has(key))
      .sort((a, b) => a.z_min - b.z_min);
  }, [filtered, selectedCell]);

  const heatmapOption = useMemo(
    () => ({
      animation: false,
      tooltip: {
        position: 'top',
        formatter: (params: { data: [number, number, number] }) => {
          const [month, yIdx, days] = params.data;
          const year = years[yIdx];
          const periods = periodCounts.get(`${year}-${month}`) ?? 0;
          if (days === 0) {
            return `<b>${MONTH_LABELS[month]} ${year}</b><br/>Аномалий нет`;
          }
          return (
            `<b>${MONTH_LABELS[month]} ${year}</b><br/>` +
            `Аномальных суток: <b>${formatInteger(days)}</b><br/>` +
            `Периодов: ${formatInteger(periods)}`
          );
        },
      },
      grid: { left: 60, right: 24, top: 12, bottom: 64, containLabel: false },
      xAxis: {
        type: 'category',
        data: MONTH_LABELS,
        splitArea: { show: true },
        axisLabel: { color: '#64748b', fontSize: 11 },
        axisLine: { lineStyle: { color: '#cbd5e1' } },
      },
      yAxis: {
        type: 'category',
        data: years.map(String),
        splitArea: { show: true },
        axisLabel: { color: '#64748b', fontSize: 11 },
        axisLine: { lineStyle: { color: '#cbd5e1' } },
      },
      visualMap: {
        min: 0,
        max: Math.max(maxDays, 1),
        calculable: true,
        orient: 'horizontal',
        left: 'center',
        bottom: 8,
        itemWidth: 12,
        itemHeight: 110,
        text: ['больше суток под угнетением', 'нет'],
        textStyle: { color: '#64748b', fontSize: 11 },
        inRange: {
          color: ['#f8fafc', '#fef3c7', '#fdba74', '#f97316', '#dc2626', '#7f1d1d'],
        },
      },
      series: [
        {
          name: 'Аномальные сутки',
          type: 'heatmap',
          data: cells,
          label: { show: false },
          itemStyle: { borderColor: '#ffffff', borderWidth: 1 },
          emphasis: {
            itemStyle: { borderColor: '#0f172a', borderWidth: 2 },
          },
        },
      ],
    }),
    [cells, years, maxDays, periodCounts]
  );

  const handleCellClick = (params: { data?: [number, number, number] }) => {
    if (!params.data) return;
    const [month, yIdx, days] = params.data;
    const year = years[yIdx];
    if (days === 0 || year === undefined) {
      setSelectedCell(null);
      return;
    }
    setSelectedCell([year, month]);
  };

  // Худший сезон по числу аномальных суток — выносим его в сводку над графиком
  const worstYear = useMemo(() => {
    const totals = new Map<number, number>();
    for (const a of filtered) {
      for (const [key, days] of daysByMonth(a)) {
        const y = Number(key.split('-')[0]);
        totals.set(y, (totals.get(y) ?? 0) + days);
      }
    }
    let best: { year: number; days: number } | null = null;
    for (const [year, days] of totals) {
      if (!best || days > best.days) best = { year, days };
    }
    return best;
  }, [filtered]);

  const totalDays = useMemo(
    () => cells.reduce((sum, [, , days]) => sum + days, 0),
    [cells]
  );

  if (loading) {
    return (
      <div className="w-full h-full overflow-y-auto p-12 text-center bg-slate-100">
        <div className="w-8 h-8 border-4 border-brand-500 border-t-transparent rounded-full animate-spin mx-auto mb-2" />
        <span className="text-xs text-slate-500">Загрузка календаря аномалий...</span>
      </div>
    );
  }

  if (error || !anomalies || !meta) {
    return (
      <div className="w-full h-full overflow-y-auto p-6 bg-slate-100">
        <div className="bg-red-50 text-red-700 p-6 rounded-xl border border-red-200">
          <h3 className="font-bold">Ошибка загрузки аномалий</h3>
          <p className="text-sm">{error || 'Файл anomalies.json не найден'}</p>
        </div>
      </div>
    );
  }

  const hasFilters = selectedCrop !== 'all' || selectedSeverity !== 'all';

  return (
    <div className="w-full h-full overflow-y-auto p-6 bg-slate-100 space-y-6">
      {/* Intro */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-xl bg-orange-100 text-orange-600 flex items-center justify-center shrink-0">
            <CalendarDays className="w-5 h-5" />
          </div>
          <div className="min-w-0">
            <h1 className="text-lg font-bold text-slate-900">
              Календарь аномалий по региону
            </h1>
            <p className="text-xs text-slate-500 mt-1 max-w-3xl">
              Все {formatInteger(meta.totals.polygons)} эталонных полей сразу. Цвет ячейки —
              сколько суток в этом месяце поля провели под угнетением вегетации. Периоды на
              стыке месяцев разнесены по суткам, а не записаны в месяц начала. Клик по
              ячейке раскрывает, что за ней стоит.
            </p>
          </div>
        </div>

        {/* Totals */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-5">
          <div className="bg-slate-50 rounded-xl border border-slate-200 p-3">
            <div className="text-[10px] uppercase tracking-wider text-slate-400 font-bold">
              Периодов
            </div>
            <div className="text-xl font-extrabold text-slate-900 mt-0.5">
              {formatInteger(filtered.length)}
            </div>
          </div>
          <div className="bg-slate-50 rounded-xl border border-slate-200 p-3">
            <div className="text-[10px] uppercase tracking-wider text-slate-400 font-bold">
              Аномальных суток
            </div>
            <div className="text-xl font-extrabold text-slate-900 mt-0.5">
              {formatInteger(totalDays)}
            </div>
          </div>
          <div className="bg-slate-50 rounded-xl border border-slate-200 p-3">
            <div className="text-[10px] uppercase tracking-wider text-slate-400 font-bold">
              Сезонов в охвате
            </div>
            <div className="text-xl font-extrabold text-slate-900 mt-0.5">
              {years.length}
            </div>
          </div>
          <div className="bg-slate-50 rounded-xl border border-slate-200 p-3">
            <div className="text-[10px] uppercase tracking-wider text-slate-400 font-bold">
              Тяжелейший год
            </div>
            <div className="text-xl font-extrabold text-orange-600 mt-0.5">
              {worstYear ? worstYear.year : '—'}
            </div>
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-4">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-500">
            <Filter className="w-3.5 h-3.5" />
            <span>Разрез:</span>
          </div>

          <select
            value={selectedCrop}
            onChange={(e) => {
              setSelectedCrop(e.target.value);
              setSelectedCell(null);
            }}
            className="text-xs border border-slate-200 rounded-lg px-2.5 py-1.5 bg-white text-slate-700 focus:ring-2 focus:ring-brand-500 focus:outline-none"
          >
            <option value="all">Все культуры</option>
            {meta.crop_types.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>

          <select
            value={selectedSeverity}
            onChange={(e) => {
              setSelectedSeverity(e.target.value);
              setSelectedCell(null);
            }}
            className="text-xs border border-slate-200 rounded-lg px-2.5 py-1.5 bg-white text-slate-700 focus:ring-2 focus:ring-brand-500 focus:outline-none"
          >
            <option value="all">Любая тяжесть</option>
            {meta.severity_values.map((sv) => (
              <option key={sv} value={sv}>
                {sv}
              </option>
            ))}
          </select>

          {hasFilters && (
            <button
              type="button"
              onClick={() => {
                setSelectedCrop('all');
                setSelectedSeverity('all');
                setSelectedCell(null);
              }}
              className="flex items-center gap-1.5 text-xs font-medium text-slate-500 hover:text-slate-800 px-2.5 py-1.5 rounded-lg hover:bg-slate-100 transition-colors"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              Сбросить
            </button>
          )}
        </div>
      </div>

      {/* Heatmap */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-4">
        {filtered.length === 0 ? (
          <div className="py-16 text-center text-sm text-slate-400">
            Под выбранный разрез аномалий нет.
          </div>
        ) : (
          <div className="w-full" style={{ height: Math.max(260, years.length * 30 + 110) }}>
            <ReactECharts
              option={heatmapOption}
              style={{ height: '100%', width: '100%' }}
              onEvents={{ click: handleCellClick }}
              opts={{ renderer: 'canvas' }}
              notMerge
            />
          </div>
        )}
      </div>

      {/* Cell drill-down */}
      {selectedCell && (
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-4 space-y-3">
          <div className="flex items-center justify-between gap-3 border-b border-slate-100 pb-3">
            <h2 className="text-sm font-bold text-slate-900">
              {MONTH_LABELS[selectedCell[1]]} {selectedCell[0]}: {formatInteger(cellAnomalies.length)}{' '}
              {cellAnomalies.length === 1 ? 'период' : 'периодов'}
            </h2>
            <button
              type="button"
              onClick={() => setSelectedCell(null)}
              className="text-xs font-medium text-slate-500 hover:text-slate-800 px-2 py-1 rounded hover:bg-slate-100"
            >
              Закрыть
            </button>
          </div>

          <div className="space-y-2 max-h-96 overflow-y-auto">
            {cellAnomalies.map((a, i) => {
              const sev = getSeverityMeta(a.severity);
              const cause = getCauseMeta(a.cause);
              const CauseIcon = cause.icon;
              return (
                <div
                  key={`${a.anon_polygon_id}-${a.start}-${i}`}
                  className={`rounded-xl border p-3 ${cause.borderColor} ${cause.bgColor}`}
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-xs font-bold text-slate-800">
                      {a.anon_polygon_id}
                    </span>
                    <span className="text-[11px] text-slate-500">{a.crop_type}</span>
                    <span className={`text-[10px] px-2 py-0.5 rounded-full font-semibold ${sev.badgeClass}`}>
                      {a.severity}
                    </span>
                  </div>
                  <div className="text-[11px] text-slate-600 mt-1.5">
                    {formatDateRange(a.start, a.end)} • {a.days} дн. • NDVI{' '}
                    {formatNdvi(a.ndvi_mean)} против нормы {formatNdvi(a.clim_mean)} (z ={' '}
                    {formatZScore(a.z_min)})
                  </div>
                  <div className={`flex items-center gap-1.5 text-[11px] mt-1.5 font-medium ${cause.textColor}`}>
                    <CauseIcon className="w-3.5 h-3.5 shrink-0" />
                    <span>{cause.label}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};
