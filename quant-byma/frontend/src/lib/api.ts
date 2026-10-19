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
  calibration?: { pred: number; observed: number; n: number }[];
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
};
