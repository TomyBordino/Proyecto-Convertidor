import Link from "next/link";

import { BiasBadge, StageBadge } from "@/components/stage-badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { Diagnosis, Driver, FundamentalState, Prediction } from "@/lib/api";
import { fmtProb, fmtReturn } from "@/lib/format";
import { cn } from "@/lib/utils";

const HORIZON_LABEL: Record<string, string> = { "20": "1 mes (20 ruedas)", "60": "3 meses (60 ruedas)", "120": "6 meses (120 ruedas)" };

export function DiagnosisPanel({ d }: { d: Diagnosis }) {
  const primary = d.predictions["60"];
  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-lg font-semibold">Diagnóstico</h2>
        <BiasBadge bias={d.bias} significant={d.bias_significant} />
        <span className="text-xs text-muted-foreground">al {d.as_of}</span>
      </div>
      <p className="rounded-lg border bg-card p-4 text-sm leading-relaxed">{d.summary}</p>

      <div className="grid gap-4 lg:grid-cols-2">
        <StageCard d={d} />
        <FundamentalCard f={d.fundamentals} />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        {(["20", "60", "120"] as const).map((h) =>
          d.predictions[h] ? <PredictionCard key={h} h={h} p={d.predictions[h]} primary={h === "60"} /> : null,
        )}
      </div>

      <RelativeCard d={d} />

      {primary && (
        <Card>
          <CardHeader>
            <CardTitle>Qué explica el puntaje{d.score_pct !== null && ` · percentil ${d.score_pct.toFixed(0)} del universo`}</CardTitle>
            <CardDescription>
              Percentil del activo en cada factor frente al resto del universo en la misma fecha. El puntaje combina
              tendencia (50%) y valuación (50%); el aporte es peso × (percentil − 50).
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-6 sm:grid-cols-2">
            <DriverList title="Empujan hacia arriba" drivers={primary.drivers_up} positive />
            <DriverList title="Empujan hacia abajo" drivers={primary.drivers_down} />
          </CardContent>
        </Card>
      )}
      <p className="text-xs text-muted-foreground">
        Las probabilidades son frecuencias históricas medidas fuera de muestra, no garantías. Ver la validación completa en{" "}
        <Link href="/modelo" className="underline">
          Modelo
        </Link>
        .
      </p>
    </section>
  );
}

function RelativeCard({ d }: { d: Diagnosis }) {
  const hs = (["20", "60", "120"] as const).filter((h) => d.relative?.[h]);
  if (!hs.length) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Probabilidad de superar al promedio del universo</CardTitle>
        <CardDescription>
          Frecuencia con que un activo con este puntaje rindió más que la mediana de todo el universo en el mismo
          período, sin importar si el mercado subió o bajó.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4 sm:grid-cols-3">
        {hs.map((h) => {
          const p = d.relative[h];
          return (
            <div key={h}>
              <p className="text-xs text-muted-foreground">{HORIZON_LABEL[h]}</p>
              <p className="tabular text-2xl font-semibold">{fmtProb(p.probability)}</p>
              <p className="text-xs text-muted-foreground">
                {p.has_skill ? `base ${fmtProb(p.base_rate)}` : "tasa base · sin ventaja demostrada fuera de muestra"}
              </p>
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}

function StageCard({ d }: { d: Diagnosis }) {
  const ev = d.stage_evidence["60"];
  return (
    <Card>
      <CardHeader>
        <CardDescription>Momento técnico</CardDescription>
        <CardTitle className="flex items-center gap-2 text-base">
          <StageBadge stage={d.stage} />
          {d.stage_name}
          {d.substate && <span className="text-sm font-normal text-muted-foreground">· {d.substate}</span>}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <p>{d.stage_description}</p>
        {d.substate_description && <p className="text-muted-foreground">{d.substate_description}</p>}
        {d.stage_since && (
          <p className="text-xs text-muted-foreground">
            En esta etapa desde el {d.stage_since} ({d.days_in_stage} ruedas).
          </p>
        )}
        {ev && (
          <div className="rounded-md bg-muted p-3 text-xs">
            Históricamente, los activos del universo en etapa {ev.stage} cotizaron más alto 60 ruedas después el{" "}
            <b>{fmtProb(ev.hit_rate)}</b> de las veces (IC95 {fmtProb(ev.ci_low)}–{fmtProb(ev.ci_high)}, n efectivo{" "}
            {ev.n_effective.toLocaleString("es-AR")}). Retorno mediano {fmtReturn(ev.median_return)}, rango intercuartil{" "}
            {fmtReturn(ev.p25_return)} a {fmtReturn(ev.p75_return)}.
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function PctRow({ label, state, pct }: { label: string; state: string | null; pct: number | null }) {
  return (
    <div className="grid grid-cols-[130px_1fr_70px] items-center gap-3 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <div className="h-1.5 rounded-full bg-muted">
        {pct !== null && <div className="h-full rounded-full bg-primary" style={{ width: `${pct * 100}%` }} />}
      </div>
      <span className="text-right font-medium">{state ?? "—"}</span>
    </div>
  );
}

function FundamentalCard({ f }: { f: FundamentalState | null }) {
  return (
    <Card>
      <CardHeader>
        <CardDescription>Momento fundamental</CardDescription>
        <CardTitle className="text-base">
          {f ? `Valuación ${f.valuation?.toLowerCase() ?? "—"} vs ${f.compared_to === "sector" ? "su sector" : "el universo"}` : "Sin balances"}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {f ? (
          <>
            <PctRow label="Barata (P/E, P/S, P/B)" state={f.valuation} pct={f.valuation_pct} />
            <PctRow label="Calidad (ROE)" state={f.quality} pct={f.quality_pct} />
            <PctRow label="Crecimiento" state={f.growth} pct={f.growth_pct} />
            <PctRow label="Endeudamiento" state={f.leverage} pct={f.leverage_pct === null ? null : 1 - f.leverage_pct} />
            <p className="pt-1 text-xs text-muted-foreground">
              Percentiles contra {f.compared_to === "sector" ? "las empresas de su sector" : "todo el universo"} con el
              último balance publicado y el precio actual.
            </p>
          </>
        ) : (
          <p className="text-sm text-muted-foreground">
            ETF o empresa sin balances disponibles en las fuentes: el diagnóstico se basa solo en precio.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function PredictionCard({ h, p, primary }: { h: string; p: Prediction; primary: boolean }) {
  const s = p.similar;
  const diff = p.base_rate === null ? null : p.probability - p.base_rate;
  return (
    <Card className={cn(primary && "border-primary/50")}>
      <CardHeader>
        <CardDescription>P(cotizar más alto en {HORIZON_LABEL[h]})</CardDescription>
        <CardTitle className="tabular flex items-baseline gap-2 text-3xl">
          {fmtProb(p.probability)}
          {!p.has_skill && <span className="text-sm font-medium text-muted-foreground">tasa base · sin ventaja demostrada</span>}
          {p.has_skill && diff !== null && (
            <span className={cn("text-sm font-medium", diff > 0.04 ? "text-positive" : diff < -0.04 ? "text-negative" : "text-muted-foreground")}>
              {diff >= 0 ? "+" : ""}
              {(diff * 100).toFixed(0)} pp vs base {fmtProb(p.base_rate)}
            </span>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-1.5 text-xs text-muted-foreground">
        {p.decile !== null && (
          <p>
            Puntaje en el <b className="text-foreground">decil {p.decile} de 10</b>: históricamente ese decil subió el{" "}
            {fmtProb(p.decile_hit_rate)} de las veces (retorno mediano {fmtReturn(p.decile_median_return)}).
            {p.decile === 10 && " El decil superior rindió algo menos que los intermedios, sin un patrón estable año a año."}
          </p>
        )}
        {s.hit_rate !== null && (
          <p>
            En {s.n.toLocaleString("es-AR")} situaciones históricas con puntaje similar (n efectivo {s.n_effective}) se cumplió el{" "}
            <b className="text-foreground">{fmtProb(s.hit_rate)}</b> (IC95 {fmtProb(s.ci_low)}–{fmtProb(s.ci_high)}).
          </p>
        )}
        <p>
          Retorno en USD de esas situaciones: mediana <b className="text-foreground">{fmtReturn(s.median_return)}</b>, la mitad
          central entre {fmtReturn(s.p25_return)} y {fmtReturn(s.p75_return)}.
        </p>
      </CardContent>
    </Card>
  );
}

function DriverList({ title, drivers, positive }: { title: string; drivers: Driver[]; positive?: boolean }) {
  const max = Math.max(0.01, ...drivers.map((d) => Math.abs(d.impact)));
  return (
    <div className="space-y-2">
      <p className="text-sm font-medium">{title}</p>
      {drivers.length === 0 && <p className="text-sm text-muted-foreground">Ningún factor relevante.</p>}
      {drivers.map((d) => (
        <div key={d.feature} className="grid grid-cols-[1fr_90px] items-center gap-3 text-sm">
          <div>
            <p>{d.label}</p>
            <p className="text-xs text-muted-foreground">valor {formatFeature(d.feature, d.value)}</p>
          </div>
          <div className="h-1.5 rounded-full bg-muted">
            <div
              className={cn("h-full rounded-full", positive ? "bg-positive" : "bg-negative")}
              style={{ width: `${(Math.abs(d.impact) / max) * 100}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

function formatFeature(_feature: string, v: number | null): string {
  return v === null ? "—" : `percentil ${(v * 100).toFixed(0)}`;
}
