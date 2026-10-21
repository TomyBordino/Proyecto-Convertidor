"use client";

import { Trash2 } from "lucide-react";
import Link from "next/link";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import useSWR from "swr";

import { ErrorState, LoadingState } from "@/components/state";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, fetcher, type TrackingReport } from "@/lib/api";
import { fmtMoney, fmtNumber, fmtProb, fmtReturn } from "@/lib/format";
import { cn } from "@/lib/utils";

const axis = { fontSize: 11, fill: "var(--muted-foreground)" };

export function TrackingView() {
  const { data, error, mutate } = useSWR<TrackingReport>("/api/tracking", fetcher);
  if (error) return <ErrorState error={error} />;
  if (!data) return <LoadingState />;
  const s = data.summary;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Seguimiento de la estrategia</h1>
        <p className="max-w-3xl text-sm text-muted-foreground">
          La prueba real: cada cartera guardada en “Qué hacer hoy” se compra (en papel) a los precios de BYMA de ese día y se mantiene
          hasta el siguiente rebalanceo guardado. El rendimiento se encadena mes a mes y se compara con el SPY y con el promedio del
          universo desde la misma fecha. Son datos que el backtest nunca vio.
        </p>
      </div>

      {!s ? (
        <Card>
          <CardContent className="space-y-2 p-4 text-sm">
            <p className="font-medium">Todavía no guardaste ninguna cartera.</p>
            <ol className="list-decimal space-y-1 pl-5 text-xs text-muted-foreground">
              <li>
                Entrá a{" "}
                <Link className="underline" href="/hoy">
                  Qué hacer hoy
                </Link>
                , ingresá el capital y tocá <b>“Guardar para seguimiento”</b>.
              </li>
              <li>Cada primer día hábil del mes, volvé a guardar la cartera nueva: así el seguimiento refleja los rebalanceos.</li>
              <li>Volvé a esta página cuando quieras: se actualiza sola con cada actualización de datos.</li>
            </ol>
          </CardContent>
        </Card>
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Kpi title="Estrategia (USD CCL)" value={fmtReturn(s.return_usd)} tone={s.return_usd} sub={`Desde el ${s.start} · ${s.days} días`} />
            <Kpi
              title="vs SPY"
              value={s.spy == null || s.return_usd == null ? "—" : fmtReturn(s.return_usd - s.spy)}
              tone={s.spy == null || s.return_usd == null ? null : s.return_usd - s.spy}
              sub={`SPY ${fmtReturn(s.spy)}`}
            />
            <Kpi
              title="vs promedio del universo"
              value={s.universe == null || s.return_usd == null ? "—" : fmtReturn(s.return_usd - s.universe)}
              tone={s.universe == null || s.return_usd == null ? null : s.return_usd - s.universe}
              sub={`Universo ${fmtReturn(s.universe)}`}
            />
            <Kpi title="En pesos" value={fmtReturn(s.return_ars)} tone={s.return_ars} sub={`Valor actual ${fmtMoney(s.value_ars, "ARS", 0)}`} />
          </div>

          <Card className={cn(s.days < 180 && "border-warning/40")}>
            <CardContent className="p-4 text-xs text-muted-foreground">
              {s.days < 180
                ? `Con ${s.days} días todavía no se puede sacar una conclusión: en el backtest, la estrategia quedó por debajo del universo en alrededor de la mitad de los meses y aun así le ganó en el largo plazo. Para juzgarla hacen falta al menos 6–12 meses (y mejor, varios años).`
                : "Compará el resultado con lo que esperaba el backtest: una ventaja chica sobre el universo, con menos caída en los momentos malos. Un año por debajo no invalida la estrategia; varios años seguidos, sí son una señal."}{" "}
              Los datos se actualizan al {s.as_of}.
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Evolución de 100 (en USD)</CardTitle>
              <CardDescription>Estrategia en dólares CCL, SPY en dólares y promedio del universo con igual peso, desde el mismo día.</CardDescription>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={data.series}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                  <XAxis dataKey="time" tick={axis} minTickGap={40} />
                  <YAxis tick={axis} domain={["auto", "auto"]} width={45} />
                  <Tooltip formatter={(v) => fmtNumber(Number(v), 1)} />
                  <Legend />
                  <Line dataKey="strategy" name="Estrategia" stroke="#3e9fff" dot={false} strokeWidth={2} isAnimationActive={false} />
                  <Line dataKey="spy" name="SPY" stroke="#f5a524" dot={false} strokeWidth={1.5} isAnimationActive={false} />
                  <Line dataKey="universe" name="Universo" stroke="#8e8cf2" dot={false} strokeWidth={1.5} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Cartera actual</CardTitle>
              <CardDescription>Rendimiento de cada papel desde que entró en el último rebalanceo guardado.</CardDescription>
            </CardHeader>
            <CardContent className="overflow-x-auto p-0">
              <Table>
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead>Papel</TableHead>
                    <TableHead className="text-right">Cantidad</TableHead>
                    <TableHead className="text-right">Precio de entrada</TableHead>
                    <TableHead className="text-right">Precio actual</TableHead>
                    <TableHead className="text-right">En pesos</TableHead>
                    <TableHead className="text-right">En USD CCL</TableHead>
                    <TableHead className="text-right">Peso objetivo → actual</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody className="tabular">
                  {data.positions.map((p) => (
                    <TableRow key={p.ticker}>
                      <TableCell>
                        <Link href={`/asset/${p.ticker}`} className="font-medium hover:text-primary">
                          {p.ticker}
                        </Link>
                      </TableCell>
                      <TableCell className="text-right">{fmtNumber(p.quantity, 0)}</TableCell>
                      <TableCell className="text-right">{fmtMoney(p.entry_price_ars, "ARS")}</TableCell>
                      <TableCell className="text-right">{fmtMoney(p.price_ars, "ARS")}</TableCell>
                      <TableCell className={cn("text-right", (p.return_ars ?? 0) >= 0 ? "text-positive" : "text-negative")}>
                        {fmtReturn(p.return_ars)}
                      </TableCell>
                      <TableCell className={cn("text-right font-medium", (p.return_usd ?? 0) >= 0 ? "text-positive" : "text-negative")}>
                        {fmtReturn(p.return_usd)}
                      </TableCell>
                      <TableCell className="text-right text-muted-foreground">
                        {fmtProb(p.weight_target, 1)} → {fmtProb(p.weight_now, 1)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Rebalanceos guardados</CardTitle>
              <CardDescription>Cada fila es un período: desde que se guardó hasta el siguiente (o hasta hoy).</CardDescription>
            </CardHeader>
            <CardContent className="overflow-x-auto p-0">
              <Table>
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead>Desde</TableHead>
                    <TableHead>Hasta</TableHead>
                    <TableHead>Estrategia</TableHead>
                    <TableHead className="text-right">Papeles</TableHead>
                    <TableHead className="text-right">Capital</TableHead>
                    <TableHead className="text-right">USD CCL</TableHead>
                    <TableHead className="text-right">Pesos</TableHead>
                    <TableHead />
                  </TableRow>
                </TableHeader>
                <TableBody className="tabular">
                  {[...data.periods].reverse().map((p) => (
                    <TableRow key={p.id}>
                      <TableCell>{p.start}</TableCell>
                      <TableCell>{p.end}</TableCell>
                      <TableCell className="text-muted-foreground">{String(p.strategy?.name ?? "—")}</TableCell>
                      <TableCell className="text-right">{p.positions}</TableCell>
                      <TableCell className="text-right">{fmtMoney(p.capital_ars, "ARS", 0)}</TableCell>
                      <TableCell className={cn("text-right", (p.return_usd ?? 0) >= 0 ? "text-positive" : "text-negative")}>
                        {fmtReturn(p.return_usd)}
                      </TableCell>
                      <TableCell className="text-right">{fmtReturn(p.return_ars)}</TableCell>
                      <TableCell>
                        <Button
                          variant="ghost"
                          size="sm"
                          aria-label={`Borrar el período del ${p.start}`}
                          onClick={async () => {
                            if (!confirm(`¿Borrar el rebalanceo del ${p.start}?`)) return;
                            await api.deleteTracking(p.id);
                            mutate();
                          }}
                        >
                          <Trash2 className="size-4" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

function Kpi({ title, value, sub, tone }: { title: string; value: string; sub: string; tone: number | null }) {
  return (
    <Card>
      <CardHeader>
        <CardDescription>{title}</CardDescription>
        <CardTitle className={cn("tabular text-xl", tone != null && tone > 0 && "text-positive", tone != null && tone < 0 && "text-negative")}>
          {value}
        </CardTitle>
      </CardHeader>
      <CardContent className="pt-0 text-xs text-muted-foreground">{sub}</CardContent>
    </Card>
  );
}
