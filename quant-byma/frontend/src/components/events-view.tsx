"use client";

import { RefreshCw } from "lucide-react";
import { useMemo, useState } from "react";
import { Line, LineChart, ResponsiveContainer, YAxis } from "recharts";
import useSWR from "swr";

import { ClassifierNotice, EventStateBadge, NewsList, PressureBadge } from "@/components/events-shared";
import { ErrorState, LoadingState } from "@/components/state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, fetcher, type EventsOverview, type LocalSeries, type MacroEvent, type MacroSeries } from "@/lib/api";
import { fmtNumber, fmtProb, fmtReturn } from "@/lib/format";
import { cn } from "@/lib/utils";

export function EventsView() {
  const [days, setDays] = useState(7);
  const { data, error, mutate } = useSWR<EventsOverview>(`/api/events?days=${days}`, fetcher);
  const [refreshing, setRefreshing] = useState(false);
  const [type, setType] = useState<string>("todos");
  const [showAll, setShowAll] = useState(false);

  const news = useMemo(
    () => (data?.news ?? []).filter((n) => type === "todos" || n.analysis?.event_type === type),
    [data, type],
  );

  if (error) return <ErrorState error={error} />;
  if (!data) return <LoadingState />;

  const live = data.events.filter((e) => e.state !== "inactivo");
  const idle = data.events.filter((e) => e.state === "inactivo");
  const types = Array.from(new Set(data.news.map((n) => n.analysis?.event_type).filter(Boolean))) as string[];
  const sectorPressure = Object.entries(data.sector_pressure).sort((a, b) => b[1].score - a[1].score);

  async function refresh() {
    setRefreshing(true);
    try {
      await api.refreshEvents();
      await mutate();
    } finally {
      setRefreshing(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Eventos y noticias</h1>
          <p className="max-w-3xl text-sm text-muted-foreground">
            Contexto al lado del modelo, sin modificar sus probabilidades. Los eventos macro se detectan con series de
            mercado reales (tasas, petróleo, VIX, dólar, granos, metales) y se compara qué hizo cada sector en las{" "}
            {data.horizon ?? 60} ruedas siguientes a cada vez que ocurrió desde 2004. Los factores macro se probaron como
            variables del modelo y empeoraron el Brier fuera de muestra, por eso quedan como contexto.
          </p>
        </div>
        <Button size="sm" variant="outline" onClick={refresh} disabled={refreshing}>
          <RefreshCw className={cn("size-4", refreshing && "animate-spin")} />
          {refreshing ? "Actualizando…" : "Actualizar eventos"}
        </Button>
      </div>

      <ClassifierNotice status={data.status} />

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Eventos macro vigentes</h2>
        {live.length === 0 && <p className="text-sm text-muted-foreground">Ninguna regla se cumple en las últimas 20 ruedas.</p>}
        <div className="grid gap-4 lg:grid-cols-2">
          {live.map((e) => (
            <EventCard key={e.key} e={e} data={data} />
          ))}
        </div>
        {idle.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle>Reglas sin disparar</CardTitle>
              <CardDescription>Valor actual de cada medida contra su umbral.</CardDescription>
            </CardHeader>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead>Evento</TableHead>
                    <TableHead>Categoría</TableHead>
                    <TableHead className="text-right">Actual</TableHead>
                    <TableHead className="text-right">Umbral</TableHead>
                    <TableHead className="text-right">Veces desde 2004</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody className="tabular">
                  {idle.map((e) => (
                    <TableRow key={e.key}>
                      <TableCell title={e.description}>{e.name}</TableCell>
                      <TableCell className="text-muted-foreground">{e.category}</TableCell>
                      <TableCell className="text-right">{e.value_label}</TableCell>
                      <TableCell className="text-right text-muted-foreground">{e.threshold_label}</TableCell>
                      <TableCell className="text-right text-muted-foreground">{e.occurrences}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        )}
      </section>

      {data.local && data.local.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-lg font-semibold">Termómetro argentino</h2>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {data.local.map((m) => (
              <LocalCard key={m.key} m={m} />
            ))}
          </div>
        </section>
      )}

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Termómetro macro</h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {data.macro.map((m) => (
            <MacroCard key={m.key} m={m} />
          ))}
        </div>
      </section>

      <section className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader className="flex-row flex-wrap items-center gap-2">
            <div className="mr-auto">
              <CardTitle>Noticias</CardTitle>
              <CardDescription>
                {data.status.classifier
                  ? `Interpretadas por Claude (${data.status.model}). Cada impacto indica dirección, magnitud y confianza.`
                  : "Titulares sin interpretar."}
              </CardDescription>
            </div>
            <div className="flex rounded-md border p-0.5">
              {[3, 7, 14].map((d) => (
                <Button key={d} size="sm" className="h-7" variant={days === d ? "secondary" : "ghost"} onClick={() => setDays(d)}>
                  {d} días
                </Button>
              ))}
            </div>
            <select
              className="h-8 rounded-md border bg-background px-2 text-xs"
              value={type}
              onChange={(e) => setType(e.target.value)}
              aria-label="Tipo de evento"
            >
              <option value="todos">Todos los tipos</option>
              {types.map((t) => (
                <option key={t} value={t}>
                  {data.event_labels[t] ?? t}
                </option>
              ))}
            </select>
            <Button size="sm" variant="ghost" className="h-7" onClick={() => setShowAll((v) => !v)}>
              {showAll ? "Ocultar sin impacto" : "Ver todas"}
            </Button>
          </CardHeader>
          <CardContent className="max-h-[720px] overflow-y-auto">
            <NewsList news={news} labels={data.event_labels} showIrrelevant={showAll || !data.status.classifier} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Presión de noticias por sector</CardTitle>
            <CardDescription>Suma de impactos con decaimiento (vida media 5 días).</CardDescription>
          </CardHeader>
          <CardContent>
            {sectorPressure.length === 0 ? (
              <p className="text-sm text-muted-foreground">Sin noticias clasificadas.</p>
            ) : (
              <ul className="space-y-2 text-sm">
                {sectorPressure.map(([sector, p]) => (
                  <li key={sector} className="flex items-center justify-between gap-2">
                    <span>{sector}</span>
                    <span className="flex items-center gap-2">
                      <span className="tabular text-xs text-muted-foreground">
                        ▲{p.pos} ▼{p.neg}
                      </span>
                      <PressureBadge label={p.label} score={p.score} />
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </section>

      <SensitivityTable data={data} />
    </div>
  );
}

function EventCard({ e, data }: { e: MacroEvent; data: EventsOverview }) {
  const st = data.study[e.key];
  const sig = (st?.sectors ?? []).filter((r) => r.significant);
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <EventStateBadge state={e.state} />
          <Badge variant="outline">{e.category}</Badge>
          {e.since && <span className="text-xs text-muted-foreground">episodio desde {e.since}</span>}
        </div>
        <CardTitle className="text-base">{e.name}</CardTitle>
        <CardDescription>
          {e.description} Hoy: <b>{e.value_label}</b> (umbral {e.threshold_label}).
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {st?.universe ? (
          <>
            <p className="text-xs text-muted-foreground">
              Ocurrió {st.n} veces. En las {data.horizon} ruedas siguientes la acción mediana del universo subió el{" "}
              {fmtProb(st.universe.hit_rate)} de las veces (IC95 {fmtProb(st.universe.ci_low)}–{fmtProb(st.universe.ci_high)};
              en cualquier momento: {fmtProb(st.universe.base_rate)}), con retorno medio {fmtReturn(st.universe.mean_return)}.
            </p>
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead>Sector</TableHead>
                  <TableHead className="text-right" title="Retorno medio del sector menos el del universo">
                    Exceso medio
                  </TableHead>
                  <TableHead className="text-right" title="% de episodios en que el sector le ganó al universo">
                    Le ganó
                  </TableHead>
                  <TableHead className="text-right">IC95</TableHead>
                  <TableHead className="text-right">n</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody className="tabular">
                {st.sectors.map((r) => (
                  <TableRow key={r.sector} className={cn(!r.significant && "text-muted-foreground")}>
                    <TableCell>
                      {r.sector}
                      {r.significant && (
                        <Badge variant={r.mean_excess > 0 ? "positive" : "negative"} className="ml-1.5">
                          {r.mean_excess > 0 ? "favorable" : "desfavorable"}
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell className={cn("text-right", r.mean_excess > 0 ? "text-positive" : "text-negative")}>
                      {fmtReturn(r.mean_excess)}
                    </TableCell>
                    <TableCell className="text-right">{fmtProb(r.hit_rate)}</TableCell>
                    <TableCell className="text-right">
                      {fmtProb(r.ci_low)}–{fmtProb(r.ci_high)}
                    </TableCell>
                    <TableCell className="text-right">{r.n}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <p className="text-xs text-muted-foreground">
              {sig.length
                ? "Se destacan los sectores cuyo IC95 de “le ganó al universo” excluye el 50%."
                : "Ningún sector se diferenció del universo con significancia estadística en este evento."}{" "}
              Son muestras chicas: tomalo como contexto, no como predicción.
            </p>
          </>
        ) : (
          <p className="text-xs text-muted-foreground">Sin ocurrencias históricas con datos de precios.</p>
        )}
      </CardContent>
    </Card>
  );
}

function fmtChange(m: MacroSeries, v: number | null): string {
  if (v === null) return "—";
  return m.unit === "pct" ? `${v > 0 ? "+" : ""}${(v * 100).toFixed(0)} pb` : fmtReturn(v);
}

function MacroCard({ m }: { m: MacroSeries }) {
  const up = (m.change_20 ?? 0) >= 0;
  return (
    <Card>
      <CardHeader className="pb-0">
        <CardDescription>{m.label}</CardDescription>
        <CardTitle className="tabular text-lg">
          {fmtNumber(m.value, m.unit === "pct" ? 2 : m.value > 100 ? 1 : 2)}
          {m.unit === "pct" && "%"}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-1">
        <div className="h-10">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={m.spark}>
              <YAxis hide domain={["dataMin", "dataMax"]} />
              <Line
                type="monotone"
                dataKey="value"
                dot={false}
                strokeWidth={1.5}
                stroke={up ? "#22a06b" : "#e5484d"}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
        <p className="tabular text-xs text-muted-foreground">
          20 ruedas {fmtChange(m, m.change_20)} · 60 ruedas {fmtChange(m, m.change_60)}
        </p>
      </CardContent>
    </Card>
  );
}

function fmtLocal(m: LocalSeries, v: number | null, delta = false): string {
  if (v === null) return "—";
  if (m.unit === "ratio") return delta ? `${v > 0 ? "+" : ""}${fmtNumber(v * 100, 1)} pp` : fmtProb(v, 1);
  if (m.unit === "rate") return delta ? `${v > 0 ? "+" : ""}${fmtNumber(v, 1)} pp` : `${fmtNumber(v, 1)}%`;
  if (delta) return fmtReturn(v);
  return m.unit === "pts" ? fmtNumber(v, 0) : fmtNumber(v, v > 100 ? 0 : 2);
}

function LocalCard({ m }: { m: LocalSeries }) {
  const rising = (m.change_30d ?? 0) >= 0;
  // Para riesgo país, inflación y brecha, subir es una mala noticia.
  const badWhenUp = m.key === "RIESGO_PAIS" || m.key === "INFLACION_AR" || m.key === "BRECHA";
  const good = badWhenUp ? !rising : rising;
  return (
    <Card>
      <CardHeader className="pb-0">
        <CardDescription>{m.label}</CardDescription>
        <CardTitle className="tabular text-lg">
          {m.key === "MERVAL_USD" ? "US$ " : ""}
          {m.key === "MEP" ? `$ ${fmtNumber(m.value, 0)}` : fmtLocal(m, m.value)}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-1">
        <div className="h-10">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={m.spark}>
              <YAxis hide domain={["dataMin", "dataMax"]} />
              <Line type="monotone" dataKey="value" dot={false} strokeWidth={1.5} stroke={good ? "#22a06b" : "#e5484d"} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
        <p className="tabular text-xs text-muted-foreground">
          30 días {fmtLocal(m, m.change_30d, true)} · 90 días {fmtLocal(m, m.change_90d, true)}
          {m.annual != null && ` · últimos 12 meses ${fmtProb(m.annual, 1)}`}
        </p>
      </CardContent>
    </Card>
  );
}

function SensitivityTable({ data }: { data: EventsOverview }) {
  const factors = Object.keys(data.factors);
  const sectors = Object.keys(data.sector_sensitivities).sort();
  if (!sectors.length) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Sensibilidad de cada sector a los factores macro</CardTitle>
        <CardDescription>
          Movimiento semanal mediano de las acciones del sector ante cada shock de referencia (beta de los últimos 3 años).
        </CardDescription>
      </CardHeader>
      <CardContent className="overflow-x-auto p-0">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead>Sector</TableHead>
              {factors.map((f) => (
                <TableHead key={f} className="text-right" title={data.factors[f].label}>
                  {data.factors[f].label}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody className="tabular">
            {sectors.map((s) => (
              <TableRow key={s}>
                <TableCell>{s}</TableCell>
                {factors.map((f) => {
                  const v = data.sector_sensitivities[s][f]?.impact;
                  return (
                    <TableCell
                      key={f}
                      className={cn(
                        "text-right",
                        v !== undefined && v > 0.005 && "text-positive",
                        v !== undefined && v < -0.005 && "text-negative",
                      )}
                    >
                      {v === undefined ? "—" : fmtReturn(v, 2)}
                    </TableCell>
                  );
                })}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
