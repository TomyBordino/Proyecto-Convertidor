"use client";

import useSWR from "swr";

import { fetcher } from "@/lib/api";

interface Health {
  as_of: string | null;
  provider: string | null;
  last_ingestion: { at: string; provider: string; status: string; message: string } | null;
}

/** Aviso permanente cuando la base contiene datos sintéticos o ninguna ingesta real. */
export function DataSourceBanner() {
  const { data } = useSWR<Health>("/api/health", fetcher, { refreshInterval: 60_000 });
  if (!data) return null;
  if (data.provider === "demo") {
    return (
      <div className="border-b border-warning/40 bg-warning/15 px-4 py-2 text-center text-sm text-warning">
        Datos SINTÉTICOS del proveedor demo: no son cotizaciones reales. Ejecutá una ingesta con{" "}
        <code>--provider real</code>.
      </div>
    );
  }
  if (!data.last_ingestion) {
    return (
      <div className="border-b bg-muted px-4 py-2 text-center text-sm text-muted-foreground">
        Sin datos todavía: ejecutá <code>python -m app.scheduler --once</code> en el backend.
      </div>
    );
  }
  return null;
}

export function DataSourceNote() {
  const { data } = useSWR<Health>("/api/health", fetcher);
  if (!data?.last_ingestion) return null;
  return (
    <span title={data.last_ingestion.message}>
      Fuente: {data.provider === "real" ? "BYMA Data · SEC EDGAR · Tiingo/Stooq" : data.provider} · estado{" "}
      {data.last_ingestion.status}
    </span>
  );
}
