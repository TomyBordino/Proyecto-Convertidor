import { ScoreBar } from "@/components/score-bar";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { AssetDetail } from "@/lib/api";
import { fmtNumber } from "@/lib/format";

const GROUP_LABEL: Record<string, string> = {
  technical: "Tendencia y momentum técnico",
  fundamental: "Descuento y calidad fundamental",
  ccl: "Descalce de CCL implícito",
};

export function ScoreBreakdown({ detail }: { detail: AssetDetail }) {
  const { breakdown } = detail;
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      {breakdown.groups.map((g) => (
        <Card key={g.group}>
          <CardHeader>
            <CardDescription>
              {GROUP_LABEL[g.group]} · peso efectivo{" "}
              {breakdown.weights[g.group] !== undefined
                ? `${fmtNumber(breakdown.weights[g.group] * 100, 0)}%`
                : "excluido"}
            </CardDescription>
            <CardTitle>
              <ScoreBar score={g.score} className="[&>div]:w-full" />
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2 text-sm">
              {g.components.map((c) => (
                <li key={c.key} className="flex items-start justify-between gap-3">
                  <div>
                    <p className={c.fraction === null ? "text-muted-foreground line-through" : ""}>{c.label}</p>
                    {c.note && <p className="text-xs text-muted-foreground">{c.note}</p>}
                  </div>
                  <div className="tabular shrink-0 text-right">
                    <span className="font-medium">{c.points === null ? "—" : fmtNumber(c.points, 1)}</span>
                    <span className="text-muted-foreground"> / {c.max_points}</span>
                    {c.value !== null && (
                      <p className="text-xs text-muted-foreground">valor {fmtNumber(c.value, 3)}</p>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
