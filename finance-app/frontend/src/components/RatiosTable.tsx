import type { Fundamentals, RatioMetadata } from "../types";
import { formatCurrency, formatPercent, formatRatio } from "../utils/format";

function formatValue(format: RatioMetadata["format"], value: number | null, currency: string): string {
  if (format === "percent") return formatPercent(value);
  if (format === "currency") return formatCurrency(value, currency);
  return formatRatio(value);
}

export default function RatiosTable({
  fundamentals,
  metadata,
  currency,
}: {
  fundamentals: Fundamentals;
  metadata: RatioMetadata[];
  currency: string;
}) {
  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 dark:border-slate-800">
      <table className="w-full text-sm">
        <tbody>
          {metadata.map((m, i) => (
            <tr
              key={m.key}
              className={i % 2 === 0 ? "bg-white dark:bg-slate-900" : "bg-slate-50 dark:bg-slate-800/40"}
            >
              <td className="px-4 py-2.5 font-medium text-slate-700 dark:text-slate-200 whitespace-nowrap">
                {m.label}
              </td>
              <td className="px-4 py-2.5 text-slate-500 hidden md:table-cell">{m.description}</td>
              <td className="px-4 py-2.5 text-right font-semibold text-slate-900 dark:text-white whitespace-nowrap">
                {formatValue(m.format, fundamentals[m.key], currency)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
