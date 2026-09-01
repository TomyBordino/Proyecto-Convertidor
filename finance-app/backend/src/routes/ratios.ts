import { Router } from "express";
import { z } from "zod";
import { getRatios, RATIO_METADATA } from "../services/ratios.js";
import { handleProviderError } from "./quotes.js";

const marketSchema = z.enum(["us", "ar"]);

export const ratiosRouter = Router();

ratiosRouter.get("/metadata", (_req, res) => {
  res.json({ metadata: RATIO_METADATA });
});

ratiosRouter.get("/:market/:symbol", async (req, res) => {
  const market = marketSchema.safeParse(req.params.market);
  if (!market.success) return res.status(400).json({ error: "Mercado invalido, usa 'us' o 'ar'" });

  try {
    const ratios = await getRatios(market.data, req.params.symbol);
    res.json(ratios);
  } catch (err) {
    handleProviderError(res, err);
  }
});
