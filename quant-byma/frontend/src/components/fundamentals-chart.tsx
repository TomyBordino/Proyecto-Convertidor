"use client";

import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { FundamentalPeriod } from "@/lib/api";
import { fmtCompact, fmtNumber } from "@/lib/format";

const axis = { fontSize: 11, fill: "var(--muted-foreground)" };
const tooltipStyle = {
  background: "var(--card)",
  border: "1px solid var(--border)",
  borderRadius: 8,
  fontSize: 12,
};

export function FlowsChart({ periods }: { periods: FundamentalPeriod[] }) {
  const data = periods.map((p) => ({ ...p, year: p.period_end.slice(0, 4) }));
  return (
    <ResponsiveContainer width="100%" height={260}>
      <ComposedChart data={data} margin={{ left: 8, right: 8, top: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
        <XAxis dataKey="year" tick={axis} axisLine={false} tickLine={false} />
        <YAxis tick={axis} axisLine={false} tickLine={false} tickFormatter={(v: number) => fmtCompact(v)} width={56} />
        <Tooltip contentStyle={tooltipStyle} formatter={(v) => `US$ ${fmtCompact(Number(v))}`} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Bar dataKey="revenue" name="Revenue" fill="#3e9fff" radius={[3, 3, 0, 0]} />
        <Bar dataKey="ebitda" name="EBITDA" fill="#8e8cf2" radius={[3, 3, 0, 0]} />
        <Bar dataKey="free_cash_flow" name="FCF" fill="#22a06b" radius={[3, 3, 0, 0]} />
        <Line dataKey="net_income" name="Resultado neto" stroke="#f5a524" strokeWidth={2} dot />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

export function MultiplesChart({ periods }: { periods: FundamentalPeriod[] }) {
  const data = periods.map((p) => ({ ...p, year: p.period_end.slice(0, 4) }));
  return (
    <ResponsiveContainer width="100%" height={260}>
      <ComposedChart data={data} margin={{ left: 8, right: 8, top: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
        <XAxis dataKey="year" tick={axis} axisLine={false} tickLine={false} />
        <YAxis tick={axis} axisLine={false} tickLine={false} width={40} />
        <Tooltip contentStyle={tooltipStyle} formatter={(v) => fmtNumber(Number(v), 1)} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Line dataKey="pe" name="P/E" stroke="#3e9fff" strokeWidth={2} connectNulls />
        <Line dataKey="ev_ebitda" name="EV/EBITDA" stroke="#f5a524" strokeWidth={2} connectNulls />
        <Line dataKey="ps" name="P/S" stroke="#22a06b" strokeWidth={2} connectNulls />
        <Line dataKey="pb" name="P/B" stroke="#a78bfa" strokeWidth={2} connectNulls />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
