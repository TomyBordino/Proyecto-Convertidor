import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getRatioMetadata, getRatios } from "../api/client";
import RatiosTable from "../components/RatiosTable";
import type { Market, RatioMetadata, Ratios } from "../types";
import { formatCurrency, formatPercent } from "../utils/format";

export default function StockDetail() {
  const params = useParams<{ market: Market; symbol: string }>();
  const market: Market = params.market === "ar" ? "ar" : "us";
  const symbol = (params.symbol ?? "").toUpperCase();

  const [ratios, setRatios] = useState<Ratios | null>(null);
  const [metadata, setMetadata] = useState<RatioMetadata[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setRatios(null);

    Promise.all([getRatios(market, symbol), getRatioMetadata()])
      .then(([r, m]) => {
        if (cancelled) return;
        setRatios(r);
        setMetadata(m);
      })
      .catch((err) => !cancelled && setError(err.message ?? "No se pudo cargar la informacion"))
      .finally(() => !cancelled && setLoading(false));

    return () => {
      cancelled = true;
    };
  }, [market, symbol]);

  if (loading) return <p className="text-slate-500">Cargando {symbol}...</p>;
  if (error || !ratios) return <p className="text-rose-600">{error ?? "Sin datos disponibles."}</p>;

  const { quote } = ratios;
  const isUp = (quote.changePercent ?? 0) >= 0;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900 dark:text-white">
            {quote.symbol} <span className="text-slate-400 font-normal text-lg">{quote.shortName}</span>
          </h1>
          <div className="mt-1 flex items-baseline gap-3">
            <span className="text-3xl font-bold text-slate-900 dark:text-white">
              {formatCurrency(quote.price, quote.currency)}
            </span>
            <span className={`text-sm font-medium ${isUp ? "text-emerald-600" : "text-rose-600"}`}>
              {quote.changePercent !== null ? formatPercent(quote.changePercent / 100) : "N/D"}
            </span>
          </div>
        </div>

        <Link
          to={`/${market}/${symbol}/analisis`}
          className="rounded-lg bg-blue-600 text-white px-4 py-2 text-sm font-medium hover:bg-blue-700 transition-colors"
        >
          Ver analisis con IA →
        </Link>
      </div>

      <section>
        <h2 className="text-lg font-semibold mb-3 text-slate-900 dark:text-white">Ratios financieros</h2>
        <RatiosTable fundamentals={ratios} metadata={metadata} currency={quote.currency} />
      </section>
    </div>
  );
}
