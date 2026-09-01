import type { Fundamentals, HistoricalPoint, Quote, SearchResult } from "../../types/domain.js";

/**
 * Contrato comun para cualquier fuente de datos de mercado.
 * Permite enchufar nuevos proveedores (ej. una API paga) sin tocar rutas ni el resto de los servicios.
 */
export interface QuoteProvider {
  readonly market: "us" | "ar";
  getQuote(symbol: string): Promise<Quote>;
  getFundamentals(symbol: string): Promise<Fundamentals>;
  getHistory(symbol: string, days: number): Promise<HistoricalPoint[]>;
  search(query: string): Promise<SearchResult[]>;
}

export class ProviderError extends Error {
  constructor(
    message: string,
    public readonly status = 502
  ) {
    super(message);
    this.name = "ProviderError";
  }
}
