import { Badge, type BadgeProps } from "@/components/ui/badge";

const VARIANT: Record<string, BadgeProps["variant"]> = {
  "Golden cross": "positive",
  Breakout: "positive",
  "Divergencia alcista RSI": "positive",
  "CCL barato": "positive",
  Sobreventa: "warning",
  "Death cross": "negative",
  "Divergencia bajista RSI": "negative",
  Sobrecompra: "warning",
  "CCL caro": "negative",
  "Ratio sospechoso": "warning",
};

export function SignalBadges({ signals }: { signals: string[] }) {
  if (!signals.length) return <span className="text-muted-foreground">—</span>;
  return (
    <div className="flex flex-wrap gap-1">
      {signals.map((s) => (
        <Badge key={s} variant={VARIANT[s] ?? "secondary"}>
          {s}
        </Badge>
      ))}
    </div>
  );
}
