import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { getDefaultWatchlist, getQuote } from "../api/client";
import QuoteCard from "../components/QuoteCard";
import SearchBar from "../components/SearchBar";
import type { Market, Quote } from "../types";

export default function Dashboard() {
  const params = useParams<{ market: Market }>();
  const market: Market = params.market === "ar" ? "ar" : "us";

  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    getDefaultWatchlist(market)
      .then(async (symbols) => {
        const settled = await Promise.allSettled(symbols.map((s) => getQuote(market, s)));
        if (cancelled) return;
        const ok = settled
          .filter((r): r is PromiseFulfilledResult<Quote> => r.status === "fulfilled")
          .map((r) => r.value);
        setQuotes(ok);
        if (ok.length === 0) setError("No se pudieron cargar las cotizaciones en este momento.");
      })
      .catch(() => !cancelled && setError("No se pudo cargar la watchlist por defecto."))
      .finally(() => !cancelled && setLoading(false));

    return () => {
      cancelled = true;
    };
  }, [market]);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3">
        <h1 className="text-2xl font-semibold text-slate-900 dark:text-white">
          Cotizaciones — {market === "us" ? "Wall Street" : "Argentina"}
        </h1>
        <SearchBar market={market} />
      </div>

      {loading && <p className="text-slate-500">Cargando cotizaciones...</p>}
      {error && !loading && <p className="text-rose-600">{error}</p>}

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
        {quotes.map((q) => (
          <QuoteCard key={q.symbol} quote={q} />
        ))}
      </div>
    </div>
  );
}
