"use client";

import { RefreshCw } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import useSWR from "swr";

import { RankingsTable } from "@/components/rankings-table";
import { ErrorState, LoadingState } from "@/components/state";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { api, fetcher, type RankingsResponse } from "@/lib/api";
import { fmtMoney } from "@/lib/format";

export function Dashboard() {
  const { data, error, isLoading, mutate } = useSWR<RankingsResponse>("/api/rankings?limit=1000", fetcher);
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState("");
  const [sector, setSector] = useState("");
  const [minScore, setMinScore] = useState(0);
  const [onlySignals, setOnlySignals] = useState(false);
  const [stage, setStage] = useState("");
  const [biasFilter, setBiasFilter] = useState("");
  const [minVolume, setMinVolume] = useState(1_000_000);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshError, setRefreshError] = useState<string | null>(null);

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
        (!stage || String(i.stage) === stage) &&
        (!biasFilter || i.bias === biasFilter) &&
        (i.avg_volume_ars ?? 0) >= minVolume &&
        (!onlySignals || i.signals.length > 0),
    );
  }, [data, query, kind, sector, minScore, onlySignals, stage, biasFilter, minVolume]);

  async function refresh() {
    setRefreshing(true);
    setRefreshError(null);
    try {
      await api.ingest();
      await mutate();
    } catch (e) {
      setRefreshError(e instanceof Error ? e.message : String(e));
    } finally {
      setRefreshing(false);
    }
  }

  if (error) return <ErrorState error={error} />;
  if (isLoading || !data) return <LoadingState />;

  const liquid = data.items.filter((i) => (i.avg_volume_ars ?? 0) >= minVolume);
  const favorable = liquid.filter((i) => i.bias === "Favorable").length;
  const unfavorable = liquid.filter((i) => i.bias === "Desfavorable").length;
  const stage2 = liquid.filter((i) => i.stage === 2).length;
  const base = data.items.find((i) => i.base_rate_60 !== null)?.base_rate_60 ?? null;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Ranking de oportunidades</h1>
          <p className="text-sm text-muted-foreground">
            {data.count} acciones BYMA y CEDEARs ordenadas por probabilidad de cotizar más alto en 3 meses
            (modelo calibrado fuera de muestra, ver{" "}
            <Link className="underline" href="/modelo">
              Modelo
            </Link>
            ). Datos al{" "}
            {data.as_of ?? "—"}.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={refresh} disabled={refreshing}>
          <RefreshCw className={refreshing ? "animate-spin" : ""} />
          {refreshing ? "Actualizando…" : "Actualizar datos"}
        </Button>
      </div>

      {refreshError && (
        <p className="rounded-md border border-negative/40 bg-negative/10 px-3 py-2 text-sm text-negative">
          La ingesta falló: {refreshError}
        </p>
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Kpi title="CCL de mercado" value={fmtMoney(data.ccl_market, "ARS")} hint="Mediana ponderada por volumen" />
        <Kpi
          title="Tasa base a 3 meses"
          value={base === null ? "—" : `${(base * 100).toFixed(0)}%`}
          hint="Frecuencia histórica de suba en 60 ruedas del universo"
        />
        <Kpi
          title="Sesgo significativo"
          value={`${favorable} favorables · ${unfavorable} desfavorables`}
          hint="Solo cuando el IC95 de situaciones similares excluye la tasa base"
        />
        <Kpi title="En tendencia alcista (etapa 2)" value={`${stage2} / ${liquid.length}`} hint="Con el filtro de volumen actual" />
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
          <Select value={stage} onChange={(e) => setStage(e.target.value)} aria-label="Etapa">
            <option value="">Todas las etapas</option>
            <option value="1">1 · Base</option>
            <option value="2">2 · Alcista</option>
            <option value="3">3 · Techo</option>
            <option value="4">4 · Bajista</option>
          </Select>
          <Select value={biasFilter} onChange={(e) => setBiasFilter(e.target.value)} aria-label="Sesgo">
            <option value="">Todo sesgo</option>
            <option value="Favorable">Favorable</option>
            <option value="Neutral">Neutral</option>
            <option value="Desfavorable">Desfavorable</option>
          </Select>
          <Select value={String(minVolume)} onChange={(e) => setMinVolume(Number(e.target.value))} aria-label="Liquidez">
            <option value="0">Cualquier volumen</option>
            <option value="1000000">Volumen ≥ $1 M/día</option>
            <option value="10000000">Volumen ≥ $10 M/día</option>
            <option value="100000000">Volumen ≥ $100 M/día</option>
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
