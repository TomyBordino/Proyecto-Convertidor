"use client";

import Link from "next/link";
import useSWR from "swr";

import { LineChart } from "@/components/price-chart";
import { ErrorState, LoadingState } from "@/components/state";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { fetcher, type CCLResponse } from "@/lib/api";
import { fmtMoney, fmtPct } from "@/lib/format";
import { cn } from "@/lib/utils";

export function CCLView() {
  const { data, error } = useSWR<CCLResponse>("/api/ccl?days=730", fetcher);
  if (error) return <ErrorState error={error} />;
  if (!data) return <LoadingState />;
  const maxAbs = Math.max(1, ...data.assets.filter((a) => !a.ratio_suspect).map((a) => Math.abs(a.deviation_pct)));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Contado con Liquidez</h1>
        <p className="text-sm text-muted-foreground">
          CCL implícito = precio BYMA × ratio / precio en EE. UU. El CCL de mercado es la mediana ponderada por
          volumen, descartando outliers (MAD).
        </p>
      </div>
      <Card>
        <CardHeader>
          <CardDescription>CCL de mercado al {data.as_of}</CardDescription>
          <CardTitle className="tabular text-2xl">{fmtMoney(data.market, "ARS")}</CardTitle>
          {data.reference_source && (
            <CardDescription>
              Referencia {data.reference_source}: desvío del CCL calculado {fmtPct(data.reference_deviation_pct)}
            </CardDescription>
          )}
        </CardHeader>
        <CardContent>
          <LineChart
            series={[
              { points: data.history, color: "#3e9fff", title: "CCL calculado" },
              ...(data.reference.length
                ? [{ points: data.reference, color: "#f5a524", title: "CCL referencia" }]
                : []),
            ]}
            height={300}
          />
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Descalce por activo</CardTitle>
          <CardDescription>
            Desvío negativo: el activo permite comprar dólares más baratos que el mercado (oportunidad de entrada).
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ul className="space-y-1.5">
            {data.assets.map((a) => {
              const width = Math.min(100, (Math.abs(a.deviation_pct) / maxAbs) * 50);
              const neg = a.deviation_pct < 0;
              return (
                <li key={a.ticker} className="grid grid-cols-[90px_1fr_130px] items-center gap-3 text-sm">
                  <Link href={`/asset/${a.ticker}`} className="font-medium hover:text-primary">
                    {a.ticker}
                  </Link>
                  <div className="relative h-4">
                    <div className="absolute inset-y-0 left-1/2 w-px bg-border" />
                    {a.ratio_suspect ? (
                      <Badge variant="warning" className="absolute left-1/2 -translate-x-1/2">
                        ratio sospechoso
                      </Badge>
                    ) : (
                      <div
                        className={cn("absolute inset-y-0.5 rounded-sm", neg ? "bg-positive" : "bg-negative")}
                        style={neg ? { right: "50%", width: `${width}%` } : { left: "50%", width: `${width}%` }}
                      />
                    )}
                  </div>
                  <span className={cn("tabular text-right", neg ? "text-positive" : "text-negative")}>
                    {fmtPct(a.deviation_pct)} · {fmtMoney(a.implied_ccl, "ARS", 0)}
                  </span>
                </li>
              );
            })}
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}
