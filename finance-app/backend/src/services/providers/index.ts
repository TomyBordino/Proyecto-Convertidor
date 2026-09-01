import type { Market } from "../../types/domain.js";
import { ArQuoteProvider } from "./arProvider.js";
import type { QuoteProvider } from "./quoteProvider.js";
import { UsQuoteProvider } from "./usProvider.js";

const providers: Record<Market, QuoteProvider> = {
  us: new UsQuoteProvider(),
  ar: new ArQuoteProvider(),
};

export function getProvider(market: Market): QuoteProvider {
  return providers[market];
}

export { ProviderError } from "./quoteProvider.js";
