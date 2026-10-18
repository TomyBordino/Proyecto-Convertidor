"use client";

import { RefreshCw } from "lucide-react";
import { useMemo, useState } from "react";
import useSWR from "swr";

import { RankingsTable } from "@/components/rankings-table";
import { ErrorState, LoadingState } from "@/components/state";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { api, fetcher, type RankingsResponse } from "@/lib/api";
import { fmtMoney, fmtNumber } from "@/lib/format";

export function Dashboard() {
  const { data, error, isLoading, mutate } = useSWR<RankingsResponse>("/api/rankings?limit=500", fetcher);
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState("");
  const [sector, setSector] = useState("");
  const [minScore, setMinScore] = useState(0);
  const [onlySignals, setOnlySignals] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const sectors = useMemo(
    () => [...new Set((data?.items ?? []).map((i) => i.sector))].sort(),
    [data],
  );

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (data?.items ?? []).filter(
      (i) =>
        (!q || i.ticker.toLowerCase().includes(q) || i.name.toLowerCase().includes(q)) &&
        (!kind || i.kind === kind) &&
        (!sector || i.sector === sector) &&
        i.composite_score >= minScore &&
        (!onlySignals || i.signals.length > 0),
    );
  }, [data, query, kind, sector, minScore, onlySignals]);

  async function refresh() {
    setRefreshing(true);
    try {
      await api.ingest();
      await mutate();
    } finally {
      setRefreshing(false);
    }
  }

  if (error) return <ErrorState error={error} />;
  if (isLoading || !data) return <LoadingState />;

  const top = data.items[0];
  const cheapest = [...data.items]
    .filter((i) => i.ccl_dev_pct !== null)
    .sort((a, b) => (a.ccl_dev_pct ?? 0) - (b.ccl_dev_pct ?? 0))[0];
  const bullish = data.items.filter((i) => i.technical_score !== null && i.technical_score >= 65).length;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Ranking de revalorización</h1>
          <p className="text-sm text-muted-foreground">
            Acciones BYMA y CEDEARs ordenados por Composite Score (técnico 40% · fundamental 35% ·
            CCL 25%). Datos al {data.as_of ?? "—"}.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={refresh} disabled={refreshing}>
          <RefreshCw className={refreshing ? "animate-spin" : ""} />
          {refreshing ? "Actualizando…" : "Actualizar datos"}
        </Button>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Kpi title="CCL de mercado" value={fmtMoney(data.ccl_market, "ARS")} hint="Mediana ponderada por volumen" />
        <Kpi title="Mejor score" value={top ? `${top.ticker} · ${fmtNumber(top.composite_score, 0)}` : "—"} hint={top?.name} />
        <Kpi
          title="CCL implícito más barato"
          value={cheapest ? `${cheapest.ticker} · ${fmtNumber(cheapest.ccl_dev_pct, 2)}%` : "—"}
          hint="Desvío vs CCL de mercado"
        />
        <Kpi title="Con sesgo técnico alcista" value={`${bullish} / ${data.count}`} hint="Score técnico ≥ 65" />
      </div>

      <Card>
        <CardHeader className="flex-row flex-wrap items-center gap-2 space-y-0">
          <Input
            placeholder="Buscar ticker o empresa…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="w-56"
          />
          <Select value={kind} onChange={(e) => setKind(e.target.value)} aria-label="Tipo">
            <option value="">Todos los tipos</option>
            <option value="CEDEAR">CEDEARs</option>
            <option value="LOCAL">Acciones locales</option>
          </Select>
          <Select value={sector} onChange={(e) => setSector(e.target.value)} aria-label="Sector">
            <option value="">Todos los sectores</option>
            {sectors.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </Select>
          <label className="flex items-center gap-2 text-sm text-muted-foreground">
            Score mín.
            <input
              type="range"
              min={0}
              max={90}
              step={5}
              value={minScore}
              onChange={(e) => setMinScore(Number(e.target.value))}
              className="accent-[var(--primary)]"
            />
            <span className="tabular w-6 text-foreground">{minScore}</span>
          </label>
          <label className="flex items-center gap-2 text-sm text-muted-foreground">
            <input type="checkbox" checked={onlySignals} onChange={(e) => setOnlySignals(e.target.checked)} />
            Solo con señales
          </label>
          <span className="ml-auto text-xs text-muted-foreground">{filtered.length} activos</span>
        </CardHeader>
        <CardContent className="p-0 pb-2">
          <RankingsTable items={filtered} />
        </CardContent>
      </Card>
    </div>
  );
}

function Kpi({ title, value, hint }: { title: string; value: string; hint?: string }) {
  return (
    <Card>
      <CardHeader>
        <CardDescription>{title}</CardDescription>
        <CardTitle className="tabular text-xl">{value}</CardTitle>
      </CardHeader>
      {hint && <CardContent className="pt-0 text-xs text-muted-foreground">{hint}</CardContent>}
    </Card>
  );
}
