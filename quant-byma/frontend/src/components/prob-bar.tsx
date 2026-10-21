import { cn } from "@/lib/utils";

/** Probabilidad con marca de la tasa base del universo. */
export function ProbBar({ p, base, className }: { p: number | null; base?: number | null; className?: string }) {
  if (p === null || p === undefined) return <span className="text-muted-foreground">—</span>;
  const tone = base === null || base === undefined ? "bg-primary" : p >= base + 0.04 ? "bg-positive" : p <= base - 0.04 ? "bg-negative" : "bg-warning";
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <div className="relative h-1.5 w-16 rounded-full bg-muted" role="meter" aria-valuenow={Math.round(p * 100)} aria-valuemin={0} aria-valuemax={100}>
        <div className={cn("h-full rounded-full", tone)} style={{ width: `${p * 100}%` }} />
        {base !== null && base !== undefined && (
          <div className="absolute -top-0.5 h-2.5 w-px bg-foreground/70" style={{ left: `${base * 100}%` }} title={`Tasa base ${(base * 100).toFixed(0)}%`} />
        )}
      </div>
      <span className="tabular w-9 text-right font-medium">{(p * 100).toFixed(0)}%</span>
    </div>
  );
}
