"use client";

import { Trash2, Upload } from "lucide-react";
import Link from "next/link";
import { useRef, useState } from "react";
import useSWR from "swr";

import { PressureBadge } from "@/components/events-shared";
import { RangeBar } from "@/components/price-range";
import { StageBadge } from "@/components/stage-badge";
import { ErrorState, LoadingState } from "@/components/state";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, fetcher, type ImportSummary, type PortfolioResponse } from "@/lib/api";
import { fmtMoney, fmtNumber, fmtProb, fmtReturn } from "@/lib/format";
import { cn } from "@/lib/utils";

const H_LABEL: Record<string, string> = { "20": "1 mes", "60": "3 meses", "120": "6 meses" };

export function PortfolioView() {
  const { data, error, mutate } = useSWR<PortfolioResponse>("/api/portfolio", fetcher);
  if (error) return <ErrorState error={error} />;
  if (!data) return <LoadingState />;
  const s = data.summary;
  const empty = data.holdings.length === 0;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Mi cartera</h1>
        <p className="max-w-3xl text-sm text-muted-foreground">
          Tus tenencias valuadas al último cierre de BYMA, con su resultado en dólares MEP, el diagnóstico de cada papel y el
          riesgo de la cartera en conjunto. Los datos quedan solo en tu computadora.
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <ImportCard onDone={() => mutate()} />
        <AddCard onDone={() => mutate()} />
      </div>

      {empty ? (
        <p className="text-sm text-muted-foreground">Todavía no cargaste tenencias.</p>
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Kpi title="Valor de la cartera" value={fmtMoney(s.value_usd, "USD")} sub={`${fmtMoney(s.value_ars, "ARS")} · MEP ${fmtMoney(s.mep, "ARS")}`} />
            <Kpi
              title="Resultado (precio)"
              value={s.pnl_usd === null ? "—" : `${s.pnl_usd >= 0 ? "+" : ""}${fmtMoney(s.pnl_usd, "USD")}`}
              sub={s.pnl_pct === null ? "Cargá el costo para verlo" : `${fmtReturn(s.pnl_pct)} sobre ${fmtMoney(s.cost_usd, "USD")} invertidos`}
              tone={s.pnl_usd === null ? undefined : s.pnl_usd >= 0 ? "pos" : "neg"}
            />
            <Kpi title="Dividendos cobrados" value={fmtMoney(s.income_usd, "USD")} sub="Según los movimientos importados" />
            <Kpi
              title="Prob. de suba a 3 meses"
              value={fmtProb(s.prob_up_60)}
              sub={`Promedio ponderado · mayor posición ${fmtProb(s.top_weight)}`}
            />
          </div>

          <HoldingsTable data={data} onChange={() => mutate()} />

          <div className="grid gap-4 lg:grid-cols-3">
            <RiskCard data={data} />
            <SectorsCard data={data} />
            <EventsCard data={data} />
          </div>
        </>
      )}
    </div>
  );
}

function Kpi({ title, value, sub, tone }: { title: string; value: string; sub: string; tone?: "pos" | "neg" }) {
  return (
    <Card>
      <CardHeader>
        <CardDescription>{title}</CardDescription>
        <CardTitle className={cn("tabular text-xl", tone === "pos" && "text-positive", tone === "neg" && "text-negative")}>{value}</CardTitle>
      </CardHeader>
      <CardContent className="pt-0 text-xs text-muted-foreground">{sub}</CardContent>
    </Card>
  );
}

function ImportCard({ onDone }: { onDone: () => void }) {
  const ref = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<ImportSummary | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [replace, setReplace] = useState(true);

  async function upload(file: File) {
    setBusy(true);
    setErr(null);
    setMsg(null);
    try {
      setMsg(await api.importPortfolio(file, replace));
      onDone();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
      if (ref.current) ref.current.value = "";
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Importar desde Balanz o un archivo</CardTitle>
        <CardDescription>
          Excel de <b>Movimientos</b> de Balanz (reconstruye cantidades, costo promedio en MEP y dividendos) o un CSV con
          columnas Ticker, Cantidad, Precio y Moneda.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <div className="flex flex-wrap items-center gap-3">
          <input ref={ref} type="file" accept=".xlsx,.xls,.csv" className="hidden" onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
          <Button size="sm" onClick={() => ref.current?.click()} disabled={busy}>
            <Upload className="size-4" />
            {busy ? "Importando…" : "Elegir archivo"}
          </Button>
          <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <input type="checkbox" checked={replace} onChange={(e) => setReplace(e.target.checked)} />
            Reemplazar la cartera actual
          </label>
        </div>
        {err && <p className="text-xs text-negative">{err}</p>}
        {msg && (
          <div className="text-xs text-muted-foreground">
            <p className="text-positive">
              {msg.positions} posiciones importadas ({msg.kind === "balanz" ? "movimientos de Balanz" : "tenencias"}, {msg.rows_used} filas usadas).
            </p>
            {msg.outside_universe.length > 0 && <p>Fuera del universo analizado (sin precio): {msg.outside_universe.join(", ")}.</p>}
            {msg.warnings.map((w) => (
              <p key={w}>⚠ {w}</p>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function AddCard({ onDone }: { onDone: () => void }) {
  const [ticker, setTicker] = useState("");
  const [qty, setQty] = useState("");
  const [price, setPrice] = useState("");
  const [currency, setCurrency] = useState<"ARS" | "USD">("ARS");
  const [day, setDay] = useState("");
  const [err, setErr] = useState<string | null>(null);

  async function save() {
    setErr(null);
    const q = Number(qty.replace(",", "."));
    const p = price ? Number(price.replace(/\./g, "").replace(",", ".")) : undefined;
    if (!ticker || !(q > 0)) return setErr("Completá ticker y cantidad");
    try {
      await api.saveHolding({ ticker, quantity: q, price: p, currency, opened_at: day || undefined });
      setTicker("");
      setQty("");
      setPrice("");
      onDone();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Agregar o editar una tenencia</CardTitle>
        <CardDescription>Si el ticker ya está en la cartera, se reemplaza. El precio es el promedio de compra (opcional).</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-wrap items-end gap-2 text-sm">
        <Input className="w-24" placeholder="Ticker" value={ticker} onChange={(e) => setTicker(e.target.value.toUpperCase())} />
        <Input className="w-24" placeholder="Cantidad" inputMode="decimal" value={qty} onChange={(e) => setQty(e.target.value)} />
        <Input className="w-28" placeholder="Precio prom." inputMode="decimal" value={price} onChange={(e) => setPrice(e.target.value)} />
        <Select value={currency} onChange={(e) => setCurrency(e.target.value as "ARS" | "USD")}>
          <option value="ARS">ARS</option>
          <option value="USD">USD (MEP)</option>
        </Select>
        <Input className="w-36" type="date" value={day} onChange={(e) => setDay(e.target.value)} title="Fecha de compra (para convertir el costo al MEP de ese día)" />
        <Button size="sm" onClick={save}>
          Guardar
        </Button>
        {err && <p className="w-full text-xs text-negative">{err}</p>}
      </CardContent>
    </Card>
  );
}

function HoldingsTable({ data, onChange }: { data: PortfolioResponse; onChange: () => void }) {
  const rows = [...data.holdings].sort((a, b) => (b.value_usd ?? -1) - (a.value_usd ?? -1));
  return (
    <Card>
      <CardContent className="overflow-x-auto p-0">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead>Activo</TableHead>
              <TableHead className="text-right">Cantidad</TableHead>
              <TableHead className="text-right">Valor (USD MEP)</TableHead>
              <TableHead className="text-right">Peso</TableHead>
              <TableHead className="text-right">Resultado</TableHead>
              <TableHead>Etapa</TableHead>
              <TableHead className="text-right">P(suba) 3M</TableHead>
              <TableHead>Rango 3M</TableHead>
              <TableHead>Noticias</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody className="tabular">
            {rows.map((h) => (
              <TableRow key={h.id}>
                <TableCell>
                  {h.in_universe ? (
                    <Link href={`/asset/${h.ticker}`} className="font-medium hover:text-primary">
                      {h.ticker}
                    </Link>
                  ) : (
                    <span className="font-medium">{h.ticker}</span>
                  )}
                  <p className="max-w-44 truncate text-xs text-muted-foreground">
                    {h.in_universe ? `${h.name ?? ""} · ${h.sector ?? ""}` : "Fuera del universo analizado"}
                  </p>
                </TableCell>
                <TableCell className="text-right">{fmtNumber(h.quantity, h.quantity % 1 ? 2 : 0)}</TableCell>
                <TableCell className="text-right">
                  {fmtMoney(h.value_usd, "USD")}
                  <p className="text-xs text-muted-foreground">{fmtMoney(h.value_ars, "ARS", 0)}</p>
                </TableCell>
                <TableCell className="text-right">{fmtProb(h.weight, 1)}</TableCell>
                <TableCell className={cn("text-right", (h.pnl_usd ?? 0) > 0 && "text-positive", (h.pnl_usd ?? 0) < 0 && "text-negative")}>
                  {h.pnl_usd === null ? "—" : fmtMoney(h.pnl_usd, "USD")}
                  <p className="text-xs">{fmtReturn(h.pnl_pct)}</p>
                </TableCell>
                <TableCell>
                  <StageBadge stage={h.stage} substate={h.substate} />
                </TableCell>
                <TableCell className="text-right">{fmtProb(h.prob_up_60)}</TableCell>
                <TableCell>
                  {h.range_low_60 != null && h.range_mid_60 != null && h.range_high_60 != null ? (
                    <div className="w-28 space-y-0.5">
                      <RangeBar r={{ p10: h.range_low_60, p25: h.range_low_60, p50: h.range_mid_60, p75: h.range_high_60, p90: h.range_high_60 }} scale={0.45} />
                      <div className="flex justify-between text-[11px]">
                        <span className="text-negative">{fmtReturn(h.range_low_60, 0)}</span>
                        <span className="text-positive">{fmtReturn(h.range_high_60, 0)}</span>
                      </div>
                    </div>
                  ) : (
                    "—"
                  )}
                </TableCell>
                <TableCell>
                  <PressureBadge label={h.news_label} />
                </TableCell>
                <TableCell>
                  <Button
                    variant="ghost"
                    size="sm"
                    aria-label={`Quitar ${h.ticker}`}
                    onClick={async () => {
                      await api.deleteHolding(h.id);
                      onChange();
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
  );
}

function RiskCard({ data }: { data: PortfolioResponse }) {
  const r = data.risk;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Riesgo de la cartera</CardTitle>
        <CardDescription>Con las correlaciones de los últimos 3 años: si los papeles se mueven distinto, el conjunto oscila menos.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {!r ? (
          <p className="text-muted-foreground">Sin historia suficiente.</p>
        ) : (
          <>
            <div className="tabular grid grid-cols-2 gap-2 text-xs">
              <div>
                <p className="text-muted-foreground">Volatilidad anual</p>
                <p className="text-base font-medium">{fmtProb(r.vol)}</p>
              </div>
              <div>
                <p className="text-muted-foreground">Promedio de cada papel</p>
                <p className="text-base font-medium">{fmtProb(r.avg_vol)}</p>
              </div>
              <div>
                <p className="text-muted-foreground">Beneficio de diversificar</p>
                <p className="text-base font-medium">{fmtProb(r.diversification)}</p>
              </div>
              <div>
                <p className="text-muted-foreground">Peor caída (3 años)</p>
                <p className="text-base font-medium text-negative">{fmtReturn(r.max_drawdown_3y)}</p>
              </div>
            </div>
            {(["20", "60", "120"] as const).map((h) =>
              r.ranges[h] ? (
                <div key={h} className="space-y-1">
                  <div className="flex justify-between text-xs">
                    <span>Rango a {H_LABEL[h]}</span>
                    <span className="tabular">
                      <span className="text-negative">{fmtReturn(r.ranges[h].p10)}</span> ·{" "}
                      <span className="text-positive">{fmtReturn(r.ranges[h].p90)}</span>
                    </span>
                  </div>
                  <RangeBar r={r.ranges[h]} scale={Math.max(Math.abs(r.ranges["120"]?.p10 ?? 0.3), r.ranges["120"]?.p90 ?? 0.3) * 1.1} />
                </div>
              ) : null,
            )}
            {r.most_correlated && (
              <p className="text-xs text-muted-foreground">
                Los más parecidos entre sí: {r.most_correlated.a} y {r.most_correlated.b} (correlación{" "}
                {fmtNumber(r.most_correlated.corr, 2)}).
              </p>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}

function SectorsCard({ data }: { data: PortfolioResponse }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Concentración por sector</CardTitle>
        <CardDescription>
          Índice de concentración {fmtNumber(data.summary.hhi, 2)} (1 = un solo papel).
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2 text-xs">
        {data.sectors.map((s) => (
          <div key={s.sector} className="space-y-0.5">
            <div className="flex justify-between">
              <span>{s.sector}</span>
              <span className="tabular">{fmtProb(s.weight, 1)}</span>
            </div>
            <div className="h-1.5 rounded bg-muted">
              <div className="h-1.5 rounded bg-primary" style={{ width: `${s.weight * 100}%` }} />
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function EventsCard({ data }: { data: PortfolioResponse }) {
  const ev = data.events;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Exposición a eventos macro</CardTitle>
        <CardDescription>Qué parte de la cartera está en sectores que históricamente reaccionaron a los eventos vigentes.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 text-xs">
        {ev.active.length === 0 && <p className="text-muted-foreground">No hay eventos macro vigentes.</p>}
        {ev.active.map((a) => (
          <div key={a.key} className="flex justify-between gap-2">
            <span>{a.name}</span>
            <span className="tabular whitespace-nowrap">
              <span className="text-positive">▲{fmtProb(a.weight_favorable)}</span> <span className="text-negative">▼{fmtProb(a.weight_unfavorable)}</span>
            </span>
          </div>
        ))}
        {ev.factors.length > 0 && (
          <div className="space-y-1 border-t pt-2">
            <p className="text-muted-foreground">Reacción semanal promedio de la cartera ante:</p>
            {ev.factors.map((f) => (
              <div key={f.factor} className="flex justify-between">
                <span>{f.label}</span>
                <span className={cn("tabular", f.impact > 0 ? "text-positive" : "text-negative")}>{fmtReturn(f.impact, 2)}</span>
              </div>
            ))}
          </div>
        )}
        <Link href="/eventos" className="block text-muted-foreground hover:text-foreground">
          Ver eventos →
        </Link>
      </CardContent>
    </Card>
  );
}
