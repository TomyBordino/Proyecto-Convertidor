export type Market = "us" | "ar";

export interface Quote {
  symbol: string;
  market: Market;
  shortName: string;
  currency: string;
  price: number | null;
  change: number | null;
  changePercent: number | null;
  previousClose: number | null;
  dayHigh: number | null;
  dayLow: number | null;
  volume: number | null;
  marketCap: number | null;
  asOf: string;
}

export interface Fundamentals {
  symbol: string;
  market: Market;
  trailingPE: number | null;
  forwardPE: number | null;
  priceToBook: number | null;
  priceToSales: number | null;
  dividendYield: number | null;
  epsTrailing: number | null;
  epsForward: number | null;
  returnOnEquity: number | null;
  returnOnAssets: number | null;
  netMargin: number | null;
  operatingMargin: number | null;
  debtToEquity: number | null;
  currentRatio: number | null;
  revenueGrowth: number | null;
  earningsGrowth: number | null;
  beta: number | null;
  fiftyTwoWeekHigh: number | null;
  fiftyTwoWeekLow: number | null;
}

export interface Ratios extends Fundamentals {
  quote: Quote;
}

export interface HistoricalPoint {
  date: string;
  close: number;
}

export interface SearchResult {
  symbol: string;
  market: Market;
  name: string;
  type: string;
}

export interface ProjectionAssumptions {
  horizonYears: number;
  annualGrowthRate: number | null;
  discountRate: number | null;
}

export interface ProjectionPoint {
  year: number;
  projectedPrice: number;
  scenario: "base" | "optimista" | "conservador";
}

export interface ProjectionResult {
  symbol: string;
  market: Market;
  generatedAt: string;
  currentPrice: number;
  historicalCagr: number | null;
  assumptions: {
    horizonYears: number;
    annualGrowthRate: number;
    discountRate: number;
  };
  points: ProjectionPoint[];
  narrative: string;
  disclaimer: string;
}
