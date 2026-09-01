import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ProjectionResult } from "../types";
import { formatCurrency } from "../utils/format";

interface ChartRow {
  year: number;
  conservador?: number;
  base?: number;
  optimista?: number;
}

const SCENARIO_COLORS: Record<string, string> = {
  conservador: "#f97316",
  base: "#2563eb",
  optimista: "#16a34a",
};

export default function ProjectionChart({ projection, currency }: { projection: ProjectionResult; currency: string }) {
  const rows = new Map<number, ChartRow>();
  rows.set(0, { year: 0, conservador: projection.currentPrice, base: projection.currentPrice, optimista: projection.currentPrice });

  for (const point of projection.points) {
    const row = rows.get(point.year) ?? { year: point.year };
    row[point.scenario] = point.projectedPrice;
    rows.set(point.year, row);
  }

  const data = Array.from(rows.values()).sort((a, b) => a.year - b.year);

  return (
    <div className="h-72 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
          <XAxis dataKey="year" tickFormatter={(y) => `Año ${y}`} />
          <YAxis
            width={80}
            tickFormatter={(v: number) => formatCurrency(v, currency)}
            domain={["auto", "auto"]}
          />
          <Tooltip
            formatter={(value) => formatCurrency(typeof value === "number" ? value : null, currency)}
            labelFormatter={(y) => `Año ${y}`}
          />
          <Legend />
          <Line type="monotone" dataKey="conservador" stroke={SCENARIO_COLORS.conservador} strokeWidth={2} dot={false} />
          <Line type="monotone" dataKey="base" stroke={SCENARIO_COLORS.base} strokeWidth={2} dot={false} />
          <Line type="monotone" dataKey="optimista" stroke={SCENARIO_COLORS.optimista} strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
