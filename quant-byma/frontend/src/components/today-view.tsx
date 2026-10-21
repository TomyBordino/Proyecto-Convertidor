"use client";

import Link from "next/link";
import { useSyncExternalStore } from "react";
import useSWR from "swr";

import { PRESET_KEY, TodayPlan, type Preset } from "@/components/backtest-view";
import { ErrorState, LoadingState } from "@/components/state";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { ApiError, fetcher, type BacktestResult, type PresetTable } from "@/lib/api";
import { fmtReturn } from "@/lib/format";
import { useStored } from "@/lib/stored";
import { cn } from "@/lib/utils";

const LABEL: Record<Preset, string> = {
  proteccion: "Robusta con protección (recomendada)",
  robusta: "Robusta",
  base: "Básica",
};

const PARAMS: Record<Preset, Record<string, string>> = {
  robusta: { sort: "trend", stages: "1,2,3", weighting: "inv_vol", regime: "none" },
  proteccion: { sort: "trend", stages: "1,2,3", weighting: "inv_vol", regime: "spy_bear" },
  base: { sort: "score", weighting: "equal", regime: "none" },
};

/** Primer día hábil (lunes a viernes) del mes siguiente a `d`, o de este mes si todavía no pasó. */
function nextRebalance(d: Date): Date {
  const first = (y: number, m: number) => {
    const x = new Date(y, m, 1);
    while (x.getDay() === 0 || x.getDay() === 6) x.setDate(x.getDate() + 1);
    return x;
  };
  const thisMonth = first(d.getFullYear(), d.getMonth());
  if (d <= thisMonth) return thisMonth;
  return first(d.getFullYear(), d.getMonth() + 1);
}

function sameDay(a: Date, b: Date) {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

const noop = () => () => {};
// La fecha de hoy solo se conoce en el navegador (no durante el prerender del servidor).
const todayKey = () => new Date().toDateString();

function RebalanceBanner() {
  const key = useSyncExternalStore(noop, todayKey, () => null);
  if (!key) return null;
  const today = new Date(key);
  const next = nextRebalance(today);
  const isDay = sameDay(today, next);
  const fmtDate = (d: Date) => d.toLocaleDateString("es-AR", { weekday: "long", day: "numeric", month: "long" });
  return (
    <Card className={cn(isDay ? "border-positive/50 bg-positive/5" : "border-warning/40 bg-warning/5")}>
      <CardContent className="p-4 text-sm">
        {isDay ? (
          <p>
            <b className="text-positive">Hoy es día de rebalanceo.</b> Verificá que los datos estén al día (fecha de abajo), seguí la
            tabla y después importá los movimientos en Mi cartera.
          </p>
        ) : (
          <p>
            <b className="text-warning">Hoy no es día de rebalanceo.</b> El próximo es el <b>{fmtDate(next)}</b>. La tabla cambia un poco
            cada día: no hace falta operar hasta esa fecha.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

export function TodayView() {
  // Preferencias guardadas en este navegador (estrategia y cantidad de papeles).
  const [storedPreset, setPreset] = useStored("qb-preset", "proteccion");
  const [storedN, setTopNStr] = useStored("qb-topn", "30");
  const preset: Preset = storedPreset in PARAMS ? (storedPreset as Preset) : "proteccion";
  const topN = Number(storedN) || 30;

  const presets = useSWR<PresetTable>("/api/backtest/presets", fetcher);
  const row = presets.data?.presets[PRESET_KEY[preset]]?.[String(topN)];
  const buffer = row?.buffer ?? 2;
  const qs = new URLSearchParams({ top_n: String(topN), rebalance: "20", buffer: String(buffer), cost_bps: "50", ...PARAMS[preset] });
  const { data, error } = useSWR<BacktestResult>(presets.data ? `/api/backtest?${qs}` : null, fetcher);


  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Qué hacer hoy</h1>
        <p className="max-w-3xl text-sm text-muted-foreground">
          Las operaciones que indica tu estrategia con los últimos datos. Se opera una vez por mes, el primer día hábil; los demás días
          esta página es solo informativa. Para ver cómo se armó cada estrategia y sus resultados históricos, entrá a{" "}
          <Link className="underline" href="/backtest">
            Backtest
          </Link>
          .
        </p>
      </div>

      <RebalanceBanner />

      <Card>
        <CardHeader>
          <CardTitle>Tu estrategia</CardTitle>
          <CardDescription>Queda guardada en este navegador.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap items-end gap-3 text-sm">
          <div className="flex flex-wrap gap-1.5">
            {(Object.keys(LABEL) as Preset[]).map((p) => (
              <Button
                key={p}
                size="sm"
                variant={preset === p ? "secondary" : "outline"}
                onClick={() => setPreset(p)}
              >
                {LABEL[p]}
              </Button>
            ))}
          </div>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-muted-foreground">Cantidad de papeles</span>
            <Select
              value={topN}
              onChange={(e) => setTopNStr(e.target.value)}
            >
              {[5, 10, 20, 30, 50].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </Select>
          </label>
          {row && (
            <p className="text-xs text-muted-foreground">
              Historia con {topN} papeles: {fmtReturn(row.full.cagr)} anual · peor caída {fmtReturn(row.full.max_drawdown, 0)} · colchón ×
              {String(row.buffer).replace(".", ",")}.
            </p>
          )}
        </CardContent>
      </Card>

      {error instanceof ApiError && error.status === 404 ? (
        <Card>
          <CardContent className="p-4 text-sm">
            Todavía no hay historia para calcular la estrategia. Entrá a{" "}
            <Link className="underline" href="/backtest">
              Backtest
            </Link>{" "}
            y tocá “Actualizar datos ahora” (la primera vez tarda 20–30 minutos).
          </CardContent>
        </Card>
      ) : error ? (
        <ErrorState error={error} />
      ) : !data ? (
        <LoadingState label="Calculando la cartera objetivo…" />
      ) : (
        <TodayPlan data={data} rebalance={20} buffer={buffer} strategy={{ name: LABEL[preset], preset }} />
      )}

      <Card>
        <CardHeader>
          <CardTitle>La rutina, paso a paso</CardTitle>
        </CardHeader>
        <CardContent>
          <ol className="list-decimal space-y-1.5 pl-5 text-xs">
            <li>El primer día hábil del mes, abrí la plataforma y esperá a que la fecha “Con datos al” sea la última rueda.</li>
            <li>Ingresá el capital destinado a la estrategia: la tabla calcula monto y cantidad de cada papel.</li>
            <li>Si aparece “Filtro de mercado activo”, vendé todo y quedate en liquidez en dólares hasta el mes siguiente.</li>
            <li>Si no: vendé lo de “Vender”, dejá lo de “Mantener” y comprá lo de “Comprar” con las cantidades indicadas.</li>
            <li>
              Exportá el Excel de Movimientos de Balanz e importalo en{" "}
              <Link className="underline" href="/cartera">
                Mi cartera
              </Link>
              , para que el mes siguiente esta página sepa qué tenés.
            </li>
          </ol>
        </CardContent>
      </Card>
    </div>
  );
}
