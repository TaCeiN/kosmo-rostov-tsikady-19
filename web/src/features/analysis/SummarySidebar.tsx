import React from 'react';
import { AnalysisSummary, FetchStats } from '../../types/domain';
import {
  formatArea,
  formatInteger,
  formatPercent,
  formatZScore,
} from '../../lib/formatters';
import { AlertCircle, Calendar, Layers, MapPin, Satellite } from 'lucide-react';

interface SummarySidebarProps {
  id: string;
  cropType: string;
  years: number[];
  areaHa?: number | null;
  summary?: AnalysisSummary | null;
  fetchStats?: FetchStats | null;
  totalDays: number;
}

export const SummarySidebar: React.FC<SummarySidebarProps> = ({
  id,
  cropType,
  years,
  areaHa,
  summary,
  fetchStats,
  totalDays,
}) => {
  const yearsText =
    years.length > 0
      ? `${years[0]}–${years[years.length - 1]} (${years.length} ${
          years.length === 1 ? 'сезон' : years.length < 5 ? 'сезона' : 'сезонов'
        })`
      : '—';

  const rowsCount = summary?.rows ?? totalDays;
  const observedCount = summary?.observed ?? fetchStats?.observed ?? 0;
  const reconstructedCount = summary?.reconstructed ?? Math.max(0, rowsCount - observedCount);
  const coveragePct =
    fetchStats?.['coverage_%'] ?? (rowsCount > 0 ? (observedCount / rowsCount) * 100 : 0);

  const sensors = fetchStats?.by_sensor;
  const totalSensorObs = sensors ? sensors.S2 + sensors.Landsat + sensors.MODIS : 0;

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm space-y-4 text-xs">
      {/* Header Info */}
      <div className="border-b border-slate-100 pb-3 space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-slate-400 font-semibold uppercase tracking-wider text-[10px]">
            Объект анализа
          </span>
          <span className="bg-slate-100 text-slate-700 px-2 py-0.5 rounded font-mono font-bold text-xs">
            {id}
          </span>
        </div>

        <div className="space-y-1.5 pt-1">
          {areaHa !== undefined && areaHa !== null && (
            <div className="flex items-center justify-between">
              <span className="text-slate-500 flex items-center gap-1.5">
                <MapPin className="w-3.5 h-3.5 text-slate-400" />
                Площадь поля:
              </span>
              <span className="font-bold text-slate-800">{formatArea(areaHa)}</span>
            </div>
          )}

          <div className="flex items-center justify-between">
            <span className="text-slate-500 flex items-center gap-1.5">
              <Layers className="w-3.5 h-3.5 text-slate-400" />
              Культура:
            </span>
            <span className="font-semibold text-slate-800 capitalize">{cropType}</span>
          </div>

          <div className="flex items-center justify-between">
            <span className="text-slate-500 flex items-center gap-1.5">
              <Calendar className="w-3.5 h-3.5 text-slate-400" />
              Период:
            </span>
            <span className="font-semibold text-slate-800">{yearsText}</span>
          </div>
        </div>
      </div>

      {/* Row Stats */}
      <div className="border-b border-slate-100 pb-3 space-y-2">
        <div className="text-slate-400 font-semibold uppercase tracking-wider text-[10px]">
          Покрытие данными
        </div>

        <div className="bg-slate-50 rounded-lg p-2.5 border border-slate-100 space-y-1.5">
          <div className="flex justify-between items-center text-slate-700 font-medium">
            <span>Всего суток сезона:</span>
            <span className="font-bold text-slate-900">{formatInteger(rowsCount)}</span>
          </div>
          <div className="flex justify-between items-center text-slate-700 font-medium">
            <span>Наблюдений со спутников:</span>
            <span className="font-bold text-slate-900">
              {formatInteger(observedCount)} ({formatPercent(coveragePct)})
            </span>
          </div>
          <div className="flex justify-between items-center text-slate-700 font-medium">
            <span>Восстановлено моделью:</span>
            <span className="font-bold text-blue-600">{formatInteger(reconstructedCount)}</span>
          </div>

          {/* Progress bar of observed vs reconstructed */}
          <div className="w-full bg-slate-200 h-2 rounded-full overflow-hidden flex mt-2">
            <div
              className="bg-slate-800 h-full transition-all"
              style={{ width: `${Math.min(100, Math.max(0, coveragePct))}%` }}
              title={`Наблюдения: ${formatPercent(coveragePct)}`}
            />
            <div
              className="bg-brand-500 h-full transition-all"
              style={{ width: `${Math.min(100, Math.max(0, 100 - coveragePct))}%` }}
              title={`Восстановлено: ${formatPercent(100 - coveragePct)}`}
            />
          </div>
          <div className="flex justify-between text-[10px] text-slate-400 pt-0.5">
            <span>■ Спутники ({formatPercent(coveragePct)})</span>
            <span>■ Восстановление ({formatPercent(100 - coveragePct)})</span>
          </div>
        </div>
      </div>

      {/* Sensor Breakdown if available */}
      {sensors && totalSensorObs > 0 && (
        <div className="border-b border-slate-100 pb-3 space-y-2">
          <div className="flex items-center gap-1.5 text-slate-400 font-semibold uppercase tracking-wider text-[10px]">
            <Satellite className="w-3.5 h-3.5" />
            <span>Разбивка по сенсорам</span>
          </div>

          <div className="space-y-1.5">
            <div>
              <div className="flex justify-between text-[11px] text-slate-600 mb-0.5">
                <span>Sentinel-2 (10–20 м):</span>
                <span className="font-semibold text-slate-800">
                  {sensors.S2} ({Math.round((sensors.S2 / totalSensorObs) * 100)}%)
                </span>
              </div>
              <div className="w-full bg-slate-100 h-1.5 rounded-full overflow-hidden">
                <div
                  className="bg-blue-600 h-full"
                  style={{ width: `${(sensors.S2 / totalSensorObs) * 100}%` }}
                />
              </div>
            </div>

            <div>
              <div className="flex justify-between text-[11px] text-slate-600 mb-0.5">
                <span>Landsat (30 м):</span>
                <span className="font-semibold text-slate-800">
                  {sensors.Landsat} ({Math.round((sensors.Landsat / totalSensorObs) * 100)}%)
                </span>
              </div>
              <div className="w-full bg-slate-100 h-1.5 rounded-full overflow-hidden">
                <div
                  className="bg-blue-800 h-full"
                  style={{ width: `${(sensors.Landsat / totalSensorObs) * 100}%` }}
                />
              </div>
            </div>

            <div>
              <div className="flex justify-between text-[11px] text-slate-600 mb-0.5">
                <span>MODIS (250 м):</span>
                <span className="font-semibold text-slate-800">
                  {sensors.MODIS} ({Math.round((sensors.MODIS / totalSensorObs) * 100)}%)
                </span>
              </div>
              <div className="w-full bg-slate-100 h-1.5 rounded-full overflow-hidden">
                <div
                  className="bg-slate-700 h-full"
                  style={{ width: `${(sensors.MODIS / totalSensorObs) * 100}%` }}
                />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Weather filled % */}
      {fetchStats?.['weather_filled_%'] !== undefined && (
        <div className="flex justify-between items-center text-slate-600 text-xs border-b border-slate-100 pb-2.5">
          <span>Заполненность погоды (ERA5):</span>
          <span className="font-bold text-slate-800">
            {formatPercent(fetchStats['weather_filled_%'])}
          </span>
        </div>
      )}

      {/* Anomaly summary stats */}
      <div className="space-y-1.5 border-b border-slate-100 pb-3">
        <div className="flex justify-between items-center text-slate-700">
          <span>Аномальных периодов:</span>
          <span className="font-bold text-slate-900">
            {summary?.anomaly_periods ?? 0}
          </span>
        </div>

        <div className="flex justify-between items-center text-slate-700">
          <span>Худшее отклонение (z):</span>
          <span
            className={`font-bold ${
              summary?.worst_z && summary.worst_z < -2 ? 'text-red-600' : 'text-slate-900'
            }`}
          >
            {formatZScore(summary?.worst_z)} {summary?.worst_z !== null && summary?.worst_z !== undefined ? 'σ' : ''}
          </span>
        </div>
      </div>

      {/* Model context disclaimer */}
      <div className="bg-slate-50 border border-slate-200/80 rounded-lg p-2.5 text-[11px] text-slate-500 flex items-start gap-2 leading-relaxed">
        <AlertCircle className="w-4 h-4 text-slate-400 shrink-0 mt-0.5" />
        <span>
          <b>Анализ одного поля:</b> часть признаков модели опирается на соседние поля и здесь недоступна — точность чуть ниже эталонной 0.064 RMSE.
        </span>
      </div>
    </div>
  );
};
