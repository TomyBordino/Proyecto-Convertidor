"use client";

import { useState } from "react";
import {
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import useSWR from "swr";

import { ErrorState, LoadingState } from "@/components/state";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { fetcher, type ModelReport } from "@/lib/api";
import { fmtNumber, fmtProb, fmtReturn, STAGE_SHORT } from "@/lib/format";

const H_LABEL: Record<string, string> = { "20": "1 mes", "60": "3 meses", "120": "6 meses" };
const axis = { fontSize: 11, fill: "var(--muted-foreground)" };

export function ModelView() {
  const { data, error } = useSWR<ModelReport>("/api/model", fetcher);
  const [h, setH] = useState("60");
  if (error) return <ErrorState error={error} />;
  if (!data) return <LoadingState />;
  const r = data.horizons[h];
  const calib = (r?.calibration ?? []).map((c) => ({ pred: c.pred * 100, observed: c.observed * 100, n: c.n }));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Modelo y validación</h1>
        <p className="max-w-3xl text-sm text-muted-foreground">
          Las probabilidades salen de una regresión logística entrenada con {data.n_assets} activos entre {data.first_date} y{" "}
          {data.last_date}. Cada año se predice con un modelo entrenado solo con años anteriores (walk-forward, con un
          período de embargo), y todas las métricas de esta página se calculan sobre esas predicciones fuera de muestra.
          Luego se calibra con regresión isotónica: un 60% significa que, en el pasado, situaciones con ese puntaje
          subieron 6 de cada 10 veces.
        </p>
      </div>

      <div className="flex gap-1">
        {Object.keys(data.horizons).map((k) => (
          <Button key={k} size="sm" variant={h === k ? "secondary" : "ghost"} onClick={() => setH(k)}>
            {H_LABEL[k] ?? `${k} ruedas`}
          </Button>
        ))}
      </div>

      {r?.status !== "ok" ? (
        <Card>
          <CardContent className="p-4 text-sm text-muted-foreground">Modelo no disponible: {r?.status}</CardContent>
        </Card>
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Metric
              title="Tasa base"
              value={fmtProb(r.base_rate)}
              hint="Frecuencia con que un activo cualquiera estuvo más alto al final del horizonte"
            />
            <Metric
              title="AUC fuera de muestra"
              value={fmtNumber(r.auc, 3)}
              hint="0,5 = azar · 1 = perfecto. Para retornos de acciones, 0,55–0,60 ya es una ventaja útil"
            />
            <Metric
              title="Quintil superior vs inferior"
              value={`${fmtProb(r.top_quintile_hit)} vs ${fmtProb(r.bottom_quintile_hit)}`}
              hint={`Acierto del 20% mejor y peor puntuado · retorno mediano ${fmtReturn(r.top_quintile_median_return)} vs ${fmtReturn(r.bottom_quintile_median_return)}`}
            />
            <Metric
              title="Brier skill score"
              value={fmtNumber(r.brier_skill, 3)}
              hint="Mejora del error cuadrático vs predecir siempre la tasa base (> 0 es mejor que la base)"
            />
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Calibración (sin recalibrar)</CardTitle>
                <CardDescription>
                  Probabilidad predicha vs frecuencia observada por decil, {r.oos_samples?.toLocaleString("es-AR")} predicciones
                  fuera de muestra ({r.oos_years?.[0]}–{r.oos_years?.at(-1)}). La diagonal es la calibración perfecta.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={280}>
                  <ComposedChart data={calib} margin={{ left: 0, right: 12, top: 8 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                    <XAxis type="number" dataKey="pred" domain={[20, 90]} tick={axis} unit="%" name="Predicha" />
                    <YAxis type="number" dataKey="observed" domain={[20, 90]} tick={axis} unit="%" width={44} name="Observada" />
                    <Tooltip
                      contentStyle={{ background: "var(--card)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 }}
                      formatter={(v) => `${Number(v).toFixed(1)}%`}
                    />
                    <Line
                      data={[{ pred: 20, observed: 20 }, { pred: 90, observed: 90 }]}
                      dataKey="observed"
                      stroke="var(--muted-foreground)"
                      strokeDasharray="4 4"
                      dot={false}
                      legendType="none"
                    />
                    <Scatter dataKey="observed" fill="#3e9fff" />
                  </ComposedChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Desempeño histórico por etapa</CardTitle>
                <CardDescription>
                  Frecuencia de suba a {H_LABEL[h]} según la etapa en que estaba el activo, en todo el universo.
                </CardDescription>
              </CardHeader>
              <CardContent className="p-0">
                <Table>
                  <TableHeader>
                    <TableRow className="hover:bg-transparent">
                      <TableHead>Etapa</TableHead>
                      <TableHead className="text-right">Subió</TableHead>
                      <TableHead className="text-right">IC95</TableHead>
                      <TableHead className="text-right">Ret. mediano</TableHead>
                      <TableHead className="text-right">n efectivo</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody className="tabular">
                    {(data.stage_stats[h] ?? []).map((s) => (
                      <TableRow key={s.stage}>
                        <TableCell>
                          {s.stage} · {STAGE_SHORT[s.stage]}
                        </TableCell>
                        <TableCell className="text-right font-medium">{fmtProb(s.hit_rate, 1)}</TableCell>
                        <TableCell className="text-right text-muted-foreground">
                          {fmtProb(s.ci_low)}–{fmtProb(s.ci_high)}
                        </TableCell>
                        <TableCell className="text-right">{fmtReturn(s.median_return)}</TableCell>
                        <TableCell className="text-right text-muted-foreground">{s.n_effective.toLocaleString("es-AR")}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Peso de cada factor</CardTitle>
              <CardDescription>
                Coeficientes del modelo final sobre variables estandarizadas: positivo aumenta la probabilidad de suba.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Coefficients coefs={r.coefficients ?? {}} labels={data.features} />
            </CardContent>
          </Card>
        </>
      )}

      <Card>
        <CardContent className="space-y-2 p-4 text-xs text-muted-foreground">
          <p>
            <b className="text-foreground">Cómo leerlo.</b> El modelo estima la probabilidad de que el precio en dólares
            esté más alto al final del horizonte. Usa momentum, posición respecto de sus medias, osciladores, volatilidad,
            la etapa de Weinstein y fundamentales «point in time» (cada balance cuenta recién 100 días después del cierre
            del ejercicio, para no usar datos que el mercado todavía no tenía).
          </p>
          <p>
            <b className="text-foreground">Límites.</b> Las ventanas de retorno se superponen, por eso los intervalos usan
            un tamaño de muestra efectivo. El pasado no garantiza el futuro y la ventaja estadística sobre la tasa base es
            moderada: sirve para ordenar oportunidades, no como certeza. No es una recomendación de inversión.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

function Metric({ title, value, hint }: { title: string; value: string; hint: string }) {
  return (
    <Card>
      <CardHeader>
        <CardDescription>{title}</CardDescription>
        <CardTitle className="tabular text-xl">{value}</CardTitle>
      </CardHeader>
      <CardContent className="pt-0 text-xs text-muted-foreground">{hint}</CardContent>
    </Card>
  );
}

function Coefficients({ coefs, labels }: { coefs: Record<string, number>; labels: Record<string, string> }) {
  const rows = Object.entries(coefs).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]));
  const max = Math.max(0.01, ...rows.map(([, v]) => Math.abs(v)));
  return (
    <ul className="grid gap-x-8 gap-y-1.5 text-sm md:grid-cols-2">
      {rows.map(([k, v]) => (
        <li key={k} className="grid grid-cols-[1fr_120px_50px] items-center gap-3">
          <span className="truncate">{labels[k] ?? k}</span>
          <div className="relative h-1.5 rounded-full bg-muted">
            <div
              className={v >= 0 ? "absolute left-1/2 h-full rounded-r-full bg-positive" : "absolute right-1/2 h-full rounded-l-full bg-negative"}
              style={{ width: `${(Math.abs(v) / max) * 50}%` }}
            />
          </div>
          <span className="tabular text-right text-muted-foreground">{v.toFixed(2)}</span>
        </li>
      ))}
    </ul>
  );
}
