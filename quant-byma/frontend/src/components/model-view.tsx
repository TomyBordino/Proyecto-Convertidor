"use client";

import { useState } from "react";
import { Bar, CartesianGrid, ComposedChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
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
  const calib = (r?.calibration ?? []).map((c) => ({ decile: c.decile, observed: c.observed * 100, n: c.n }));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Modelo y validación</h1>
        <p className="max-w-3xl text-sm text-muted-foreground">
          El puntaje es un modelo de factores con pesos fijos (50% tendencia, 50% valuación) y la probabilidad es su
          calibración contra lo que pasó realmente, con {data.n_assets} activos entre {data.first_date} y {data.last_date}.
          Cada año se califica con una calibración ajustada solo con años anteriores (walk-forward, con embargo), y todas
          las métricas de esta página salen de esas predicciones fuera de muestra. Un 60% significa que, en el pasado,
          situaciones con ese puntaje subieron 6 de cada 10 veces.
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
          <p className={r.has_skill ? "text-sm text-positive" : "text-sm text-warning"}>
            {r.has_skill
              ? `Ventaja demostrada a ${H_LABEL[h]}: supera a la tasa base fuera de muestra (AUC > 0,5 en ${r.years_auc_above_half} de ${r.by_year?.length} años).`
              : `Sin ventaja demostrada a ${H_LABEL[h]}: en este horizonte se informa la tasa base en lugar de una probabilidad del modelo.`}
          </p>
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
                <CardTitle>Acierto por decil de puntaje</CardTitle>
                <CardDescription>
                  Frecuencia de suba observada fuera de muestra en cada décimo del puntaje (1 = peor, 10 = mejor), sobre{" "}
                  {r.oos_samples?.toLocaleString("es-AR")} predicciones ({r.oos_years?.[0]}–{r.oos_years?.at(-1)}). La línea
                  es la tasa base.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={280}>
                  <ComposedChart data={calib} margin={{ left: 0, right: 12, top: 8 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                    <XAxis dataKey="decile" tick={axis} />
                    <YAxis domain={[40, 70]} tick={axis} unit="%" width={44} />
                    <Tooltip
                      contentStyle={{ background: "var(--card)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 }}
                      formatter={(v, name) => [`${Number(v).toFixed(1)}%`, name === "observed" ? "Subió" : "Retorno mediano"]}
                      labelFormatter={(d) => `Decil ${d}`}
                    />
                    <ReferenceLine y={(r.base_rate ?? 0) * 100} stroke="var(--muted-foreground)" strokeDasharray="4 4" />
                    <Bar dataKey="observed" fill="#3e9fff" radius={[3, 3, 0, 0]} />
                  </ComposedChart>
                </ResponsiveContainer>
                <p className="mt-2 text-xs text-muted-foreground">
                  La señal es más fuerte en los deciles bajos: sirve sobre todo para evitar los activos más débiles.
                </p>
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
              <CardTitle>Estabilidad año por año</CardTitle>
              <CardDescription>
                AUC fuera de muestra de cada año (0,5 = azar). Los años flojos de la tendencia suelen ser rebotes
                posteriores a crisis, cuando la valuación compensa.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <YearBars rows={r.by_year ?? []} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Composición del puntaje</CardTitle>
              <CardDescription>Pesos fijos, elegidos por evidencia académica y no ajustados a estos datos.</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-4 text-sm sm:grid-cols-2">
              <div>
                <p className="font-medium">Tendencia · {fmtProb(r.weights?.trend)}</p>
                <ul className="mt-1 list-disc pl-5 text-muted-foreground">
                  {(r.weights?.trend_factors ?? []).map((f) => (
                    <li key={f}>{data.features[f] ?? f}</li>
                  ))}
                </ul>
              </div>
              <div>
                <p className="font-medium">Valuación · {fmtProb(r.weights?.value)} (si hay balances)</p>
                <ul className="mt-1 list-disc pl-5 text-muted-foreground">
                  {(r.weights?.value_factors ?? []).map((f) => (
                    <li key={f}>{data.features[f] ?? f}</li>
                  ))}
                </ul>
              </div>
            </CardContent>
          </Card>
        </>
      )}

      <Card>
        <CardContent className="space-y-2 p-4 text-xs text-muted-foreground">
          <p>
            <b className="text-foreground">Por qué factores fijos.</b> Con estos datos se probaron regresión logística y
            gradient boosting con muchas variables: ninguno le ganó a la tasa base fuera de muestra. Los factores clásicos
            de tendencia y valuación sí, y se compensan entre sí («Value and Momentum Everywhere», Asness, Moskowitz y
            Pedersen, 2013). Los balances cuentan recién 100 días después del cierre del ejercicio, para no usar datos que
            el mercado todavía no tenía.
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

function YearBars({ rows }: { rows: { year: number; auc: number; n: number }[] }) {
  return (
    <div className="flex h-40 items-end gap-1">
      {rows.map((r) => {
        const d = r.auc - 0.5;
        const h = Math.min(100, (Math.abs(d) / 0.15) * 100);
        return (
          <div key={r.year} className="flex h-full flex-1 flex-col items-center justify-end" title={`${r.year}: AUC ${r.auc.toFixed(3)} (n=${r.n})`}>
            <div className="flex h-1/2 w-full items-end">
              {d > 0 && <div className="w-full rounded-t-sm bg-positive" style={{ height: `${h}%` }} />}
            </div>
            <div className="h-px w-full bg-border" />
            <div className="flex h-1/2 w-full items-start">
              {d < 0 && <div className="w-full rounded-b-sm bg-negative" style={{ height: `${h}%` }} />}
            </div>
            <span className="mt-1 text-[10px] text-muted-foreground">{String(r.year).slice(2)}</span>
          </div>
        );
      })}
    </div>
  );
}
