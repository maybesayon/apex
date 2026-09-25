"use client";

import Link from "next/link";
import { ArrowRight, FlaskConical, MessageSquare } from "lucide-react";
import {
  Card,
  Delta,
  EmptyState,
  ErrorState,
  PageTransition,
  SectionHeading,
  Skeleton,
  SymbolMark,
} from "@/components/ui";
import { api } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import { cn, money } from "@/lib/utils";

const PULSE = ["SPY", "QQQ", "VIX"];

export default function OverviewPage() {
  const portfolio = useAsync(() => api.portfolio(), []);
  const watchlist = useAsync(() => api.watchlist(), []);
  const pulse = useAsync(() => api.quotes(PULSE), []);

  const spy = pulse.data?.find((q) => q.symbol === "SPY");
  const vix = pulse.data?.find((q) => q.symbol === "VIX");
  const bullish = (spy?.pct_change ?? 0) >= 0;

  if (portfolio.error)
    return <ErrorState message={portfolio.error} onRetry={portfolio.reload} />;

  return (
    <PageTransition>
      {/* Market pulse — the banner from the Streamlit Overview tab. */}
      <SectionHeading title="Market" />
      <div className="grid grid-cols-2 gap-2.5 lg:grid-cols-4">
        {pulse.loading ? (
          [0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-[86px] rounded-[var(--radius-card)]" />
          ))
        ) : (
          <>
            <Card className="p-4">
              <p className="text-[10.5px] font-semibold uppercase tracking-[0.05em] text-faint">Condition</p>
              <p className={cn("mt-1.5 text-[19px] font-semibold", bullish ? "text-up" : "text-down")}>
                {bullish ? "Bullish" : "Bearish"}
              </p>
            </Card>
            <Card className="p-4">
              <p className="text-[10.5px] font-semibold uppercase tracking-[0.05em] text-faint">S&amp;P 500</p>
              <Delta value={spy?.pct_change} className="mt-1.5 text-[19px] font-semibold" />
            </Card>
            <Card className="p-4">
              <p className="text-[10.5px] font-semibold uppercase tracking-[0.05em] text-faint">Volatility</p>
              <p className="tnum mt-1.5 text-[19px] font-semibold text-ink">
                {vix ? vix.price.toFixed(2) : "—"}
              </p>
              <p className="mt-0.5 text-[12px] text-muted">VIX</p>
            </Card>
            <Card className="p-4">
              <p className="text-[10.5px] font-semibold uppercase tracking-[0.05em] text-faint">Sentiment</p>
              <p className="mt-1.5 text-[19px] font-semibold text-ink">
                {vix ? (vix.price < 20 ? "Low fear" : "Elevated fear") : "—"}
              </p>
            </Card>
          </>
        )}
      </div>

      {/* Portfolio */}
      <div className="mt-9">
        <SectionHeading
          title="Portfolio"
          action={
            <Link href="/portfolio" className="inline-flex items-center gap-1 text-[13px] text-accent hover:underline">
              Manage <ArrowRight className="size-3.5" />
            </Link>
          }
        />
        {portfolio.loading ? (
          <Skeleton className="h-[148px] rounded-[var(--radius-lg)]" />
        ) : (portfolio.data?.positions.length ?? 0) === 0 ? (
          <EmptyState title="No holdings yet" body="Add your first position to track value and performance." />
        ) : (
          <Card className="rounded-[var(--radius-lg)] p-7">
            <p className="text-[13px] font-medium text-muted">Total portfolio value</p>
            <p className="tnum mt-2 text-[44px] font-semibold leading-none tracking-[-0.032em] text-ink">
              {money(portfolio.data!.total_value)}
            </p>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <Delta value={portfolio.data!.total_pnl_pct} showBackground />
              <span className="tnum text-[13.5px] text-muted">
                {money(portfolio.data!.total_pnl)} unrealised
              </span>
            </div>
          </Card>
        )}
      </div>

      {/* Watchlist */}
      <div className="mt-9">
        <SectionHeading
          title="Watchlist"
          action={
            <Link href="/watchlist" className="inline-flex items-center gap-1 text-[13px] text-accent hover:underline">
              See all <ArrowRight className="size-3.5" />
            </Link>
          }
        />
        <Card className="overflow-hidden p-1.5">
          {watchlist.loading ? (
            <div className="space-y-1 p-2">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-14" />)}</div>
          ) : (watchlist.data ?? []).length === 0 ? (
            <p className="px-4 py-8 text-center text-[14px] text-muted">Your watchlist is empty.</p>
          ) : (
            (watchlist.data ?? []).slice(0, 6).map((item, i) => (
              <div key={item.symbol}>
                {i > 0 && <div className="mx-4 h-px bg-line" />}
                <Link
                  href={`/stocks/${item.symbol}`}
                  className="flex items-center gap-3.5 rounded-2xl px-4 py-3 transition-colors hover:bg-surface-2"
                >
                  <SymbolMark symbol={item.symbol} />
                  <div className="min-w-0 flex-1">
                    <p className="text-[15px] font-semibold text-ink">{item.symbol}</p>
                    {item.name && item.name !== item.symbol && (
                      <p className="truncate text-[12.5px] text-muted">{item.name}</p>
                    )}
                  </div>
                  <div className="text-right">
                    <p className="tnum text-[15px] font-semibold text-ink">{money(item.price)}</p>
                    <Delta value={item.pct_change} className="text-[12.5px]" />
                  </div>
                </Link>
              </div>
            ))
          )}
        </Card>
      </div>

      {/* Tools — the two destinations that do not fit the mobile tab bar. */}
      <div className="mt-9 grid gap-3 sm:grid-cols-2">
        {[
          { href: "/backtest", icon: FlaskConical, title: "Backtest a strategy", body: "Test RSI + MACD momentum over two years of daily bars." },
          { href: "/assistant", icon: MessageSquare, title: "Ask the assistant", body: "Questions about a stock, a strategy or your own positions." },
        ].map(({ href, icon: Icon, title, body }) => (
          <Link key={href} href={href}>
            <Card interactive className="flex h-full items-start gap-3.5 p-5">
              <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-accent-soft text-accent">
                <Icon className="size-[18px]" />
              </span>
              <span className="min-w-0">
                <span className="block text-[15px] font-semibold text-ink">{title}</span>
                <span className="mt-0.5 block text-[13px] text-muted">{body}</span>
              </span>
            </Card>
          </Link>
        ))}
      </div>
    </PageTransition>
  );
}
