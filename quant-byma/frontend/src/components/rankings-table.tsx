"use client";

import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import { ScoreBar } from "@/components/score-bar";
import { SignalBadges } from "@/components/signal-badges";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { RankingItem } from "@/lib/api";
import { fmtMoney, fmtNumber, fmtPct } from "@/lib/format";
import { cn } from "@/lib/utils";

type SortKey =
  | "rank"
  | "ticker"
  | "price_ars"
  | "price_usd"
  | "change_1m_pct"
  | "rsi14"
  | "pe"
  | "ccl_dev_pct"
  | "technical_score"
  | "fundamental_score"
  | "ccl_score"
  | "composite_score";

interface Column {
  key: SortKey;
  label: string;
  align?: "right";
  title?: string;
}

const COLUMNS: Column[] = [
  { key: "rank", label: "#" },
  { key: "ticker", label: "Activo" },
  { key: "price_ars", label: "Precio ARS", align: "right" },
  { key: "price_usd", label: "USD CCL", align: "right" },
  { key: "change_1m_pct", label: "1M (USD)", align: "right" },
  { key: "rsi14", label: "RSI", align: "right" },
  { key: "pe", label: "P/E", align: "right" },
  { key: "ccl_dev_pct", label: "Desvío CCL", align: "right", title: "CCL implícito vs mercado" },
  { key: "technical_score", label: "Técnico" },
  { key: "fundamental_score", label: "Fund." },
  { key: "ccl_score", label: "CCL" },
  { key: "composite_score", label: "Score", title: "Score de Revalorización (0–100)" },
];

function compare(a: unknown, b: unknown): number {
  if (a === null || a === undefined) return 1;
  if (b === null || b === undefined) return -1;
  if (typeof a === "string" && typeof b === "string") return a.localeCompare(b);
  return (a as number) - (b as number);
}

export function RankingsTable({ items }: { items: RankingItem[] }) {
  const [sort, setSort] = useState<{ key: SortKey; dir: "asc" | "desc" }>({
    key: "composite_score",
    dir: "desc",
  });

  const sorted = useMemo(() => {
    const out = [...items].sort((a, b) => {
      const av = a[sort.key];
      const bv = b[sort.key];
      // los nulos quedan siempre al final, sin importar la dirección
      if (av === null || av === undefined) return 1;
      if (bv === null || bv === undefined) return -1;
      const c = compare(av, bv);
      return sort.dir === "asc" ? c : -c;
    });
    return out;
  }, [items, sort]);

  function toggle(key: SortKey) {
    setSort((s) =>
      s.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" } : { key, dir: key === "ticker" ? "asc" : "desc" },
    );
  }

  return (
    <Table>
      <TableHeader>
        <TableRow className="hover:bg-transparent">
          {COLUMNS.map((c) => {
            const Icon = sort.key !== c.key ? ArrowUpDown : sort.dir === "asc" ? ArrowUp : ArrowDown;
            return (
              <TableHead key={c.key} className={cn(c.align === "right" && "text-right")} title={c.title}>
                <button
                  type="button"
                  onClick={() => toggle(c.key)}
                  className={cn(
                    "inline-flex items-center gap-1 hover:text-foreground",
                    sort.key === c.key && "text-foreground",
                  )}
                >
                  {c.label}
                  <Icon className="size-3" />
                </button>
              </TableHead>
            );
          })}
          <TableHead>Señales</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody className="tabular">
        {sorted.map((r) => (
          <TableRow key={r.ticker}>
            <TableCell className="text-muted-foreground">{r.rank}</TableCell>
            <TableCell>
              <Link href={`/asset/${r.ticker}`} className="group flex flex-col">
                <span className="flex items-center gap-1.5 font-medium group-hover:text-primary">
                  {r.ticker}
                  <Badge variant={r.kind === "CEDEAR" ? "default" : "secondary"}>{r.kind}</Badge>
                </span>
                <span className="max-w-48 truncate text-xs text-muted-foreground">
                  {r.name} · {r.sector}
                </span>
              </Link>
            </TableCell>
            <TableCell className="text-right">{fmtMoney(r.price_ars, "ARS")}</TableCell>
            <TableCell className="text-right">{fmtMoney(r.price_usd, "USD")}</TableCell>
            <TableCell
              className={cn(
                "text-right",
                (r.change_1m_pct ?? 0) > 0 ? "text-positive" : (r.change_1m_pct ?? 0) < 0 ? "text-negative" : "",
              )}
            >
              {fmtPct(r.change_1m_pct ?? null, 1)}
            </TableCell>
            <TableCell className="text-right">{fmtNumber(r.rsi14, 1)}</TableCell>
            <TableCell className="text-right">{fmtNumber(r.pe, 1)}</TableCell>
            <TableCell
              className={cn(
                "text-right",
                r.ccl_dev_pct !== null && r.ccl_dev_pct < 0 && "text-positive",
                r.ccl_dev_pct !== null && r.ccl_dev_pct > 0 && "text-negative",
              )}
            >
              {fmtPct(r.ccl_dev_pct)}
            </TableCell>
            <TableCell>
              <ScoreBar score={r.technical_score} />
            </TableCell>
            <TableCell>
              <ScoreBar score={r.fundamental_score} />
            </TableCell>
            <TableCell>
              <ScoreBar score={r.ccl_score} />
            </TableCell>
            <TableCell>
              <ScoreBar score={r.composite_score} className="font-semibold" />
            </TableCell>
            <TableCell>
              <SignalBadges signals={r.signals} />
            </TableCell>
          </TableRow>
        ))}
        {!sorted.length && (
          <TableRow>
            <TableCell colSpan={COLUMNS.length + 1} className="py-10 text-center text-muted-foreground">
              Ningún activo cumple los filtros.
            </TableCell>
          </TableRow>
        )}
      </TableBody>
    </Table>
  );
}
