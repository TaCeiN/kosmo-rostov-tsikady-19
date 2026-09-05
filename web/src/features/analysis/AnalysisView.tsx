import React, { useState } from 'react';
import { SeriesView } from '../../adapters/series';
import { AnalysisSummary, AnomalyRecord, FetchStats } from '../../types/domain';
import { NdviChart } from './NdviChart';
import { AnomalyCards } from './AnomalyCards';
import { SummarySidebar } from './SummarySidebar';
import { ExportButtons } from '../export/ExportButtons';
import { Table, BarChart2 } from 'lucide-react';
import { formatDateRu, formatNdvi, formatPrecip, formatTemp, formatZScore } from '../../lib/formatters';

interface AnalysisViewProps {
  series: SeriesView;
  anomalies: AnomalyRecord[];
  summary?: AnalysisSummary | null;
  fetchStats?: FetchStats | null;
  areaHa?: number | null;
  comparisonSeries?: SeriesView | null;
  rawResult?: unknown;
}

export const AnalysisView: React.FC<AnalysisViewProps> = ({
  series,
  anomalies,
  summary,
  fetchStats,
  areaHa,
  comparisonSeries,
  rawResult,
}) => {
  const [selectedAnomaly, setSelectedAnomaly] = useState<AnomalyRecord | null>(null);
  const [showDataTable, setShowDataTable] = useState(false);
  const [tableSeason, setTableSeason] = useState<number>(series.years[series.years.length - 1] ?? 2025);

  const handleSelectAnomaly = (anomaly: AnomalyRecord) => {
    setSelectedAnomaly(anomaly);
    // Прокрутка к графику: выбранная аномалия подсвечивается именно на нём
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  // Строки таблицы за выбранный сезон
  const seasonRows = series.date
    .map((d, i) => ({
      date: d,
      obs: series.ndviObs[i],
      filled: series.ndviFilled[i],
      smooth: series.ndviSmooth[i],
      norm: series.climMean[i],
      std: series.climStd[i],
      z: series.z[i],
      status: series.status[i],
      precip: series.precip30d[i],
      temp: series.temp30d[i],
    }))
    .filter((r) => r.date.startsWith(tableSeason.toString()));

  return (
    <div className="space-y-6">
      {/* Top action bar with Export and Mode toggle */}
      <div className="flex flex-wrap items-center justify-between gap-4 bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
        <div>
          <h2 className="text-lg font-bold text-slate-900 flex items-center gap-2">
            <span>Анализ вегетации и климатических стрессов</span>
            <span className="bg-brand-100 text-brand-800 text-xs px-2.5 py-0.5 rounded-full font-semibold">
              {series.id}
            </span>
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Культура: <b className="text-slate-700 capitalize">{series.cropType}</b> • Период:{' '}
            <b className="text-slate-700">
              {series.years[0]}–{series.years[series.years.length - 1]}
            </b>
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={() => setShowDataTable(!showDataTable)}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border transition-colors ${
              showDataTable
                ? 'bg-slate-800 text-white border-slate-800'
                : 'bg-white text-slate-700 border-slate-200 hover:bg-slate-50'
            }`}
          >
            {showDataTable ? (
              <>
                <BarChart2 className="w-3.5 h-3.5" />
                <span>Показать график</span>
              </>
            ) : (
              <>
                <Table className="w-3.5 h-3.5" />
                <span>Таблица данных сезона</span>
              </>
            )}
          </button>

          <ExportButtons
            series={series}
            anomalies={anomalies}
            rawResult={rawResult}
            getChartDataUrl={() => {
              // ECharts отдаёт готовый PNG прямо из canvas
              const canvas = document.querySelector('.echarts-for-react canvas') as HTMLCanvasElement | null;
              return canvas ? canvas.toDataURL('image/png', 1.0) : null;
            }}
          />
        </div>
      </div>

      {/* Main Grid: Left = Chart & Cards, Right = Summary */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Left Column (3/4) */}
        <div className="lg:col-span-3 space-y-6">
          {!showDataTable ? (
            <>
              {/* ECharts Main Graphic */}
              <NdviChart
                series={series}
                anomalies={anomalies}
                comparisonSeries={comparisonSeries}
                onAnomalyClick={handleSelectAnomaly}
                selectedAnomaly={selectedAnomaly}
              />

              {/* Anomaly Cards List */}
              <AnomalyCards
                anomalies={anomalies}
                hasClimateNorm={series.hasClimateNorm}
                onSelectAnomaly={handleSelectAnomaly}
                selectedAnomaly={selectedAnomaly}
              />
            </>
          ) : (
            /* Таблица данных: тот же ряд, но пригодный для чтения и копирования */
            <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-4 space-y-3">
              <div className="flex items-center justify-between border-b pb-3">
                <h3 className="font-bold text-slate-900 text-sm">
                  Таблица суточных значений NDVI и факторов
                </h3>
                <div className="flex items-center gap-2 text-xs">
                  <span className="text-slate-500">Сезон:</span>
                  <select
                    value={tableSeason}
                    onChange={(e) => setTableSeason(parseInt(e.target.value, 10))}
                    className="border border-slate-300 rounded px-2 py-1 bg-slate-50 font-medium"
                  >
                    {series.years.map((y) => (
                      <option key={y} value={y}>
                        {y} год
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="overflow-x-auto max-h-[600px] border border-slate-100 rounded-lg">
                <table className="w-full text-left text-xs border-collapse">
                  <thead className="bg-slate-100 sticky top-0 text-slate-700 uppercase text-[10px] font-semibold tracking-wider">
                    <tr>
                      <th className="p-2.5">Дата</th>
                      <th className="p-2.5">Наблюдение</th>
                      <th className="p-2.5">Восстановленный</th>
                      <th className="p-2.5">Сглаженный</th>
                      <th className="p-2.5">Норма ± σ</th>
                      <th className="p-2.5">z-score</th>
                      <th className="p-2.5">Статус</th>
                      <th className="p-2.5">Осадки 30д</th>
                      <th className="p-2.5">Темп. 30д</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 text-slate-800">
                    {seasonRows.map((r) => (
                      <tr key={r.date} className="hover:bg-slate-50">
                        <td className="p-2 font-mono font-medium">{formatDateRu(r.date)}</td>
                        <td className="p-2">{r.obs !== null ? formatNdvi(r.obs) : <span className="text-slate-400 italic">Облачно</span>}</td>
                        <td className="p-2 text-blue-600 font-semibold">{formatNdvi(r.filled)}</td>
                        <td className="p-2 text-blue-800 font-bold">{formatNdvi(r.smooth)}</td>
                        <td className="p-2">
                          {r.norm !== null && r.std !== null ? `${formatNdvi(r.norm)} ± ${formatNdvi(r.std)}` : '—'}
                        </td>
                        <td className="p-2 font-mono">
                          {r.z !== null && r.z !== undefined ? (
                            <span className={r.z < -2 ? 'text-red-600 font-bold' : r.z < -1 ? 'text-amber-600 font-bold' : ''}>
                              {formatZScore(r.z)}
                            </span>
                          ) : (
                            '—'
                          )}
                        </td>
                        <td className="p-2">{r.status}</td>
                        <td className="p-2">{formatPrecip(r.precip)}</td>
                        <td className="p-2">{formatTemp(r.temp)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>

        {/* Right Column (1/4): Sidebar Summary */}
        <div className="lg:col-span-1">
          <div className="sticky top-4">
            <SummarySidebar
              id={series.id}
              cropType={series.cropType}
              years={series.years}
              areaHa={areaHa}
              summary={summary}
              fetchStats={fetchStats}
              totalDays={series.n}
            />
          </div>
        </div>
      </div>
    </div>
  );
};
