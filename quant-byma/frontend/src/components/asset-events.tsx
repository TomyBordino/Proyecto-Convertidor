"use client";

import Link from "next/link";
import useSWR from "swr";

import { ClassifierNotice, EventStateBadge, NewsList, PressureBadge } from "@/components/events-shared";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { fetcher, type AssetEvents } from "@/lib/api";
import { fmtNumber, fmtProb, fmtReturn } from "@/lib/format";
import { cn } from "@/lib/utils";

export function AssetEventsPanel({ ticker }: { ticker: string }) {
  const { data } = useSWR<AssetEvents>(`/api/instruments/${ticker}/events`, fetcher);
  if (!data) return null;
  const factors = Object.keys(data.factors);
  const hasSens = Object.keys(data.sensitivities).length > 0;

  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-lg font-semibold">Eventos y noticias</h2>
        <PressureBadge label={data.pressure?.label} score={data.pressure?.score} />
        <Link href="/eventos" className="ml-auto text-xs text-muted-foreground hover:text-foreground">
          Ver todos los eventos →
        </Link>
      </div>
      <p className="max-w-3xl text-xs text-muted-foreground">
        Contexto separado del modelo: no cambia las probabilidades de arriba, que solo usan información validada fuera
        de muestra.
      </p>
      <ClassifierNotice status={data.status} />

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Eventos macro vigentes y cómo le fue antes</CardTitle>
            <CardDescription>
              Historia del sector {data.sector} tras cada ocurrencia y reacción semanal del activo al factor.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {data.exposure.length === 0 && (
              <p className="text-sm text-muted-foreground">No hay eventos macro vigentes.</p>
            )}
            {data.exposure.map((x) => (
              <div key={x.event} className="space-y-1 rounded-md border p-3">
                <div className="flex flex-wrap items-center gap-1.5">
                  <EventStateBadge state={x.state} />
                  <span className="text-sm font-medium">{x.name}</span>
                  {x.tone && (
                    <Badge variant={x.tone === "favorable" ? "positive" : "negative"} className="ml-auto">
                      Históricamente {x.tone}
                    </Badge>
                  )}
                </div>
                {x.sector_history ? (
                  <p className="text-xs text-muted-foreground">
                    En {x.sector_history.n} episodios, {data.sector} rindió{" "}
                    <b className={x.sector_history.mean_excess > 0 ? "text-positive" : "text-negative"}>
                      {fmtReturn(x.sector_history.mean_excess)}
                    </b>{" "}
                    contra el universo y le ganó el {fmtProb(x.sector_history.hit_rate)} de las veces (IC95{" "}
                    {fmtProb(x.sector_history.ci_low)}–{fmtProb(x.sector_history.ci_high)})
                    {x.sector_history.significant ? "." : ", sin diferencia significativa."}
                  </p>
                ) : (
                  <p className="text-xs text-muted-foreground">Sin historia suficiente del sector para este evento.</p>
                )}
                {x.reaction && (
                  <p className="text-xs text-muted-foreground">
                    Ante {x.reaction.shock}, {data.ticker} se movió en promedio{" "}
                    <b className={x.reaction.impact > 0 ? "text-positive" : "text-negative"}>{fmtReturn(x.reaction.impact)}</b>{" "}
                    en la semana (t = {fmtNumber(x.reaction.t, 1)}
                    {x.reaction.significant ? ", significativo" : ", no significativo"}).
                  </p>
                )}
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Sensibilidad a factores macro</CardTitle>
            <CardDescription>Movimiento semanal promedio ante cada shock (últimos 3 años) vs la mediana del sector.</CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            {hasSens ? (
              <Table>
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead>Shock</TableHead>
                    <TableHead className="text-right">{data.ticker}</TableHead>
                    <TableHead className="text-right">t</TableHead>
                    <TableHead className="text-right">Sector</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody className="tabular">
                  {factors.map((f) => {
                    const s = data.sensitivities[f];
                    const sec = data.sector_sensitivities[f];
                    const sig = s?.t !== null && s?.t !== undefined && Math.abs(s.t) >= 2;
                    return (
                      <TableRow key={f} className={cn(!sig && "text-muted-foreground")}>
                        <TableCell>{data.factors[f].label}</TableCell>
                        <TableCell
                          className={cn(
                            "text-right",
                            sig && s.impact > 0 && "text-positive",
                            sig && s.impact < 0 && "text-negative",
                          )}
                        >
                          {s ? fmtReturn(s.impact, 2) : "—"}
                        </TableCell>
                        <TableCell className="text-right">{s ? fmtNumber(s.t, 1) : "—"}</TableCell>
                        <TableCell className="text-right">{sec ? fmtReturn(sec.impact, 2) : "—"}</TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            ) : (
              <p className="p-4 text-sm text-muted-foreground">Sin historia semanal suficiente.</p>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Noticias del activo y su sector</CardTitle>
          <CardDescription>
            {data.pressure
              ? `Presión ${fmtNumber(data.pressure.score, 1)} (▲${data.pressure.pos} ▼${data.pressure.neg})` +
                (data.sector_pressure ? ` · sector ${fmtNumber(data.sector_pressure.score, 1)}` : "")
              : "Últimos 14 días."}
          </CardDescription>
        </CardHeader>
        <CardContent className="max-h-[520px] overflow-y-auto">
          <NewsList news={data.news} labels={data.event_labels} showIrrelevant={!data.status.classifier} />
        </CardContent>
      </Card>
    </section>
  );
}
