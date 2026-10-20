const nf = (digits: number) =>
  new Intl.NumberFormat("es-AR", { minimumFractionDigits: digits, maximumFractionDigits: digits });

export function fmtNumber(v: number | null | undefined, digits = 2): string {
  return v === null || v === undefined || !Number.isFinite(v) ? "—" : nf(digits).format(v);
}

export function fmtPct(v: number | null | undefined, digits = 2, signed = true): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  const s = nf(digits).format(v);
  return `${signed && v > 0 ? "+" : ""}${s}%`;
}

/** Ratios expresados como fracción (0.18 → 18,0%). */
export function fmtRatioPct(v: number | null | undefined, digits = 1): string {
  return v === null || v === undefined ? "—" : fmtPct(v * 100, digits, false);
}

export function fmtMoney(v: number | null | undefined, currency: "ARS" | "USD", digits = 2) {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return `${currency === "ARS" ? "$" : "US$"} ${nf(digits).format(v)}`;
}

export function fmtCompact(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return new Intl.NumberFormat("es-AR", { notation: "compact", maximumFractionDigits: 1 }).format(v);
}

export function scoreTone(score: number | null | undefined): string {
  if (score === null || score === undefined) return "text-muted-foreground";
  if (score >= 65) return "text-positive";
  if (score >= 45) return "text-warning";
  return "text-negative";
}

export function fmtProb(v: number | null | undefined, digits = 0): string {
  return v === null || v === undefined || !Number.isFinite(v) ? "—" : `${nf(digits).format(v * 100)}%`;
}

export function fmtReturn(v: number | null | undefined, digits = 1): string {
  return v === null || v === undefined || !Number.isFinite(v) ? "—" : fmtPct(v * 100, digits);
}

export const STAGE_SHORT: Record<number, string> = {
  1: "Base",
  2: "Alcista",
  3: "Techo",
  4: "Bajista",
};
