import { Badge, type BadgeProps } from "@/components/ui/badge";
import type { Bias } from "@/lib/api";
import { STAGE_SHORT } from "@/lib/format";

const STAGE_VARIANT: Record<number, BadgeProps["variant"]> = {
  1: "secondary",
  2: "positive",
  3: "warning",
  4: "negative",
};

export function StageBadge({ stage, substate }: { stage: number | null; substate?: string | null }) {
  if (stage === null) return <span className="text-muted-foreground">—</span>;
  return (
    <div className="flex flex-col items-start gap-0.5">
      <Badge variant={STAGE_VARIANT[stage]}>
        {stage} · {STAGE_SHORT[stage]}
      </Badge>
      {substate && <span className="text-[11px] text-muted-foreground">{substate}</span>}
    </div>
  );
}

const BIAS_VARIANT: Record<Bias, BadgeProps["variant"]> = {
  Favorable: "positive",
  Neutral: "secondary",
  Desfavorable: "negative",
  "Sin datos": "outline",
};

export function BiasBadge({ bias, significant }: { bias: Bias | null; significant?: boolean | null }) {
  if (!bias) return <span className="text-muted-foreground">—</span>;
  return (
    <Badge
      variant={BIAS_VARIANT[bias]}
      title={
        significant
          ? "La frecuencia histórica de situaciones similares difiere de la tasa base (IC95)"
          : "No se distingue estadísticamente de la tasa base"
      }
    >
      {bias}
      {significant ? " ✓" : ""}
    </Badge>
  );
}
