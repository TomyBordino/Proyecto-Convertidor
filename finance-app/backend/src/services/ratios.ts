import type { Fundamentals, Market, Ratios } from "../types/domain.js";
import { getProvider } from "./providers/index.js";

export async function getRatios(market: Market, symbol: string): Promise<Ratios> {
  const provider = getProvider(market);
  const [quote, fundamentals] = await Promise.all([
    provider.getQuote(symbol),
    provider.getFundamentals(symbol),
  ]);
  return { ...fundamentals, quote };
}

export type RatioFormat = "ratio" | "percent" | "currency";

export interface RatioMetadata {
  key: keyof Fundamentals;
  label: string;
  format: RatioFormat;
  description: string;
}

/**
 * Metadata declarativa de cada ratio: la usa el frontend para renderizar la tabla
 * de ratios de forma generica (label + formato) sin duplicar este conocimiento.
 */
export const RATIO_METADATA: RatioMetadata[] = [
  { key: "trailingPE", label: "P/E (trailing)", format: "ratio", description: "Precio sobre ganancias de los ultimos 12 meses." },
  { key: "forwardPE", label: "P/E (forward)", format: "ratio", description: "Precio sobre ganancias estimadas a futuro." },
  { key: "priceToBook", label: "P/B", format: "ratio", description: "Precio sobre valor libro." },
  { key: "priceToSales", label: "P/S", format: "ratio", description: "Precio sobre ventas." },
  { key: "dividendYield", label: "Dividend Yield", format: "percent", description: "Rendimiento por dividendos anual." },
  { key: "epsTrailing", label: "EPS (trailing)", format: "ratio", description: "Ganancia por accion de los ultimos 12 meses." },
  { key: "epsForward", label: "EPS (forward)", format: "ratio", description: "Ganancia por accion estimada a futuro." },
  { key: "returnOnEquity", label: "ROE", format: "percent", description: "Retorno sobre el patrimonio neto." },
  { key: "returnOnAssets", label: "ROA", format: "percent", description: "Retorno sobre los activos totales." },
  { key: "netMargin", label: "Margen neto", format: "percent", description: "Ganancia neta sobre ventas." },
  { key: "operatingMargin", label: "Margen operativo", format: "percent", description: "Resultado operativo sobre ventas." },
  { key: "debtToEquity", label: "Deuda / Patrimonio", format: "ratio", description: "Apalancamiento financiero." },
  { key: "currentRatio", label: "Ratio corriente", format: "ratio", description: "Liquidez de corto plazo." },
  { key: "revenueGrowth", label: "Crecimiento de ingresos", format: "percent", description: "Variacion interanual de ventas." },
  { key: "earningsGrowth", label: "Crecimiento de ganancias", format: "percent", description: "Variacion interanual de ganancias." },
  { key: "beta", label: "Beta", format: "ratio", description: "Volatilidad relativa al mercado." },
  { key: "fiftyTwoWeekHigh", label: "Maximo 52 semanas", format: "currency", description: "Precio maximo del ultimo año." },
  { key: "fiftyTwoWeekLow", label: "Minimo 52 semanas", format: "currency", description: "Precio minimo del ultimo año." },
];
