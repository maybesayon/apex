"use client";

/**
 * Price chart, built on TradingView's Lightweight Charts.
 *
 * Chosen over Recharts because Recharts has no candlestick primitive —
 * OHLC bars would have to be hand-rolled, and overlaying moving averages
 * plus a separate RSI pane gets awkward fast. Lightweight Charts is ~45KB
 * and purpose-built for exactly this.
 *
 * Note: v5 replaced `chart.addAreaSeries(opts)` with
 * `chart.addSeries(AreaSeries, opts)`.
 */

import {
  AreaSeries,
  CandlestickSeries,
  ColorType,
  LineSeries,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";
import { useEffect, useRef } from "react";
import { useTheme } from "@/components/providers";
import type { Bar } from "@/lib/api";

export type ChartStyle = "area" | "candles";

/** Palette read from the live CSS tokens, so the chart follows the theme. */
function tokens() {
  const css = getComputedStyle(document.documentElement);
  const read = (name: string, fallback: string) =>
    css.getPropertyValue(name).trim() || fallback;
  return {
    up: read("--color-up", "#00a862"),
    down: read("--color-down", "#e0334b"),
    ink: read("--color-ink", "#1d1d1f"),
    muted: read("--color-muted", "#6e6e73"),
    line: read("--color-line", "rgba(0,0,0,0.07)"),
    surface: read("--color-surface", "#ffffff"),
    accent: read("--color-accent", "#0a84ff"),
  };
}

function toTime(iso: string): UTCTimestamp {
  return (Date.parse(`${iso}T00:00:00Z`) / 1000) as UTCTimestamp;
}

export function PriceChart({
  bars,
  style = "area",
  height = 340,
  overlays,
}: {
  bars: Bar[];
  style?: ChartStyle;
  height?: number;
  /** Optional indicator lines, e.g. moving averages. */
  overlays?: { label: string; color: string; points: (number | null)[] }[];
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const { theme } = useTheme();

  useEffect(() => {
    const el = containerRef.current;
    if (!el || bars.length === 0) return;

    const t = tokens();
    // Direction over the visible window decides the colour, so a falling
    // stock is not drawn in green.
    const first = bars[0]?.close ?? 0;
    const last = bars[bars.length - 1]?.close ?? 0;
    const rising = last >= first;
    const tone = rising ? t.up : t.down;

    const chart = createChart(el, {
      height,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: t.muted,
        fontFamily:
          '-apple-system, BlinkMacSystemFont, "SF Pro Display", Inter, sans-serif',
        fontSize: 11,
        attributionLogo: false,
      },
      // Minimal grid: one horizontal reference set, no vertical noise.
      grid: {
        vertLines: { visible: false },
        horzLines: { color: t.line },
      },
      rightPriceScale: { borderVisible: false, scaleMargins: { top: 0.12, bottom: 0.08 } },
      timeScale: { borderVisible: false, fixLeftEdge: true, fixRightEdge: true },
      crosshair: {
        mode: 1,
        vertLine: { color: t.muted, width: 1, style: 3, labelBackgroundColor: t.ink },
        horzLine: { color: t.muted, width: 1, style: 3, labelBackgroundColor: t.ink },
      },
      handleScale: { axisPressedMouseMove: false },
      autoSize: true,
    });
    chartRef.current = chart;

    let series: ISeriesApi<"Area"> | ISeriesApi<"Candlestick">;
    if (style === "candles") {
      series = chart.addSeries(CandlestickSeries, {
        upColor: t.up,
        downColor: t.down,
        borderUpColor: t.up,
        borderDownColor: t.down,
        wickUpColor: t.up,
        wickDownColor: t.down,
      });
      series.setData(
        bars
          .filter((b) => b.open != null && b.close != null)
          .map((b) => ({
            time: toTime(b.time) as Time,
            open: b.open as number,
            high: b.high as number,
            low: b.low as number,
            close: b.close as number,
          })),
      );
    } else {
      series = chart.addSeries(AreaSeries, {
        lineColor: tone,
        topColor: `${tone}33`,
        bottomColor: `${tone}05`,
        lineWidth: 2,
        priceLineVisible: false,
      });
      series.setData(
        bars
          .filter((b) => b.close != null)
          .map((b) => ({ time: toTime(b.time) as Time, value: b.close as number })),
      );
    }

    for (const overlay of overlays ?? []) {
      const line = chart.addSeries(LineSeries, {
        color: overlay.color,
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      });
      line.setData(
        overlay.points
          .map((value, i) =>
            value == null || bars[i] == null
              ? null
              : { time: toTime(bars[i].time) as Time, value },
          )
          .filter((p): p is { time: Time; value: number } => p !== null),
      );
    }

    chart.timeScale().fitContent();

    return () => {
      chart.remove();
      chartRef.current = null;
    };
  }, [bars, style, height, overlays, theme]);

  if (bars.length === 0) {
    return (
      <div
        className="flex items-center justify-center rounded-[var(--radius-card)] border border-line text-[13.5px] text-muted"
        style={{ height }}
      >
        No price history available
      </div>
    );
  }

  return <div ref={containerRef} style={{ height }} className="w-full" />;
}

export const RANGES = [
  { label: "1M", period: "1mo" },
  { label: "3M", period: "3mo" },
  { label: "6M", period: "6mo" },
  { label: "1Y", period: "1y" },
  { label: "2Y", period: "2y" },
  { label: "5Y", period: "5y" },
] as const;

export type RangeKey = (typeof RANGES)[number]["period"];
