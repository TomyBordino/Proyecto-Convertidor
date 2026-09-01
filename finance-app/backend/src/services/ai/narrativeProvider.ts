import type { Market, ProjectionPoint } from "../../types/domain.js";

export interface NarrativeInput {
  market: Market;
  symbol: string;
  currentPrice: number;
  historicalCagr: number | null;
  baseGrowth: number;
  discountRate: number;
  horizonYears: number;
  points: ProjectionPoint[];
}

export interface AiNarrativeProvider {
  readonly name: string;
  generate(input: NarrativeInput): Promise<string>;
}

function pct(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function money(value: number): string {
  return value.toLocaleString("es-AR", { maximumFractionDigits: 2, minimumFractionDigits: 2 });
}

/**
 * Genera la narrativa por reglas/plantillas, sin depender de ningun proveedor de IA
 * externo ni de una API key. Es el modo por defecto de la app.
 */
export class HeuristicNarrativeProvider implements AiNarrativeProvider {
  readonly name = "heuristic";

  async generate(input: NarrativeInput): Promise<string> {
    const baseAtHorizon = input.points.find(
      (p) => p.scenario === "base" && p.year === input.horizonYears
    );
    const optimisticAtHorizon = input.points.find(
      (p) => p.scenario === "optimista" && p.year === input.horizonYears
    );
    const conservativeAtHorizon = input.points.find(
      (p) => p.scenario === "conservador" && p.year === input.horizonYears
    );

    const trendLine = input.historicalCagr !== null
      ? `El precio historico muestra una tendencia compuesta de aproximadamente ${pct(input.historicalCagr)} anual, `
      : `No hubo suficiente historial de precios para estimar una tendencia confiable, por lo que `;

    const growthSource = input.historicalCagr !== null
      ? "y ese valor se uso como punto de partida del escenario base"
      : `se uso un supuesto por defecto del ${pct(input.baseGrowth)} anual como escenario base`;

    return [
      `Analisis cuantitativo de ${input.symbol} (${input.market === "us" ? "Wall Street" : "Argentina"}).`,
      `${trendLine}${growthSource}.`,
      `Partiendo de un precio actual de ${money(input.currentPrice)}, en un horizonte de ${input.horizonYears} año(s):`,
      conservativeAtHorizon
        ? `- Escenario conservador (${pct(input.baseGrowth * 0.5)} anual): ${money(conservativeAtHorizon.projectedPrice)}.`
        : "",
      baseAtHorizon ? `- Escenario base (${pct(input.baseGrowth)} anual): ${money(baseAtHorizon.projectedPrice)}.` : "",
      optimisticAtHorizon
        ? `- Escenario optimista (${pct(input.baseGrowth * 1.5)} anual): ${money(optimisticAtHorizon.projectedPrice)}.`
        : "",
      `Se aplico una tasa de referencia del ${pct(input.discountRate)} como umbral de retorno exigido para contextualizar los escenarios.`,
      "Este texto se genera con reglas deterministicas (sin modelo de lenguaje externo). " +
        "Para narrativa generada por un LLM real, configura ANTHROPIC_API_KEY en el backend.",
    ]
      .filter(Boolean)
      .join("\n");
  }
}

/**
 * Narrativa generada por un modelo de Anthropic. Se activa automaticamente cuando
 * hay una ANTHROPIC_API_KEY configurada (ver getNarrativeProvider mas abajo).
 * Si la llamada falla por cualquier motivo, el caller debe tener un fallback
 * (getNarrativeProvider ya lo resuelve envolviendo esta clase).
 */
export class AnthropicNarrativeProvider implements AiNarrativeProvider {
  readonly name = "anthropic";

  constructor(
    private readonly apiKey: string,
    private readonly model = process.env.ANTHROPIC_MODEL ?? "claude-sonnet-5"
  ) {}

  async generate(input: NarrativeInput): Promise<string> {
    const prompt = [
      `Sos un analista financiero. Redacta en español rioplatense un analisis breve (max 6 lineas) de ${input.symbol}`,
      `(mercado: ${input.market === "us" ? "Wall Street" : "Argentina"}), precio actual ${input.currentPrice}.`,
      `CAGR historico estimado: ${input.historicalCagr ?? "sin datos suficientes"}.`,
      `Supuesto de crecimiento anual usado: ${input.baseGrowth}. Tasa de referencia: ${input.discountRate}.`,
      `Horizonte de proyeccion: ${input.horizonYears} año(s).`,
      "Aclara siempre que es un ejercicio cuantitativo educativo, no una recomendacion de inversion.",
    ].join(" ");

    const res = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-api-key": this.apiKey,
        "anthropic-version": "2023-06-01",
      },
      body: JSON.stringify({
        model: this.model,
        max_tokens: 400,
        messages: [{ role: "user", content: prompt }],
      }),
      signal: AbortSignal.timeout(15000),
    });

    if (!res.ok) throw new Error(`Anthropic API respondio ${res.status}`);
    const data = (await res.json()) as { content?: Array<{ type: string; text?: string }> };
    const text = data.content?.find((block) => block.type === "text")?.text;
    if (!text) throw new Error("Respuesta de Anthropic sin texto");
    return text;
  }
}

let cachedProvider: AiNarrativeProvider | null = null;

export function getNarrativeProvider(): AiNarrativeProvider {
  if (cachedProvider) return cachedProvider;

  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) {
    cachedProvider = new HeuristicNarrativeProvider();
    return cachedProvider;
  }

  const anthropicProvider = new AnthropicNarrativeProvider(apiKey);
  const heuristicFallback = new HeuristicNarrativeProvider();

  cachedProvider = {
    name: "anthropic-with-fallback",
    async generate(input) {
      try {
        return await anthropicProvider.generate(input);
      } catch {
        return heuristicFallback.generate(input);
      }
    },
  };
  return cachedProvider;
}
