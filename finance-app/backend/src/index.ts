import cors from "cors";
import "dotenv/config";
import express from "express";
import { aiRouter } from "./routes/ai.js";
import { quotesRouter } from "./routes/quotes.js";
import { ratiosRouter } from "./routes/ratios.js";

const app = express();
const port = Number(process.env.PORT ?? 4000);
const allowedOrigin = process.env.CORS_ORIGIN ?? "http://localhost:5173";

app.use(cors({ origin: allowedOrigin }));
app.use(express.json());

app.get("/api/health", (_req, res) => {
  res.json({ status: "ok", time: new Date().toISOString() });
});

app.use("/api/quotes", quotesRouter);
app.use("/api/ratios", ratiosRouter);
app.use("/api/ai", aiRouter);

app.use((_req, res) => {
  res.status(404).json({ error: "Ruta no encontrada" });
});

app.listen(port, () => {
  console.log(`Finance app backend escuchando en http://localhost:${port}`);
});
