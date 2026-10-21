import { cn } from "@/lib/utils";

function barColor(score: number) {
  if (score >= 65) return "bg-positive";
  if (score >= 45) return "bg-warning";
  return "bg-negative";
}

export function ScoreBar({ score, className }: { score: number | null; className?: string }) {
  if (score === null) return <span className="text-muted-foreground">—</span>;
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <div
        className="h-1.5 w-16 overflow-hidden rounded-full bg-muted"
        role="meter"
        aria-valuenow={score}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div className={cn("h-full rounded-full", barColor(score))} style={{ width: `${score}%` }} />
      </div>
      <span className="tabular w-9 text-right font-medium">{score.toFixed(0)}</span>
    </div>
  );
}
