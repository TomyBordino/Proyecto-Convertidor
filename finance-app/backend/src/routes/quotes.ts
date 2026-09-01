import { Router } from "express";
import { z } from "zod";
import { getProvider, ProviderError } from "../services/providers/index.js";
import { ARGENTINA_TICKERS } from "../services/providers/argentinaTickers.js";

const marketSchema = z.enum(["us", "ar"]);

export const quotesRouter = Router();

quotesRouter.get("/search", async (req, res) => {
  const market = marketSchema.safeParse(req.query.market);
  const query = z.string().min(1).safeParse(req.query.q);
  if (!market.success || !query.success) {
    return res.status(400).json({ error: "Parametros invalidos: se requiere market=us|ar y q=<texto>" });
  }
  try {
    const results = await getProvider(market.data).search(query.data);
    res.json({ results });
  } catch (err) {
    handleProviderError(res, err);
  }
});

quotesRouter.get("/default-watchlist", (req, res) => {
  const market = marketSchema.safeParse(req.query.market);
  if (!market.success) return res.status(400).json({ error: "Parametro market invalido" });

  const symbols =
    market.data === "ar"
      ? ARGENTINA_TICKERS.filter((t) => t.type !== "BONO").slice(0, 8).map((t) => t.symbol)
      : ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META", "MELI"];

  res.json({ market: market.data, symbols });
});

quotesRouter.get("/:market/:symbol", async (req, res) => {
  const market = marketSchema.safeParse(req.params.market);
  if (!market.success) return res.status(400).json({ error: "Mercado invalido, usa 'us' o 'ar'" });

  try {
    const quote = await getProvider(market.data).getQuote(req.params.symbol);
    res.json(quote);
  } catch (err) {
    handleProviderError(res, err);
  }
});

quotesRouter.get("/:market/:symbol/history", async (req, res) => {
  const market = marketSchema.safeParse(req.params.market);
  const days = z.coerce.number().int().min(5).max(3650).default(365).safeParse(req.query.days ?? 365);
  if (!market.success) return res.status(400).json({ error: "Mercado invalido, usa 'us' o 'ar'" });
  if (!days.success) return res.status(400).json({ error: "Parametro days invalido" });

  try {
    const history = await getProvider(market.data).getHistory(req.params.symbol, days.data);
    res.json({ symbol: req.params.symbol, market: market.data, history });
  } catch (err) {
    handleProviderError(res, err);
  }
});

export function handleProviderError(res: import("express").Response, err: unknown) {
  if (err instanceof ProviderError) {
    return res.status(err.status).json({ error: err.message });
  }
  console.error(err);
  res.status(500).json({ error: "Error interno inesperado" });
}
