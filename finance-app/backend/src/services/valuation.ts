import type { HistoricalPoint, Market, ProjectionPoint, ProjectionResult } from "../types/domain.js";
import { getNarrativeProvider } from "./ai/narrativeProvider.js";

const DEFAULT_GROWTH_RATE = 0.08; // usado solo si no hay suficiente historial para estimar un CAGR
const DEFAULT_DISCOUNT_RATE = 0.12; // proxy simple de tasa requerida (no reemplaza un WACC real)
const MIN_POINTS_FOR_TREND = 10;

/**
 * Estima el CAGR historico ajustando una regresion lineal sobre el logaritmo del
 * precio de cierre (equivalente a una regresion log-lineal). Es mas robusto ante
 * ruido dia a dia que comparar solo el primer y ultimo precio.
 */
export function estimateHistoricalCagr(history: HistoricalPoint[]): number | null {
  const points = history.filter((p) => p.close > 0);
  if (points.length < MIN_POINTS_FOR_TREND) return null;

  const xs = points.map((_, i) => i);
  const ys = points.map((p) => Math.log(p.close));
  const n = xs.length;
  const meanX = xs.reduce((a, b) => a + b, 0) / n;
  const meanY = ys.reduce((a, b) => a + b, 0) / n;

  let num = 0;
  let den = 0;
  for (let i = 0; i < n; i++) {
    num += (xs[i] - meanX) * (ys[i] - meanY);
    den += (xs[i] - meanX) ** 2;
  }
  if (den === 0) return null;

  const dailySlope = num / den;
  const cagr = Math.exp(dailySlope * 365) - 1;
  // Acotamos a un rango razonable para que un tramo corto y ruidoso de datos
  // no dispare una proyeccion absurda (+500%/año, -90%/año).
  return Math.max(-0.6, Math.min(1.5, cagr));
}

function clampGrowth(rate: number): number {
  return Math.max(-0.6, Math.min(1.5, rate));
}

export interface ProjectionInput {
  market: Market;
  symbol: string;
  currentPrice: number;
  history: HistoricalPoint[];
  horizonYears: number;
  growthOverride?: number | null;
  discountRateOverride?: number | null;
}

export async function buildProjection(input: ProjectionInput): Promise<ProjectionResult> {
  const horizonYears = Math.min(Math.max(Math.round(input.horizonYears), 1), 10);
  const historicalCagr = estimateHistoricalCagr(input.history);
  const baseGrowth = clampGrowth(input.growthOverride ?? historicalCagr ?? DEFAULT_GROWTH_RATE);
  const discountRate = input.discountRateOverride ?? DEFAULT_DISCOUNT_RATE;

  const scenarios: Array<{ key: ProjectionPoint["scenario"]; growth: number }> = [
    { key: "conservador", growth: clampGrowth(baseGrowth * 0.5) },
    { key: "base", growth: baseGrowth },
    { key: "optimista", growth: clampGrowth(baseGrowth * 1.5) },
  ];

  const points: ProjectionPoint[] = [];
  for (const scenario of scenarios) {
    for (let year = 1; year <= horizonYears; year++) {
      points.push({
        year,
        scenario: scenario.key,
        projectedPrice: input.currentPrice * (1 + scenario.growth) ** year,
      });
    }
  }

  const narrativeProvider = getNarrativeProvider();
  const narrative = await narrativeProvider.generate({
    market: input.market,
    symbol: input.symbol,
    currentPrice: input.currentPrice,
    historicalCagr,
    baseGrowth,
    discountRate,
    horizonYears,
    points,
  });

  return {
    symbol: input.symbol,
    market: input.market,
    generatedAt: new Date().toISOString(),
    currentPrice: input.currentPrice,
    historicalCagr,
    assumptions: { horizonYears, annualGrowthRate: baseGrowth, discountRate },
    points,
    narrative,
    disclaimer:
      "Esta proyeccion es un ejercicio cuantitativo basado en tendencia historica y supuestos declarados. " +
      "No es una recomendacion de inversion ni predice el precio real futuro: los mercados dependen de " +
      "variables que este modelo no captura. Uso educativo/informativo.",
  };
}
