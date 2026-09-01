/**
 * Lista curada de tickers argentinos mas negociados (acciones lideres del panel
 * general de BYMA y CEDEARs mas populares). Se usa como universo de busqueda y como
 * watchlist por defecto, ya que ni data912 ni Yahoo Finance exponen un endpoint de
 * busqueda confiable para el mercado local.
 *
 * Se puede editar/ampliar libremente sin tocar el resto del codigo.
 */
export interface ArgentinaTicker {
  symbol: string;
  name: string;
  type: "ACCION" | "CEDEAR" | "BONO";
}

export const ARGENTINA_TICKERS: ArgentinaTicker[] = [
  { symbol: "GGAL", name: "Grupo Financiero Galicia", type: "ACCION" },
  { symbol: "YPFD", name: "YPF", type: "ACCION" },
  { symbol: "PAMP", name: "Pampa Energia", type: "ACCION" },
  { symbol: "ALUA", name: "Aluar", type: "ACCION" },
  { symbol: "BMA", name: "Banco Macro", type: "ACCION" },
  { symbol: "BBAR", name: "BBVA Banco Frances", type: "ACCION" },
  { symbol: "CRES", name: "Cresud", type: "ACCION" },
  { symbol: "COME", name: "Sociedad Comercial del Plata", type: "ACCION" },
  { symbol: "EDN", name: "Edenor", type: "ACCION" },
  { symbol: "TGSU2", name: "Transportadora de Gas del Sur", type: "ACCION" },
  { symbol: "TXAR", name: "Ternium Argentina", type: "ACCION" },
  { symbol: "LOMA", name: "Loma Negra", type: "ACCION" },
  { symbol: "CEPU", name: "Central Puerto", type: "ACCION" },
  { symbol: "SUPV", name: "Grupo Supervielle", type: "ACCION" },
  { symbol: "TRAN", name: "Transener", type: "ACCION" },
  { symbol: "AAPL", name: "Apple Inc. (CEDEAR)", type: "CEDEAR" },
  { symbol: "MSFT", name: "Microsoft Corp. (CEDEAR)", type: "CEDEAR" },
  { symbol: "TSLA", name: "Tesla Inc. (CEDEAR)", type: "CEDEAR" },
  { symbol: "AMZN", name: "Amazon.com Inc. (CEDEAR)", type: "CEDEAR" },
  { symbol: "GOOGL", name: "Alphabet Inc. (CEDEAR)", type: "CEDEAR" },
  { symbol: "KO", name: "Coca-Cola Co. (CEDEAR)", type: "CEDEAR" },
  { symbol: "NVDA", name: "NVIDIA Corp. (CEDEAR)", type: "CEDEAR" },
  { symbol: "MELI", name: "Mercado Libre (CEDEAR)", type: "CEDEAR" },
];

export function findArgentinaTicker(symbol: string): ArgentinaTicker | undefined {
  return ARGENTINA_TICKERS.find((t) => t.symbol.toUpperCase() === symbol.toUpperCase());
}
