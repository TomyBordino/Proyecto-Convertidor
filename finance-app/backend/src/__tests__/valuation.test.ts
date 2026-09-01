import { describe, expect, it } from "vitest";
import type { HistoricalPoint } from "../types/domain.js";
import { buildProjection, estimateHistoricalCagr } from "../services/valuation.js";

function makeHistory(days: number, dailyGrowth: number, startPrice = 100): HistoricalPoint[] {
  const points: HistoricalPoint[] = [];
  let price = startPrice;
  const start = new Date("2023-01-01");
  for (let i = 0; i < days; i++) {
    const date = new Date(start.getTime() + i * 24 * 60 * 60 * 1000);
    points.push({ date: date.toISOString().slice(0, 10), close: price });
    price *= 1 + dailyGrowth;
  }
  return points;
}

describe("estimateHistoricalCagr", () => {
  it("devuelve null si hay muy pocos puntos", () => {
    expect(estimateHistoricalCagr(makeHistory(3, 0.001))).toBeNull();
  });

  it("estima un CAGR positivo cercano al esperado para una tendencia alcista constante", () => {
    // ~0.1%/dia compuesto ~ 44% anual
    const history = makeHistory(250, 0.001);
    const cagr = estimateHistoricalCagr(history);
    expect(cagr).not.toBeNull();
    expect(cagr!).toBeGreaterThan(0.2);
    expect(cagr!).toBeLessThan(0.8);
  });

  it("estima un CAGR negativo para una tendencia bajista", () => {
    const history = makeHistory(250, -0.001);
    const cagr = estimateHistoricalCagr(history);
    expect(cagr).not.toBeNull();
    expect(cagr!).toBeLessThan(0);
  });

  it("acota valores extremos dentro de un rango razonable", () => {
    const history = makeHistory(100, 0.05); // crecimiento diario absurdo
    const cagr = estimateHistoricalCagr(history);
    expect(cagr).not.toBeNull();
    expect(cagr!).toBeLessThanOrEqual(1.5);
  });
});

describe("buildProjection", () => {
  it("genera puntos para los 3 escenarios y el horizonte pedido", async () => {
    const history = makeHistory(250, 0.001);
    const result = await buildProjection({
      market: "us",
      symbol: "TEST",
      currentPrice: 150,
      history,
      horizonYears: 4,
    });

    expect(result.points).toHaveLength(3 * 4);
    expect(result.assumptions.horizonYears).toBe(4);
    expect(new Set(result.points.map((p) => p.scenario))).toEqual(
      new Set(["conservador", "base", "optimista"])
    );
    // el escenario optimista siempre deberia proyectar un precio mayor o igual al conservador
    const opt5 = result.points.find((p) => p.scenario === "optimista" && p.year === 4)!;
    const cons5 = result.points.find((p) => p.scenario === "conservador" && p.year === 4)!;
    expect(opt5.projectedPrice).toBeGreaterThanOrEqual(cons5.projectedPrice);
    expect(result.narrative.length).toBeGreaterThan(0);
  });

  it("respeta un growthOverride explicito por sobre el CAGR historico", async () => {
    const history = makeHistory(250, 0.001);
    const result = await buildProjection({
      market: "ar",
      symbol: "GGAL",
      currentPrice: 1000,
      history,
      horizonYears: 1,
      growthOverride: 0.2,
    });
    expect(result.assumptions.annualGrowthRate).toBeCloseTo(0.2, 5);
  });

  it("clampea el horizonte a un maximo de 10 años", async () => {
    const result = await buildProjection({
      market: "us",
      symbol: "TEST",
      currentPrice: 100,
      history: [],
      horizonYears: 50,
    });
    expect(result.assumptions.horizonYears).toBe(10);
  });
});
