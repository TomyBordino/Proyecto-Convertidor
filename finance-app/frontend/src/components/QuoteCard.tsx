import { Link } from "react-router-dom";
import type { Quote } from "../types";
import { formatCurrency, formatPercent } from "../utils/format";

export default function QuoteCard({ quote }: { quote: Quote }) {
  const isUp = (quote.changePercent ?? 0) >= 0;

  return (
    <Link
      to={`/${quote.market}/${quote.symbol}`}
      className="block rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 hover:shadow-md transition-shadow"
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="font-semibold text-slate-900 dark:text-white">{quote.symbol}</p>
          <p className="text-xs text-slate-500 truncate max-w-[10rem]">{quote.shortName}</p>
        </div>
        <span
          className={`text-xs font-medium px-2 py-0.5 rounded-full ${
            isUp
              ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300"
              : "bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-300"
          }`}
        >
          {quote.changePercent !== null ? formatPercent(quote.changePercent / 100) : "N/D"}
        </span>
      </div>
      <p className="mt-3 text-xl font-semibold text-slate-900 dark:text-white">
        {formatCurrency(quote.price, quote.currency)}
      </p>
    </Link>
  );
}
