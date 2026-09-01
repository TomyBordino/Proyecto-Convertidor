import NodeCache from "node-cache";

// TTL corto para cotizaciones (semi tiempo real) y mas largo para fundamentals,
// que cambian con baja frecuencia (una vez por trimestre).
export const quoteCache = new NodeCache({ stdTTL: 30, checkperiod: 15 });
export const fundamentalsCache = new NodeCache({ stdTTL: 60 * 60, checkperiod: 300 });
export const historyCache = new NodeCache({ stdTTL: 60 * 30, checkperiod: 300 });

export async function withCache<T>(
  cache: NodeCache,
  key: string,
  fetcher: () => Promise<T>
): Promise<T> {
  const cached = cache.get<T>(key);
  if (cached !== undefined) return cached;
  const value = await fetcher();
  cache.set(key, value);
  return value;
}
