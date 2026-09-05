import React, { useRef, useState } from 'react';
import { FieldDigest } from '../../types/domain';
import { postAiAsk, postAiCompare, postAiReport } from '../../api/client';
import {
  AlertCircle,
  GitCompare,
  Loader2,
  Send,
  Sparkles,
  StopCircle,
} from 'lucide-react';

interface AiInsightsProps {
  /** Выжимка текущего поля. */
  field: FieldDigest;
  /** Второе поле, если на графике включено сравнение. */
  compareField?: FieldDigest | null;
  /** Модель с бэкенда — показываем, чтобы было видно, кто отвечает. */
  model?: string;
}

type Mode = 'report' | 'compare' | 'ask';

const SUGGESTIONS = [
  'В каком сезоне поле чувствовало себя хуже всего и почему?',
  'Похожи ли просадки на засуху или больше на проблемы агротехники?',
  'Что проверить в поле в ближайший сезон?',
];

/**
 * ИИ-разбор поля поверх готовых чисел.
 *
 * Панель намеренно не хранит историю диалога: каждый запрос уходит с полной
 * выжимкой по полю, поэтому ответы воспроизводимы и не зависят от того, что
 * спрашивали до этого. Для разбора данных так надёжнее, чем чат с памятью.
 */
export const AiInsights: React.FC<AiInsightsProps> = ({ field, compareField, model }) => {
  const [text, setText] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode | null>(null);
  const [loading, setLoading] = useState<Mode | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [question, setQuestion] = useState('');

  const abortRef = useRef<AbortController | null>(null);

  const run = async (next: Mode, task: (signal: AbortSignal) => Promise<{ text: string }>) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(next);
    setMode(next);
    setError(null);
    setText(null);

    try {
      const res = await task(controller.signal);
      setText(res.text);
    } catch (err) {
      if (controller.signal.aborted) return;
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      if (!controller.signal.aborted) setLoading(null);
    }
  };

  const handleReport = () => run('report', (s) => postAiReport(field, s));

  const handleCompare = () => {
    if (!compareField) return;
    run('compare', (s) => postAiCompare(field, compareField, s));
  };

  const handleAsk = (q: string) => {
    const trimmed = q.trim();
    if (trimmed.length < 2) return;
    setQuestion(trimmed);
    run('ask', (s) => postAiAsk(field, trimmed, compareField ?? null, s));
  };

  const handleStop = () => {
    abortRef.current?.abort();
    setLoading(null);
    setMode(null);
  };

  const busy = loading !== null;

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
      <div className="px-4 py-3 border-b border-slate-100 flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <div className="w-7 h-7 rounded-lg bg-blue-600 text-white flex items-center justify-center shrink-0">
            <Sparkles className="w-4 h-4" />
          </div>
          <div className="min-w-0">
            <div className="text-sm font-black text-slate-900">Разбор от ИИ</div>
            <div className="text-[11px] text-slate-500 truncate">
              Читает сезонные агрегаты и аномалии этого поля
              {model ? ` • ${model}` : ''}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2 ml-auto">
          <button
            type="button"
            onClick={handleReport}
            disabled={busy}
            className="flex items-center gap-1.5 text-xs font-bold text-white bg-blue-600 hover:bg-blue-500 disabled:opacity-50 px-3 py-1.5 rounded-lg shadow-sm transition-colors"
          >
            {loading === 'report' ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Sparkles className="w-3.5 h-3.5" />
            )}
            <span>Разобрать поле</span>
          </button>

          <button
            type="button"
            onClick={handleCompare}
            disabled={busy || !compareField}
            className="flex items-center gap-1.5 text-xs font-bold text-blue-700 bg-blue-50 hover:bg-blue-100 disabled:opacity-40 disabled:cursor-not-allowed border border-blue-200 px-3 py-1.5 rounded-lg transition-colors"
            title={
              compareField
                ? `Сравнить с полем «${compareField.name}»`
                : 'Выберите второе поле для сравнения выше'
            }
          >
            {loading === 'compare' ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <GitCompare className="w-3.5 h-3.5" />
            )}
            <span>Сравнить поля</span>
          </button>

          {busy && (
            <button
              type="button"
              onClick={handleStop}
              className="flex items-center gap-1.5 text-xs font-semibold text-slate-600 bg-slate-100 hover:bg-slate-200 px-2.5 py-1.5 rounded-lg transition-colors"
            >
              <StopCircle className="w-3.5 h-3.5" />
              <span>Стоп</span>
            </button>
          )}
        </div>
      </div>

      <div className="p-4 space-y-3">
        {/* Свободный вопрос */}
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !busy) handleAsk(question);
            }}
            placeholder="Спросить про это поле…"
            className="flex-1 min-w-0 text-xs bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          />
          <button
            type="button"
            onClick={() => handleAsk(question)}
            disabled={busy || question.trim().length < 2}
            className="flex items-center gap-1.5 text-xs font-bold text-white bg-slate-800 hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed px-3 py-2 rounded-lg transition-colors shrink-0"
          >
            {loading === 'ask' ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Send className="w-3.5 h-3.5" />
            )}
            <span>Спросить</span>
          </button>
        </div>

        {!text && !busy && !error && (
          <div className="flex flex-wrap gap-1.5">
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => handleAsk(s)}
                className="text-[11px] text-slate-600 bg-slate-50 hover:bg-slate-100 border border-slate-200 px-2.5 py-1 rounded-full transition-colors"
              >
                {s}
              </button>
            ))}
          </div>
        )}

        {busy && (
          <div className="flex items-center gap-2 text-xs text-slate-500 bg-slate-50 border border-slate-200 rounded-lg p-3">
            <Loader2 className="w-4 h-4 animate-spin text-blue-600 shrink-0" />
            <span>
              {loading === 'report' && 'Читаю сезоны и аномалии поля…'}
              {loading === 'compare' && 'Сравниваю два поля…'}
              {loading === 'ask' && 'Ищу ответ в данных поля…'}
            </span>
          </div>
        )}

        {error && (
          <div className="flex items-start gap-2 text-xs text-amber-900 bg-amber-50 border border-amber-300 rounded-lg p-3">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5 text-amber-600" />
            <div>
              <div className="font-bold">Разбор не получился</div>
              <div className="mt-0.5">{error}</div>
            </div>
          </div>
        )}

        {text && !busy && (
          <div className="bg-slate-50 border border-slate-200 rounded-xl p-4">
            <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-2">
              {mode === 'report' && 'Разбор поля'}
              {mode === 'compare' && `Сравнение: ${field.name} и ${compareField?.name ?? ''}`}
              {mode === 'ask' && 'Ответ'}
            </div>
            {/* whitespace-pre-wrap: модель отвечает абзацами, markdown мы у неё
                не просим — рендерить его тут было бы нечем */}
            <div className="text-xs text-slate-800 leading-relaxed whitespace-pre-wrap">
              {text}
            </div>
            <div className="text-[10px] text-slate-400 mt-3 pt-2 border-t border-slate-200">
              Сгенерировано по числам этого поля. Проверяйте выводы перед решениями в поле.
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
