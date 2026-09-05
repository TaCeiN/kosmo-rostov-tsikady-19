import React, { useMemo, useState } from 'react';
import Papa from 'papaparse';
import { postPredict } from '../api/client';
import { AnalysisResult } from '../types/domain';
import { fromApiSeries, SeriesView } from '../adapters/series';
import { AnalysisView } from '../features/analysis/AnalysisView';
import {
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  FileSpreadsheet,
  Loader2,
  UploadCloud,
} from 'lucide-react';
import { formatInteger } from '../lib/formatters';

export const PredictPage: React.FC = () => {
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [parsing, setParsing] = useState(false);
  const [parsedRows, setParsedRows] = useState<Array<Record<string, unknown>>>([]);
  const [columns, setColumns] = useState<string[]>([]);

  // Сопоставление колонок файла с полями модели
  const [colPolygonId, setColPolygonId] = useState<string>('anon_polygon_id');
  const [colDate, setColDate] = useState<string>('date');

  // Состояние отправки и инференса
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [analysisResult, setAnalysisResult] = useState<AnalysisResult | null>(null);
  const [seriesView, setSeriesView] = useState<SeriesView | null>(null);

  // Разбор CSV в воркере: большой файл не должен вешать интерфейс
  const handleFileChange = (file: File) => {
    setCsvFile(file);
    setParsing(true);
    setError(null);
    setAnalysisResult(null);

    Papa.parse(file, {
      header: true,
      skipEmptyLines: true,
      dynamicTyping: true,
      worker: true,
      complete: (results) => {
        const rows = results.data as Array<Record<string, unknown>>;
        setParsedRows(rows);

        const cols = results.meta.fields || [];
        setColumns(cols);

        // Пробуем угадать нужные колонки по названию
        const foundId = cols.find(
          (c) => c.toLowerCase() === 'anon_polygon_id' || c.toLowerCase().includes('polygon') || c.toLowerCase() === 'id'
        );
        if (foundId) setColPolygonId(foundId);

        const foundDate = cols.find(
          (c) => c.toLowerCase() === 'date' || c.toLowerCase() === 'дата' || c.toLowerCase().includes('date')
        );
        if (foundDate) setColDate(foundDate);

        setParsing(false);
      },
      error: (err) => {
        setError(`Ошибка парсинга CSV: ${err.message}`);
        setParsing(false);
      },
    });
  };

  // Проверки качества входных данных (§8.6)
  const analysisWarnings = useMemo(() => {
    if (parsedRows.length === 0) return [];

    const warnings: string[] = [];

    // Считаем уникальные полигоны и сезоны
    const polygonsSet = new Set<unknown>();
    const datesList: string[] = [];
    const yearsSet = new Set<number>();

    for (const r of parsedRows) {
      const p = r[colPolygonId];
      const d = String(r[colDate] ?? '');
      if (p !== undefined && p !== null) polygonsSet.add(p);
      if (d) {
        datesList.push(d);
        const y = parseInt(d.slice(0, 4), 10);
        if (!isNaN(y)) yearsSet.add(y);
      }
    }

    if (polygonsSet.size === 1) {
      warnings.push('В файле один полигон: часть признаков модели смотрит на соседние поля в ту же дату, точность будет чуть ниже.');
    }

    if (yearsSet.size < 3) {
      warnings.push(`В файле меньше 3 сезонов (${yearsSet.size}): климатическая норма останется пустой, аномалии найдены не будут.`);
    }

    // Отличаем суточную сетку от списка дат съёмок: признаки считаются по сетке
    if (datesList.length > 5) {
      let largeGapCount = 0;
      for (let i = 1; i < Math.min(datesList.length, 30); i++) {
        const d1 = new Date(datesList[i - 1] + 'T00:00:00Z').getTime();
        const d2 = new Date(datesList[i] + 'T00:00:00Z').getTime();
        const diff = Math.round((d2 - d1) / 86400000);
        if (diff > 2) largeGapCount++;
      }
      if (largeGapCount > 5) {
        warnings.push('В файле, вероятно, только даты съёмок, а не сплошная суточная сетка: признаки и погодные окна считаются по сетке, поэтому качество интерполяции снизится.');
      }
    }

    return warnings;
  }, [parsedRows, colPolygonId, colDate]);

  // Отправка на POST /predict
  const handleSubmitPredict = async () => {
    if (parsedRows.length === 0) return;

    setSubmitting(true);
    setError(null);

    try {
      // Приводим колонки к именам, которых ждёт модель: anon_polygon_id и date
      const preparedRows = parsedRows.map((r) => {
        const row = { ...r };
        row.anon_polygon_id = r[colPolygonId];
        row.date = r[colDate];
        return row;
      });

      const result = await postPredict({
        rows: preparedRows,
        with_anomalies: true,
      });

      setAnalysisResult(result);
      setSeriesView(fromApiSeries(result.series));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  };

  // Расчёт закончен — показываем общий разбор
  if (analysisResult && seriesView) {
    return (
      <div className="w-full h-full overflow-y-auto p-6 bg-slate-100">
        <div className="space-y-4 max-w-7xl mx-auto">
          <div className="flex justify-between items-center bg-white p-3 rounded-xl border border-slate-200 shadow-sm">
            <button
              type="button"
              onClick={() => {
                setAnalysisResult(null);
                setSeriesView(null);
              }}
              className="text-xs font-semibold text-slate-700 bg-slate-100 hover:bg-slate-200 px-3 py-1.5 rounded-lg transition-colors"
            >
              ← Загрузить другой CSV файл
            </button>
            <span className="text-xs text-slate-500 font-medium">
              Обработано строк: <b>{formatInteger(analysisResult.summary.rows)}</b> • Найдено аномалий: <b>{analysisResult.summary.anomaly_periods}</b>
            </span>
          </div>

          <AnalysisView
            series={seriesView}
            anomalies={analysisResult.anomalies}
            summary={analysisResult.summary}
            rawResult={analysisResult}
          />
        </div>
      </div>
    );
  }

  return (
    <div className="w-full h-full overflow-y-auto p-6 bg-slate-100">
      <div className="space-y-6 max-w-4xl mx-auto">
      {/* Header */}
      <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm space-y-2">
        <h2 className="text-xl font-extrabold text-slate-900 flex items-center gap-2">
          <FileSpreadsheet className="w-5 h-5 text-blue-600" />
          <span>Пакетный инференс из CSV-файла (/predict)</span>
        </h2>
        <p className="text-xs text-slate-500 leading-relaxed">
          Загрузите CSV с суточными рядами или снимками полей. Модель синхронно восстановит пропуски, рассчитает климатическую норму и найдет аномалии вегетации с погодными причинами.
        </p>
      </div>

      {/* Drop-zone */}
      <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm space-y-4">
        <div
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            const file = e.dataTransfer.files[0];
            if (file) handleFileChange(file);
          }}
          className="border-2 border-dashed border-slate-300 hover:border-brand-500 rounded-2xl p-8 text-center bg-slate-50/50 hover:bg-brand-50/30 transition-all cursor-pointer"
        >
          <label className="cursor-pointer block space-y-3">
            <div className="w-12 h-12 bg-white rounded-full shadow-sm flex items-center justify-center mx-auto text-brand-600 border border-slate-100">
              <UploadCloud className="w-6 h-6" />
            </div>
            <div>
              <div className="text-sm font-bold text-slate-800">
                {csvFile ? csvFile.name : 'Выберите или перетащите CSV-файл сюда'}
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                Парсинг выполняется в фоновом Web Worker (PapaParse) для файлов любого объема
              </p>
            </div>
            <input
              type="file"
              accept=".csv,text/csv"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) handleFileChange(file);
              }}
              className="hidden"
            />
          </label>
        </div>

        {parsing && (
          <div className="p-4 text-center flex items-center justify-center gap-2 text-xs text-slate-600">
            <Loader2 className="w-4 h-4 animate-spin text-brand-600" />
            <span>Идет разбор CSV-файла...</span>
          </div>
        )}

        {/* Error alert */}
        {error && (
          <div className="bg-red-50 border border-red-200 p-4 rounded-xl flex items-start gap-2.5 text-xs text-red-700">
            <AlertTriangle className="w-4 h-4 text-red-600 shrink-0 mt-0.5" />
            <div className="leading-relaxed">
              <div className="font-bold">Ошибка обработки:</div>
              <div>{error}</div>
            </div>
          </div>
        )}

        {/* Column Mapping & Preview */}
        {parsedRows.length > 0 && (
          <div className="space-y-4 pt-2">
            <div className="bg-slate-50 p-4 rounded-xl border border-slate-200 space-y-3 text-xs">
              <h4 className="font-bold text-slate-800 text-sm flex items-center gap-2">
                <span>Сопоставление колонок</span>
                <span className="text-slate-500 font-normal">
                  (обнаружено {parsedRows.length} строк, {columns.length} колонок)
                </span>
              </h4>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="text-[11px] font-semibold text-slate-700 block mb-1">
                    Колонка идентификатора поля (обязательно):
                  </label>
                  <select
                    value={colPolygonId}
                    onChange={(e) => setColPolygonId(e.target.value)}
                    className="w-full bg-white border border-slate-300 rounded-lg p-2 font-mono text-xs"
                  >
                    {columns.map((c) => (
                      <option key={c} value={c}>
                        {c}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="text-[11px] font-semibold text-slate-700 block mb-1">
                    Колонка даты YYYY-MM-DD (обязательно):
                  </label>
                  <select
                    value={colDate}
                    onChange={(e) => setColDate(e.target.value)}
                    className="w-full bg-white border border-slate-300 rounded-lg p-2 font-mono text-xs"
                  >
                    {columns.map((c) => (
                      <option key={c} value={c}>
                        {c}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            </div>

            {/* Non-blocking Warnings (§8.6) */}
            {analysisWarnings.length > 0 && (
              <div className="space-y-2">
                {analysisWarnings.map((w, idx) => (
                  <div
                    key={idx}
                    className="bg-amber-50 border border-amber-200 p-3 rounded-xl flex items-start gap-2 text-xs text-amber-800"
                  >
                    <AlertCircle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
                    <span>{w}</span>
                  </div>
                ))}
              </div>
            )}

            {/* Preview of first 20 rows */}
            <div className="space-y-2">
              <div className="flex justify-between items-center text-xs text-slate-500">
                <span>Предпросмотр первых 20 строк:</span>
                <span>Всего строк в файле: <b>{parsedRows.length}</b></span>
              </div>

              <div className="overflow-x-auto max-h-56 border border-slate-200 rounded-xl bg-white shadow-inner">
                <table className="w-full text-left text-[11px] font-mono border-collapse">
                  <thead className="bg-slate-100 text-slate-700 sticky top-0 border-b">
                    <tr>
                      {columns.slice(0, 8).map((c) => (
                        <th key={c} className="p-2 truncate max-w-[150px]">
                          {c}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 text-slate-700">
                    {parsedRows.slice(0, 20).map((r, i) => (
                      <tr key={i} className="hover:bg-slate-50">
                        {columns.slice(0, 8).map((c) => (
                          <td key={c} className="p-2 truncate max-w-[150px]">
                            {r[c] !== null && r[c] !== undefined ? String(r[c]) : '—'}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Submit button */}
            <div className="pt-2">
              <button
                type="button"
                disabled={submitting}
                onClick={handleSubmitPredict}
                className="w-full py-3 px-4 bg-brand-600 hover:bg-brand-700 text-white font-bold text-xs rounded-xl shadow-md flex items-center justify-center gap-2 cursor-pointer transition-colors disabled:bg-slate-300"
              >
                {submitting ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Выполняется инференс LightGBM...</span>
                  </>
                ) : (
                  <>
                    <span>Запустить восстановление и анализ аномалий</span>
                    <ArrowRight className="w-4 h-4" />
                  </>
                )}
              </button>
              {submitting && (
                <div className="text-[11px] text-slate-400 text-center mt-2">
                  Первый запрос после запуска бэкенда может занять на пару секунд дольше из-за подгрузки модели в память.
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  </div>
);
};
