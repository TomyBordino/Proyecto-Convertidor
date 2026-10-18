"use client";

import {
  CandlestickSeries,
  ColorType,
  createChart,
  HistogramSeries,
  LineSeries,
  type IChartApi,
  type LineData,
  type Time,
} from "lightweight-charts";
import { useEffect, useRef } from "react";

import type { PriceSeries, Point } from "@/lib/api";

export interface Overlays {
  sma: boolean;
  bollinger: boolean;
  rsi: boolean;
  macd: boolean;
}

const COLORS = {
  up: "#22a06b",
  down: "#e5484d",
  sma20: "#8e8cf2",
  sma50: "#f5a524",
  sma200: "#3e9fff",
  bb: "rgba(148,163,184,0.7)",
  rsi: "#a78bfa",
  macd: "#3e9fff",
  signal: "#f5a524",
};

/** lightweight-charts solo acepta hex/rgb: no puede leer los tokens oklch de globals.css. */
function themeColors() {
  const dark = typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: dark)").matches;
  return dark ? { text: "#9aa3b2", border: "#2e3442" } : { text: "#64748b", border: "#e2e8f0" };
}

const line = (points: Point[]): LineData<Time>[] => points.map((p) => ({ time: p.time as Time, value: p.value }));

export function PriceChart({ data, overlays }: { data: PriceSeries; overlays: Overlays }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current) return;
    const theme = themeColors();
    const chart: IChartApi = createChart(ref.current, {
      autoSize: true,
      localization: { locale: "es-AR" },
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: theme.text,
        panes: { separatorColor: theme.border },
      },
      grid: {
        vertLines: { color: "rgba(128,128,128,0.08)" },
        horzLines: { color: "rgba(128,128,128,0.08)" },
      },
      rightPriceScale: { borderVisible: false },
      timeScale: { borderVisible: false },
      crosshair: { mode: 0 },
    });

    const candles = chart.addSeries(CandlestickSeries, {
      upColor: COLORS.up,
      downColor: COLORS.down,
      wickUpColor: COLORS.up,
      wickDownColor: COLORS.down,
      borderVisible: false,
    });
    candles.setData(data.candles.map((c) => ({ ...c, time: c.time as Time })));

    const volume = chart.addSeries(HistogramSeries, {
      priceScaleId: "volume",
      priceFormat: { type: "volume" },
      lastValueVisible: false,
      priceLineVisible: false,
    });
    volume.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    volume.setData(
      data.candles.map((c) => ({
        time: c.time as Time,
        value: c.volume,
        color: c.close >= c.open ? "rgba(34,160,107,0.35)" : "rgba(229,72,77,0.35)",
      })),
    );

    const addLine = (points: Point[], color: string, pane = 0, width: 1 | 2 = 1, dashed = false) => {
      const s = chart.addSeries(
        LineSeries,
        { color, lineWidth: width, lineStyle: dashed ? 2 : 0, lastValueVisible: false, priceLineVisible: false },
        pane,
      );
      s.setData(line(points));
      return s;
    };

    const ind = data.indicators;
    if (overlays.sma) {
      addLine(ind.sma20, COLORS.sma20);
      addLine(ind.sma50, COLORS.sma50, 0, 2);
      addLine(ind.sma200, COLORS.sma200, 0, 2);
    }
    if (overlays.bollinger) {
      addLine(ind.bb_upper, COLORS.bb, 0, 1, true);
      addLine(ind.bb_lower, COLORS.bb, 0, 1, true);
    }
    let pane = 1;
    if (overlays.rsi) {
      const rsi = addLine(ind.rsi14, COLORS.rsi, pane, 2);
      rsi.createPriceLine({ price: 70, color: COLORS.down, lineStyle: 2, lineWidth: 1, axisLabelVisible: false, title: "" });
      rsi.createPriceLine({ price: 30, color: COLORS.up, lineStyle: 2, lineWidth: 1, axisLabelVisible: false, title: "" });
      pane += 1;
    }
    if (overlays.macd) {
      const hist = chart.addSeries(HistogramSeries, { lastValueVisible: false, priceLineVisible: false }, pane);
      hist.setData(
        ind.macd_hist.map((p) => ({
          time: p.time as Time,
          value: p.value,
          color: p.value >= 0 ? "rgba(34,160,107,0.6)" : "rgba(229,72,77,0.6)",
        })),
      );
      addLine(ind.macd, COLORS.macd, pane);
      addLine(ind.macd_signal, COLORS.signal, pane);
    }
    const panes = chart.panes();
    panes.slice(1).forEach((p) => p.setHeight(110));
    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [data, overlays]);

  return <div ref={ref} className="h-[520px] w-full" />;
}

export function LineChart({ series, height = 260 }: { series: { points: Point[]; color: string; title: string }[]; height?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current) return;
    const chart = createChart(ref.current, {
      autoSize: true,
      localization: { locale: "es-AR" },
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: themeColors().text,
      },
      grid: { vertLines: { visible: false }, horzLines: { color: "rgba(128,128,128,0.08)" } },
      rightPriceScale: { borderVisible: false },
      timeScale: { borderVisible: false },
    });
    for (const s of series) {
      chart.addSeries(LineSeries, { color: s.color, lineWidth: 2, title: s.title, priceLineVisible: false }).setData(line(s.points));
    }
    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [series]);
  return <div ref={ref} style={{ height }} className="w-full" />;
}
