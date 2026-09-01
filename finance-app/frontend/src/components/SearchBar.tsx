import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { searchSymbols } from "../api/client";
import type { Market, SearchResult } from "../types";

export default function SearchBar({ market }: { market: Market }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    const trimmed = query.trim();
    if (trimmed.length < 1) {
      setResults([]);
      return;
    }
    setLoading(true);
    const timeout = setTimeout(() => {
      searchSymbols(market, trimmed)
        .then((res) => setResults(res))
        .catch(() => setResults([]))
        .finally(() => setLoading(false));
    }, 300);
    return () => clearTimeout(timeout);
  }, [query, market]);

  function goTo(symbol: string) {
    setOpen(false);
    setQuery("");
    navigate(`/${market}/${symbol}`);
  }

  return (
    <div className="relative w-full max-w-md">
      <input
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        placeholder={market === "us" ? "Buscar en Wall Street (ej. AAPL)" : "Buscar en Argentina (ej. GGAL)"}
        className="w-full rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-4 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500"
      />
      {open && (loading || results.length > 0) && (
        <ul className="absolute z-20 mt-1 w-full rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 shadow-lg max-h-72 overflow-auto">
          {loading && <li className="px-4 py-2 text-sm text-slate-400">Buscando...</li>}
          {!loading &&
            results.map((r) => (
              <li key={r.symbol}>
                <button
                  type="button"
                  onMouseDown={() => goTo(r.symbol)}
                  className="w-full text-left px-4 py-2 text-sm hover:bg-blue-50 dark:hover:bg-slate-800 flex justify-between gap-2"
                >
                  <span className="font-medium">{r.symbol}</span>
                  <span className="text-slate-500 truncate">{r.name}</span>
                </button>
              </li>
            ))}
        </ul>
      )}
    </div>
  );
}
