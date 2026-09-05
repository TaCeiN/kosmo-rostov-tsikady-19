import React, { useEffect, useState } from 'react';
import { AnalyzeJobStatusResponse, FetchStats } from '../../types/domain';
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Loader2,
  RefreshCw,
  Satellite,
  XCircle,
} from 'lucide-react';
import { formatInteger, formatPercent } from '../../lib/formatters';

interface JobProgressViewProps {
  jobId: string;
  expectedSeconds: number;
  statusData: AnalyzeJobStatusResponse | null;
  error: string | null;
  isLost: boolean;
  onCancel: () => void;
  onRetry: () => void;
  onChangeArea: () => void;
}

const FACTS = [
  'Модель обучена на 106 агро- и метеопризнаках и восстанавливает суточный ряд с точностью RMSE 0.064.',
  'Спутники Sentinel-2 и Landsat снимают поле раз в несколько дней, а облака скрывают до 70% снимков.',
  'Периоды угнетения определяются по сглаженному ряду NDVI против 15-летней климатической нормы.',
  'Метеоданные ERA5 включают осадки и температуру за 30 дней, сопоставленные с климатической нормой региона.',
];

export const JobProgressView: React.FC<JobProgressViewProps> = ({
  jobId,
  expectedSeconds,
  statusData,
  error,
  isLost,
  onCancel,
  onRetry,
  onChangeArea,
}) => {
  const [elapsed, setElapsed] = useState(0);
  const [factIndex, setFactIndex] = useState(0);

  // Счётчик прошедших секунд
  useEffect(() => {
    const timer = setInterval(() => {
      setElapsed((prev) => prev + 1);
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  // Меняем поясняющие факты раз в 10 секунд, чтобы ожидание не было пустым
  useEffect(() => {
    const timer = setInterval(() => {
      setFactIndex((prev) => (prev + 1) % FACTS.length);
    }, 10000);
    return () => clearInterval(timer);
  }, []);

  const rawProgress = statusData?.progress ?? 0;
  const stage = statusData?.stage ?? 'подготовка задачи';
  const fetchStats: FetchStats | undefined = statusData?.fetch;

  // Сглаженный прогресс: за опору берём значение бэкенда,
  // но подтягиваем его по времени — иначе полоса подолгу стоит на 10%
  const timeProgress = Math.min(0.95, elapsed / Math.max(1, expectedSeconds));
  const displayProgress = Math.max(rawProgress, timeProgress);
  const pct = Math.round(displayProgress * 100);

  const remainingSeconds = Math.max(0, expectedSeconds - elapsed);

  // Состояние двух стадий: выгрузка и расчёт
  const isStage1Done = rawProgress >= 0.6 || !!fetchStats;
  const isStage2Running = isStage1Done && rawProgress < 1.0;

  // 1. Ошибка 404: задача потеряна (истёк час хранения или сервис перезапускался)
  if (isLost) {
    return (
      <div className="bg-white/[0.03] rounded-2xl border border-amber-500/30 p-6 shadow-sm text-center space-y-4 text-white">
        <div className="w-14 h-14 bg-amber-500/15 text-amber-400 border border-amber-500/30 rounded-full flex items-center justify-center mx-auto">
          <AlertTriangle className="w-7 h-7" />
        </div>
        <div className="space-y-1">
          <h3 className="text-base font-bold text-white">Задача анализа не найдена</h3>
          <p className="text-xs text-white/70">
            Истёк 1 час хранения результатов в памяти сервера или сервис был перезапущен.
          </p>
        </div>
        <div className="flex justify-center gap-3 pt-2">
          <button
            type="button"
            onClick={onRetry}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white font-semibold text-xs rounded-xl shadow-lg shadow-blue-600/30 hover:bg-blue-500 transition-colors"
          >
            <RefreshCw className="w-4 h-4" />
            <span>Повторить анализ области</span>
          </button>
          <button
            type="button"
            onClick={onChangeArea}
            className="px-4 py-2 bg-white/10 text-white font-semibold text-xs rounded-xl border border-white/15 hover:bg-white/20 transition-colors"
          >
            Изменить область
          </button>
        </div>
      </div>
    );
  }

  // 2. Ошибка выполнения на стороне бэкенда
  if (error || statusData?.status === 'error') {
    const errorText = error || statusData?.error || 'Произошла неизвестная ошибка при обработке';
    return (
      <div className="bg-white/[0.03] rounded-2xl border border-rose-500/30 p-6 shadow-sm text-center space-y-4 text-white">
        <div className="w-14 h-14 bg-rose-500/15 text-rose-400 border border-rose-500/30 rounded-full flex items-center justify-center mx-auto">
          <XCircle className="w-7 h-7" />
        </div>
        <div className="space-y-2">
          <h3 className="text-base font-bold text-white">Ошибка выполнения анализа</h3>
          <p className="text-xs text-rose-200 bg-rose-500/15 p-3 rounded-lg border border-rose-500/30 leading-relaxed text-left font-mono">
            {errorText}
          </p>
        </div>
        <div className="flex justify-center gap-3 pt-2">
          <button
            type="button"
            onClick={onChangeArea}
            className="px-4 py-2 bg-blue-600 text-white font-semibold text-xs rounded-xl shadow-lg shadow-blue-600/30 hover:bg-blue-500 transition-colors"
          >
            Изменить область на карте
          </button>
        </div>
      </div>
    );
  }

  // 3. Обычный ход выполнения (§8.2)
  return (
    <div className="bg-white/[0.03] rounded-2xl border border-white/10 p-5 shadow-sm space-y-5 text-white">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-white/10 pb-3">
        <div>
          <h3 className="text-sm font-bold text-white flex items-center gap-2">
            <Loader2 className="w-4 h-4 text-blue-400 animate-spin" />
            <span>Выполняется спутниковый NDVI-анализ поля</span>
          </h3>
          <p className="text-[11px] text-white/60 mt-0.5">
            ID задачи: <span className="font-mono text-white/80">{jobId.slice(0, 12)}...</span>
          </p>
        </div>

        <button
          type="button"
          onClick={onCancel}
          className="text-xs text-white/70 hover:text-white bg-white/10 hover:bg-white/20 px-3 py-1.5 rounded-lg border border-white/15 transition-colors"
        >
          Отменить
        </button>
      </div>

      {/* Checklist of 2 Named Stages (§8.2) */}
      <div className="space-y-3 bg-white/[0.04] p-3.5 rounded-xl border border-white/10">
        <div className="text-xs font-bold text-white/80 uppercase tracking-wider">
          Стадии выполнения
        </div>

        {/* Stage 1 */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5 text-xs">
            {isStage1Done ? (
              <CheckCircle2 className="w-4 h-4 text-blue-400" />
            ) : (
              <Loader2 className="w-4 h-4 text-blue-400 animate-spin" />
            )}
            <span className={`font-semibold ${isStage1Done ? 'text-white' : 'text-blue-300'}`}>
              1. Тянем спутниковые снимки и погоду из Earth Engine
            </span>
          </div>
          <span className="text-[11px] text-white/50 font-medium">
            {isStage1Done ? 'готово' : '~40–60 с'}
          </span>
        </div>

        {/* Stage 2 */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5 text-xs">
            {isStage2Running ? (
              <Loader2 className="w-4 h-4 text-blue-400 animate-spin" />
            ) : isStage1Done ? (
              <Clock className="w-4 h-4 text-white/40" />
            ) : (
              <div className="w-4 h-4 rounded-full border border-white/30" />
            )}
            <span
              className={`font-semibold ${
                isStage2Running ? 'text-blue-300' : isStage1Done ? 'text-white/80' : 'text-white/40'
              }`}
            >
              2. Считаем 106 признаков, восстанавливаем ряд и ищем аномалии
            </span>
          </div>
          <span className="text-[11px] text-white/50 font-medium">
            {isStage2Running ? 'в процессе' : '~2 с'}
          </span>
        </div>
      </div>

      {/* Progress Bar and Timers */}
      <div className="space-y-2">
        <div className="flex justify-between items-center text-xs">
          <span className="font-semibold text-white/80 capitalize">{stage}</span>
          <span className="font-mono font-bold text-blue-400">{pct}%</span>
        </div>

        <div className="w-full bg-white/10 h-2.5 rounded-full overflow-hidden p-0.5 border border-white/15">
          <div
            className="bg-gradient-to-r from-blue-600 to-blue-400 h-full rounded-full transition-all duration-300 shadow-sm"
            style={{ width: `${pct}%` }}
          />
        </div>

        <div className="flex justify-between text-[11px] text-white/50 pt-0.5">
          <span>Прошло времени: <b className="text-white">{elapsed} с</b></span>
          <span>Осталось примерно: <b className="text-white">{remainingSeconds > 0 ? `${remainingSeconds} с` : 'завершение...'}</b></span>
        </div>
      </div>

      {/* Instant Fetch Stats Widget (shown as soon as fetch arrives!) */}
      {fetchStats && (
        <div className="bg-white/[0.04] border border-white/10 rounded-xl p-3.5 space-y-3">
          <div className="flex items-center gap-1.5 text-xs font-bold text-white">
            <Satellite className="w-4 h-4 text-blue-400" />
            <span>Спутниковые данные получены:</span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
            <div className="bg-white/[0.04] p-2 rounded-lg border border-white/10">
              <div className="text-[11px] text-white/50">Всего суток</div>
              <div className="font-bold text-white text-sm mt-0.5 font-mono">
                {formatInteger(fetchStats.days)}
              </div>
            </div>

            <div className="bg-white/[0.04] p-2 rounded-lg border border-white/10">
              <div className="text-[11px] text-white/50">Снимков без облаков</div>
              <div className="font-bold text-white text-sm mt-0.5 font-mono">
                {formatInteger(fetchStats.observed)}
              </div>
            </div>

            <div className="bg-white/[0.04] p-2 rounded-lg border border-white/10">
              <div className="text-[11px] text-white/50">Покрытие ряда</div>
              <div className="font-bold text-blue-400 text-sm mt-0.5 font-mono">
                {formatPercent(fetchStats['coverage_%'])}
              </div>
            </div>

            <div className="bg-white/[0.04] p-2 rounded-lg border border-white/10">
              <div className="text-[11px] text-white/50">Погода (ERA5)</div>
              <div className="font-bold text-white text-sm mt-0.5 font-mono">
                {formatPercent(fetchStats['weather_filled_%'])}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-4 text-[11px] text-white/60 pt-1">
            <span>Сенсоры:</span>
            <span>Sentinel-2: <b className="text-white">{fetchStats.by_sensor.S2}</b></span>
            <span>Landsat: <b className="text-white">{fetchStats.by_sensor.Landsat}</b></span>
            <span>MODIS: <b className="text-white">{fetchStats.by_sensor.MODIS}</b></span>
          </div>
        </div>
      )}

      {/* Facts Card during waiting */}
      <div className="bg-white/[0.03] border border-white/10 rounded-xl p-3 flex items-start gap-2.5 text-xs text-white/70">
        <AlertCircle className="w-4 h-4 text-blue-400 shrink-0 mt-0.5" />
        <div>
          <div className="font-bold text-white text-[11px] uppercase tracking-wider mb-0.5">
            Пока идет расчет:
          </div>
          <div className="italic leading-relaxed">{FACTS[factIndex]}</div>
        </div>
      </div>

      <div className="text-[11px] text-white/40 text-center">
        Кнопка «Отменить» останавливает ожидание в браузере; вычисление на сервере не прерывается.
      </div>
    </div>
  );
};
