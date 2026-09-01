import { Router } from "express";
import { z } from "zod";
import { getProvider } from "../services/providers/index.js";
import { buildProjection } from "../services/valuation.js";
import { handleProviderError } from "./quotes.js";

const bodySchema = z.object({
  market: z.enum(["us", "ar"]),
  symbol: z.string().min(1),
  horizonYears: z.number().int().min(1).max(10).default(5),
  annualGrowthRate: z.number().min(-0.9).max(3).nullable().optional(),
  discountRate: z.number().min(0).max(1).nullable().optional(),
});

export const aiRouter = Router();

aiRouter.post("/projection", async (req, res) => {
  const parsed = bodySchema.safeParse(req.body);
  if (!parsed.success) {
    return res.status(400).json({ error: "Body invalido", details: parsed.error.flatten() });
  }
  const { market, symbol, horizonYears, annualGrowthRate, discountRate } = parsed.data;

  try {
    const provider = getProvider(market);
    const [quote, history] = await Promise.all([
      provider.getQuote(symbol),
      provider.getHistory(symbol, 730),
    ]);

    if (quote.price === null) {
      return res.status(422).json({ error: `No hay precio disponible para "${symbol}" en este momento` });
    }

    const projection = await buildProjection({
      market,
      symbol,
      currentPrice: quote.price,
      history,
      horizonYears,
      growthOverride: annualGrowthRate ?? null,
      discountRateOverride: discountRate ?? null,
    });

    res.json(projection);
  } catch (err) {
    handleProviderError(res, err);
  }
});
