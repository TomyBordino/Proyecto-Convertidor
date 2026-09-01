import type {
  HistoricalPoint,
  Market,
  ProjectionResult,
  Quote,
  Ratios,
  RatioMetadata,
  SearchResult,
} from "../types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:4000";

class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "content-type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ error: res.statusText }));
    throw new ApiError(body.error ?? `Error ${res.status}`, res.status);
  }
  return res.json() as Promise<T>;
}

export { ApiError };

export function getQuote(market: Market, symbol: string): Promise<Quote> {
  return request(`/api/quotes/${market}/${encodeURIComponent(symbol)}`);
}

export async function getHistory(
  market: Market,
  symbol: string,
  days = 365
): Promise<HistoricalPoint[]> {
  const data = await request<{ history: HistoricalPoint[] }>(
    `/api/quotes/${market}/${encodeURIComponent(symbol)}/history?days=${days}`
  );
  return data.history;
}

export function getRatios(market: Market, symbol: string): Promise<Ratios> {
  return request(`/api/ratios/${market}/${encodeURIComponent(symbol)}`);
}

export async function getRatioMetadata(): Promise<RatioMetadata[]> {
  const data = await request<{ metadata: RatioMetadata[] }>("/api/ratios/metadata");
  return data.metadata;
}

export async function searchSymbols(market: Market, query: string): Promise<SearchResult[]> {
  const data = await request<{ results: SearchResult[] }>(
    `/api/quotes/search?market=${market}&q=${encodeURIComponent(query)}`
  );
  return data.results;
}

export async function getDefaultWatchlist(market: Market): Promise<string[]> {
  const data = await request<{ symbols: string[] }>(`/api/quotes/default-watchlist?market=${market}`);
  return data.symbols;
}

export function getProjection(input: {
  market: Market;
  symbol: string;
  horizonYears: number;
  annualGrowthRate?: number | null;
  discountRate?: number | null;
}): Promise<ProjectionResult> {
  return request("/api/ai/projection", {
    method: "POST",
    body: JSON.stringify(input),
  });
}
