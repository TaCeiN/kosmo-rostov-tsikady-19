/**
 * Типы предметной области NDVI-анализа.
 * Покрывают и формат API, и формат статических данных из data/ — оба описаны в API.md.
 */

export interface RegionBox {
  min_lon: number;
  min_lat: number;
  max_lon: number;
  max_lat: number;
}

export interface MetaResponse {
  region_box: RegionBox;
  crop_types: string[];
  years: {
    min: number;
    max: number;
    default: [number, number];
    min_span: number;
  };
  max_area_ha: number;
  gee_available: boolean;
  gee_project?: string;
  typical_fetch_seconds: number;
  /** Задан ли на бэкенде ключ Gemini. Без него ИИ-панель не показываем. */
  ai_available?: boolean;
  ai_model?: string;
}

export interface HealthResponse {
  status: string;
  features: number;
  config: {
    target: string;
    clip: [number, number];
    rounds: number;
    seed: number;
    n_features: number;
  };
}

export interface AnalyzeRequest {
  geometry: GeoJSON.Geometry | GeoJSON.Feature;
  years: number[];
  crop_type?: string;
}

export interface AnalyzeJobCreatedResponse {
  job_id: string;
  status: 'queued';
  area_ha: number;
  years: number[];
  poll: string;
  expected_seconds: number;
}

export interface SensorBreakdown {
  S2: number;
  Landsat: number;
  MODIS: number;
}

export interface FetchStats {
  days: number;
  observed: number;
  'coverage_%': number;
  years: number[];
  by_sensor: SensorBreakdown;
  'weather_filled_%': number;
}

export interface AnalysisSummary {
  rows: number;
  reconstructed: number;
  observed: number;
  anomaly_periods: number;
  worst_z: number | null;
}

export interface ApiSeriesRow {
  anon_polygon_id: string;
  date: string;
  year: number;
  doy: number;
  crop_type: string;
  ndvi_obs: number | null;
  ndvi_filled: number;
  ndvi_smooth: number;
  clim_mean: number | null;
  clim_std: number | null;
  z: number | null;
  status_pred: string;
  precip_30d: number | null;
  temp_30d: number | null;
  precip_30d_norm?: number | null;
  temp_30d_norm?: number | null;
  temp_anom?: number | null;
}

export interface AnomalyRecord {
  anon_polygon_id: string;
  year: number;
  start: string;
  end: string;
  days: number;
  z_min: number;
  z_mean: number;
  ndvi_mean: number;
  clim_mean: number;
  drop_vs_norm: number;
  severity: string; // "Угнетение биомассы" | "Критическая аномалия"
  crop_type: string;
  precip_30d: number | null;
  precip_30d_norm: number | null;
  temp_anom: number | null;
  precip_ratio: number | null;
  cause: string;
  comment: string;
}

export interface AnalysisResult {
  series: ApiSeriesRow[];
  anomalies: AnomalyRecord[];
  summary: AnalysisSummary;
  fetch?: FetchStats;
  area_ha?: number;
}

/**
 * Выжимка по полю для ИИ-разбора. Суточный ряд туда не влезет и не нужен:
 * модель рассуждает по сезонным агрегатам и списку аномалий.
 */
export interface FieldDigest {
  name: string;
  area_ha?: number | null;
  crop_type: string;
  years: number[];
  outside_region?: boolean;
  observed_pct?: number | null;
  reconstructed?: number | null;
  seasons: Array<{
    year: number;
    ndvi_mean?: number | null;
    ndvi_peak?: number | null;
    peak_date?: string | null;
    days_below_norm?: number | null;
    precip_mean_30d?: number | null;
    temp_mean_30d?: number | null;
  }>;
  anomalies: Array<{
    start: string;
    end: string;
    days?: number | null;
    z_min?: number | null;
    drop_pct?: number | null;
    cause?: string | null;
    status?: string | null;
  }>;
}

export interface AiTextResponse {
  text: string;
  model: string;
}

export interface AnalyzeJobStatusResponse {
  status: 'queued' | 'running' | 'done' | 'error';
  stage?: string;
  progress?: number;
  created?: number;
  area_ha?: number;
  years?: number[];
  fetch?: FetchStats;
  result?: AnalysisResult;
  error?: string;
  traceback?: string;
}

export interface PredictRequest {
  rows: Array<Record<string, unknown>>;
  with_anomalies: boolean;
}

// Типы статических данных из data/ (демо-режим без бэкенда)
export interface StaticPolygonSummary {
  id: string;
  crop_type: string;
  years: [number, number]; // [min, max]
  n_days: number;
  n_observed: number;
  n_reconstructed: number;
  n_control_points: number;
  n_anomalies: number;
}

export interface StaticMeta {
  generated_from: string;
  polygons: StaticPolygonSummary[];
  crop_types: string[];
  totals: {
    polygons: number;
    days: number;
    observed: number;
    reconstructed: number;
    anomalies: number;
  };
  status_values: string[];
  severity_values: string[];
  causes: string[];
}

export interface StaticSeries {
  id: string;
  crop_type: string;
  years: number[]; // full list [2010, 2011, ...]
  date: string[];
  ndvi_obs: (number | null)[];
  ndvi_filled: (number | null)[];
  ndvi_smooth: (number | null)[];
  clim_mean: (number | null)[];
  clim_std: (number | null)[];
  z: (number | null)[];
  status: (string | null)[];
  is_control_point: boolean[];
  precip_30d: (number | null)[];
  temp_30d: (number | null)[];
}

export interface ModelTruthMetrics {
  n: number;
  RMSE: number;
  MAE?: number;
  MedAE?: number;
  R2: number;
  bias?: number;
  'sMAPE_%'?: number;
  p90_AE?: number;
  max_AE?: number;
  'within_0.05'?: number;
  'within_0.10'?: number;
  GapScore: number;
}

export interface ValidationItem {
  method: string;
  n: number;
  RMSE: number;
  MAE: number;
  MedAE: number;
  R2: number;
  bias: number;
  'sMAPE_%': number;
  p90_AE: number;
  max_AE: number;
  'within_0.05': number;
  'within_0.10': number;
}

export interface GapItem {
  gap_bucket: string;
  lightgbm: number;
  linear: number;
}

export interface AnomalyAgreementItem {
  method: string;
  n?: number;
  'status_accuracy_%': number;
  z_RMSE: number;
  'аномалия_recall_%': number;
}

export interface TruthByGroupItem {
  группа: string;
  n: number;
  RMSE: number;
  MAE: number;
  R2: number;
  bias: number;
  'within_0.05': number;
}

export interface TruthByPhaseItem {
  phase: string;
  n: number;
  RMSE: number;
  MAE: number;
  R2: number;
  bias: number;
  'within_0.05': number;
}

export interface TruthByCropItem {
  crop_type: string;
  n: number;
  RMSE: number;
  MAE: number;
  R2: number;
  bias: number;
  'within_0.05': number;
}

export interface TruthByGapItem {
  gap_bucket: string;
  n: number;
  RMSE: number;
  MAE: number;
  R2: number;
  bias: number;
  'within_0.05': number;
}

export interface StaticMetrics {
  truth: {
    lightgbm: ModelTruthMetrics;
    'линейная интерполяция': ModelTruthMetrics;
  };
  validation: ValidationItem[];
  by_gap_length: GapItem[];
  anomaly_agreement: AnomalyAgreementItem[];
  truth_by_group: TruthByGroupItem[];
  truth_by_phase: TruthByPhaseItem[];
  truth_by_crop: TruthByCropItem[];
  truth_by_gap: TruthByGapItem[];
}
