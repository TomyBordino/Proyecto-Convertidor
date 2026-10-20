"use client";

import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import useSWR from "swr";

import { ErrorState, LoadingState } from "@/components/state";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, ApiError, fetcher, type BacktestResult, type PerfMetrics } from "@/lib/api";
import { fmtNumber, fmtProb, fmtReturn } from "@/lib/format";
import { cn } from "@/lib/utils";

const axis = { fontSize: 11, fill: "var(--muted-foreground)" };
const COLORS = { strategy: "#3e9fff", universe: "#8e8cf2", benchmark: "#f5a524" };

export function BacktestView() {
  const [topN, setTopN] = useState(20);
  const [rebalance, setRebalance] = useState(20);
  const [sort, setSort] = useState("score");
  const [stages, setStages] = useState("");
  const [kind, setKind] = useState("");
  const [cap, setCap] = useState("");
  const [cost, setCost] = useState(50);
  const [period, setPeriod] = useState("");
  const [buffer, setBuffer] = useState(2);
  const [weighting, setWeighting] = useState("equal");
  const [regime, setRegime] = useState("none");

  function preset(p: "robusta" | "proteccion" | "base") {
    setTopN(p === "base" ? 20 : 30);
    setSort(p === "base" ? "score" : "trend");
    setStages(p === "base" ? "" : "1,2,3");
    setWeighting(p === "base" ? "equal" : "inv_vol");
    setRegime(p === "proteccion" ? "spy_bear" : "none");
    setCap("");
    setBuffer(2);
  }

  const qs = new URLSearchParams({ top_n: String(topN), rebalance: String(rebalance), sort, cost_bps: String(cost), buffer: String(buffer), weighting, regime });
  if (stages) qs.set("stages", stages);
  if (kind) qs.set("kind", kind);
  if (cap) qs.set("max_per_sector", cap);
  const [from, to] = period.split("-");
  if (from) qs.set("start_year", from);
  if (to) qs.set("end_year", to);
  const { data, error, isLoading, mutate } = useSWR<BacktestResult>(`/api/backtest?${qs}`, fetcher, { keepPreviousData: true });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Backtest</h1>
        <p className="max-w-3xl text-sm text-muted-foreground">
          Qué habría pasado siguiendo el ranking en la historia: en cada rebalanceo se compran, con igual peso, los N
          activos mejor ordenados usando solo información disponible ese día, y se mantienen hasta el siguiente. Retornos
          en dólares, con dividendos y descontando costos por la rotación de la cartera.
        </p>
      </div>

      <Card>
        <CardContent className="flex flex-wrap items-center gap-2 p-4 text-sm">
          <span className="text-xs text-muted-foreground">Estrategias validadas:</span>
          <Button size="sm" variant="outline" onClick={() => preset("robusta")} title="30 papeles, tendencia, sin etapa bajista, ponderados por volatilidad">
            Robusta
          </Button>
          <Button size="sm" variant="outline" onClick={() => preset("proteccion")} title="Robusta + liquidez cuando el SPY está en etapa bajista">
            Robusta con protección
          </Button>
          <Button size="sm" variant="ghost" onClick={() => preset("base")}>
            Volver a la básica
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="flex flex-wrap items-end gap-3 p-4 text-sm">
          <Field label="Cantidad de activos">
            <Select value={topN} onChange={(e) => setTopN(Number(e.target.value))}>
              {[5, 10, 20, 30, 50].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Rebalanceo">
            <Select value={rebalance} onChange={(e) => setRebalance(Number(e.target.value))}>
              <option value={20}>Mensual (20 ruedas)</option>
              <option value={60}>Trimestral (60)</option>
              <option value={120}>Semestral (120)</option>
            </Select>
          </Field>
          <Field label="Ordenar por">
            <Select value={sort} onChange={(e) => setSort(e.target.value)}>
              <option value="score">Puntaje del modelo</option>
              <option value="trend">Solo tendencia</option>
              <option value="value">Solo valuación</option>
            </Select>
          </Field>
          <Field label="Etapas">
            <Select value={stages} onChange={(e) => setStages(e.target.value)}>
              <option value="">Todas</option>
              <option value="2">Solo alcista (2)</option>
              <option value="1,2">Base o alcista (1, 2)</option>
              <option value="1">Solo base (1)</option>
            </Select>
          </Field>
          <Field label="Tipo">
            <Select value={kind} onChange={(e) => setKind(e.target.value)}>
              <option value="">Todos</option>
              <option value="CEDEAR">CEDEARs</option>
              <option value="LOCAL">Acciones locales</option>
            </Select>
          </Field>
          <Field label="Máx. por sector">
            <Select value={cap} onChange={(e) => setCap(e.target.value)}>
              <option value="">Sin límite</option>
              {[2, 3, 5].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Costo por operación">
            <Select value={cost} onChange={(e) => setCost(Number(e.target.value))}>
              {[0, 25, 50, 100].map((n) => (
                <option key={n} value={n}>
                  {(n / 100).toFixed(2).replace(".", ",")}%
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Colchón de permanencia">
            <Select value={buffer} onChange={(e) => setBuffer(Number(e.target.value))} title="Un activo en cartera se mantiene mientras siga entre los primeros colchón × N: baja la rotación y los costos">
              <option value={1}>Sin colchón</option>
              <option value={1.5}>×1,5</option>
              <option value={2}>×2</option>
              <option value={3}>×3</option>
            </Select>
          </Field>
          <Field label="Ponderación">
            <Select value={weighting} onChange={(e) => setWeighting(e.target.value)} title="Inversa de la volatilidad: los papeles más volátiles pesan menos">
              <option value="equal">Igual peso</option>
              <option value="inv_vol">Inversa de la volatilidad</option>
            </Select>
          </Field>
          <Field label="Filtro de mercado">
            <Select value={regime} onChange={(e) => setRegime(e.target.value)} title="Pasa a liquidez (tasa a 3 meses) cuando el SPY está en etapa bajista">
              <option value="none">Siempre invertido</option>
              <option value="spy_bear">Liquidez si el SPY está bajista</option>
              <option value="spy_weak">Liquidez si el SPY está en techo o bajista</option>
            </Select>
          </Field>
          <Field label="Período">
            <Select value={period} onChange={(e) => setPeriod(e.target.value)}>
              <option value="">Toda la historia</option>
              <option value="-2015">2004–2015 (diseño)</option>
              <option value="2016-">2016–hoy (prueba)</option>
              <option value="2020-">Desde 2020</option>
              <option value="2022-">Desde 2022</option>
            </Select>
          </Field>
          {isLoading && <span className="text-xs text-muted-foreground">Calculando…</span>}
        </CardContent>
      </Card>

      {error instanceof ApiError && error.status === 404 ? (
        <MissingPanel onDone={() => mutate()} />
      ) : error ? (
        <ErrorState error={error} />
      ) : !data ? (
        <LoadingState />
      ) : data.status !== "ok" ? (
        <p className="text-sm text-muted-foreground">Sin resultados: {data.status}</p>
      ) : (
        <Results data={data} />
      )}

      <Card>
        <CardContent className="space-y-2 p-4 text-xs text-muted-foreground">
          <p>
            <b className="text-foreground">Sesgo de supervivencia.</b> El universo son los activos que cotizan hoy en BYMA:
            las empresas que quebraron o dejaron de cotizar no están. Eso infla los retornos de todas las curvas por igual,
            así que la comparación que importa es contra el promedio del universo, no el número absoluto.
          </p>
          <p>
            <b className="text-foreground">Cuidado con elegir la mejor combinación.</b> Si probás muchas variantes y te
            quedás con la que mejor salió, parte de esa ventaja es suerte. Las conclusiones más firmes son las que se
            repiten con distintas cantidades de activos, rebalanceos y períodos.
          </p>
          <p>
            <b className="text-foreground">Sin ajuste a los datos.</b> El puntaje usa pesos fijos elegidos de antemano, así
            que la estrategia no está optimizada sobre esta misma historia. Los CEDEARs se miden con su subyacente en EE.
            UU., incluso en años en que todavía no cotizaban en BYMA. No es una recomendación de inversión.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

function MissingPanel({ onDone }: { onDone: () => void }) {
  const [state, setState] = useState<"idle" | "running" | "error">("idle");
  const [msg, setMsg] = useState("");
  async function run() {
    setState("running");
    try {
      await api.ingest();
      for (;;) {
        await new Promise((r) => setTimeout(r, 10_000));
        const st = await api.ingestStatus();
        if (!st.running) {
          if (st.error) {
            setMsg(st.error);
            setState("error");
            return;
          }
          break;
        }
      }
      setState("idle");
      onDone();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
      setState("error");
    }
  }
  return (
    <Card>
      <CardContent className="space-y-3 p-4 text-sm">
        <p className="font-medium">Falta la historia del modelo para correr el backtest</p>
        <p className="text-muted-foreground">
          Se genera al final de cada actualización de datos. La primera vez con esta versión tarda 20–30 minutos (baja
          dividendos, balances trimestrales y series argentinas); podés seguir usando la plataforma mientras tanto.
        </p>
        <Button size="sm" onClick={run} disabled={state === "running"}>
          {state === "running" ? "Actualizando… (no cierres esta pestaña)" : "Actualizar datos ahora"}
        </Button>
        {state === "error" && <p className="text-xs text-negative">La actualización falló: {msg}</p>}
      </CardContent>
    </Card>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs text-muted-foreground">{label}</span>
      {children}
    </label>
  );
}

function Results({ data }: { data: BacktestResult }) {
  const m = data.metrics;
  const curves = data.curves.map((c) => ({ ...c, strategy: c.strategy * 100, universe: c.universe * 100, benchmark: c.benchmark * 100 }));
  const verdict =
    (m.strategy.cagr ?? 0) > (m.universe.cagr ?? 0)
      ? `La estrategia le ganó al promedio del universo por ${fmtReturn((m.strategy.cagr ?? 0) - (m.universe.cagr ?? 0))} anual.`
      : `La estrategia rindió ${fmtReturn((m.strategy.cagr ?? 0) - (m.universe.cagr ?? 0))} anual contra el promedio del universo: no le ganó.`;
  return (
    <>
      <Card className={cn((m.strategy.cagr ?? 0) > (m.universe.cagr ?? 0) ? "border-positive/40" : "border-negative/40")}>
        <CardContent className="p-4 text-sm">
          <p className="font-medium">{verdict}</p>
          <p className="mt-1 text-muted-foreground">
            {data.periods} rebalanceos entre {data.first_date} y {data.last_date}. Le ganó al universo en el{" "}
            {fmtProb(data.beat_universe)} de los períodos y en {data.years_beat_universe} de {data.by_year.length} años; al SPY le ganó en{" "}
            {data.by_year.filter((y) => y.strategy > y.benchmark).length} de {data.by_year.length} años.
            Rotación promedio por rebalanceo: {fmtProb(data.avg_turnover)}.
            {data.time_in_market != null && data.time_in_market < 1 && ` Estuvo invertida el ${fmtProb(data.time_in_market)} del tiempo.`}
          </p>
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-3">
        <MetricsCard title="Estrategia (neta de costos)" m={m.strategy} color={COLORS.strategy} sub={`Sin costos: ${fmtReturn(m.strategy_gross.cagr)} anual`} />
        <MetricsCard title="Promedio del universo" m={m.universe} color={COLORS.universe} sub="Comprar todo con igual peso" />
        <MetricsCard title="SPY (S&P 500)" m={m.benchmark as PerfMetrics} color={COLORS.benchmark} sub="Referencia de mercado" />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Evolución de US$ 100</CardTitle>
          <CardDescription>Escala logarítmica: la pendiente es la tasa de crecimiento.</CardDescription>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={320}>
            <LineChart data={curves}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
              <XAxis dataKey="time" tick={axis} minTickGap={50} tickFormatter={(v: string) => v.slice(0, 4)} />
              <YAxis scale="log" domain={["auto", "auto"]} tick={axis} width={60} allowDataOverflow
                tickFormatter={(v: number) => `US$ ${fmtNumber(v, 0)}`} />
              <Tooltip formatter={(v) => `US$ ${fmtNumber(Number(v), 0)}`} />
              <Legend />
              <Line dataKey="strategy" name="Estrategia" stroke={COLORS.strategy} dot={false} strokeWidth={2} isAnimationActive={false} />
              <Line dataKey="universe" name="Universo" stroke={COLORS.universe} dot={false} strokeWidth={1.5} isAnimationActive={false} />
              <Line dataKey="benchmark" name="SPY" stroke={COLORS.benchmark} dot={false} strokeWidth={1.5} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>¿El orden del modelo se traduce en plata?</CardTitle>
            <CardDescription>
              Retorno anual de cada quinto del universo según el criterio elegido (1 = peor puntuado, 5 = mejor), sin costos.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={data.quintiles.map((q) => ({ ...q, cagr: (q.cagr ?? 0) * 100 }))}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                <XAxis dataKey="quintile" tick={axis} />
                <YAxis tick={axis} tickFormatter={(v: number) => `${v.toFixed(0)}%`} width={40} />
                <Tooltip formatter={(v) => `${Number(v).toFixed(1)}% anual`} />
                <Bar dataKey="cagr" name="Retorno anual" fill={COLORS.strategy} radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Si hoy siguieras esta estrategia</CardTitle>
            <CardDescription>Selección del último rebalanceo.</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-1.5">
            {data.picks.map((p) => (
              <a key={p.ticker} href={`/asset/${p.ticker}`} title={p.name ?? ""} className="rounded-md border px-2 py-1 text-xs font-medium hover:border-primary">
                {p.ticker}
              </a>
            ))}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Año por año</CardTitle>
        </CardHeader>
        <CardContent className="overflow-x-auto p-0">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Año</TableHead>
                <TableHead className="text-right">Estrategia</TableHead>
                <TableHead className="text-right">Universo</TableHead>
                <TableHead className="text-right">SPY</TableHead>
                <TableHead className="text-right">Diferencia vs universo</TableHead>
                <TableHead className="text-right">Diferencia vs SPY</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody className="tabular">
              {[...data.by_year].reverse().map((y) => (
                <TableRow key={y.year}>
                  <TableCell>{y.year}</TableCell>
                  <TableCell className={cn("text-right", y.strategy >= 0 ? "text-positive" : "text-negative")}>{fmtReturn(y.strategy)}</TableCell>
                  <TableCell className="text-right">{fmtReturn(y.universe)}</TableCell>
                  <TableCell className="text-right">{fmtReturn(y.benchmark)}</TableCell>
                  <TableCell className={cn("text-right", y.strategy - y.universe >= 0 ? "text-positive" : "text-negative")}>
                    {fmtReturn(y.strategy - y.universe)}
                  </TableCell>
                  <TableCell className={cn("text-right", y.strategy - y.benchmark >= 0 ? "text-positive" : "text-negative")}>
                    {fmtReturn(y.strategy - y.benchmark)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </>
  );
}

function MetricsCard({ title, m, color, sub }: { title: string; m: PerfMetrics; color: string; sub: string }) {
  const rows: [string, string][] = [
    ["Retorno anual", fmtReturn(m?.cagr)],
    ["Volatilidad", fmtProb(m?.vol)],
    ["Retorno / volatilidad", fmtNumber(m?.sharpe ?? null, 2)],
    ["Peor caída", fmtReturn(m?.max_drawdown)],
    ["Períodos positivos", fmtProb(m?.hit_rate)],
  ];
  return (
    <Card>
      <CardHeader>
        <CardDescription className="flex items-center gap-2">
          <span className="inline-block size-2.5 rounded-full" style={{ background: color }} />
          {title}
        </CardDescription>
        <CardTitle className="tabular text-2xl">{fmtReturn(m?.cagr)}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-1 text-xs">
        {rows.slice(1).map(([k, v]) => (
          <div key={k} className="flex justify-between">
            <span className="text-muted-foreground">{k}</span>
            <span className="tabular">{v}</span>
          </div>
        ))}
        <p className="pt-1 text-muted-foreground">{sub}</p>
      </CardContent>
    </Card>
  );
}
