import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { PriceRange } from "@/lib/api";
import { fmtMoney, fmtProb, fmtReturn } from "@/lib/format";
import { cn } from "@/lib/utils";

const H_LABEL: Record<string, string> = { "20": "1 mes", "60": "3 meses", "120": "6 meses" };

/** Barra horizontal: p10–p90 (claro), p25–p75 (oscuro), mediana y precio actual (0%). */
export function RangeBar({ r, scale, className }: { r: PriceRange["returns"]; scale: number; className?: string }) {
  const pos = (v: number) => `${Math.min(100, Math.max(0, 50 + (v / scale) * 50))}%`;
  const span = (a: number, b: number) => ({ left: pos(a), width: `calc(${pos(b)} - ${pos(a)})` });
  return (
    <div className={cn("relative h-3 w-full", className)}>
      <div className="absolute inset-y-1 rounded bg-primary/20" style={span(r.p10, r.p90)} />
      <div className="absolute inset-y-0.5 rounded bg-primary/45" style={span(r.p25, r.p75)} />
      <div className="absolute inset-y-0 w-0.5 bg-primary" style={{ left: pos(r.p50) }} title={`Mediana ${fmtReturn(r.p50)}`} />
      <div className="absolute -inset-y-0.5 w-px bg-foreground" style={{ left: pos(0) }} title="Precio actual" />
    </div>
  );
}

export function PriceRangeCard({
  ranges,
  priceArs,
  priceUsd,
}: {
  ranges: Record<string, PriceRange>;
  priceArs: number;
  priceUsd: number;
}) {
  const hs = (["20", "60", "120"] as const).filter((h) => ranges[h]);
  if (!hs.length) return null;
  const scale = Math.max(...hs.map((h) => Math.max(Math.abs(ranges[h].returns.p10), Math.abs(ranges[h].returns.p90)))) * 1.1;
  const cov = ranges[hs[0]].coverage_80;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Rango probable de precio</CardTitle>
        <CardDescription>
          No es un precio objetivo: es el intervalo donde históricamente cayó el precio en 8 de cada 10 casos (barra
          clara) y en 5 de cada 10 (barra oscura), según la volatilidad del activo ({fmtProb(ranges[hs[0]].vol)} anual) y lo
          que hicieron los activos con su mismo puntaje. Medido fuera de muestra, el rango del 80% contuvo al{" "}
          {fmtProb(cov, 1)} de los resultados reales.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {hs.map((h) => {
          const r = ranges[h].returns;
          return (
            <div key={h} className="space-y-1.5">
              <div className="flex flex-wrap items-baseline justify-between gap-2 text-sm">
                <span className="font-medium">{H_LABEL[h]}</span>
                <span className="tabular text-xs text-muted-foreground">
                  mediana <b className={r.p50 >= 0 ? "text-positive" : "text-negative"}>{fmtReturn(r.p50)}</b>
                </span>
              </div>
              <RangeBar r={r} scale={scale} />
              <div className="tabular grid grid-cols-3 text-xs">
                <div>
                  <p className="text-muted-foreground">Piso (10%)</p>
                  <p className="font-medium text-negative">{fmtReturn(r.p10)}</p>
                  <p>{fmtMoney(priceArs * (1 + r.p10), "ARS")}</p>
                  <p className="text-muted-foreground">{fmtMoney(priceUsd * (1 + r.p10), "USD", 2)}</p>
                </div>
                <div className="text-center">
                  <p className="text-muted-foreground">Mediana</p>
                  <p className="font-medium">{fmtReturn(r.p50)}</p>
                  <p>{fmtMoney(priceArs * (1 + r.p50), "ARS")}</p>
                  <p className="text-muted-foreground">{fmtMoney(priceUsd * (1 + r.p50), "USD", 2)}</p>
                </div>
                <div className="text-right">
                  <p className="text-muted-foreground">Techo (90%)</p>
                  <p className="font-medium text-positive">{fmtReturn(r.p90)}</p>
                  <p>{fmtMoney(priceArs * (1 + r.p90), "ARS")}</p>
                  <p className="text-muted-foreground">{fmtMoney(priceUsd * (1 + r.p90), "USD", 2)}</p>
                </div>
              </div>
            </div>
          );
        })}
        <p className="text-xs text-muted-foreground">
          Los retornos son en dólares (CCL). Los precios en pesos suponen el CCL actual: si el CCL sube, el precio en
          pesos sube en la misma proporción. Un 10% de las veces el precio terminó por debajo del piso y otro 10% por
          encima del techo.
        </p>
      </CardContent>
    </Card>
  );
}
