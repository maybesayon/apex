"use client";

/**
 * TradingView embed widgets.
 *
 * In Streamlit these were HTML strings shoved through st.iframe
 * (tradingview.py's tv_*_html functions). React embeds the scripts
 * directly, which is simpler and lets the widgets follow our theme.
 *
 * Each widget is a <script> the vendor injects into its own container, so
 * the effect has to clear the container on teardown — React will not do it
 * for DOM the script created.
 */

import { useEffect, useRef } from "react";
import { useTheme } from "@/components/providers";

function useTradingViewWidget(
  src: string,
  config: Record<string, unknown>,
  deps: unknown[] = [],
) {
  const container = useRef<HTMLDivElement>(null);
  const { theme } = useTheme();

  useEffect(() => {
    const node = container.current;
    if (!node) return;

    node.innerHTML = "";
    // The vendor scripts querySelector for this exact class inside their
    // container. Without it they throw on load.
    const mount = document.createElement("div");
    mount.className = "tradingview-widget-container__widget";
    node.appendChild(mount);

    const script = document.createElement("script");
    script.src = src;
    script.async = true;
    script.type = "text/javascript";
    script.innerHTML = JSON.stringify({ ...config, colorTheme: theme });
    node.appendChild(script);

    return () => {
      node.innerHTML = "";
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [src, theme, ...deps]);

  return container;
}

/** Full interactive price chart — the Charts tab in Streamlit. */
export function AdvancedChart({
  symbol,
  height = 520,
}: {
  symbol: string;
  height?: number;
}) {
  const { theme } = useTheme();
  const container = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const node = container.current;
    if (!node) return;
    node.innerHTML = "";
    const mount = document.createElement("div");
    mount.className = "tradingview-widget-container__widget";
    mount.style.height = "100%";
    node.appendChild(mount);

    const script = document.createElement("script");
    script.src =
      "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";
    script.async = true;
    script.innerHTML = JSON.stringify({
      autosize: true,
      symbol,
      interval: "D",
      timezone: "America/New_York",
      theme,
      style: "1",
      locale: "en",
      enable_publishing: false,
      allow_symbol_change: true,
      hide_side_toolbar: false,
      studies: ["RSI@tv-basicstudies"],
      support_host: "https://www.tradingview.com",
    });
    node.appendChild(script);

    return () => {
      node.innerHTML = "";
    };
  }, [symbol, theme]);

  return (
    <div
      className="tradingview-widget-container overflow-hidden rounded-[var(--radius-card)] border border-line"
      ref={container}
      style={{ height }}
    />
  );
}

/** Buy / neutral / sell gauge. */
export function TechnicalGauge({
  symbol,
  height = 400,
}: {
  symbol: string;
  height?: number;
}) {
  const ref = useTradingViewWidget(
    "https://s3.tradingview.com/external-embedding/embed-widget-technical-analysis.js",
    {
      interval: "1D",
      width: "100%",
      height,
      // isTransparent paints no background, and the widget then shows a
      // white page beneath while using pale dark-theme text. Let it paint
      // its own themed background instead.
      isTransparent: false,
      symbol,
      showIntervalTabs: true,
      displayMode: "single",
      locale: "en",
    },
    [symbol],
  );

  return (
    <div
      className="tradingview-widget-container overflow-hidden rounded-[var(--radius-card)] border border-line bg-surface"
      ref={ref}
      style={{ height }}
    />
  );
}
