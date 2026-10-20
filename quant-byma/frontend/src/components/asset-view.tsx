"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";

import { AssetEventsPanel } from "@/components/asset-events";
import { DiagnosisPanel } from "@/components/diagnosis-panel";
import { FlowsChart, MultiplesChart } from "@/components/fundamentals-chart";
import { LineChart, PriceChart, type Overlays } from "@/components/price-chart";
import { PriceRangeCard } from "@/components/price-range";
import { ScoreBar } from "@/components/score-bar";
import { ScoreBreakdown } from "@/components/score-breakdown";
import { SignalBadges } from "@/components/signal-badges";
import { ErrorState, LoadingState } from "@/components/state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { fetcher, type AssetDetail, type Currency, type FundamentalsResponse, type PriceSeries } from "@/lib/api";
import { fmtMoney, fmtNumber, fmtPct, fmtRatioPct } from "@/lib/format";
import { cn } from "@/lib/utils";

const CURRENCY_LABEL: Record<Currency, string> = {
  ARS: "ARS (BYMA)",
  USD: "USD (CCL)",
  US: "Subyacente EE. UU.",
};

export function AssetView({ ticker }: { ticker: string }) {
  const [currency, setCurrency] = useState<Currency>("ARS");
  const [days, setDays] = useState(365);
  const [overlays, setOverlays] = useState<Overlays>({ sma: true, bollinger: false, rsi: true, macd: false });

  const detail = useSWR<AssetDetail>(`/api/instruments/${ticker}`, fetcher);
  const prices = useSWR<PriceSeries>(`/api/instruments/${ticker}/prices?currency=${currency}&days=${days}`, fetcher);
  const fundamentals = useSWR<FundamentalsResponse>(`/api/instruments/${ticker}/fundamentals`, fetcher);

  if (detail.error) return <ErrorState error={detail.error} />;
  if (!detail.data) return <LoadingState />;
  const d = detail.data;
  const m = d.metrics;
  const currencies: Currency[] = d.us_symbol ? ["ARS", "USD", "US"] : ["ARS", "USD"];

  return (
    <div className="space-y-6">
      <Link href="/" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-4" /> Ranking
      </Link>

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">{d.ticker}</h1>
            <Badge variant={d.kind === "CEDEAR" ? "default" : "secondary"}>{d.kind}</Badge>
            <Badge variant="outline">{d.sector}</Badge>
          </div>
          <p className="text-sm text-muted-foreground">
            {d.name}
            {d.us_symbol && d.ratio && (
              <>
                {" "}· {d.kind === "CEDEAR" ? "Subyacente" : "ADR"} {d.us_symbol} · ratio {d.ratio}:1
              </>
            )}
          </p>
          <div className="mt-2">
            <SignalBadges signals={m.signals ?? []} />
          </div>
        </div>
        <Card className="min-w-64">
          <CardHeader>
            <CardDescription>Score de revalorización</CardDescription>
            <CardTitle className="text-3xl">
              <ScoreBar score={m.composite_score ?? null} className="[&>div]:w-32 [&>span]:w-12" />
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-0 text-xs text-muted-foreground">Datos al {d.as_of ?? "—"}</CardContent>
        </Card>
      </div>

      {d.breakdown.diagnosis && <DiagnosisPanel d={d.breakdown.diagnosis} />}

      {d.breakdown.diagnosis?.ranges && (
        <PriceRangeCard ranges={d.breakdown.diagnosis.ranges} priceArs={m.price_ars} priceUsd={m.price_usd} />
      )}

      <AssetEventsPanel ticker={d.ticker} />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <Stat label="Precio BYMA" value={fmtMoney(m.price_ars, "ARS")} />
        <Stat label="Precio USD CCL" value={fmtMoney(m.price_usd, "USD", 3)} />
        <Stat label="CCL implícito" value={fmtMoney(m.implied_ccl, "ARS")} sub={`CCL mercado ${fmtMoney(d.breakdown.ccl_market, "ARS")}`} />
        <Stat
          label="Desvío CCL"
          value={fmtPct(m.ccl_dev_pct)}
          tone={m.ccl_dev_pct === null ? undefined : m.ccl_dev_pct < 0 ? "pos" : "neg"}
          sub="Negativo = dólar implícito barato"
        />
        <Stat label="RSI 14 · ATR %" value={`${fmtNumber(m.rsi14, 1)} · ${fmtNumber(m.atr_pct as number | null, 2)}%`} />
      </div>

      <Card>
        <CardHeader className="flex-row flex-wrap items-center gap-2">
          <div className="flex rounded-md border p-0.5">
            {currencies.map((c) => (
              <Toggle key={c} active={currency === c} onClick={() => setCurrency(c)}>
                {CURRENCY_LABEL[c]}
              </Toggle>
            ))}
          </div>
          <div className="flex rounded-md border p-0.5">
            {[90, 180, 365, 730].map((n) => (
              <Toggle key={n} active={days === n} onClick={() => setDays(n)}>
                {n < 365 ? `${n / 30}M` : `${n / 365}A`}
              </Toggle>
            ))}
          </div>
          <div className="ml-auto flex flex-wrap gap-1">
            {(Object.keys(overlays) as (keyof Overlays)[]).map((k) => (
              <Toggle key={k} active={overlays[k]} onClick={() => setOverlays((o) => ({ ...o, [k]: !o[k] }))}>
                {{ sma: "SMA 20/50/200", bollinger: "Bollinger", rsi: "RSI", macd: "MACD" }[k]}
              </Toggle>
            ))}
          </div>
        </CardHeader>
        <CardContent>
          {prices.error ? (
            <ErrorState error={prices.error} />
          ) : prices.data ? (
            <PriceChart data={prices.data} overlays={overlays} />
          ) : (
            <LoadingState />
          )}
        </CardContent>
      </Card>

      {prices.data && prices.data.implied_ccl.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>CCL implícito vs CCL de mercado</CardTitle>
            <CardDescription>Precio BYMA × ratio / precio en EE. UU.</CardDescription>
          </CardHeader>
          <CardContent>
            <LineChart
              series={[
                { points: prices.data.implied_ccl, color: "#f5a524", title: `CCL ${d.ticker}` },
                { points: prices.data.market_ccl, color: "#3e9fff", title: "CCL mercado" },
              ]}
            />
          </CardContent>
        </Card>
      )}

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Desglose del score cuantitativo (heurístico)</h2>
        <ScoreBreakdown detail={d} />
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Evolución de fundamentales</h2>
        {fundamentals.data && fundamentals.data.periods.length > 0 ? (
          <>
            <p className="text-xs text-muted-foreground">
              Valores en USD
              {fundamentals.data.reporting_currency === "ARS" &&
                " (balance original en ARS convertido: stocks a CCL de cierre, flujos a CCL promedio del ejercicio)"}
              .
            </p>
            <div className="grid gap-4 lg:grid-cols-2">
              <Card>
                <CardHeader>
                  <CardTitle>Resultados y caja</CardTitle>
                </CardHeader>
                <CardContent>
                  <FlowsChart periods={fundamentals.data.periods} />
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle>Múltiplos de valoración</CardTitle>
                </CardHeader>
                <CardContent>
                  <MultiplesChart periods={fundamentals.data.periods} />
                </CardContent>
              </Card>
            </div>
            <Card>
              <CardContent className="p-0">
                <FundamentalsTable data={fundamentals.data} />
              </CardContent>
            </Card>
          </>
        ) : (
          <p className="text-sm text-muted-foreground">
            {fundamentals.data ? "Sin balances disponibles (ETF o sin cobertura del proveedor)." : "Cargando…"}
          </p>
        )}
      </section>
    </div>
  );
}

function Toggle({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <Button
      variant={active ? "secondary" : "ghost"}
      size="sm"
      onClick={onClick}
      className={cn("h-7", active && "font-semibold")}
      aria-pressed={active}
    >
      {children}
    </Button>
  );
}

function Stat({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: "pos" | "neg" }) {
  return (
    <Card>
      <CardHeader>
        <CardDescription>{label}</CardDescription>
        <CardTitle className={cn("tabular text-lg", tone === "pos" && "text-positive", tone === "neg" && "text-negative")}>
          {value}
        </CardTitle>
      </CardHeader>
      {sub && <CardContent className="pt-0 text-xs text-muted-foreground">{sub}</CardContent>}
    </Card>
  );
}

const ROWS: { key: keyof FundamentalsResponse["periods"][number]; label: string; pct?: boolean }[] = [
  { key: "pe", label: "P/E" },
  { key: "ps", label: "P/S" },
  { key: "ev_ebitda", label: "EV/EBITDA" },
  { key: "pb", label: "P/B" },
  { key: "roe", label: "ROE", pct: true },
  { key: "roic", label: "ROIC", pct: true },
  { key: "revenue_growth", label: "Crec. revenue YoY", pct: true },
  { key: "fcf_yield", label: "FCF Yield", pct: true },
  { key: "debt_to_equity", label: "Deuda / PN" },
  { key: "current_ratio", label: "Current ratio" },
  { key: "altman_z", label: "Altman Z" },
];

function FundamentalsTable({ data }: { data: FundamentalsResponse }) {
  return (
    <Table>
      <TableHeader>
        <TableRow className="hover:bg-transparent">
          <TableHead>Ratio</TableHead>
          {data.periods.map((p) => (
            <TableHead key={p.period_end} className="text-right">
              {p.period_end.slice(0, 4)}
            </TableHead>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody className="tabular">
        {ROWS.map((r) => (
          <TableRow key={r.key}>
            <TableCell className="text-muted-foreground">{r.label}</TableCell>
            {data.periods.map((p) => {
              const v = p[r.key] as number | null;
              return (
                <TableCell key={p.period_end} className="text-right">
                  {r.pct ? fmtRatioPct(v) : fmtNumber(v, 2)}
                </TableCell>
              );
            })}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
