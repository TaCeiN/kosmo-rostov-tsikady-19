import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createAnalyzeJob, fetchMeta, getAnalyzeJobStatus } from '../api/client';
import {
  AnalysisResult,
  AnalyzeJobStatusResponse,
  AnomalyRecord,
} from '../types/domain';
import { buildFieldDigest } from '../features/analysis/digest';
import { AiInsights } from '../features/analysis/AiInsights';
import { fromApiSeries, SeriesView } from '../adapters/series';
import { AreaMap } from '../features/map/AreaMap';
import { validateGeometry } from '../features/map/validation';
import { JobProgressView } from '../features/job/JobProgressView';
import { AnalysisView } from '../features/analysis/AnalysisView';
import { pollJob } from '../features/job/polling';
import { formatArea } from '../lib/formatters';
import { DEFAULT_META, useAppStore } from '../lib/store';
import {
  SavedPolygon,
  addSavedPolygon,
  loadAnalysis,
  saveAnalysisFor,
  toPolygon,
} from '../features/map/savedPolygons';
import {
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  Bookmark,
  BookmarkCheck,
  Clock,
  Expand,
  GitCompare,
  Layers,
  Sparkles,
  SlidersHorizontal,
  X,
  Maximize2,
  Minimize2,
  Calendar,
  ChevronLeft,
} from 'lucide-react';

export const AnalyzePage: React.FC = () => {
  const {
    geometry,
    setGeometry,
    meta,
    setMeta,
    savedPolygons,
    setSavedPolygons,
    sidebarCollapsed,
  } = useAppStore();

  // Число поставленных вершин приходит из AreaMap
  const [pointsCount, setPointsCount] = useState<number>(0);

  // Видимость панели параметров: её можно свернуть
  const [drawerMinimized, setDrawerMinimized] = useState(false);
  const [isExpandedWide, setIsExpandedWide] = useState(false);

  // Состояние формы
  const [startYear, setStartYear] = useState<number>(2016);
  const [endYear, setEndYear] = useState<number>(2025);
  const [cropType, setCropType] = useState<string>('неизвестно');

  // Состояние запуска и опроса задачи
  const [jobId, setJobId] = useState<string | null>(null);
  const [expectedSeconds, setExpectedSeconds] = useState<number>(80);
  const [pollStatus, setPollStatus] = useState<AnalyzeJobStatusResponse | null>(null);
  const [pollError, setPollError] = useState<string | null>(null);
  const [isJobLost, setIsJobLost] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Результат разбора
  const [analysisResult, setAnalysisResult] = useState<AnalysisResult | null>(null);
  const [seriesView, setSeriesView] = useState<SeriesView | null>(null);

  // Сезоны и культура, по которым посчитан текущий разбор. Форма к этому
  // моменту может показывать уже другое: в закладку кладём то, что считалось.
  const [resultParams, setResultParams] = useState<{ years: number[]; cropType: string } | null>(
    null
  );

  // Итог последнего сохранения в закладки: показываем прямо в панели
  const [bookmarkNote, setBookmarkNote] = useState<
    { kind: 'ok' | 'warn'; text: string } | null
  >(null);

  // Закладка, из которой открыт текущий разбор, либо только что созданная
  const [activeBookmarkId, setActiveBookmarkId] = useState<string | null>(null);

  // Готовый разбор показываем во весь экран, как каталог полей в демо-режиме:
  // в панели шириной 420 px график читать нечем
  const [fullscreen, setFullscreen] = useState(false);

  // Имя поля для заголовка карточки: у закладки своё, у свежей обводки нет
  const [fieldTitle, setFieldTitle] = useState<string | null>(null);

  // Контур, которому принадлежит показанный разбор. Нужен, чтобы отличить
  // «пользователь обвёл другое поле» от «карта переставила те же вершины».
  const resultRingRef = useRef<string | null>(null);

  // Второе поле для наложения на график и сравнения. Берём из своих же
  // закладок: сравнивать есть смысл только с тем, что уже посчитано.
  const [compareId, setCompareId] = useState<string | null>(null);
  const [compareSeries, setCompareSeries] = useState<SeriesView | null>(null);
  const [compareAnomalies, setCompareAnomalies] = useState<AnomalyRecord[]>([]);
  const [compareAreaHa, setCompareAreaHa] = useState<number | null>(null);

  // Тянем /meta при старте, если его ещё нет в сторе
  useEffect(() => {
    if (meta) {
      setStartYear(meta.years.default[0] ?? 2016);
      setEndYear(meta.years.default[1] ?? 2025);
      return;
    }

    let cancelled = false;
    fetchMeta()
      .then((data) => {
        if (!cancelled) {
          setMeta(data);
          setStartYear(data.years.default[0] ?? 2016);
          setEndYear(data.years.default[1] ?? 2025);
        }
      })
      .catch((err) => {
        // Бэкенд не поднят: работаем на параметрах по умолчанию, чтобы
        // карта и валидация оставались живыми
        console.warn('GET /meta недоступен, берём параметры по умолчанию:', err);
        if (!cancelled) {
          setMeta(DEFAULT_META);
          setStartYear(DEFAULT_META.years.default[0]);
          setEndYear(DEFAULT_META.years.default[1]);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [meta, setMeta]);

  /**
   * Отпечаток контура: набор вершин без оглядки на их порядок. Карта
   * пересобирает кольцо своим обходом по часовой и дописывает замыкающую
   * точку, так что сравнение «в лоб» ложно срабатывало бы на том же поле.
   */
  const ringKey = (geom: GeoJSON.Geometry | GeoJSON.Feature | null): string | null => {
    const polygon = toPolygon(geom);
    const ring = polygon?.coordinates[0];
    if (!ring) return null;

    const seen = new Set(
      ring.map((pt) => `${(pt[0] ?? 0).toFixed(7)},${(pt[1] ?? 0).toFixed(7)}`)
    );
    return [...seen].sort().join(';');
  };

  const geometryRing = useMemo(() => ringKey(geometry), [geometry]);

  // Контур сменился — показанный разбор к нему больше не относится.
  // Без этого свежая обводка открывалась с результатами прошлого поля.
  useEffect(() => {
    if (!analysisResult) return;
    if (resultRingRef.current === null) return;
    if (geometryRing === resultRingRef.current) return;

    setAnalysisResult(null);
    setSeriesView(null);
    setResultParams(null);
    setActiveBookmarkId(null);
    setFieldTitle(null);
    setFullscreen(false);
    setBookmarkNote(null);
    setCompareId(null);
    setCompareSeries(null);
    setCompareAnomalies([]);
    setCompareAreaHa(null);
    resultRingRef.current = null;
  }, [geometryRing, analysisResult]);

  // Валидация выбранной области
  const validation = useMemo(() => {
    const active = meta ?? DEFAULT_META;
    return validateGeometry(geometry, active.region_box, active.max_area_ha);
  }, [geometry, meta]);

  const yearSpan = endYear - startYear + 1;
  const isYearSpanValid = yearSpan >= (meta?.years.min_span ?? 3);

  const canSubmit = validation.valid && isYearSpanValid && !jobId;

  // Контур готов, когда набрано минимум 3 вершины либо геометрия пришла
  // готовой: из файла, из списка участков или из найденного контура OSM
  const hasSelectedField = pointsCount >= 3 || (geometry !== null && validation.valid);

  // Как только контур замкнулся, снова раскрываем панель параметров
  useEffect(() => {
    if (hasSelectedField) {
      setDrawerMinimized(false);
    }
  }, [hasSelectedField]);

  // Смена годов с оглядкой на минимальную длину периода
  const handleStartYearChange = (newStart: number) => {
    if (!meta) return;
    const minSpan = meta.years.min_span;
    if (endYear - newStart + 1 < minSpan) {
      setEndYear(Math.min(meta.years.max, newStart + minSpan - 1));
    }
    setStartYear(newStart);
  };

  const handleEndYearChange = (newEnd: number) => {
    if (!meta) return;
    const minSpan = meta.years.min_span;
    if (newEnd - startYear + 1 < minSpan) {
      setStartYear(Math.max(meta.years.min, newEnd - minSpan + 1));
    }
    setEndYear(newEnd);
  };

  // Постановка задачи на анализ
  const handleSubmit = async () => {
    if (!canSubmit || !geometry || !meta) return;

    setPollError(null);
    setIsJobLost(false);
    setAnalysisResult(null);
    setSeriesView(null);
    setResultParams(null);
    setBookmarkNote(null);
    setActiveBookmarkId(null);
    setFieldTitle(null);
    setFullscreen(false);
    setCompareId(null);
    setCompareSeries(null);
    setCompareAnomalies([]);
    setCompareAreaHa(null);

    // Контур, который уходит на расчёт: результат привяжем именно к нему
    const submittedRing = geometryRing;

    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    try {
      const yearsList: number[] = [];
      for (let y = startYear; y <= endYear; y++) {
        yearsList.push(y);
      }

      const created = await createAnalyzeJob({
        geometry,
        years: yearsList,
        crop_type: cropType,
      });

      setJobId(created.job_id);
      setExpectedSeconds(created.expected_seconds);

      // Запускаем опрос статуса
      await pollJob({
        jobId: created.job_id,
        fetchStatus: (id, sig) => getAnalyzeJobStatus(id, sig),
        intervalMs: 2500,
        signal: abortController.signal,
        onEvent: (event) => {
          if (event.type === 'status') {
            setPollStatus(event.data);
          } else if (event.type === 'done') {
            resultRingRef.current = submittedRing;
            setAnalysisResult(event.result);
            setSeriesView(
              fromApiSeries(event.result.series, {
                id: 'USER-AREA',
                cropType,
                years: yearsList,
              })
            );
            setResultParams({ years: yearsList, cropType });
            setJobId(null);
            // Расчёт закончен — сразу показываем поле целиком
            setFullscreen(true);
          } else if (event.type === 'lost') {
            setIsJobLost(true);
            setPollError(event.message);
          } else if (event.type === 'error') {
            setPollError(event.message);
          }
        },
      });
    } catch (err: unknown) {
      if (!abortController.signal.aborted) {
        setPollError(err instanceof Error ? err.message : String(err));
      }
    }
  };

  const handleCancelJob = () => {
    abortControllerRef.current?.abort();
    setJobId(null);
    setPollStatus(null);
    setPollError(null);
  };

  /**
   * Кладёт в закладки то, что есть: посчитанный разбор целиком либо один
   * контур, если расчёт ещё не запускали.
   */
  const handleSaveBookmark = () => {
    if (!geometry) return;

    if (!analysisResult || !resultParams) {
      setSavedPolygons(addSavedPolygon(savedPolygons, geometry));
      setBookmarkNote({ kind: 'ok', text: 'Контур сохранён в «Мои участки»' });
      return;
    }

    const outcome = saveAnalysisFor(savedPolygons, geometry, {
      years: resultParams.years,
      cropType: resultParams.cropType,
      result: analysisResult,
    });

    if (!outcome.entry) {
      setBookmarkNote({ kind: 'warn', text: 'Не удалось сохранить: контур не распознан' });
      return;
    }

    setSavedPolygons(outcome.list);
    setActiveBookmarkId(outcome.entry.id);
    setFieldTitle(outcome.entry.name);

    setBookmarkNote(
      outcome.stored
        ? {
            kind: 'ok',
            text: `Разбор сохранён как «${outcome.entry.name}» — откроется из «Мои участки» без пересчёта`,
          }
        : {
            kind: 'warn',
            text: 'Контур сохранён, а разбор не поместился в хранилище браузера. Удалите старые закладки и повторите',
          }
    );
  };

  /**
   * Восстанавливает поле из закладки: контур всегда, разбор — если сохранён.
   * Возвращает признак того, что разбор действительно поднялся.
   */
  const restoreBookmark = (entry: SavedPolygon): boolean => {
    abortControllerRef.current?.abort();
    setJobId(null);
    setPollStatus(null);
    setPollError(null);
    setIsJobLost(false);
    setBookmarkNote(null);
    setDrawerMinimized(false);
    setCompareId(null);
    setCompareSeries(null);
    setCompareAnomalies([]);
    setCompareAreaHa(null);
    setGeometry(entry.geometry);
    setFieldTitle(entry.name);

    const payload = entry.analysis ? loadAnalysis(entry.id) : null;

    if (!payload) {
      resultRingRef.current = null;
      setAnalysisResult(null);
      setSeriesView(null);
      setResultParams(null);
      setActiveBookmarkId(null);
      setFullscreen(false);
      return false;
    }

    resultRingRef.current = ringKey(entry.geometry);
    const years = payload.years;
    setAnalysisResult(payload.result);
    setSeriesView(
      fromApiSeries(payload.result.series, {
        id: entry.name,
        cropType: payload.cropType,
        years,
      })
    );
    setResultParams({ years, cropType: payload.cropType });
    setActiveBookmarkId(entry.id);

    // Форма должна показывать параметры открытого разбора, а не прошлые
    setCropType(payload.cropType);
    const firstYear = years[0];
    const lastYear = years[years.length - 1];
    if (firstYear !== undefined) setStartYear(firstYear);
    if (lastYear !== undefined) setEndYear(lastYear);

    return true;
  };

  /** Выбор из списка участков: камера летит к полю, разбор ждёт в панели. */
  const handlePickSaved = (entry: SavedPolygon) => {
    restoreBookmark(entry);
    setFullscreen(false);
  };

  /** Клик по периметру поля на карте: полная карточка на весь экран. */
  const handleOpenSavedField = (entry: SavedPolygon) => {
    setFullscreen(restoreBookmark(entry));
  };

  /**
   * Возврат к карте: выделение снимаем целиком, иначе поле остаётся обведённым
   * с вершинами наперевес и мешает выбрать следующее. Несохранённый разбор
   * перед этим уходит в закладки — за него заплачено минутой ожидания,
   * терять его молча нельзя. Поле останется на карте слоем «Мои поля».
   */
  const handleBackToMap = () => {
    if (analysisResult && resultParams && geometry && !isBookmarked) {
      const outcome = saveAnalysisFor(savedPolygons, geometry, {
        years: resultParams.years,
        cropType: resultParams.cropType,
        result: analysisResult,
      });
      if (outcome.entry) setSavedPolygons(outcome.list);
    }

    resultRingRef.current = null;
    setFullscreen(false);
    setAnalysisResult(null);
    setSeriesView(null);
    setResultParams(null);
    setActiveBookmarkId(null);
    setFieldTitle(null);
    setBookmarkNote(null);
    setIsExpandedWide(false);
    setDrawerMinimized(false);
    setCompareId(null);
    setCompareSeries(null);
    setCompareAnomalies([]);
    setCompareAreaHa(null);
    setGeometry(null);
  };

  const isBookmarked = activeBookmarkId !== null &&
    savedPolygons.some((p) => p.id === activeBookmarkId && p.analysis);

  /** Свои поля, с которыми есть что сравнивать: разбор уже посчитан. */
  const compareCandidates = savedPolygons.filter(
    (p) => p.analysis && p.id !== activeBookmarkId
  );

  /** Выбор второго поля: разбор поднимаем из localStorage, бэкенд не трогаем. */
  const handleSelectCompare = (id: string) => {
    if (!id) {
      setCompareId(null);
      setCompareSeries(null);
      setCompareAnomalies([]);
      setCompareAreaHa(null);
      return;
    }

    const entry = savedPolygons.find((p) => p.id === id);
    const payload = entry ? loadAnalysis(entry.id) : null;
    if (!entry || !payload) {
      setBookmarkNote({
        kind: 'warn',
        text: 'Разбор этого поля не нашёлся в хранилище браузера — откройте его и пересчитайте',
      });
      return;
    }

    setCompareId(id);
    setCompareAreaHa(payload.result.area_ha ?? entry.areaHa);
    setCompareAnomalies(payload.result.anomalies ?? []);
    setCompareSeries(
      fromApiSeries(payload.result.series, {
        // id уходит в подпись серии на графике — там нужно имя поля
        id: entry.name,
        cropType: payload.cropType,
        years: payload.years,
      })
    );
  };

  // Выжимки для ИИ: пересобираем только когда меняется сам разбор
  const fieldDigest = useMemo(() => {
    if (!seriesView || !analysisResult) return null;
    return buildFieldDigest(seriesView, analysisResult.anomalies, {
      name: fieldTitle ?? 'Выделенное поле',
      areaHa: analysisResult.area_ha ?? validation.areaHa,
      outsideRegion: validation.isOutsideRegion,
      observedPct:
        analysisResult.summary && analysisResult.summary.rows
          ? Math.round((analysisResult.summary.observed / analysisResult.summary.rows) * 1000) / 10
          : null,
      reconstructed: analysisResult.summary?.reconstructed ?? null,
    });
  }, [seriesView, analysisResult, fieldTitle, validation.areaHa, validation.isOutsideRegion]);

  const compareDigest = useMemo(() => {
    if (!compareSeries) return null;
    return buildFieldDigest(compareSeries, compareAnomalies, {
      name: compareSeries.id,
      areaHa: compareAreaHa,
    });
  }, [compareSeries, compareAnomalies, compareAreaHa]);

  return (
    <div className="w-full h-full relative overflow-hidden bg-slate-100">
      {/* 1. Full-Screen Interactive Map */}
      <AreaMap
        regionBox={meta?.region_box ?? DEFAULT_META.region_box}
        geometry={geometry}
        onChangeGeometry={setGeometry}
        isOutsideRegion={validation.isOutsideRegion}
        onPointsCountChange={setPointsCount}
        onSaveCurrent={handleSaveBookmark}
        saveLabel={analysisResult ? 'Сохранить разбор' : undefined}
        onPickSaved={handlePickSaved}
        onOpenSavedField={handleOpenSavedField}
      />

      {/* 1a. Готовое поле целиком: карточка поверх карты, как каталог в демо */}
      {fullscreen && analysisResult && seriesView && (
        <div
          /* Меню на этой странице лежит поверх карты и рисуется в своём слое:
             перекрыть его изнутри нельзя, поэтому карточку двигаем правее. */
          className={`absolute inset-y-0 right-0 z-[1100] bg-slate-100 overflow-y-auto animate-in fade-in transition-all duration-300 ${
            sidebarCollapsed ? 'left-20' : 'left-64'
          }`}
        >
          <div className="max-w-7xl mx-auto p-6 space-y-4">
            {/* Шапка карточки */}
            <div className="flex flex-wrap items-center justify-between gap-3 bg-white p-3 rounded-xl border border-slate-200 shadow-sm sticky top-0 z-10">
              <div className="flex items-center gap-3 min-w-0">
                <button
                  type="button"
                  onClick={handleBackToMap}
                  className="flex items-center gap-1.5 text-xs font-semibold text-slate-700 bg-slate-100 hover:bg-slate-200 px-3 py-1.5 rounded-lg transition-colors shrink-0"
                  title="Вернуться к карте и снять выделение. Поле останется в слое «Мои поля»"
                >
                  <ArrowLeft className="w-3.5 h-3.5" />
                  <span>К карте</span>
                </button>

                <div className="min-w-0">
                  <div className="text-sm font-black text-slate-900 truncate">
                    {fieldTitle ?? 'Выделенное поле'}
                  </div>
                  <div className="text-[11px] text-slate-500 truncate">
                    {formatArea(analysisResult.area_ha ?? validation.areaHa)}
                    {' • '}
                    {resultParams?.cropType ?? cropType}
                    {' • '}
                    сезонов: {seriesView.years.length}
                    {validation.isOutsideRegion && ' • вне региона обучения'}
                  </div>
                </div>
              </div>

              <button
                type="button"
                onClick={handleSaveBookmark}
                className={`text-xs font-bold px-3 py-1.5 rounded-lg border transition-colors flex items-center gap-1.5 shrink-0 ${
                  isBookmarked
                    ? 'text-blue-700 bg-blue-50 border-blue-200 hover:bg-blue-100'
                    : 'text-white bg-blue-600 border-blue-600 hover:bg-blue-500 shadow-sm'
                }`}
                title="Сохранить разбор в «Мои участки»: закладка откроется без повторного расчёта"
              >
                {isBookmarked ? (
                  <BookmarkCheck className="w-3.5 h-3.5" />
                ) : (
                  <Bookmark className="w-3.5 h-3.5" />
                )}
                <span>{isBookmarked ? 'Обновить закладку' : 'В закладки'}</span>
              </button>
            </div>

            {bookmarkNote && (
              <div
                className={`text-xs p-3 rounded-xl border flex items-start gap-2 ${
                  bookmarkNote.kind === 'ok'
                    ? 'text-blue-800 bg-blue-50 border-blue-200'
                    : 'text-amber-900 bg-amber-50 border-amber-300'
                }`}
              >
                {bookmarkNote.kind === 'ok' ? (
                  <BookmarkCheck className="w-4 h-4 shrink-0 mt-0.5" />
                ) : (
                  <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                )}
                <span className="flex-1">{bookmarkNote.text}</span>
                <button
                  type="button"
                  onClick={() => setBookmarkNote(null)}
                  className="text-slate-400 hover:text-slate-700 font-semibold shrink-0"
                >
                  ✕
                </button>
              </div>
            )}

            {/* Сравнение со своим же полем: наложение второго ряда на график */}
            <div className="bg-white p-3 rounded-xl border border-slate-200 shadow-sm flex flex-wrap items-center gap-2 text-xs">
              <span className="flex items-center gap-1.5 font-semibold text-slate-700">
                <GitCompare className="w-3.5 h-3.5 text-blue-600" />
                Сравнить со вторым полем:
              </span>

              <select
                value={compareId ?? ''}
                onChange={(e) => handleSelectCompare(e.target.value)}
                disabled={compareCandidates.length === 0}
                className="bg-slate-50 border border-slate-300 rounded-lg px-2.5 py-1 text-xs text-slate-800 font-medium disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="">
                  {compareCandidates.length === 0
                    ? '(нет других полей с разбором)'
                    : '(выберите для наложения)'}
                </option>
                {compareCandidates.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} — {formatArea(p.areaHa)}
                    {p.analysis
                      ? `, ${p.analysis.years[0]}–${p.analysis.years[p.analysis.years.length - 1]}`
                      : ''}
                  </option>
                ))}
              </select>

              {compareId && (
                <button
                  type="button"
                  onClick={() => handleSelectCompare('')}
                  className="text-xs text-rose-600 hover:text-rose-800 underline"
                >
                  Убрать сравнение
                </button>
              )}

              {compareCandidates.length === 0 && (
                <span className="text-[11px] text-slate-400">
                  Посчитайте и сохраните ещё одно поле — оно появится в списке
                </span>
              )}
            </div>

            {/* ИИ-разбор поверх готовых чисел */}
            {meta?.ai_available && fieldDigest && (
              <AiInsights
                field={fieldDigest}
                compareField={compareDigest}
                model={meta.ai_model}
              />
            )}

            <AnalysisView
              series={seriesView}
              anomalies={analysisResult.anomalies}
              summary={analysisResult.summary}
              fetchStats={analysisResult.fetch}
              areaHa={analysisResult.area_ha}
              comparisonSeries={compareSeries}
              rawResult={analysisResult}
            />
          </div>
        </div>
      )}

      {/* 2. Floating button to re-open parameters if user minimized drawer */}
      {hasSelectedField && drawerMinimized && (
        <button
          type="button"
          onClick={() => setDrawerMinimized(false)}
          className="absolute top-4 right-4 z-[1000] bg-black/65 backdrop-blur-md px-4 py-2.5 rounded-2xl shadow-2xl border border-white/10 text-xs font-bold text-white flex items-center gap-2 hover:bg-black/80 hover:border-white/30 hover:scale-105 transition-all animate-in fade-in"
        >
          <SlidersHorizontal className="w-4 h-4 text-white" />
          <span>Параметры поля ({formatArea(validation.areaHa)})</span>
        </button>
      )}

      {/* 3. Right-Side Parameter Drawer (appears after selecting 4 points) */}
      {hasSelectedField && !drawerMinimized && (
        <aside
          className={`absolute top-4 right-4 bottom-4 z-[1000] bg-black/65 backdrop-blur-md rounded-2xl shadow-2xl border border-white/10 flex flex-col overflow-hidden text-white transition-all duration-300 animate-in slide-in-from-right ${
            isExpandedWide
              ? 'w-[800px] max-w-[calc(100vw-300px)]'
              : 'w-[420px] max-w-[calc(100vw-300px)]'
          }`}
        >
          {/* Drawer Top Header */}
          <div className="px-4 py-3.5 border-b border-white/10 bg-white/[0.03] flex items-center justify-between gap-2 shrink-0">
            <div className="flex items-center gap-2 min-w-0">
              <div className="w-7 h-7 rounded-lg bg-white/10 text-white flex items-center justify-center shrink-0 border border-white/15">
                <SlidersHorizontal className="w-4 h-4" />
              </div>
              <div className="min-w-0">
                <div className="font-bold text-white text-xs truncate">
                  Параметры анализа поля
                </div>
                <div className="text-[11px] text-white/60 truncate flex items-center gap-1.5">
                  <span>Площадь: <b className="text-white">{formatArea(validation.areaHa)}</b></span>
                  {validation.valid ? (
                    <span className="text-[10px] text-white bg-white/15 border border-white/20 font-semibold px-1.5 py-0.2 rounded">
                      В норме
                    </span>
                  ) : (
                    <span className="text-[10px] text-rose-300 bg-rose-500/20 border border-rose-500/30 font-semibold px-1.5 py-0.2 rounded">
                      Ошибка
                    </span>
                  )}
                </div>
              </div>
            </div>

            <div className="flex items-center gap-1 shrink-0">
              {analysisResult && (
                <button
                  type="button"
                  onClick={() => setIsExpandedWide(!isExpandedWide)}
                  className="p-1.5 text-white/60 hover:text-white hover:bg-white/10 rounded-lg transition-colors"
                  title={isExpandedWide ? 'Компактный вид' : 'Широкий вид графиков'}
                >
                  {isExpandedWide ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
                </button>
              )}
              <button
                type="button"
                onClick={() => setDrawerMinimized(true)}
                className="p-1.5 text-white/60 hover:text-white hover:bg-white/10 rounded-lg transition-colors"
                title="Свернуть панель"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Drawer Body */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {/* Validation warnings / errors if any */}
            {!validation.valid && (
              <div className="text-xs text-rose-300 bg-rose-500/15 p-3 rounded-xl border border-rose-500/30 flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
                <div>
                  <div className="font-bold">Ошибка выделения:</div>
                  <div className="text-[11px] mt-0.5">{validation.error}</div>
                </div>
              </div>
            )}

            {validation.warning && (
              <div
                className={`text-xs p-3 rounded-xl border flex items-start gap-2 ${
                  validation.isOutsideRegion
                    ? 'text-amber-200 bg-amber-500/20 border-amber-500/45'
                    : 'text-amber-300 bg-amber-500/15 border-amber-500/30'
                }`}
              >
                <AlertCircle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                <div className="text-[11px]">
                  {validation.isOutsideRegion && (
                    <div className="font-bold mb-0.5">Вне региона обучения — расчёт доступен</div>
                  )}
                  {validation.warning}
                </div>
              </div>
            )}

            {/* A. Job is in progress */}
            {jobId && (
              <JobProgressView
                jobId={jobId}
                expectedSeconds={expectedSeconds}
                statusData={pollStatus}
                error={pollError}
                isLost={isJobLost}
                onCancel={handleCancelJob}
                onRetry={handleSubmit}
                onChangeArea={handleCancelJob}
              />
            )}

            {/* B. Analysis is done */}
            {!jobId && analysisResult && seriesView && (
              <div className="space-y-4">
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  <button
                    type="button"
                    onClick={() => {
                      resultRingRef.current = null;
                      setAnalysisResult(null);
                      setSeriesView(null);
                      setResultParams(null);
                      setActiveBookmarkId(null);
                      setBookmarkNote(null);
                      setFieldTitle(null);
                      setFullscreen(false);
                      setIsExpandedWide(false);
                    }}
                    className="text-xs font-semibold text-white bg-white/10 hover:bg-white/20 border border-white/15 px-3 py-1.5 rounded-lg transition-colors flex items-center gap-1"
                  >
                    <ChevronLeft className="w-3.5 h-3.5" />
                    <span>К параметрам</span>
                  </button>

                  <div className="flex items-center gap-2 ml-auto">
                    <span className="text-xs text-white/60">
                      Сезонов: <b className="text-white">{seriesView.years.length}</b>
                    </span>

                    <button
                      type="button"
                      onClick={() => setFullscreen(true)}
                      className="text-xs font-bold text-white bg-white/10 hover:bg-white/20 border border-white/15 px-3 py-1.5 rounded-lg transition-colors flex items-center gap-1.5"
                      title="Показать поле целиком"
                    >
                      <Expand className="w-3.5 h-3.5" />
                      <span>На весь экран</span>
                    </button>

                    <button
                      type="button"
                      onClick={handleSaveBookmark}
                      className={`text-xs font-bold px-3 py-1.5 rounded-lg border transition-colors flex items-center gap-1.5 ${
                        isBookmarked
                          ? 'text-blue-200 bg-blue-600/25 border-blue-400/50 hover:bg-blue-600/40'
                          : 'text-white bg-blue-600 border-blue-400/50 hover:bg-blue-500 shadow-lg shadow-blue-600/30'
                      }`}
                      title="Сохранить разбор в «Мои участки»: закладка откроется без повторного расчёта"
                    >
                      {isBookmarked ? (
                        <BookmarkCheck className="w-3.5 h-3.5" />
                      ) : (
                        <Bookmark className="w-3.5 h-3.5" />
                      )}
                      <span>{isBookmarked ? 'Обновить закладку' : 'В закладки'}</span>
                    </button>
                  </div>
                </div>

                {bookmarkNote && (
                  <div
                    className={`text-[11px] p-2.5 rounded-xl border flex items-start gap-2 ${
                      bookmarkNote.kind === 'ok'
                        ? 'text-blue-200 bg-blue-500/15 border-blue-400/30'
                        : 'text-amber-200 bg-amber-500/15 border-amber-500/35'
                    }`}
                  >
                    {bookmarkNote.kind === 'ok' ? (
                      <BookmarkCheck className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                    ) : (
                      <AlertCircle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                    )}
                    <span className="flex-1">{bookmarkNote.text}</span>
                    <button
                      type="button"
                      onClick={() => setBookmarkNote(null)}
                      className="text-white/40 hover:text-white font-semibold shrink-0"
                    >
                      ✕
                    </button>
                  </div>
                )}

                <AnalysisView
                  series={seriesView}
                  anomalies={analysisResult.anomalies}
                  summary={analysisResult.summary}
                  fetchStats={analysisResult.fetch}
                  areaHa={analysisResult.area_ha}
                  rawResult={analysisResult}
                />
              </div>
            )}

            {/* C. Parameter Selection Form */}
            {!jobId && !analysisResult && meta && (
              <div className="space-y-4">
                {/* Year range selection */}
                <div className="bg-white/[0.04] p-3.5 rounded-xl border border-white/10 space-y-2.5">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-bold text-white flex items-center gap-1.5">
                      <Calendar className="w-3.5 h-3.5 text-white/80" />
                      Диапазон сезонов:
                    </span>
                    <span className="font-mono font-bold text-white text-xs bg-white/10 px-2 py-0.5 rounded border border-white/15">
                      {startYear} – {endYear} ({yearSpan} {yearSpan < 5 ? 'года' : 'лет'})
                    </span>
                  </div>

                  <div className="grid grid-cols-2 gap-2 pt-1">
                    <div>
                      <label className="text-[10px] text-white/60 block mb-1">С года:</label>
                      <select
                        value={startYear}
                        onChange={(e) => handleStartYearChange(parseInt(e.target.value, 10))}
                        className="w-full bg-black/40 border border-white/15 hover:border-white/30 rounded-lg p-2 text-xs font-semibold text-white focus:ring-2 focus:ring-white focus:border-white shadow-inner transition-colors"
                      >
                        {Array.from(
                          { length: meta.years.max - meta.years.min + 1 },
                          (_, i) => meta.years.min + i
                        ).map((y) => (
                          <option key={y} value={y} className="bg-slate-900 text-white">
                            {y}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div>
                      <label className="text-[10px] text-white/60 block mb-1">По год:</label>
                      <select
                        value={endYear}
                        onChange={(e) => handleEndYearChange(parseInt(e.target.value, 10))}
                        className="w-full bg-black/40 border border-white/15 hover:border-white/30 rounded-lg p-2 text-xs font-semibold text-white focus:ring-2 focus:ring-white focus:border-white shadow-inner transition-colors"
                      >
                        {Array.from(
                          { length: meta.years.max - meta.years.min + 1 },
                          (_, i) => meta.years.min + i
                        ).map((y) => (
                          <option key={y} value={y} className="bg-slate-900 text-white">
                            {y}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>

                  <p className="text-[10px] text-white/40 italic">
                    Минимум 3 сезона: климатическая норма рассчитывается методом исключения года.
                  </p>
                </div>

                {/* Crop type selection */}
                <div className="bg-white/[0.04] p-3.5 rounded-xl border border-white/10 space-y-2">
                  <label className="text-xs font-bold text-white flex items-center justify-between">
                    <span className="flex items-center gap-1.5">
                      <Layers className="w-3.5 h-3.5 text-white/80" />
                      Сельхозкультура:
                    </span>
                    <span className="text-[10px] text-white/40 font-normal">необязательно</span>
                  </label>

                  <select
                    value={cropType}
                    onChange={(e) => setCropType(e.target.value)}
                    className="w-full bg-black/40 border border-white/15 hover:border-white/30 rounded-lg p-2 text-xs font-semibold text-white capitalize focus:ring-2 focus:ring-white focus:border-white shadow-inner transition-colors"
                  >
                    {meta.crop_types.map((c) => (
                      <option key={c} value={c} className="bg-slate-900 text-white">
                        {c}
                      </option>
                    ))}
                  </select>
                  <p className="text-[10px] text-white/40">
                    Указание культуры позволяет модели точнее оценить типичные фазы вегетации.
                  </p>
                </div>

                {/* Calculation time estimate */}
                <div className="bg-white/[0.04] p-3 rounded-xl border border-white/10 flex items-center justify-between text-xs text-white/80">
                  <span className="flex items-center gap-1.5 text-white/60 text-[11px]">
                    <Clock className="w-3.5 h-3.5" />
                    Расчетное время:
                  </span>
                  <span className="font-bold text-white text-xs">
                    ~{40 + 4 * yearSpan} секунд
                  </span>
                </div>

                {/* CTA Submit Button */}
                <div className="pt-2">
                  <button
                    type="button"
                    disabled={!canSubmit}
                    onClick={handleSubmit}
                    className={`w-full py-3 px-4 rounded-xl font-bold text-xs flex items-center justify-center gap-2 shadow-sm transition-all duration-150 ${
                      canSubmit
                        ? 'bg-white text-black hover:bg-white/90 font-extrabold shadow-lg shadow-white/10 cursor-pointer hover:scale-[1.01]'
                        : 'bg-white/10 text-white/30 cursor-not-allowed'
                    }`}
                  >
                    <Sparkles className="w-4 h-4 text-black" />
                    <span>Проанализировать поле</span>
                  </button>

                  {!validation.valid && (
                    <div className="text-[10px] text-rose-400 text-center mt-1.5">
                      Скорректируйте контур поля на карте
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </aside>
      )}
    </div>
  );
};
