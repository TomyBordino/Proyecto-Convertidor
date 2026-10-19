import { ExternalLink } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { EventsStatus, MacroEvent, NewsImpact, NewsLabel, NewsRow, Pressure } from "@/lib/api";
import { cn } from "@/lib/utils";

export function PressureBadge({ label, score, className }: { label: NewsLabel | null | undefined; score?: number | null; className?: string }) {
  if (!label) return null;
  const variant = label === "Viento a favor" ? "positive" : label === "Viento en contra" ? "negative" : "outline";
  return (
    <Badge
      variant={variant}
      className={className}
      title={`Presión de noticias interpretadas por Claude${score !== undefined && score !== null ? `: ${score.toFixed(1)}` : ""} (dirección × magnitud × confianza, vida media 5 días)`}
    >
      Noticias: {label.toLowerCase()}
    </Badge>
  );
}

export function EventStateBadge({ state }: { state: MacroEvent["state"] }) {
  if (state === "activo") return <Badge variant="warning">Activo</Badge>;
  if (state === "reciente") return <Badge variant="secondary">Reciente</Badge>;
  return <Badge variant="outline">Inactivo</Badge>;
}

const DIR_TONE: Record<NewsImpact["direction"], "positive" | "negative" | "outline"> = {
  positivo: "positive",
  negativo: "negative",
  mixto: "outline",
};
const DIR_ARROW: Record<NewsImpact["direction"], string> = { positivo: "▲", negativo: "▼", mixto: "◆" };

export function ImpactBadges({ impacts }: { impacts: NewsImpact[] }) {
  return (
    <div className="flex flex-wrap gap-1">
      {impacts.map((i, k) => (
        <Badge
          key={k}
          variant={DIR_TONE[i.direction]}
          title={`Magnitud ${i.magnitude} · confianza ${i.confidence} · horizonte ${i.horizon}`}
        >
          {DIR_ARROW[i.direction]} {i.target}
        </Badge>
      ))}
    </div>
  );
}

function ago(iso: string): string {
  const h = (Date.now() - new Date(iso).getTime()) / 3_600_000;
  if (h < 1) return "hace minutos";
  if (h < 24) return `hace ${Math.round(h)} h`;
  return `hace ${Math.round(h / 24)} d`;
}

export function NewsList({
  news,
  labels,
  showIrrelevant = false,
}: {
  news: NewsRow[];
  labels: Record<string, string>;
  showIrrelevant?: boolean;
}) {
  const rows = showIrrelevant ? news : news.filter((n) => !n.analysis || n.analysis.relevant);
  if (!rows.length) return <p className="text-sm text-muted-foreground">Sin titulares en el período.</p>;
  return (
    <ul className="divide-y">
      {rows.map((n) => (
        <li key={n.id} className="space-y-1 py-3">
          <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
            {n.analysis && <Badge variant="secondary">{labels[n.analysis.event_type] ?? n.analysis.event_type}</Badge>}
            {n.analysis && !n.analysis.relevant && <Badge variant="outline">Sin impacto</Badge>}
            <span>{n.publisher}</span>
            <span>· {ago(n.published_at)}</span>
          </div>
          <a
            href={n.link || undefined}
            target="_blank"
            rel="noreferrer"
            className={cn("inline-flex items-start gap-1 text-sm font-medium", n.link && "hover:text-primary")}
          >
            {n.title}
            {n.link && <ExternalLink className="mt-0.5 size-3 shrink-0" />}
          </a>
          {n.analysis?.relevant && (
            <>
              <p className="text-xs text-muted-foreground">{n.analysis.rationale || n.analysis.summary}</p>
              <ImpactBadges impacts={n.analysis.impacts} />
            </>
          )}
        </li>
      ))}
    </ul>
  );
}

export function ClassifierNotice({ status }: { status: EventsStatus }) {
  if (status.classifier) return null;
  return (
    <div className="rounded-md border border-warning/40 bg-warning/10 p-3 text-xs">
      <p className="font-medium text-warning">Titulares sin interpretar</p>
      <p className="mt-1 text-muted-foreground">
        Para que Claude clasifique cada noticia (tipo de evento, sectores y activos afectados, dirección y confianza),
        agregá <code>ANTHROPIC_API_KEY</code> en <code>backend/.env</code> y corré{" "}
        <code>python -m app.scheduler --events</code>. Los eventos macro medidos con series de mercado funcionan sin clave.
      </p>
    </div>
  );
}

export function pressureTone(p: Pressure | null | undefined): string {
  if (!p) return "text-muted-foreground";
  return p.label === "Viento a favor" ? "text-positive" : p.label === "Viento en contra" ? "text-negative" : "";
}
