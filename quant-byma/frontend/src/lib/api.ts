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
  [key: string]: unknown;
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
