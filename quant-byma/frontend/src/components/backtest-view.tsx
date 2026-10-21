"use client";

import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import useSWR from "swr";

import { ErrorState, LoadingState } from "@/components/state";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, ApiError, fetcher, type BacktestResult, type PerfMetrics, type PresetRow, type PresetTable } from "@/lib/api";
import { fmtMoney, fmtNumber, fmtProb, fmtReturn } from "@/lib/format";
import { useStored } from "@/lib/stored";
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

  const presets = useSWR<PresetTable>("/api/backtest/presets", fetcher);
  const table = presets.data?.presets;

  const active: Preset | null =
    sort === "trend" && stages === "1,2,3" && weighting === "inv_vol" && !cap
      ? regime === "spy_bear"
        ? "proteccion"
        : regime === "none"
          ? "robusta"
          : null
      : sort === "score" && !stages && weighting === "equal" && regime === "none" && !cap
        ? "base"
        : null;
  const recommendedBuffer = active ? table?.[PRESET_KEY[active]]?.[String(topN)]?.buffer : undefined;

  function preset(p: Preset, n: number = topN) {
    setSort(p === "base" ? "score" : "trend");
    setStages(p === "base" ? "" : "1,2,3");
    setWeighting(p === "base" ? "equal" : "inv_vol");
    setRegime(p === "proteccion" ? "spy_bear" : "none");
    setCap("");
    setRebalance(20);
    setBuffer(table?.[PRESET_KEY[p]]?.[String(n)]?.buffer ?? 2);
  }

  function changeTopN(n: number) {
    setTopN(n);
    // Al cambiar la cantidad de papeles, la estrategia validada usa el colchón de esa cantidad.
    if (active) preset(active, n);
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
          <span className="text-xs text-muted-foreground">Estrategias validadas (con {topN} papeles):</span>
          <Button size="sm" variant={active === "robusta" ? "secondary" : "outline"} onClick={() => preset("robusta")} title="30 papeles, tendencia, sin etapa bajista, ponderados por volatilidad">
            Robusta
          </Button>
          <Button size="sm" variant={active === "proteccion" ? "secondary" : "outline"} onClick={() => preset("proteccion")} title="Robusta + liquidez cuando el SPY está en etapa bajista">
            Robusta con protección
          </Button>
          <Button size="sm" variant={active === "base" ? "secondary" : "ghost"} onClick={() => preset("base")}>
            Básica
          </Button>
          <span className="text-xs text-muted-foreground">{active ? "" : "· configuración personalizada"}</span>
        </CardContent>
      </Card>

      <StrategyGuide
        active={active}
        rebalance={rebalance}
        topN={topN}
        buffer={buffer}
        recommendedBuffer={recommendedBuffer}
        table={presets.data}
        onPick={(n) => changeTopN(n)}
      />

      <Card>
        <CardContent className="flex flex-wrap items-end gap-3 p-4 text-sm">
          <Field label="Cantidad de activos">
            <Select value={topN} onChange={(e) => changeTopN(Number(e.target.value))}>
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
              <option value="1,2,3">Sin etapa bajista (1, 2, 3)</option>
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
            <Select value={weighting} onChange={(e) => setWeighting(e.target.value)} title="Igual peso: capital ÷ N. Inversa de la volatilidad: los más volátiles pesan menos. Por ranking: el primero pesa N veces más que el último. Paridad de riesgo: cada papel aporta el mismo riesgo, teniendo en cuenta cuánto se mueven juntos (36 meses)">
              <option value="equal">Igual peso</option>
              <option value="inv_vol">Inversa de la volatilidad</option>
              <option value="rank">Por ranking (#1 pesa más)</option>
              <option value="risk_parity">Paridad de riesgo (con correlaciones)</option>
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
        <Results data={data} rebalance={rebalance} buffer={buffer} />
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

export type Preset = "robusta" | "proteccion" | "base";

export const PRESET_KEY: Record<Preset, "robusta" | "proteccion" | "basica"> = {
  robusta: "robusta",
  proteccion: "proteccion",
  base: "basica",
};

const PRESETS: Record<Preset, { title: string; what: (n: number) => string; when: string }> = {
  robusta: {
    title: "Robusta",
    what: (n) =>
      `Compra los ${n} papeles con mejor tendencia (pendiente de la media de 200 ruedas, momentum de 12 meses, distancia a la media y cercanía al máximo), descarta los que están en etapa bajista y les da más peso a los menos volátiles.`,
    when: "Para quien quiere la estrategia que mejoró en los dos períodos de prueba, sin intentar adivinar el mercado.",
  },
  proteccion: {
    title: "Robusta con protección",
    what: () =>
      "Igual que la Robusta, pero cuando el SPY entra en etapa bajista vende todo y espera en liquidez (rinde la tasa a 3 meses) hasta que el SPY salga de esa etapa.",
    when: "Para quien prioriza evitar las caídas grandes, aunque eso cueste algo de retorno en los rebotes rápidos.",
  },
  base: {
    title: "Básica",
    what: (n) => `Compra los ${n} papeles con mejor puntaje del modelo (tendencia + valuación y calidad), con igual peso.`,
    when: "Como referencia: es la que sigue directamente el ranking de la plataforma.",
  },
};

const N_ADVICE: Record<number, string> = {
  5: "Muy concentrada: cada papel pesa alrededor del 20% y uno solo puede mover la cartera ±5% en un mes. Rindió más en la historia, pero casi toda la ventaja vino de 2016–2026 y dependió de pocos ganadores. Usala solo con una parte chica del capital.",
  10: "Concentrada: cada papel pesa alrededor del 10%. Más retorno histórico que con 20–30, a cambio de más volatilidad y años muy distintos del índice.",
  20: "Equilibrio entre seguimiento y diversificación: ~5% por papel y pocas operaciones por mes.",
  30: "Diversificada (~3% por papel): la que mejor se comportó en los dos períodos de prueba, con rotación baja.",
  50: "Muy diversificada (~2% por papel): se parece cada vez más al promedio del universo; tiene sentido con la protección, que es la que más suaviza las caídas.",
};

function pct(v: number | null | undefined, d = 1) {
  return fmtReturn(v ?? null, d);
}

function rowSummary(r: PresetRow | undefined) {
  if (!r) return "Calculando…";
  return `${pct(r.full.cagr)} anual (universo ${pct(r.full.universe_cagr)}) · peor caída ${pct(r.full.max_drawdown, 0)} · le ganó al universo en ${r.full.years_beat_universe} de ${r.full.years} años`;
}

function StrategyGuide({
  active,
  rebalance,
  topN,
  buffer,
  recommendedBuffer,
  table,
  onPick,
}: {
  active: Preset | null;
  rebalance: number;
  topN: number;
  buffer: number;
  recommendedBuffer: number | undefined;
  table: PresetTable | undefined;
  onPick: (n: number) => void;
}) {
  const [open, setOpen] = useState(true);
  const every = rebalance === 20 ? "cada mes" : rebalance === 60 ? "cada 3 meses" : "cada 6 meses";
  const key = active ? PRESET_KEY[active] : "robusta";
  const row = table?.presets[key]?.[String(topN)];
  const zone = Math.round(topN * buffer);
  const trades = row?.full.avg_turnover != null ? Math.max(1, Math.round(2 * row.full.avg_turnover * topN)) : null;
  const minPos = (min: number) => fmtNumber(min / 0.005, 0);
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <div>
          <CardTitle>Las estrategias y cómo usarlas · con {topN} papeles</CardTitle>
          <CardDescription>
            Qué hace cada una, cómo le fue con la cantidad de papeles elegida y los pasos para llevarla a tu cuenta.
          </CardDescription>
        </div>
        <Button size="sm" variant="ghost" onClick={() => setOpen((v) => !v)}>
          {open ? "Ocultar" : "Mostrar"}
        </Button>
      </CardHeader>
      {open && (
        <CardContent className="space-y-5 text-sm">
          <div className="grid gap-3 lg:grid-cols-3">
            {(Object.keys(PRESETS) as Preset[]).map((k) => {
              const r = table?.presets[PRESET_KEY[k]]?.[String(topN)];
              return (
                <div key={k} className={cn("space-y-1.5 rounded-md border p-3", active === k && "border-primary bg-primary/5")}>
                  <p className="font-medium">
                    {PRESETS[k].title}
                    {active === k && <span className="ml-2 text-xs font-normal text-primary">(seleccionada)</span>}
                  </p>
                  <p className="text-xs">{PRESETS[k].what(topN)}</p>
                  <p className="text-xs text-muted-foreground">
                    <b>Para quién:</b> {PRESETS[k].when}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    <b>Con {topN} papeles:</b> {rowSummary(r)}
                    {r && ` · colchón ×${String(r.buffer).replace(".", ",")}`}.
                  </p>
                  {r && (
                    <p className="text-xs text-muted-foreground">
                      Diseño 2004–{table?.design_end}: {pct(r.design.cagr)} · prueba {Number(table?.design_end) + 1}–hoy: {pct(r.test.cagr)}{" "}
                      (universo {pct(r.test.universe_cagr)}).
                    </p>
                  )}
                </div>
              );
            })}
          </div>

          <div className="space-y-2">
            <p className="font-medium">
              {active ? PRESETS[active].title : "Robusta"} según la cantidad de papeles
            </p>
            <p className="text-xs text-muted-foreground">
              Rebalanceo mensual y 0,5% de costo por operación. El colchón de cada fila se eligió mirando solo 2004–
              {table?.design_end ?? 2015}; la columna “Prueba” son años que no se usaron para elegirlo. Tocá una fila para usarla.
            </p>
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead>Papeles</TableHead>
                    <TableHead className="text-right">Colchón</TableHead>
                    <TableHead className="text-right">Diseño</TableHead>
                    <TableHead className="text-right">Prueba</TableHead>
                    <TableHead className="text-right">Toda la historia</TableHead>
                    <TableHead className="text-right">Volatilidad</TableHead>
                    <TableHead className="text-right">Peor caída</TableHead>
                    <TableHead className="text-right">Años &gt; universo</TableHead>
                    <TableHead className="text-right">Operaciones por mes</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody className="tabular">
                  {[5, 10, 20, 30, 50].map((n) => {
                    const r = table?.presets[key]?.[String(n)];
                    return (
                      <TableRow key={n} onClick={() => onPick(n)} className={cn("cursor-pointer", n === topN && "bg-primary/5 font-medium")}>
                        <TableCell>{n}</TableCell>
                        <TableCell className="text-right">{r ? `×${String(r.buffer).replace(".", ",")}` : "—"}</TableCell>
                        <TableCell className="text-right">{pct(r?.design.cagr)}</TableCell>
                        <TableCell className="text-right">{pct(r?.test.cagr)}</TableCell>
                        <TableCell className="text-right">{pct(r?.full.cagr)}</TableCell>
                        <TableCell className="text-right">{fmtProb(r?.full.vol)}</TableCell>
                        <TableCell className="text-right text-negative">{pct(r?.full.max_drawdown, 0)}</TableCell>
                        <TableCell className="text-right">{r ? `${r.full.years_beat_universe}/${r.full.years}` : "—"}</TableCell>
                        <TableCell className="text-right">
                          {r?.full.avg_turnover != null ? `≈ ${Math.max(1, Math.round(2 * r.full.avg_turnover * n))}` : "—"}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                  {table && (
                    <TableRow className="text-muted-foreground hover:bg-transparent">
                      <TableCell>Universo</TableCell>
                      <TableCell />
                      <TableCell className="text-right">{pct(table.presets[key]?.["20"]?.design.universe_cagr)}</TableCell>
                      <TableCell className="text-right">{pct(table.presets[key]?.["20"]?.test.universe_cagr)}</TableCell>
                      <TableCell className="text-right">{pct(table.presets[key]?.["20"]?.full.universe_cagr)}</TableCell>
                      <TableCell />
                      <TableCell className="text-right">{pct(table.presets[key]?.["20"]?.full.universe_drawdown, 0)}</TableCell>
                      <TableCell />
                      <TableCell />
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </div>
            <p className="rounded-md border p-3 text-xs">
              <b>Con {topN} papeles:</b> {N_ADVICE[topN] ?? ""}
            </p>
            <p className="text-xs text-muted-foreground">
              <b>¿Por qué ponderar por la inversa de la volatilidad?</b> Se compararon cuatro formas de repartir el capital. La inversa
              de la volatilidad fue la que bajó la peor caída de forma consistente en los dos períodos. “Por ranking” mejoró el
              retorno por unidad de riesgo solo con carteras chicas (10 papeles), a cambio de algo más de caída; la paridad de riesgo con
              correlaciones fue muy buena en algunos casos de 2004–2015 y peor en 2016–hoy, por eso no se usa por defecto. Las cuatro
              están en el selector <i>Ponderación</i>.
            </p>
          </div>

          <div className="space-y-2">
            <p className="font-medium">Pasos para seguirla con {topN} papeles</p>
            <ol className="list-decimal space-y-1.5 pl-5 text-xs">
              <li>
                <b>Elegí la estrategia</b> con los botones de arriba (respetan la cantidad de papeles) y revisá la tabla: si solo le fue
                bien en “Diseño” o solo en “Prueba”, desconfiá.
                {recommendedBuffer != null && recommendedBuffer !== buffer && (
                  <span className="text-warning">
                    {" "}
                    Ojo: tenés colchón ×{String(buffer).replace(".", ",")} y el validado para {topN} papeles es ×
                    {String(recommendedBuffer).replace(".", ",")}.
                  </span>
                )}
              </li>
              <li>
                <b>Definí el capital.</b> Con {topN} papeles, cada posición es ≈ {fmtProb(1 / topN)} del capital
                {active && active !== "base" ? " (con ponderación por volatilidad, más para los tranquilos y menos para los volátiles)" : ""}.
                Si tu broker cobra una comisión mínima por operación, cada posición tiene que ser al menos 200 veces ese mínimo para no
                pagar más del 0,5% supuesto (por ejemplo, con un mínimo de $ 1.000, posiciones de $ {minPos(1000)} o más, es decir un
                capital de al menos $ {fmtNumber((1000 / 0.005) * topN, 0)}).
              </li>
              <li>
                <b>Rebalanceá {every}</b>, siempre el mismo día (por ejemplo, el primer día hábil), con los datos actualizados.
                {trades != null && ` Con ${topN} papeles son ≈ ${trades} operaciones por rebalanceo (compras + ventas).`}
              </li>
              <li>
                <b>Mirá el panel “Qué hacer hoy”</b> (más abajo). Si el filtro de mercado está activo y dice “liquidez”, vendé todo y
                dejá el dinero en un instrumento de corto plazo en dólares (caución o fondo money market) hasta el próximo rebalanceo.
              </li>
              <li>
                <b>Vendé</b> los papeles que tengas y aparezcan en “Vender”: quedaron fuera de los primeros {zone} (la zona de permanencia
                = {topN} × colchón).
              </li>
              <li>
                <b>Mantené</b> los de “Mantener”, aunque ya no estén entre los primeros {topN}: mientras sigan dentro de los primeros {zone},
                venderlos solo generaría comisiones.
              </li>
              <li>
                <b>Comprá</b> los de “Comprar” hasta tener {topN} papeles en total, con el monto de cada uno = capital × peso. No hace
                falta rebalancear el peso de los que mantenés salvo que uno se haya duplicado respecto de su peso objetivo. En CEDEARs,
                revisá el desvío de CCL en el Ranking: evitá comprar un CEDEAR con el dólar implícito muy caro.
              </li>
              <li>
                <b>Registrá las operaciones</b> en Mi cartera (importando el Excel de movimientos de Balanz) para que el próximo mes el
                panel compare contra lo que realmente tenés.
              </li>
              <li>
                <b>Aguantá los años malos.</b>
                {row
                  ? ` Con ${topN} papeles la peor caída histórica fue ${pct(row.full.max_drawdown, 0)} y le ganó al universo en ${row.full.years_beat_universe} de ${row.full.years} años: hubo ${row.full.years - (row.full.years_beat_universe ?? 0)} años peores que el promedio.`
                  : " Todas las estrategias tuvieron años de −10% a −40% y años por debajo del índice."}{" "}
                Abandonar después de uno malo es la forma más común de perder la ventaja.
              </li>
            </ol>
            <p className="text-xs text-muted-foreground">
              Los resultados históricos no garantizan los futuros, no incluyen impuestos y suponen el costo por operación elegido. No es
              una recomendación de inversión.
            </p>
          </div>
        </CardContent>
      )}
    </Card>
  );
}

export function TodayPlan({ data, rebalance, buffer }: { data: BacktestResult; rebalance: number; buffer: number }) {
  const plan = data.plan;
  const [capital, saveCapital] = useStored("qb-capital", "");
  if (!plan) return null;
  const cap = Number(capital.replace(/\./g, "").replace(",", ".")) || 0;
  const rows = [...plan.picks].sort((a, b) => Number(a.held) - Number(b.held) || b.weight - a.weight);
  const nBuy = rows.filter((r) => !r.held).length;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Qué hacer hoy</CardTitle>
        <CardDescription>
          Con datos al {plan.as_of}. Rebalanceo {rebalance === 20 ? "mensual" : rebalance === 60 ? "trimestral" : "semestral"} · zona de
          permanencia: primeros {plan.keep_zone.length}
          {buffer > 1 ? ` (colchón ×${String(buffer).replace(".", ",")})` : ""}.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 text-xs">
        {plan.out_of_market ? (
          <p className="rounded-md border border-warning/40 bg-warning/10 p-3">
            <b className="text-warning">Filtro de mercado activo:</b> el SPY está en etapa {plan.benchmark_stage}. La estrategia indica
            estar en liquidez hasta el próximo rebalanceo.
          </p>
        ) : (
          <>
            <p className="text-muted-foreground">
              El porcentaje es el <b>peso objetivo</b> de cada papel: la parte del capital que destinás a la estrategia. Los pesos de la
              cartera objetivo ({rows.length} papeles) suman 100%: los que ya tenés y se mantienen ocupan lugares, y se compran solo los{" "}
              {nBuy} que faltan.
              {!plan.has_portfolio && (
                <>
                  {" "}
                  Cargá tu cartera en <a className="underline" href="/cartera">Mi cartera</a> para ver qué mantener y qué vender.
                </>
              )}
            </p>
            <label className="flex flex-wrap items-center gap-2">
              <span>Capital destinado a la estrategia (ARS):</span>
              <Input className="h-8 w-44" inputMode="decimal" placeholder="Ej.: 5.000.000" value={capital} onChange={(e) => saveCapital(e.target.value)} />
            </label>
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead>Papel</TableHead>
                    <TableHead>Acción</TableHead>
                    <TableHead className="text-right">Peso</TableHead>
                    <TableHead className="text-right">Precio ARS</TableHead>
                    <TableHead className="text-right">Monto objetivo</TableHead>
                    <TableHead className="text-right">Cantidad objetivo</TableHead>
                    {plan.has_portfolio && <TableHead className="text-right">Tenés</TableHead>}
                  </TableRow>
                </TableHeader>
                <TableBody className="tabular">
                  {rows.map((r) => {
                    const amount = cap * r.weight;
                    const qty = r.price_ars ? Math.floor(amount / r.price_ars) : null;
                    return (
                      <TableRow key={r.ticker}>
                        <TableCell>
                          <a href={`/asset/${r.ticker}`} className="font-medium hover:text-primary" title={r.name ?? ""}>
                            {r.ticker}
                          </a>
                        </TableCell>
                        <TableCell className={r.held ? "text-muted-foreground" : "text-positive"}>{r.held ? "Mantener" : "Comprar"}</TableCell>
                        <TableCell className="text-right">{fmtProb(r.weight, 1)}</TableCell>
                        <TableCell className="text-right">{fmtMoney(r.price_ars, "ARS")}</TableCell>
                        <TableCell className="text-right">{cap ? fmtMoney(amount, "ARS", 0) : "—"}</TableCell>
                        <TableCell className="text-right">{cap && qty !== null ? fmtNumber(qty, 0) : "—"}</TableCell>
                        {plan.has_portfolio && (
                          <TableCell className="text-right text-muted-foreground">
                            {r.quantity_held != null ? fmtNumber(r.quantity_held, 0) : "—"}
                          </TableCell>
                        )}
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
            {plan.sell.length > 0 && (
              <PlanList title="Vender (salieron de la zona de permanencia)" tone="neg" items={plan.sell} />
            )}
            <p className="text-muted-foreground">
              La cantidad objetivo redondea hacia abajo (CEDEARs o acciones enteras), así que puede sobrar algo de efectivo. En los que
              mantenés no hace falta ajustar la cantidad salvo que estén muy lejos del objetivo (por ejemplo, el doble o la mitad):
              cada ajuste cuesta comisión.
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function PlanList({
  title,
  items,
  tone,
}: {
  title: string;
  items: { ticker: string; name: string | null; w?: number }[];
  tone?: "pos" | "neg";
}) {
  if (!items.length) return null;
  return (
    <div className="space-y-1">
      <p className={cn("font-medium", tone === "pos" && "text-positive", tone === "neg" && "text-negative")}>
        {title} ({items.length})
      </p>
      <div className="flex flex-wrap gap-1.5">
        {items.map((p) => (
          <a key={p.ticker} href={`/asset/${p.ticker}`} title={p.name ?? ""} className="rounded-md border px-2 py-1 font-medium hover:border-primary">
            {p.ticker}
            {p.w != null && <span className="ml-1 font-normal text-muted-foreground">{fmtProb(p.w, 1)}</span>}
          </a>
        ))}
      </div>
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

function Results({ data, rebalance, buffer }: { data: BacktestResult; rebalance: number; buffer: number }) {
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

      <div className="grid gap-4">
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
      </div>

      <TodayPlan data={data} rebalance={rebalance} buffer={buffer} />

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
