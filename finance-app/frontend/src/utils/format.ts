export function formatCurrency(value: number | null, currency = "USD"): string {
  if (value === null || Number.isNaN(value)) return "N/D";
  try {
    return new Intl.NumberFormat("es-AR", { style: "currency", currency, maximumFractionDigits: 2 }).format(
      value
    );
  } catch {
    return value.toFixed(2);
  }
}

export function formatPercent(value: number | null): string {
  if (value === null || Number.isNaN(value)) return "N/D";
  return `${(value * 100).toFixed(2)}%`;
}

export function formatRatio(value: number | null): string {
  if (value === null || Number.isNaN(value)) return "N/D";
  return value.toFixed(2);
}

export function formatCompactNumber(value: number | null): string {
  if (value === null || Number.isNaN(value)) return "N/D";
  return new Intl.NumberFormat("es-AR", { notation: "compact", maximumFractionDigits: 1 }).format(value);
}
