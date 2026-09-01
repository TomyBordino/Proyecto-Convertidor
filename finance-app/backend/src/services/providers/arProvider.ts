import YahooFinance from "yahoo-finance2";
import type { Fundamentals, HistoricalPoint, Quote, SearchResult } from "../../types/domain.js";
import { fundamentalsCache, historyCache, quoteCache, withCache } from "../cache.js";
import { ProviderError, type QuoteProvider } from "./quoteProvider.js";
import { ARGENTINA_TICKERS, findArgentinaTicker } from "./argentinaTickers.js";

const yahooFinance = new YahooFinance();

const DATA912_BASE = process.env.DATA912_BASE_URL ?? "https://data912.com/live";
const DATA912_ENDPOINTS = ["arg_stocks", "arg_cedears"];

// data912.com es una API publica y sin autenticacion muy usada por proyectos fintech
// argentinos para precios de BYMA en tiempo casi real. No tiene documentacion oficial
// estable, asi que esta lectura es defensiva: acepta varios nombres de campo posibles
// y, si el shape cambia o el servicio no responde, cae a Yahoo Finance (sufijo .BA)
// para no romper la app. Si notas datos raros, revisa el response real de
// `${DATA912_BASE}/arg_stocks` y ajusta `pickField` / `mapData912Item`.
interface RawData912Item {
  [key: string]: unknown;
}

function pickField(item: RawData912Item, ...keys: string[]): number | null {
  for (const key of keys) {
    const value = item[key];
    if (typeof value === "number" && Number.isFinite(value)) return value;
  }
  return null;
}

function pickSymbol(item: RawData912Item): string | null {
  const raw = item.symbol ?? item.ticker ?? item.simbolo;
  return typeof raw === "string" ? raw.toUpperCase() : null;
}

async function fetchData912(endpoint: string): Promise<RawData912Item[]> {
  const res = await fetch(`${DATA912_BASE}/${endpoint}`, {
    headers: { accept: "application/json" },
    signal: AbortSignal.timeout(8000),
  });
  if (!res.ok) throw new Error(`data912 respondio ${res.status}`);
  const body = (await res.json()) as unknown;
  if (Array.isArray(body)) return body as RawData912Item[];
  if (body && typeof body === "object" && Array.isArray((body as { data?: unknown }).data)) {
    return (body as { data: RawData912Item[] }).data;
  }
  throw new Error("respuesta de data912 con formato inesperado");
}

async function findInData912(symbol: string): Promise<RawData912Item | null> {
  for (const endpoint of DATA912_ENDPOINTS) {
    try {
      const items = await fetchData912(endpoint);
      const match = items.find((item) => pickSymbol(item) === symbol.toUpperCase());
      if (match) return match;
    } catch {
      // probamos el siguiente endpoint (acciones / cedears) antes de rendirnos
    }
  }
  return null;
}

function mapData912ToQuote(symbol: string, item: RawData912Item): Quote {
  const price = pickField(item, "c", "close", "last", "px", "ultimo");
  const previousClose = pickField(item, "pc", "previous_close", "cierre_anterior");
  const change = pickField(item, "change", "var");
  const changePercent = pickField(item, "pct_change", "change_percent", "var_pct", "variacion");

  return {
    symbol,
    market: "ar",
    shortName: findArgentinaTicker(symbol)?.name ?? symbol,
    currency: "ARS",
    price,
    change,
    changePercent,
    previousClose,
    dayHigh: pickField(item, "high", "maximo"),
    dayLow: pickField(item, "low", "minimo"),
    volume: pickField(item, "v", "volume", "volumen"),
    marketCap: null,
    asOf: new Date().toISOString(),
  };
}

async function getQuoteFromYahooBA(symbol: string): Promise<Quote> {
  const yahooSymbol = `${symbol}.BA`;
  const q = await yahooFinance.quote(yahooSymbol);
  if (!q || !q.symbol) throw new ProviderError(`No se encontro el ticker "${symbol}" en Argentina`, 404);
  return {
    symbol,
    market: "ar",
    shortName: q.shortName ?? findArgentinaTicker(symbol)?.name ?? symbol,
    currency: q.currency ?? "ARS",
    price: q.regularMarketPrice ?? null,
    change: q.regularMarketChange ?? null,
    changePercent: q.regularMarketChangePercent ?? null,
    previousClose: q.regularMarketPreviousClose ?? null,
    dayHigh: q.regularMarketDayHigh ?? null,
    dayLow: q.regularMarketDayLow ?? null,
    volume: q.regularMarketVolume ?? null,
    marketCap: q.marketCap ?? null,
    asOf: new Date().toISOString(),
  };
}

export class ArQuoteProvider implements QuoteProvider {
  readonly market = "ar" as const;

  async getQuote(symbol: string): Promise<Quote> {
    return withCache(quoteCache, `ar:quote:${symbol}`, async () => {
      const fromData912 = await findInData912(symbol).catch(() => null);
      if (fromData912) return mapData912ToQuote(symbol, fromData912);

      try {
        return await getQuoteFromYahooBA(symbol);
      } catch (err) {
        if (err instanceof ProviderError) throw err;
        throw new ProviderError(
          `No se pudo obtener la cotizacion de "${symbol}" (Argentina): ${(err as Error).message}`
        );
      }
    });
  }

  async getFundamentals(symbol: string): Promise<Fundamentals> {
    return withCache(fundamentalsCache, `ar:fundamentals:${symbol}`, async () => {
      const empty: Fundamentals = {
        symbol,
        market: "ar",
        trailingPE: null,
        forwardPE: null,
        priceToBook: null,
        priceToSales: null,
        dividendYield: null,
        epsTrailing: null,
        epsForward: null,
        returnOnEquity: null,
        returnOnAssets: null,
        netMargin: null,
        operatingMargin: null,
        debtToEquity: null,
        currentRatio: null,
        revenueGrowth: null,
        earningsGrowth: null,
        beta: null,
        fiftyTwoWeekHigh: null,
        fiftyTwoWeekLow: null,
      };

      try {
        const summary = await yahooFinance.quoteSummary(`${symbol}.BA`, {
          modules: ["summaryDetail", "defaultKeyStatistics", "financialData"],
        });
        const summaryDetail = summary.summaryDetail;
        const keyStats = summary.defaultKeyStatistics;
        const financialData = summary.financialData;

        return {
          ...empty,
          trailingPE: summaryDetail?.trailingPE ?? null,
          forwardPE: summaryDetail?.forwardPE ?? keyStats?.forwardPE ?? null,
          priceToBook: keyStats?.priceToBook ?? null,
          priceToSales: summaryDetail?.priceToSalesTrailing12Months ?? null,
          dividendYield: summaryDetail?.dividendYield ?? null,
          epsTrailing: keyStats?.trailingEps ?? null,
          epsForward: keyStats?.forwardEps ?? null,
          returnOnEquity: financialData?.returnOnEquity ?? null,
          returnOnAssets: financialData?.returnOnAssets ?? null,
          netMargin: financialData?.profitMargins ?? null,
          operatingMargin: financialData?.operatingMargins ?? null,
          debtToEquity: financialData?.debtToEquity ?? null,
          currentRatio: financialData?.currentRatio ?? null,
          revenueGrowth: financialData?.revenueGrowth ?? null,
          earningsGrowth: financialData?.earningsGrowth ?? null,
          beta: summaryDetail?.beta ?? null,
          fiftyTwoWeekHigh: summaryDetail?.fiftyTwoWeekHigh ?? null,
          fiftyTwoWeekLow: summaryDetail?.fiftyTwoWeekLow ?? null,
        } satisfies Fundamentals;
      } catch {
        // Muchas acciones y la mayoria de los CEDEARs locales no tienen fundamentals
        // propios cargados en Yahoo bajo el sufijo .BA. Devolvemos nulls en vez de
        // romper: el frontend ya sabe mostrar "no disponible" para cada ratio.
        return empty;
      }
    });
  }

  async getHistory(symbol: string, days: number): Promise<HistoricalPoint[]> {
    return withCache(historyCache, `ar:history:${symbol}:${days}`, async () => {
      try {
        const period1 = new Date(Date.now() - days * 24 * 60 * 60 * 1000);
        const result = await yahooFinance.chart(`${symbol}.BA`, {
          period1,
          interval: days > 400 ? "1wk" : "1d",
        });
        return result.quotes
          .filter((point) => typeof point.close === "number")
          .map((point) => ({
            date: new Date(point.date).toISOString().slice(0, 10),
            close: point.close as number,
          }));
      } catch (err) {
        throw new ProviderError(
          `No se pudo obtener el historial de "${symbol}" (Argentina): ${(err as Error).message}`
        );
      }
    });
  }

  async search(query: string): Promise<SearchResult[]> {
    const normalized = query.trim().toUpperCase();
    if (!normalized) return [];
    return ARGENTINA_TICKERS.filter(
      (t) => t.symbol.includes(normalized) || t.name.toUpperCase().includes(normalized)
    ).map((t) => ({ symbol: t.symbol, market: "ar", name: t.name, type: t.type }));
  }
}
