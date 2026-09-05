import React, { useMemo, useState } from 'react';
import { AnomalyRecord } from '../../types/domain';
import {
  formatDateRange,
  formatNdvi,
  formatPrecip,
  formatTemp,
  formatZScore,
} from '../../lib/formatters';
import { getCauseMeta, getSeverityMeta } from '../../lib/constants';
import { ArrowDownUp, CheckCircle, Filter, Info } from 'lucide-react';

interface AnomalyCardsProps {
  anomalies: AnomalyRecord[];
  hasClimateNorm: boolean;
  onSelectAnomaly?: (anomaly: AnomalyRecord) => void;
  selectedAnomaly?: AnomalyRecord | null;
}

type SortOption = 'severity' | 'date_asc' | 'date_desc' | 'days';

export const AnomalyCards: React.FC<AnomalyCardsProps> = ({
  anomalies,
  hasClimateNorm,
  onSelectAnomaly,
  selectedAnomaly,
}) => {
  const [sortOption, setSortOption] = useState<SortOption>('severity');
  const [filterYear, setFilterYear] = useState<string>('all');
  const [filterSeverity, setFilterSeverity] = useState<string>('all');
  const [filterCause, setFilterCause] = useState<string>('all');

  // Уникальные значения для выпадающих фильтров
  const years = useMemo(
    () => Array.from(new Set(anomalies.map((a) => a.year))).sort((a, b) => b - a),
    [anomalies]
  );
  const severities = useMemo(
    () => Array.from(new Set(anomalies.map((a) => a.severity))),
    [anomalies]
  );
  const causes = useMemo(
    () => Array.from(new Set(anomalies.map((a) => a.cause))),
    [anomalies]
  );

  // Фильтрация и сортировка
  const filteredAnomalies = useMemo(() => {
    let list = [...anomalies];

    if (filterYear !== 'all') {
      const y = parseInt(filterYear, 10);
      list = list.filter((a) => a.year === y);
    }

    if (filterSeverity !== 'all') {
      list = list.filter((a) => a.severity === filterSeverity);
    }

    if (filterCause !== 'all') {
      list = list.filter((a) => a.cause === filterCause);
    }

    // Сортировка
    list.sort((a, b) => {
      if (sortOption === 'severity') {
        // Сначала самые глубокие просадки: z_min отрицательный, поэтому -4.5 идёт раньше -2.5
        return a.z_min - b.z_min;
      }
      if (sortOption === 'date_asc') {
        return a.start.localeCompare(b.start);
      }
      if (sortOption === 'date_desc') {
        return b.start.localeCompare(a.start);
      }
      if (sortOption === 'days') {
        return b.days - a.days;
      }
      return 0;
    });

    return list;
  }, [anomalies, filterYear, filterSeverity, filterCause, sortOption]);

  if (!hasClimateNorm) {
    return (
      <div className="bg-white rounded-xl border border-slate-200 p-8 text-center space-y-3">
        <div className="w-12 h-12 rounded-full bg-amber-100 text-amber-700 flex items-center justify-center mx-auto">
          <Info className="w-6 h-6" />
        </div>
        <h3 className="text-base font-semibold text-slate-800">Климатическая норма не построена</h3>
        <p className="text-sm text-slate-600 max-w-md mx-auto">
          Для расчёта климатической нормы (leave-one-year-out) и поиска периодов угнетения требуется история минимум за 3 сезона. В текущих данных меньше трёх сезонов, поэтому аномалии не рассчитывались.
        </p>
      </div>
    );
  }

  if (anomalies.length === 0) {
    return (
      <div className="bg-white rounded-xl border border-slate-200 p-8 text-center space-y-3">
        <div className="w-12 h-12 rounded-full bg-blue-50 text-blue-600 border border-blue-100 flex items-center justify-center mx-auto">
          <CheckCircle className="w-6 h-6" />
        </div>
        <h3 className="text-base font-semibold text-slate-800">Угнетения вегетации не обнаружено</h3>
        <p className="text-sm text-slate-600 max-w-md mx-auto">
          За выбранный период развитие культуры соответствовало климатической норме. Сильных отклонений индекса NDVI не зафиксировано.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header with counts and filters */}
      <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="font-bold text-slate-900 text-base flex items-center gap-2">
              <span>Периоды угнетения и аномалии</span>
              <span className="bg-slate-100 text-slate-700 px-2 py-0.5 rounded-full text-xs font-semibold">
                {filteredAnomalies.length} из {anomalies.length}
              </span>
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Нажмите на карточку, чтобы подсветить и приблизить период на графике
            </p>
          </div>

          {/* Sort dropdown */}
          <div className="flex items-center gap-2 text-xs">
            <ArrowDownUp className="w-3.5 h-3.5 text-slate-400" />
            <span className="text-slate-500">Сортировка:</span>
            <select
              value={sortOption}
              onChange={(e) => setSortOption(e.target.value as SortOption)}
              className="bg-slate-50 border border-slate-300 text-slate-800 rounded px-2 py-1 text-xs focus:ring-1 focus:ring-brand-500"
            >
              <option value="severity">По глубине просадки (z-score)</option>
              <option value="date_desc">Сначала новые (по дате)</option>
              <option value="date_asc">Сначала старые (по дате)</option>
              <option value="days">По длительности периода</option>
            </select>
          </div>
        </div>

        {/* Filter chips / selects */}
        <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-slate-100 text-xs">
          <div className="flex items-center gap-1 text-slate-400 mr-1">
            <Filter className="w-3.5 h-3.5" />
            <span>Фильтры:</span>
          </div>

          {/* Year filter */}
          {years.length > 1 && (
            <select
              value={filterYear}
              onChange={(e) => setFilterYear(e.target.value)}
              className="bg-slate-50 border border-slate-200 text-slate-700 rounded px-2 py-1 text-xs"
            >
              <option value="all">Все годы</option>
              {years.map((y) => (
                <option key={y} value={y.toString()}>
                  {y} год
                </option>
              ))}
            </select>
          )}

          {/* Severity filter */}
          {severities.length > 1 && (
            <select
              value={filterSeverity}
              onChange={(e) => setFilterSeverity(e.target.value)}
              className="bg-slate-50 border border-slate-200 text-slate-700 rounded px-2 py-1 text-xs"
            >
              <option value="all">Все типы тяжести</option>
              {severities.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          )}

          {/* Cause filter */}
          {causes.length > 1 && (
            <select
              value={filterCause}
              onChange={(e) => setFilterCause(e.target.value)}
              className="bg-slate-50 border border-slate-200 text-slate-700 rounded px-2 py-1 text-xs max-w-[240px] truncate"
            >
              <option value="all">Все причины</option>
              {causes.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          )}

          {(filterYear !== 'all' || filterSeverity !== 'all' || filterCause !== 'all') && (
            <button
              type="button"
              onClick={() => {
                setFilterYear('all');
                setFilterSeverity('all');
                setFilterCause('all');
              }}
              className="text-xs text-brand-600 hover:text-brand-800 underline ml-auto"
            >
              Сбросить фильтры
            </button>
          )}
        </div>
      </div>

      {/* Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {filteredAnomalies.map((anom, idx) => {
          const isSelected =
            selectedAnomaly &&
            selectedAnomaly.start === anom.start &&
            selectedAnomaly.end === anom.end;

          const sevMeta = getSeverityMeta(anom.severity);
          const causeMeta = getCauseMeta(anom.cause);
          const SevIcon = sevMeta.icon;
          const CauseIcon = causeMeta.icon;

          // Насколько NDVI ниже нормы в процентах, например -45%
          const pctLower =
            anom.clim_mean > 0
              ? Math.round(((anom.clim_mean - anom.ndvi_mean) / anom.clim_mean) * 100)
              : null;

          return (
            <div
              key={`${anom.start}-${anom.end}-${idx}`}
              onClick={() => onSelectAnomaly?.(anom)}
              className={`rounded-xl border p-4 bg-white shadow-sm cursor-pointer transition-all duration-150 hover:shadow-md ${
                isSelected
                  ? 'border-brand-600 ring-2 ring-brand-500/20 bg-brand-50/20'
                  : 'border-slate-200 hover:border-slate-300'
              }`}
            >
              {/* Card Header */}
              <div className="flex items-start justify-between gap-2 border-b border-slate-100 pb-2.5">
                <div>
                  <h4 className="font-bold text-slate-900 text-sm">
                    {formatDateRange(anom.start, anom.end)}
                  </h4>
                  <div className="text-xs text-slate-500 mt-0.5">
                    Длительность: <b>{anom.days} дн.</b> ({anom.year} год)
                  </div>
                </div>

                <div className={`flex items-center gap-1 text-xs px-2.5 py-1 rounded-full font-semibold ${sevMeta.badgeClass}`}>
                  <SevIcon className="w-3.5 h-3.5" />
                  <span>{sevMeta.label}</span>
                </div>
              </div>

              {/* Card Body: Human-friendly numbers */}
              <div className="py-2.5 space-y-2 text-xs">
                {/* NDVI vs Norm */}
                <div className="bg-slate-50 rounded-lg p-2.5 border border-slate-100">
                  <div className="text-slate-800 font-medium leading-relaxed">
                    NDVI <b>{formatNdvi(anom.ndvi_mean)}</b> при норме <b>{formatNdvi(anom.clim_mean)}</b>
                    {pctLower !== null && (
                      <span className="text-red-700 font-bold ml-1">
                        (на {pctLower}% ниже нормы)
                      </span>
                    )}
                  </div>
                  <div className="text-slate-400 text-[11px] mt-1 flex items-center gap-1.5" title="На сколько стандартных отклонений ниже климатической нормы">
                    <span>Глубина просадки:</span>
                    <span className="font-semibold text-slate-700">z = {formatZScore(anom.z_min)} σ</span>
                    <span className="text-slate-300">•</span>
                    <span>в единицах NDVI:</span>
                    <span className="font-semibold text-slate-700">{formatNdvi(anom.drop_vs_norm)}</span>
                  </div>
                </div>

                {/* Cause badge */}
                <div className={`flex items-center gap-2 p-2 rounded-lg border ${causeMeta.bgColor} ${causeMeta.borderColor}`}>
                  <CauseIcon className={`w-4 h-4 shrink-0 ${causeMeta.textColor}`} />
                  <div className="font-semibold text-slate-800">{causeMeta.label}</div>
                </div>

                {/* Weather details if available */}
                {(anom.precip_30d !== null || anom.temp_anom !== null) && (
                  <div className="text-[11px] text-slate-600 bg-slate-50/60 p-2 rounded border border-slate-100 space-y-1">
                    {anom.precip_30d !== null && (
                      <div>
                        Осадки: <b>{formatPrecip(anom.precip_30d)}</b>
                        {anom.precip_30d_norm !== null && ` при норме ${formatPrecip(anom.precip_30d_norm)}`}
                        {anom.precip_ratio !== null && (
                          <span className="text-slate-500 ml-1 font-medium">
                            ({Math.round(anom.precip_ratio * 100)}% от нормы)
                          </span>
                        )}
                      </div>
                    )}
                    {anom.temp_anom !== null && (
                      <div>
                        Температура за 30д: <b>{anom.temp_anom >= 0 ? `выше нормы на ${formatTemp(anom.temp_anom)}` : `ниже нормы на ${formatTemp(Math.abs(anom.temp_anom))}`}</b>
                      </div>
                    )}
                  </div>
                )}

                {/* Comment */}
                <p className="text-slate-600 italic text-[11px] leading-snug">
                  {anom.comment}
                </p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
