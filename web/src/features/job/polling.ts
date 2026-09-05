import { AnalyzeJobStatusResponse } from '../../types/domain';
import { ApiError } from '../../api/client';

export type JobPollEvent =
  | { type: 'status'; data: AnalyzeJobStatusResponse }
  | { type: 'done'; result: NonNullable<AnalyzeJobStatusResponse['result']> }
  | { type: 'error'; message: string }
  | { type: 'lost'; message: string };

export interface PollJobOptions {
  jobId: string;
  fetchStatus: (jobId: string, signal?: AbortSignal) => Promise<AnalyzeJobStatusResponse>;
  intervalMs?: number;
  maxAttempts?: number;
  onEvent: (event: JobPollEvent) => void;
  signal?: AbortSignal;
}

/**
 * Опрашивает статус задачи с интервалом intervalMs до перехода в done/error или 404.
 */
export async function pollJob({
  jobId,
  fetchStatus,
  intervalMs = 2500,
  maxAttempts = 120, // 5 минут при 2.5с
  onEvent,
  signal,
}: PollJobOptions): Promise<void> {
  let attempts = 0;

  while (!signal?.aborted && attempts < maxAttempts) {
    attempts++;
    try {
      const status = await fetchStatus(jobId, signal);
      onEvent({ type: 'status', data: status });

      if (status.status === 'done' && status.result) {
        onEvent({ type: 'done', result: status.result });
        return;
      }

      if (status.status === 'error') {
        onEvent({
          type: 'error',
          message: status.error || 'Произошла ошибка при выполнении анализа',
        });
        return;
      }
    } catch (err: unknown) {
      if (signal?.aborted) {
        return;
      }
      if (err instanceof ApiError && err.status === 404) {
        onEvent({
          type: 'lost',
          message: 'Задача не найдена: истёк срок хранения (1 час) или сервис перезапускался',
        });
        return;
      }
      // Обычная сетевая ошибка на одном из тиков — пробуем следующий тик, но если 404 - сразу выход
      onEvent({
        type: 'error',
        message: err instanceof Error ? err.message : 'Сетевая ошибка при проверке задачи',
      });
      return;
    }

    // Задержка перед следующим опросом
    await new Promise<void>((resolve) => {
      const timeout = setTimeout(resolve, intervalMs);
      signal?.addEventListener(
        'abort',
        () => {
          clearTimeout(timeout);
          resolve();
        },
        { once: true }
      );
    });
  }

  if (attempts >= maxAttempts && !signal?.aborted) {
    onEvent({
      type: 'error',
      message: 'Время ожидания ответа сервиса истекло. Попробуйте позже.',
    });
  }
}
