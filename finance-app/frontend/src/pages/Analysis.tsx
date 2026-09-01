import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getProjection, getQuote } from "../api/client";
import ProjectionChart from "../components/ProjectionChart";
import type { Market, ProjectionResult, Quote } from "../types";
import { formatPercent } from "../utils/format";

export default function Analysis() {
  const params = useParams<{ market: Market; symbol: string }>();
  const market: Market = params.market === "ar" ? "ar" : "us";
  const symbol = (params.symbol ?? "").toUpperCase();

  const [quote, setQuote] = useState<Quote | null>(null);
  const [horizonYears, setHorizonYears] = useState(5);
  const [growthOverride, setGrowthOverride] = useState<string>("");
  const [discountRate, setDiscountRate] = useState<string>("");

  const [projection, setProjection] = useState<ProjectionResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getQuote(market, symbol).then(setQuote).catch(() => setQuote(null));
  }, [market, symbol]);

  async function runProjection(e?: React.FormEvent) {
    e?.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const result = await getProjection({
        market,
        symbol,
        horizonYears,
        annualGrowthRate: growthOverride.trim() ? Number(growthOverride) / 100 : null,
        discountRate: discountRate.trim() ? Number(discountRate) / 100 : null,
      });
      setProjection(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo generar la proyeccion");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    runProjection();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [market, symbol]);

  return (
    <div className="space-y-6">
      <div>
        <Link to={`/${market}/${symbol}`} className="text-sm text-blue-600 hover:underline">
          ← Volver a {symbol}
        </Link>
        <h1 className="text-2xl font-semibold text-slate-900 dark:text-white mt-1">
          Analisis con IA — {symbol}
        </h1>
        {quote && (
          <p className="text-slate-500 text-sm">
            {quote.shortName} · {market === "us" ? "Wall Street" : "Argentina"}
          </p>
        )}
      </div>

      <form
        onSubmit={runProjection}
        className="grid grid-cols-1 sm:grid-cols-4 gap-3 rounded-xl border border-slate-200 dark:border-slate-800 p-4"
      >
        <label className="flex flex-col text-sm gap-1">
          Horizonte (años)
          <input
            type="number"
            min={1}
            max={10}
            value={horizonYears}
            onChange={(e) => setHorizonYears(Number(e.target.value))}
            className="rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-1.5"
          />
        </label>
        <label className="flex flex-col text-sm gap-1">
          Crecimiento anual (%) — opcional
          <input
            type="number"
            step="0.1"
            placeholder="auto (tendencia historica)"
            value={growthOverride}
            onChange={(e) => setGrowthOverride(e.target.value)}
            className="rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-1.5"
          />
        </label>
        <label className="flex flex-col text-sm gap-1">
          Tasa de referencia (%) — opcional
          <input
            type="number"
            step="0.1"
            placeholder="12 (por defecto)"
            value={discountRate}
            onChange={(e) => setDiscountRate(e.target.value)}
            className="rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-1.5"
          />
        </label>
        <button
          type="submit"
          disabled={loading}
          className="self-end rounded-lg bg-blue-600 text-white px-4 py-2 text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? "Calculando..." : "Recalcular proyeccion"}
        </button>
      </form>

      {error && <p className="text-rose-600">{error}</p>}

      {projection && (
        <div className="space-y-6">
          <div className="rounded-xl border border-slate-200 dark:border-slate-800 p-4">
            <div className="flex flex-wrap gap-6 text-sm mb-4">
              <span>
                CAGR historico:{" "}
                <strong>
                  {projection.historicalCagr !== null ? formatPercent(projection.historicalCagr) : "sin datos"}
                </strong>
              </span>
              <span>
                Crecimiento base usado: <strong>{formatPercent(projection.assumptions.annualGrowthRate)}</strong>
              </span>
              <span>
                Tasa de referencia: <strong>{formatPercent(projection.assumptions.discountRate)}</strong>
              </span>
            </div>
            <ProjectionChart projection={projection} currency={quote?.currency ?? "USD"} />
          </div>

          <div className="rounded-xl border border-slate-200 dark:border-slate-800 p-4 space-y-2">
            <h2 className="font-semibold text-slate-900 dark:text-white">Narrativa generada</h2>
            <p className="whitespace-pre-line text-sm text-slate-700 dark:text-slate-300">{projection.narrative}</p>
            <p className="text-xs text-slate-400 border-t border-slate-200 dark:border-slate-800 pt-2 mt-2">
              {projection.disclaimer}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
