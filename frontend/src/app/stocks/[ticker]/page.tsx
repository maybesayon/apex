"use client";

/**
 * Stock detail.
 *
 * Every number here comes from the Python analysis engine through the API —
 * nothing is recomputed in JavaScript. That is deliberate: the engine is
 * the tested source of truth, and a JS reimplementation would be a second
 * one that silently drifts.
 */

import { motion } from "motion/react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, Star } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { PriceChart, RANGES } from "@/components/price-chart";
import {
  Button,
  Card,
  Delta,
  ErrorState,
  PageTransition,
  Pill,
  SectionHeading,
  Skeleton,
  SymbolMark,
} from "@/components/ui";
import { api } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import { cn, money, percent } from "@/lib/utils";

type Analysis = {
  symbol: string;
  price: number;
  overall_score: number;
  indicators: Record<string, number | null>;
  signals: Record<string, { score: number; label: string; value: unknown }>;
  levels: Record<string, number | null>;
};

type Forecast = {
  direction: string;
  confidence: number;
  model_accuracy: number | null;
  baseline_accuracy: number | null;
  has_skill: boolean;
  edge_vs_baseline: number | null;
  note: string;
  top_factors: string[];
};

const INDICATOR_LABELS: Record<string, string> = {
  rsi: "RSI (14)",
  macd_hist: "MACD",
  ma50: "50-day MA",
  ma200: "200-day MA",
  vol_ratio: "Volume",
  atr: "ATR",
};

export default function StockPage() {
  const params = useParams<{ ticker: string }>();
  const ticker = (params.ticker ?? "").toUpperCase();

  const [period, setPeriod] = useState<string>("1y");
  const [watched, setWatched] = useState<boolean | null>(null);

  const quote = useAsync(() => api.quote(ticker), [ticker]);
  const profile = useAsync(() => api.profile(ticker), [ticker]);
  const history = useAsync(() => api.history(ticker, period), [ticker, period]);
  const analysis = useAsync(
    () => api.analysis(ticker) as Promise<Analysis>,
    [ticker],
  );
  const rating = useAsync(() => api.rating(ticker), [ticker]);

  // The forecast trains a model, so it is requested on demand rather than
  // on every page view.
  const [forecast, setForecast] = useState<Forecast | null>(null);
  const [forecastBusy, setForecastBusy] = useState(false);
  const [forecastError, setForecastError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .watchlist()
      .then((items) => {
        if (!cancelled) setWatched(items.some((i) => i.symbol === ticker));
      })
      .catch(() => {
        if (!cancelled) setWatched(false);
      });
    return () => {
      cancelled = true;
    };
  }, [ticker]);

  async function toggleWatch() {
    const next = !watched;
    setWatched(next); // optimistic — reverted below if the call fails
    try {
      if (next) await api.addToWatchlist(ticker);
      else await api.removeFromWatchlist(ticker);
    } catch {
      setWatched(!next);
    }
  }

  async function runForecast() {
    setForecastBusy(true);
    setForecastError(null);
    try {
      setForecast((await api.forecast(ticker)) as unknown as Forecast);
    } catch (e) {
      setForecastError(e instanceof Error ? e.message : "Forecast failed");
    } finally {
      setForecastBusy(false);
    }
  }

  const bars = history.data?.bars ?? [];
  const rangeChange = useMemo(() => {
    if (bars.length < 2) return null;
    const first = bars[0].close;
    const last = bars[bars.length - 1].close;
    if (!first || !last) return null;
    return ((last - first) / first) * 100;
  }, [bars]);

  if (quote.error && !quote.data) {
    return <ErrorState message={quote.error} onRetry={quote.reload} />;
  }

  return (
    <PageTransition>
      <Link
        href="/"
        className="mb-4 inline-flex items-center gap-1.5 text-[13.5px] text-muted transition-colors hover:text-ink"
      >
        <ArrowLeft className="size-4" />
        Back
      </Link>

      {/* ── Header ─────────────────────────────────────────────── */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3.5">
          <SymbolMark symbol={ticker} size={48} />
          <div>
            <h1 className="text-[26px] font-bold tracking-[-0.03em] text-ink">
              {ticker}
            </h1>
            <div className="text-[14px] text-muted">
              {profile.loading ? (
                <Skeleton className="mt-1 h-3.5 w-36" />
              ) : (
                (profile.data?.name ?? ticker)
              )}
            </div>
          </div>
        </div>
        <button
          onClick={toggleWatch}
          aria-label={watched ? "Remove from watchlist" : "Add to watchlist"}
          aria-pressed={watched ?? false}
          className={cn(
            "flex size-10 items-center justify-center rounded-full border transition-colors",
            watched
              ? "border-transparent bg-accent-soft text-accent"
              : "border-line-strong text-muted hover:text-ink",
          )}
        >
          <Star className={cn("size-[18px]", watched && "fill-current")} />
        </button>
      </div>

      <div className="mt-5">
        {quote.loading ? (
          <Skeleton className="h-12 w-52" />
        ) : (
          <>
            <p className="tnum text-[40px] font-semibold leading-none tracking-[-0.03em] text-ink">
              {money(quote.data?.price)}
            </p>
            <div className="mt-2.5 flex items-center gap-2">
              <Delta value={quote.data?.pct_change} showBackground />
              <span className="tnum text-[13.5px] text-muted">
                {money(quote.data?.change)} today
              </span>
            </div>
          </>
        )}
      </div>

      {/* ── Chart ──────────────────────────────────────────────── */}
      <Card className="mt-6 p-4 pb-3">
        {history.loading ? (
          <Skeleton className="h-[340px]" />
        ) : (
          <PriceChart bars={bars} height={340} />
        )}

        <div className="mt-3 flex items-center justify-between gap-3">
          <div className="flex gap-1 rounded-full bg-surface-2 p-1">
            {RANGES.map((r) => (
              <button
                key={r.period}
                onClick={() => setPeriod(r.period)}
                className={cn(
                  "relative rounded-full px-3 py-1.5 text-[12.5px] font-medium transition-colors",
                  period === r.period ? "text-ink" : "text-muted hover:text-ink",
                )}
              >
                {period === r.period && (
                  <motion.span
                    layoutId="range-pill"
                    className="absolute inset-0 rounded-full bg-surface shadow-card"
                    transition={{ duration: 0.26, ease: [0.32, 0.72, 0, 1] }}
                  />
                )}
                <span className="relative">{r.label}</span>
              </button>
            ))}
          </div>
          {rangeChange !== null && (
            <span className="tnum text-[13px] text-muted">
              <span className={rangeChange >= 0 ? "text-up" : "text-down"}>
                {percent(rangeChange)}
              </span>{" "}
              over range
            </span>
          )}
        </div>
      </Card>

      {/* ── Key metrics ────────────────────────────────────────── */}
      <div className="mt-9">
        <SectionHeading
          title="Technicals"
          action={
            analysis.data ? (
              <span className="text-[13px] text-muted">
                Signal score{" "}
                <span className="font-semibold text-ink">
                  {analysis.data.overall_score}/100
                </span>
              </span>
            ) : null
          }
        />
        {analysis.loading ? (
          <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-6">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-[86px] rounded-[var(--radius-card)]" />
            ))}
          </div>
        ) : analysis.error ? (
          <ErrorState message={analysis.error} onRetry={analysis.reload} />
        ) : (
          <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-6">
            {Object.entries(INDICATOR_LABELS).map(([key, label]) => {
              const value = analysis.data?.indicators?.[key];
              const isPrice = key.startsWith("ma") || key === "atr";
              return (
                <Card key={key} className="p-4" interactive>
                  <p className="text-[10.5px] font-semibold uppercase tracking-[0.05em] text-faint">
                    {label}
                  </p>
                  <p className="tnum mt-1.5 text-[19px] font-semibold tracking-[-0.02em] text-ink">
                    {value == null
                      ? "—"
                      : isPrice
                        ? money(value)
                        : key === "vol_ratio"
                          ? `${value.toFixed(1)}x`
                          : value.toFixed(2)}
                  </p>
                </Card>
              );
            })}
          </div>
        )}
      </div>

      {/* ── Signals and levels ─────────────────────────────────── */}
      {analysis.data && (
        <div className="mt-6 grid gap-4 lg:grid-cols-2">
          <Card className="p-5">
            <p className="mb-3 text-[14px] font-semibold text-ink">Signals</p>
            <ul className="flex flex-col gap-2.5">
              {Object.entries(analysis.data.signals).map(([name, s]) => (
                <li key={name} className="flex items-center gap-3">
                  <span className="w-[70px] shrink-0 text-[12.5px] uppercase tracking-wide text-muted">
                    {name}
                  </span>
                  <span className="flex gap-1" aria-hidden>
                    {[1, 2, 3, 4, 5].map((i) => (
                      <span
                        key={i}
                        className={cn(
                          "h-1.5 w-5 rounded-full",
                          i <= s.score ? "bg-up" : "bg-line-strong",
                        )}
                      />
                    ))}
                  </span>
                  <span className="flex-1 text-right text-[12.5px] text-muted">
                    {s.label}
                  </span>
                </li>
              ))}
            </ul>
          </Card>

          <Card className="p-5">
            <p className="mb-1 text-[14px] font-semibold text-ink">
              Suggested levels
            </p>
            <p className="mb-4 text-[12.5px] text-muted">
              Derived from volatility (ATR) and your configured risk limits.
              Not a recommendation.
            </p>
            <div className="grid grid-cols-3 gap-2.5">
              {[
                { key: "entry", label: "Entry", tone: "text-ink" },
                { key: "target", label: "Target", tone: "text-up" },
                { key: "stop", label: "Stop", tone: "text-down" },
              ].map(({ key, label, tone }) => (
                <div key={key} className="rounded-xl bg-surface-2 px-3 py-3">
                  <p className="text-[10.5px] font-semibold uppercase tracking-[0.05em] text-faint">
                    {label}
                  </p>
                  <p className={cn("tnum mt-1 text-[16px] font-semibold", tone)}>
                    {money(analysis.data!.levels[key])}
                  </p>
                </div>
              ))}
            </div>
            {analysis.data.levels.risk_reward != null && (
              <p className="mt-3 text-[12.5px] text-muted">
                Risk / reward{" "}
                <span className="font-semibold text-ink">
                  {analysis.data.levels.risk_reward}:1
                </span>
              </p>
            )}
          </Card>
        </div>
      )}

      {/* ── Rating and forecast ────────────────────────────────── */}
      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <Card className="p-5">
          <p className="mb-3 text-[14px] font-semibold text-ink">
            TradingView rating
          </p>
          {rating.loading ? (
            <Skeleton className="h-9 w-40" />
          ) : rating.data ? (
            <>
              <p
                className={cn(
                  "text-[24px] font-bold tracking-[-0.02em]",
                  rating.data.recommendation.includes("BUY")
                    ? "text-up"
                    : rating.data.recommendation.includes("SELL")
                      ? "text-down"
                      : "text-warn",
                )}
              >
                {rating.data.recommendation.replace(/_/g, " ")}
              </p>
              <div className="mt-2.5 flex gap-1.5">
                <Pill tone="up">{rating.data.buy} buy</Pill>
                <Pill>{rating.data.neutral} neutral</Pill>
                <Pill tone="down">{rating.data.sell} sell</Pill>
              </div>
            </>
          ) : (
            <p className="text-[13.5px] text-muted">
              Unavailable for this symbol.
            </p>
          )}
        </Card>

        <Card className="p-5">
          <p className="mb-1 text-[14px] font-semibold text-ink">Forecast</p>
          <p className="mb-4 text-[12.5px] text-muted">
            Gradient boosting, predicting a move above 5% within 10 trading
            days.
          </p>

          {!forecast && !forecastError && (
            <Button onClick={runForecast} loading={forecastBusy}>
              Run forecast
            </Button>
          )}
          {forecastError && (
            <p className="text-[13px] text-down">{forecastError}</p>
          )}

          {forecast && (
            <>
              {/* A model that loses to "always guess the majority class" has
                  no demonstrated skill. Saying so is more useful than the
                  headline accuracy, which looks respectable either way. */}
              {!forecast.has_skill && (
                <div className="mb-3 rounded-xl bg-down-soft px-3.5 py-3 text-[12.5px] text-down">
                  <strong className="font-semibold">
                    No demonstrated skill on {ticker}.
                  </strong>{" "}
                  Walk-forward accuracy {forecast.model_accuracy}% is{" "}
                  {Math.abs(forecast.edge_vs_baseline ?? 0).toFixed(1)} points
                  below the {forecast.baseline_accuracy}% you would get by
                  always guessing the majority class.
                </div>
              )}
              <div className="grid grid-cols-3 gap-2.5">
                <div className="rounded-xl bg-surface-2 px-3 py-3">
                  <p className="text-[10.5px] font-semibold uppercase tracking-[0.05em] text-faint">
                    Direction
                  </p>
                  <p className="mt-1 text-[15px] font-semibold text-ink">
                    {forecast.direction.charAt(0) +
                      forecast.direction.slice(1).toLowerCase()}
                  </p>
                </div>
                <div className="rounded-xl bg-surface-2 px-3 py-3">
                  <p className="text-[10.5px] font-semibold uppercase tracking-[0.05em] text-faint">
                    Accuracy
                  </p>
                  <p className="tnum mt-1 text-[15px] font-semibold text-ink">
                    {forecast.model_accuracy}%
                  </p>
                </div>
                <div className="rounded-xl bg-surface-2 px-3 py-3">
                  <p className="text-[10.5px] font-semibold uppercase tracking-[0.05em] text-faint">
                    Baseline
                  </p>
                  <p
                    className={cn(
                      "tnum mt-1 text-[15px] font-semibold",
                      forecast.has_skill ? "text-up" : "text-down",
                    )}
                  >
                    {forecast.baseline_accuracy}%
                  </p>
                </div>
              </div>
            </>
          )}
        </Card>
      </div>

      <p className="mt-8 text-center text-[12px] text-faint">
        APEX is an analysis tool. Nothing here is financial advice.
      </p>
    </PageTransition>
  );
}
