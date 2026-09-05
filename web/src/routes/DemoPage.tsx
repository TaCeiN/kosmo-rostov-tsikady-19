import React, { useEffect, useMemo, useState } from 'react';
import {
  getStaticAnomaliesForPolygon,
  getStaticMeta,
  getStaticSeries,
} from '../data/static';
import { AnomalyRecord, StaticMeta, StaticPolygonSummary } from '../types/domain';
import { fromStaticSeries, SeriesView } from '../adapters/series';
import { AnalysisView } from '../features/analysis/AnalysisView';
import {
  formatInteger,
  formatPercent,
} from '../lib/formatters';
import {
  ArrowLeft,
  ArrowUpDown,
  CheckCircle2,
  Database,
  Filter,
  Layers,
  Search,
  Sparkles,
  Zap,
  WifiOff,
} from 'lucide-react';

type SortField = 'id' | 'crop_type' | 'years' | 'n_days' | 'coverage' | 'n_anomalies';

export const DemoPage: React.FC = () => {
  const [meta, setMeta] = useState<StaticMeta | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Полигон, выбранный для разбора
  const [selectedPolygonId, setSelectedPolygonId] = useState<string | null>(null);
  const [seriesView, setSeriesView] = useState<SeriesView | null>(null);
  const [anomalies, setAnomalies] = useState<AnomalyRecord[]>([]);
  const [loadingSeries, setLoadingSeries] = useState(false);

  // Второй полигон для сравнения на одном графике
  const [comparePolygonId, setComparePolygonId] = useState<string | null>(null);
  const [compareSeriesView, setCompareSeriesView] = useState<SeriesView | null>(null);

  // Фильтры и поиск по таблице
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCrop, setSelectedCrop] = useState<string>('all');
  const [onlyWithAnomalies, setOnlyWithAnomalies] = useState(false);
  const [sortField, setSortField] = useState<SortField>('id');
  const [sortAsc, setSortAsc] = useState(true);

  // Загружаем meta.json при монтировании
  useEffect(() => {
    let cancelled = false;
    getStaticMeta()
      .then((data) => {
        if (!cancelled) {
          setMeta(data);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err));
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  // Ряд полигона подгружаем по клику, а не все 16 МБ сразу
  const handleSelectPolygon = async (id: string) => {
    setLoadingSeries(true);
    setSelectedPolygonId(id);
    setComparePolygonId(null);
    setCompareSeriesView(null);

    try {
      const [rawSeries, anoms] = await Promise.all([
        getStaticSeries(id),
        getStaticAnomaliesForPolygon(id),
      ]);
      setSeriesView(fromStaticSeries(rawSeries));
      setAnomalies(anoms);
    } catch (err) {
      alert(`Ошибка загрузки данных полигона ${id}: ${err}`);
    } finally {
      setLoadingSeries(false);
    }
  };

  // Загрузка второго полигона
  const handleToggleCompare = async (id: string) => {
    if (comparePolygonId === id) {
      setComparePolygonId(null);
      setCompareSeriesView(null);
      return;
    }

    try {
      const rawComp = await getStaticSeries(id);
      setComparePolygonId(id);
      setCompareSeriesView(fromStaticSeries(rawComp));
    } catch (err) {
      alert(`Ошибка загрузки второго полигона ${id}: ${err}`);
    }
  };

  // Сортировка и фильтрация списка
  const filteredPolygons = useMemo(() => {
    if (!meta) return [];

    let list = [...meta.polygons];

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase().trim();
      list = list.filter(
        (p) =>
          p.id.toLowerCase().includes(q) ||
          p.crop_type.toLowerCase().includes(q)
      );
    }

    if (selectedCrop !== 'all') {
      list = list.filter((p) => p.crop_type === selectedCrop);
    }

    if (onlyWithAnomalies) {
      list = list.filter((p) => p.n_anomalies > 0);
    }

    list.sort((a, b) => {
      let valA: any = a[sortField as keyof StaticPolygonSummary];
      let valB: any = b[sortField as keyof StaticPolygonSummary];

      if (sortField === 'coverage') {
        valA = a.n_days > 0 ? a.n_observed / a.n_days : 0;
        valB = b.n_days > 0 ? b.n_observed / b.n_days : 0;
      } else if (sortField === 'years') {
        valA = a.years[0];
        valB = b.years[0];
      }

      if (valA < valB) return sortAsc ? -1 : 1;
      if (valA > valB) return sortAsc ? 1 : -1;
      return 0;
    });

    return list;
  }, [meta, searchQuery, selectedCrop, onlyWithAnomalies, sortField, sortAsc]);

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortAsc(!sortAsc);
    } else {
      setSortField(field);
      setSortAsc(true);
    }
  };

  if (loading) {
    return (
      <div className="p-8 text-center space-y-3">
        <div className="w-8 h-8 border-4 border-brand-500 border-t-transparent rounded-full animate-spin mx-auto" />
        <p className="text-sm text-slate-500">Загрузка каталога демо-полигонов...</p>
      </div>
    );
  }

  if (error || !meta) {
    return (
      <div className="bg-red-50 border border-red-200 text-red-700 p-6 rounded-xl space-y-2">
        <h3 className="font-bold">Ошибка загрузки статических данных</h3>
        <p className="text-sm">{error || 'Файлы каталога не найдены'}</p>
      </div>
    );
  }

  // Полигон выбран — показываем полный разбор
  if (selectedPolygonId && seriesView) {
    return (
      <div className="w-full h-full overflow-y-auto p-6 bg-slate-100">
        <div className="max-w-7xl mx-auto space-y-4">
          {/* Navigation back and comparison bar */}
          <div className="flex flex-wrap items-center justify-between gap-3 bg-white p-3 rounded-xl border border-slate-200 shadow-sm">
            <button
              type="button"
              onClick={() => {
                setSelectedPolygonId(null);
                setSeriesView(null);
                setComparePolygonId(null);
                setCompareSeriesView(null);
              }}
              className="flex items-center gap-1.5 text-xs font-semibold text-slate-700 bg-slate-100 hover:bg-slate-200 px-3 py-1.5 rounded-lg transition-colors"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              <span>Вернуться к каталогу полей</span>
            </button>

          {/* Comparison select */}
          <div className="flex items-center gap-2 text-xs">
            <span className="text-slate-500">Сравнить со вторым полем:</span>
            <select
              value={comparePolygonId ?? ''}
              onChange={(e) => {
                const val = e.target.value;
                if (val) handleToggleCompare(val);
                else {
                  setComparePolygonId(null);
                  setCompareSeriesView(null);
                }
              }}
              className="bg-slate-50 border border-slate-300 rounded px-2.5 py-1 text-xs text-slate-800 font-medium"
            >
              <option value="">(выберите для наложения)</option>
              {meta.polygons
                .filter((p) => p.id !== selectedPolygonId)
                .map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.id} ({p.crop_type}, {p.years[0]}–{p.years[1]})
                  </option>
                ))}
            </select>
            {comparePolygonId && (
              <button
                type="button"
                onClick={() => {
                  setComparePolygonId(null);
                  setCompareSeriesView(null);
                }}
                className="text-xs text-red-600 hover:text-red-800 underline ml-1"
              >
                Убрать сравнение
              </button>
            )}
          </div>
        </div>

        {loadingSeries ? (
          <div className="p-12 text-center">
            <div className="w-8 h-8 border-4 border-brand-500 border-t-transparent rounded-full animate-spin mx-auto mb-2" />
            <span className="text-xs text-slate-500">Загрузка данных ряда...</span>
          </div>
        ) : (
          <AnalysisView
            series={seriesView}
            anomalies={anomalies}
            comparisonSeries={compareSeriesView}
            summary={{
              rows: seriesView.n,
              reconstructed: seriesView.ndviFilled.filter((_, i) => seriesView.ndviObs[i] === null).length,
              observed: seriesView.ndviObs.filter((v) => v !== null).length,
              anomaly_periods: anomalies.length,
              worst_z: anomalies.length > 0 ? Math.min(...anomalies.map((a) => a.z_min)) : null,
            }}
          />
        )}
        </div>
      </div>
    );
  }

  // Каталог полигонов
  return (
    <div className="w-full h-full overflow-y-auto p-6 bg-slate-100">
      <div className="space-y-6 max-w-7xl mx-auto">
        {/* Page Title */}
        <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm flex items-center justify-between">
          <div>
            <h2 className="text-lg font-black text-slate-900 tracking-tight flex items-center gap-2">
              <WifiOff className="w-5 h-5 text-blue-600" />
              <span>Оффлайн режим (78 эталонных полей)</span>
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Предрассчитанные суточные ряды индексов вегетации, восстановленные пропуски и обнаруженные аномалии.
            </p>
          </div>
        </div>

      {/* Overview Totals Tiles (§8.4) */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
          <div className="text-slate-400 text-[11px] font-semibold uppercase tracking-wider flex items-center gap-1.5">
            <Database className="w-3.5 h-3.5 text-slate-500" />
            Полигонов
          </div>
          <div className="text-2xl font-extrabold text-slate-900 mt-1">
            {formatInteger(meta.totals.polygons)}
          </div>
          <div className="text-[11px] text-slate-500 mt-0.5">сельхозугодий</div>
        </div>

        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
          <div className="text-slate-400 text-[11px] font-semibold uppercase tracking-wider flex items-center gap-1.5">
            <Layers className="w-3.5 h-3.5 text-blue-600" />
            Суток ряда
          </div>
          <div className="text-2xl font-extrabold text-slate-900 mt-1">
            {formatInteger(meta.totals.days)}
          </div>
          <div className="text-[11px] text-slate-500 mt-0.5">2010–2025 гг.</div>
        </div>

        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
          <div className="text-slate-400 text-[11px] font-semibold uppercase tracking-wider flex items-center gap-1.5">
            <Sparkles className="w-3.5 h-3.5 text-blue-500" />
            Снимков
          </div>
          <div className="text-2xl font-extrabold text-slate-900 mt-1">
            {formatInteger(meta.totals.observed)}
          </div>
          <div className="text-[11px] text-slate-500 mt-0.5">
            {formatPercent((meta.totals.observed / meta.totals.days) * 100)} покрытия
          </div>
        </div>

        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
          <div className="text-slate-400 text-[11px] font-semibold uppercase tracking-wider flex items-center gap-1.5">
            <Zap className="w-3.5 h-3.5 text-blue-600" />
            Восстановлено
          </div>
          <div className="text-2xl font-extrabold text-blue-600 mt-1">
            {formatInteger(meta.totals.reconstructed)}
          </div>
          <div className="text-[11px] text-slate-500 mt-0.5">суточных значений</div>
        </div>

        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm col-span-2 sm:col-span-1">
          <div className="text-slate-400 text-[11px] font-semibold uppercase tracking-wider flex items-center gap-1.5">
            <CheckCircle2 className="w-3.5 h-3.5 text-amber-500" />
            Аномалий
          </div>
          <div className="text-2xl font-extrabold text-amber-700 mt-1">
            {formatInteger(meta.totals.anomalies)}
          </div>
          <div className="text-[11px] text-slate-500 mt-0.5">периодов стресса</div>
        </div>
      </div>

      {/* Filter and search bar */}
      <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex flex-wrap items-center justify-between gap-3">
        {/* Search */}
        <div className="relative flex-1 min-w-[220px]">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Поиск по ID (AOI-0001) или культуре..."
            className="w-full pl-9 pr-3 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-500 focus:bg-white"
          />
        </div>

        {/* Crop filter */}
        <div className="flex items-center gap-2 text-xs">
          <span className="text-slate-500 flex items-center gap-1">
            <Filter className="w-3.5 h-3.5" />
            Культура:
          </span>
          <select
            value={selectedCrop}
            onChange={(e) => setSelectedCrop(e.target.value)}
            className="bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-1.5 text-xs text-slate-700 focus:ring-1 focus:ring-brand-500"
          >
            <option value="all">Все культуры ({meta.polygons.length})</option>
            {meta.crop_types.map((c) => (
              <option key={c} value={c}>
                {c} ({meta.polygons.filter((p) => p.crop_type === c).length})
              </option>
            ))}
          </select>
        </div>

        {/* Has anomalies toggle */}
        <label className="flex items-center gap-2 text-xs text-slate-700 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={onlyWithAnomalies}
            onChange={(e) => setOnlyWithAnomalies(e.target.checked)}
            className="rounded text-brand-600 focus:ring-brand-500"
          />
          <span>Только с аномалиями</span>
        </label>
      </div>

      {/* Table of 78 Polygons (§8.4) */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead className="bg-slate-100 text-slate-600 uppercase text-[10px] font-bold tracking-wider border-b border-slate-200">
              <tr>
                <th
                  onClick={() => handleSort('id')}
                  className="p-3 cursor-pointer hover:bg-slate-200 transition-colors"
                >
                  <div className="flex items-center gap-1">
                    <span>ID полигона</span>
                    <ArrowUpDown className="w-3 h-3" />
                  </div>
                </th>
                <th
                  onClick={() => handleSort('crop_type')}
                  className="p-3 cursor-pointer hover:bg-slate-200 transition-colors"
                >
                  <div className="flex items-center gap-1">
                    <span>Культура</span>
                    <ArrowUpDown className="w-3 h-3" />
                  </div>
                </th>
                <th
                  onClick={() => handleSort('years')}
                  className="p-3 cursor-pointer hover:bg-slate-200 transition-colors"
                >
                  <div className="flex items-center gap-1">
                    <span>Годы</span>
                    <ArrowUpDown className="w-3 h-3" />
                  </div>
                </th>
                <th
                  onClick={() => handleSort('n_days')}
                  className="p-3 cursor-pointer hover:bg-slate-200 transition-colors text-right"
                >
                  <div className="flex items-center justify-end gap-1">
                    <span>Суток</span>
                    <ArrowUpDown className="w-3 h-3" />
                  </div>
                </th>
                <th className="p-3 text-right">Наблюдений</th>
                <th
                  onClick={() => handleSort('coverage')}
                  className="p-3 cursor-pointer hover:bg-slate-200 transition-colors text-right"
                >
                  <div className="flex items-center justify-end gap-1">
                    <span>Покрытие</span>
                    <ArrowUpDown className="w-3 h-3" />
                  </div>
                </th>
                <th
                  onClick={() => handleSort('n_anomalies')}
                  className="p-3 cursor-pointer hover:bg-slate-200 transition-colors text-center"
                >
                  <div className="flex items-center justify-center gap-1">
                    <span>Аномалий</span>
                    <ArrowUpDown className="w-3 h-3" />
                  </div>
                </th>
                <th className="p-3 text-right">Действие</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-800">
              {filteredPolygons.map((p) => {
                const isSingleSeason = p.years[0] === p.years[1];
                const coverage = p.n_days > 0 ? (p.n_observed / p.n_days) * 100 : 0;

                return (
                  <tr
                    key={p.id}
                    onClick={() => handleSelectPolygon(p.id)}
                    className="hover:bg-brand-50/50 cursor-pointer transition-colors group"
                  >
                    <td className="p-3 font-mono font-bold text-slate-900 group-hover:text-brand-700">
                      {p.id}
                    </td>
                    <td className="p-3 capitalize text-slate-700">{p.crop_type}</td>
                    <td className="p-3 text-slate-600">
                      {p.years[0]}–{p.years[1]}
                      {isSingleSeason && (
                        <span className="ml-2 bg-amber-100 text-amber-800 text-[10px] px-2 py-0.5 rounded font-medium">
                          1 сезон
                        </span>
                      )}
                    </td>
                    <td className="p-3 text-right font-mono text-slate-700">
                      {formatInteger(p.n_days)}
                    </td>
                    <td className="p-3 text-right font-mono text-slate-700">
                      {formatInteger(p.n_observed)}
                    </td>
                    <td className="p-3 text-right font-mono">
                      <div className="flex items-center justify-end gap-2">
                        <div className="w-12 bg-slate-200 h-1.5 rounded-full overflow-hidden hidden sm:block">
                          <div
                            className="bg-brand-500 h-full"
                            style={{ width: `${Math.min(100, coverage)}%` }}
                          />
                        </div>
                        <span className="font-semibold text-slate-800">
                          {formatPercent(coverage)}
                        </span>
                      </div>
                    </td>
                    <td className="p-3 text-center">
                      {p.n_anomalies > 0 ? (
                        <span className="bg-red-50 text-red-700 border border-red-200 px-2.5 py-0.5 rounded-full font-bold text-xs">
                          {p.n_anomalies}
                        </span>
                      ) : isSingleSeason ? (
                        <span className="bg-slate-100 text-slate-500 px-2 py-0.5 rounded text-[11px]">
                          климатнорма не построена
                        </span>
                      ) : (
                        <span className="bg-slate-100 text-slate-500 px-2 py-0.5 rounded text-[11px]">
                          без аномалий
                        </span>
                      )}
                    </td>
                    <td className="p-3 text-right">
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleSelectPolygon(p.id);
                        }}
                        className="px-2.5 py-1 bg-brand-50 text-brand-700 group-hover:bg-brand-600 group-hover:text-white rounded-md text-xs font-semibold transition-colors shadow-sm"
                      >
                        Разбор
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
);
};
