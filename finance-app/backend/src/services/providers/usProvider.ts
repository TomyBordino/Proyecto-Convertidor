import YahooFinance from "yahoo-finance2";
import type { Fundamentals, HistoricalPoint, Quote, SearchResult } from "../../types/domain.js";
import { fundamentalsCache, historyCache, quoteCache, withCache } from "../cache.js";
import { ProviderError, type QuoteProvider } from "./quoteProvider.js";

const yahooFinance = new YahooFinance();
// Silencia el aviso interno de encuesta de yahoo-finance2 en logs de servidor.
yahooFinance._notices.suppress(["yahooSurvey"]);

function toNumberOrNull(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export class UsQuoteProvider implements QuoteProvider {
  readonly market = "us" as const;

  async getQuote(symbol: string): Promise<Quote> {
    return withCache(quoteCache, `us:quote:${symbol}`, async () => {
      try {
        const q = await yahooFinance.quote(symbol);
        if (!q || !q.symbol) {
          throw new ProviderError(`No se encontro el ticker "${symbol}" en Wall Street`, 404);
        }
        return {
          symbol: q.symbol,
          market: "us",
          shortName: q.shortName ?? q.longName ?? q.symbol,
          currency: q.currency ?? "USD",
          price: toNumberOrNull(q.regularMarketPrice),
          change: toNumberOrNull(q.regularMarketChange),
          changePercent: toNumberOrNull(q.regularMarketChangePercent),
          previousClose: toNumberOrNull(q.regularMarketPreviousClose),
          dayHigh: toNumberOrNull(q.regularMarketDayHigh),
          dayLow: toNumberOrNull(q.regularMarketDayLow),
          volume: toNumberOrNull(q.regularMarketVolume),
          marketCap: toNumberOrNull(q.marketCap),
          asOf: new Date().toISOString(),
        } satisfies Quote;
      } catch (err) {
        if (err instanceof ProviderError) throw err;
        throw new ProviderError(
          `No se pudo obtener la cotizacion de "${symbol}" (Wall Street): ${(err as Error).message}`
        );
      }
    });
  }

  async getFundamentals(symbol: string): Promise<Fundamentals> {
    return withCache(fundamentalsCache, `us:fundamentals:${symbol}`, async () => {
      try {
        const summary = await yahooFinance.quoteSummary(symbol, {
          modules: ["summaryDetail", "defaultKeyStatistics", "financialData"],
        });
        const summaryDetail = summary.summaryDetail;
        const keyStats = summary.defaultKeyStatistics;
        const financialData = summary.financialData;

        return {
          symbol,
          market: "us",
          trailingPE: toNumberOrNull(summaryDetail?.trailingPE),
          forwardPE: toNumberOrNull(summaryDetail?.forwardPE ?? keyStats?.forwardPE),
          priceToBook: toNumberOrNull(keyStats?.priceToBook),
          priceToSales: toNumberOrNull(summaryDetail?.priceToSalesTrailing12Months),
          dividendYield: toNumberOrNull(summaryDetail?.dividendYield),
          epsTrailing: toNumberOrNull(keyStats?.trailingEps),
          epsForward: toNumberOrNull(keyStats?.forwardEps),
          returnOnEquity: toNumberOrNull(financialData?.returnOnEquity),
          returnOnAssets: toNumberOrNull(financialData?.returnOnAssets),
          netMargin: toNumberOrNull(financialData?.profitMargins),
          operatingMargin: toNumberOrNull(financialData?.operatingMargins),
          debtToEquity: toNumberOrNull(financialData?.debtToEquity),
          currentRatio: toNumberOrNull(financialData?.currentRatio),
          revenueGrowth: toNumberOrNull(financialData?.revenueGrowth),
          earningsGrowth: toNumberOrNull(financialData?.earningsGrowth),
          beta: toNumberOrNull(summaryDetail?.beta),
          fiftyTwoWeekHigh: toNumberOrNull(summaryDetail?.fiftyTwoWeekHigh),
          fiftyTwoWeekLow: toNumberOrNull(summaryDetail?.fiftyTwoWeekLow),
        } satisfies Fundamentals;
      } catch (err) {
        throw new ProviderError(
          `No se pudieron obtener los ratios de "${symbol}" (Wall Street): ${(err as Error).message}`
        );
      }
    });
  }

  async getHistory(symbol: string, days: number): Promise<HistoricalPoint[]> {
    return withCache(historyCache, `us:history:${symbol}:${days}`, async () => {
      try {
        const period1 = new Date(Date.now() - days * 24 * 60 * 60 * 1000);
        const result = await yahooFinance.chart(symbol, {
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
          `No se pudo obtener el historial de "${symbol}" (Wall Street): ${(err as Error).message}`
        );
      }
    });
  }

  async search(query: string): Promise<SearchResult[]> {
    try {
      const result = await yahooFinance.search(query, { quotesCount: 8, newsCount: 0 });
      const results: SearchResult[] = [];
      for (const item of result.quotes) {
        if (!item.isYahooFinance || !item.symbol) continue;
        results.push({
          symbol: item.symbol,
          market: "us",
          name: item.shortname ?? item.longname ?? item.symbol,
          type: item.quoteType ?? "EQUITY",
        });
      }
      return results;
    } catch (err) {
      throw new ProviderError(`No se pudo buscar "${query}" en Wall Street: ${(err as Error).message}`);
    }
  }
}
