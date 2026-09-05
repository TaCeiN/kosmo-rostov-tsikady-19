import {
  AnalyzeJobCreatedResponse,
  AnalyzeJobStatusResponse,
  AnalyzeRequest,
  HealthResponse,
  MetaResponse,
  PredictRequest,
  AnalysisResult,
  AiTextResponse,
  FieldDigest,
} from '../types/domain';

const BASE_URL = (import.meta.env.VITE_API_URL as string | undefined) || 'http://localhost:8000';

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

async function fetchWithTimeout(url: string, options: RequestInit = {}, timeoutMs = 15000): Promise<Response> {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const res = await fetch(url, {
      ...options,
      signal: options.signal ?? controller.signal,
    });
    return res;
  } finally {
    clearTimeout(id);
  }
}

export async function fetchHealth(): Promise<HealthResponse> {
  try {
    const res = await fetchWithTimeout(`${BASE_URL}/health`, {}, 15000);
    if (!res.ok) {
      throw new ApiError(res.status, `Ошибка проверки здоровья бэкенда: HTTP ${res.status}`);
    }
    return (await res.json()) as HealthResponse;
  } catch (err: unknown) {
    if (err instanceof ApiError) throw err;
    const msg = err instanceof Error ? err.message : String(err);
    throw new ApiError(0, `Бэкенд недоступен по адресу ${BASE_URL}: ${msg}`);
  }
}

export async function fetchMeta(): Promise<MetaResponse> {
  try {
    const res = await fetchWithTimeout(`${BASE_URL}/meta`, {}, 15000);
    if (!res.ok) {
      throw new ApiError(res.status, `Ошибка получения метаданных: HTTP ${res.status}`);
    }
    return (await res.json()) as MetaResponse;
  } catch (err: unknown) {
    if (err instanceof ApiError) throw err;
    const msg = err instanceof Error ? err.message : String(err);
    throw new ApiError(0, `Не удалось загрузить параметры сервиса с ${BASE_URL}: ${msg}`);
  }
}

export async function createAnalyzeJob(req: AnalyzeRequest): Promise<AnalyzeJobCreatedResponse> {
  const res = await fetchWithTimeout(`${BASE_URL}/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  }, 15000);

  if (!res.ok) {
    let errorDetail = '';
    try {
      const errJson = await res.json();
      errorDetail = typeof errJson.detail === 'string' ? errJson.detail : JSON.stringify(errJson.detail);
    } catch {
      errorDetail = `HTTP ${res.status}`;
    }
    throw new ApiError(res.status, errorDetail || `Ошибка запуска анализа (HTTP ${res.status})`, errorDetail);
  }

  return (await res.json()) as AnalyzeJobCreatedResponse;
}

export async function getAnalyzeJobStatus(jobId: string, signal?: AbortSignal): Promise<AnalyzeJobStatusResponse> {
  const res = await fetch(`${BASE_URL}/analyze/${jobId}`, { signal });

  if (res.status === 404) {
    throw new ApiError(404, 'Задача не найдена: истёк срок хранения (1 час) или сервис перезапускался');
  }

  if (!res.ok) {
    let errorDetail = '';
    try {
      const errJson = await res.json();
      errorDetail = typeof errJson.detail === 'string' ? errJson.detail : JSON.stringify(errJson.detail);
    } catch {
      errorDetail = `HTTP ${res.status}`;
    }
    throw new ApiError(res.status, errorDetail || `Ошибка опроса статуса (HTTP ${res.status})`);
  }

  return (await res.json()) as AnalyzeJobStatusResponse;
}

export async function postPredict(req: PredictRequest, signal?: AbortSignal): Promise<AnalysisResult> {
  const res = await fetch(`${BASE_URL}/predict`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
    signal,
  });

  if (!res.ok) {
    let errorDetail = '';
    try {
      const errJson = await res.json();
      if (Array.isArray(errJson.detail)) {
        // FastAPI отдаёт ошибки валидации массивом
        errorDetail = errJson.detail.map((e: { loc?: unknown[]; msg?: string }) => `${e.loc?.join('.')}: ${e.msg}`).join(', ');
      } else if (typeof errJson.detail === 'string') {
        errorDetail = errJson.detail;
      } else {
        errorDetail = JSON.stringify(errJson.detail);
      }
    } catch {
      errorDetail = `HTTP ${res.status}`;
    }
    throw new ApiError(res.status, errorDetail || `Ошибка инференса (HTTP ${res.status})`);
  }

  return (await res.json()) as AnalysisResult;
}

export async function configureGeeProject(project: string): Promise<{ status: string; project: string; gee_available: boolean; message: string }> {
  const res = await fetch(`${BASE_URL}/config/gee`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ project }),
  });

  if (!res.ok) {
    let errorDetail = '';
    try {
      const errJson = await res.json();
      errorDetail = typeof errJson.detail === 'string' ? errJson.detail : JSON.stringify(errJson.detail);
    } catch {
      errorDetail = `HTTP ${res.status}`;
    }
    throw new ApiError(res.status, errorDetail || `Ошибка настройки GEE (HTTP ${res.status})`);
  }

  return await res.json();
}

// ------------------------------------------------------------------ ИИ-разбор

/**
 * Общий вызов /ai/*. Генерация занимает десятки секунд, поэтому таймаут
 * заметно больше обычного: оборвать разбор на середине хуже, чем подождать.
 */
async function postAi<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  const res = await fetchWithTimeout(
    `${BASE_URL}${path}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal,
    },
    120000
  );

  if (!res.ok) {
    let errorDetail = '';
    try {
      const errJson = await res.json();
      errorDetail = typeof errJson.detail === 'string' ? errJson.detail : JSON.stringify(errJson.detail);
    } catch {
      errorDetail = `HTTP ${res.status}`;
    }
    throw new ApiError(res.status, errorDetail || `Ошибка ИИ-разбора (HTTP ${res.status})`);
  }

  return (await res.json()) as T;
}

/** Агрономический разбор одного поля. */
export async function postAiReport(field: FieldDigest, signal?: AbortSignal): Promise<AiTextResponse> {
  return postAi<AiTextResponse>('/ai/report', { field }, signal);
}

/** Сравнение двух полей: чем и почему разошлись. */
export async function postAiCompare(
  a: FieldDigest,
  b: FieldDigest,
  signal?: AbortSignal
): Promise<AiTextResponse> {
  return postAi<AiTextResponse>('/ai/compare', { a, b }, signal);
}

/** Свободный вопрос по данным поля (и, если выбрано, второго). */
export async function postAiAsk(
  field: FieldDigest,
  question: string,
  secondField?: FieldDigest | null,
  signal?: AbortSignal
): Promise<AiTextResponse> {
  return postAi<AiTextResponse>(
    '/ai/ask',
    { field, question, second_field: secondField ?? null },
    signal
  );
}
