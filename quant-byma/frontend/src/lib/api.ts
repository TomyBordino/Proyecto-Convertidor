export type Kind = "CEDEAR" | "LOCAL";

export interface RankingItem {
  rank: number;
  ticker: string;
  name: string;
  kind: Kind;
  sector: string;
  price_ars: number;
  price_usd: number;
  implied_ccl: number | null;
  ccl_dev_pct: number | null;
  rsi14: number | null;
  pe: number | null;
  ev_ebitda: number | null;
  composite_score: number;
  technical_score: number | null;
  fundamental_score: number | null;
  ccl_score: number | null;
  signals: string[];
  change_1d_pct?: number | null;
  change_1m_pct?: number | null;
  roe?: number | null;
  stage: number | null;
  stage_name: string | null;
  substate: string | null;
  bias: Bias | null;
  bias_significant: boolean | null;
  prob_up_20: number | null;
  prob_up_60: number | null;
  prob_up_120: number | null;
  base_rate_60: number | null;
  valuation_state: string | null;
  avg_volume_ars: number | null;
  score_pct: number | null;
  prob_outperform_20: number | null;
  prob_outperform_60: number | null;
  prob_outperform_120: number | null;
  range_low_60?: number | null;
  range_mid_60?: number | null;
  range_high_60?: number | null;
  news_score: number | null;
  news_label: NewsLabel | null;
  events_favorable: number;
  events_unfavorable: number;
  [key: string]: unknown;
}

export type Bias = "Favorable" | "Neutral" | "Desfavorable" | "Sin datos";

export interface Driver {
  feature: string;
  label: string;
  value: number | null;
  impact: number;
}

export interface Prediction {
  horizon: number;
  probability: number;
  score: number;
  has_skill: boolean;
  decile: number | null;
  decile_hit_rate: number | null;
  decile_median_return: number | null;
  base_rate: number | null;
  similar: {
    hit_rate: number | null;
    ci_low: number;
    ci_high: number;
    n: number;
    n_effective: number;
    median_return: number | null;
    p25_return: number | null;
    p75_return: number | null;
  };
  drivers_up: Driver[];
  drivers_down: Driver[];
}

export interface PriceRange {
  horizon: number;
  returns: { p10: number; p25: number; p50: number; p75: number; p90: number };
  vol: number;
  decile: number | null;
  conditional: boolean;
  coverage_80: number | null;
  coverage_50: number | null;
}

export interface RangeReport {
  horizon: number;
  status: string;
  conditional?: boolean;
  coverage_80?: number;
  coverage_50?: number;
  below_80?: number;
  oos_samples?: number;
  pinball_universe?: number;
  pinball_decile?: number;
  years_80_within_10pp?: number;
  by_year?: { year: number; cov80: number; n: number }[];
  example_vol30?: number[];
}

export interface StageStat {
  stage: number;
  hit_rate: number;
  ci_low: number;
  ci_high: number;
  n: number;
  n_effective: number;
  median_return: number;
  p25_return: number;
  p75_return: number;
}

export interface FundamentalState {
  compared_to: "sector" | "universo";
  valuation_pct: number | null;
  valuation: string | null;
  quality_pct: number | null;
  quality: string | null;
  growth_pct: number | null;
  growth: string | null;
  leverage_pct: number | null;
  leverage: string | null;
  fcf_pct: number | null;
}

export interface Diagnosis {
  as_of: string;
  stage: number | null;
  stage_name: string | null;
  stage_description: string | null;
  substate: string | null;
  substate_description: string | null;
  stage_since: string | null;
  days_in_stage: number | null;
  stage_evidence: Record<string, StageStat>;
  fundamentals: FundamentalState | null;
  predictions: Record<string, Prediction>;
  relative: Record<string, Prediction>;
  ranges?: Record<string, PriceRange>;
  score: number | null;
  score_pct: number | null;
  bias: Bias;
  bias_significant: boolean;
  summary: string;
}

export interface HorizonReport {
  horizon: number;
  status: string;
  n_samples: number;
  oos_samples?: number;
  oos_effective?: number;
  oos_years?: number[];
  base_rate?: number;
  auc?: number;
  brier?: number;
  brier_base?: number;
  brier_skill?: number;
  top_quintile_hit?: number;
  bottom_quintile_hit?: number;
  top_quintile_median_return?: number;
  bottom_quintile_median_return?: number;
  calibration?: { decile: number; pred: number; observed: number; median_return: number; n: number }[];
  has_skill?: boolean;
  method?: string;
  weights?: { trend: number; value: number; trend_factors: string[]; value_factors: string[] };
  by_year?: { year: number; auc: number; base_rate: number; n: number }[];
  years_auc_above_half?: number;
}

export interface ModelReport {
  as_of: string;
  n_assets: number;
  first_date: string;
  last_date: string;
  horizons: Record<string, HorizonReport>;
  relative: Record<string, HorizonReport>;
  ranges?: Record<string, RangeReport>;
  stage_stats: Record<string, StageStat[]>;
  features: Record<string, string>;
  stages: Record<string, { name: string; description: string }>;
}

export interface RankingsResponse {
  as_of: string | null;
  ccl_market: number | null;
  count: number;
  items: RankingItem[];
}

export interface ScoreComponent {
  key: string;
  label: string;
  max_points: number;
  fraction: number | null;
  points: number | null;
  value: number | null;
  note: string;
}

export interface ScoreGroup {
  group: "technical" | "fundamental" | "ccl";
  score: number | null;
  components: ScoreComponent[];
}

export interface AssetDetail {
  ticker: string;
  name: string;
  kind: Kind;
  sector: string;
  ratio: number | null;
  us_symbol: string | null;
  ba_symbol: string;
  as_of: string | null;
  metrics: RankingItem & Record<string, unknown>;
  breakdown: {
    weights: Record<string, number>;
    groups: ScoreGroup[];
    ccl_market: number;
    diagnosis?: Diagnosis | null;
  };
}

export interface Candle {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface Point {
  time: string;
  value: number;
}

export type Currency = "ARS" | "USD" | "US";

export interface PriceSeries {
  ticker: string;
  currency: Currency;
  candles: Candle[];
  indicators: Record<string, Point[]>;
  implied_ccl: Point[];
  market_ccl: Point[];
}

export interface FundamentalPeriod {
  period_end: string;
  price_usd: number | null;
  revenue: number | null;
  net_income: number | null;
  ebitda: number | null;
  free_cash_flow: number | null;
  pe: number | null;
  ps: number | null;
  pb: number | null;
  ev_ebitda: number | null;
  roe: number | null;
  roic: number | null;
  revenue_growth: number | null;
  fcf_yield: number | null;
  debt_to_equity: number | null;
  current_ratio: number | null;
  altman_z: number | null;
}

export interface FundamentalsResponse {
  ticker: string;
  reporting_currency: string | null;
  currency: "USD";
  periods: FundamentalPeriod[];
}

export interface CCLResponse {
  as_of: string | null;
  market: number | null;
  history: Point[];
  reference: Point[];
  reference_source: string | null;
  reference_deviation_pct: number | null;
  assets: { ticker: string; kind: Kind; implied_ccl: number; deviation_pct: number; ratio_suspect: boolean }[];
}

export type NewsLabel = "Viento a favor" | "Viento en contra" | "Neutral";

export interface MacroEvent {
  key: string;
  name: string;
  category: string;
  description: string;
  state: "activo" | "reciente" | "inactivo";
  since: string | null;
  as_of: string;
  value: number;
  value_label: string;
  threshold_label: string;
  occurrences: number;
  factor: string | null;
}

export interface SectorEventRow {
  sector: string;
  n: number;
  mean_excess: number;
  median_excess: number;
  hit_rate: number;
  ci_low: number;
  ci_high: number;
  significant: boolean;
}

export interface EventStudy {
  n: number;
  dates: string[];
  universe: {
    mean_return: number;
    hit_rate: number;
    ci_low: number;
    ci_high: number;
    base_rate: number | null;
  } | null;
  sectors: SectorEventRow[];
}

export interface MacroSeries {
  key: string;
  label: string;
  unit: "pct" | "pts" | "usd";
  as_of: string;
  value: number;
  change_20: number | null;
  change_60: number | null;
  spark: Point[];
}

export interface NewsImpact {
  target_type: "sector" | "ticker";
  target: string;
  direction: "positivo" | "negativo" | "mixto";
  magnitude: "baja" | "media" | "alta";
  confidence: "baja" | "media" | "alta";
  horizon: "dias" | "semanas" | "meses";
}

export interface NewsRow {
  id: number;
  title: string;
  publisher: string;
  link: string;
  published_at: string;
  related: string[];
  analysis: {
    relevant: boolean;
    event_type: string;
    scope: "macro" | "sector" | "empresa";
    summary: string;
    rationale: string;
    impacts: NewsImpact[];
    model: string;
  } | null;
}

export interface Pressure {
  score: number;
  pos: number;
  neg: number;
  label: NewsLabel;
  sector_score?: number;
}

export interface EventsStatus {
  news_enabled: boolean;
  classifier: boolean;
  model: string | null;
  lookback_days: number;
}

export interface EventsOverview {
  status: EventsStatus;
  as_of: string | null;
  horizon: number | null;
  events: MacroEvent[];
  study: Record<string, EventStudy>;
  sector_sensitivities: Record<string, Record<string, { impact: number; n: number }>>;
  factors: Record<string, { label: string }>;
  macro: MacroSeries[];
  event_labels: Record<string, string>;
  sector_pressure: Record<string, Pressure>;
  ticker_pressure: Record<string, Pressure>;
  news: NewsRow[];
}

export interface Sensitivity {
  beta: number;
  impact: number;
  t: number | null;
  corr: number;
  n_weeks: number;
}

export interface Exposure {
  event: string;
  name: string;
  state: MacroEvent["state"];
  sector_history: SectorEventRow | null;
  reaction: { factor: string; shock: string | null; impact: number; t: number | null; significant: boolean } | null;
  tone: "favorable" | "desfavorable" | null;
}

export interface AssetEvents {
  status: EventsStatus;
  ticker: string;
  sector: string;
  as_of: string | null;
  exposure: Exposure[];
  sensitivities: Record<string, Sensitivity>;
  sector_sensitivities: Record<string, { impact: number; n: number }>;
  factors: Record<string, { label: string }>;
  pressure: Pressure | null;
  sector_pressure: Pressure | null;
  event_labels: Record<string, string>;
  news: NewsRow[];
}

export type Op = "gt" | "gte" | "lt" | "lte" | "eq" | "neq" | "between" | "in";

export interface Condition {
  field: string;
  op: Op;
  value: number | string | boolean | (number | string)[];
}

export interface FilterDefinition {
  conditions: Condition[];
  sort_by: string;
  sort_dir: "asc" | "desc";
  limit: number;
}

export interface SavedFilter {
  id: number;
  name: string;
  definition: FilterDefinition;
  created_at: string | null;
}

export interface FieldInfo {
  key: string;
  label: string;
  type: "num" | "str" | "bool";
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* respuesta sin cuerpo JSON */
    }
    throw new ApiError(res.status, detail);
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

export const fetcher = <T,>(path: string) => request<T>(path);

export const api = {
  runScreener: (def: FilterDefinition) =>
    request<RankingsResponse>("/api/screener/run", { method: "POST", body: JSON.stringify(def) }),
  saveFilter: (name: string, definition: FilterDefinition) =>
    request<SavedFilter>("/api/filters", { method: "POST", body: JSON.stringify({ name, definition }) }),
  deleteFilter: (id: number) => request<void>(`/api/filters/${id}`, { method: "DELETE" }),
  ingest: () => request<Record<string, unknown>>("/api/ingest", { method: "POST" }),
  refreshEvents: () => request<Record<string, unknown>>("/api/events/refresh", { method: "POST" }),
};
