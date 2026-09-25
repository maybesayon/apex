"use client";

import { useEffect, useState } from "react";
import { api, type PortfolioResponse, type WatchlistItem } from "@/lib/api";
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
import { money } from "@/lib/utils";

export default function OverviewPage() {
  const [portfolio, setPortfolio] = useState<PortfolioResponse | null>(null);
  const [watchlist, setWatchlist] = useState<WatchlistItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setError(null);
    try {
      const [p, w] = await Promise.all([api.portfolio(), api.watchlist()]);
      setPortfolio(p);
      setWatchlist(w);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    }
  }

  useEffect(() => {
    void load();
  }, []);

  if (error) return <ErrorState message={error} onRetry={load} />;

  return (
    <PageTransition>
      <SectionHeading title="Portfolio" />
      {!portfolio ? (
        <Skeleton className="h-[148px] rounded-[var(--radius-lg)]" />
      ) : portfolio.positions.length === 0 ? (
        <EmptyState
          title="No holdings yet"
          body="Add your first position to track value and performance."
        />
      ) : (
        <Card className="rounded-[var(--radius-lg)] p-7">
          <p className="text-[13px] font-medium text-muted">
            Total portfolio value
          </p>
          <p className="tnum mt-2 text-[44px] font-semibold leading-none tracking-[-0.032em] text-ink">
            {money(portfolio.total_value)}
          </p>
          <div className="mt-3">
            <Delta value={portfolio.total_pnl_pct} showBackground />
          </div>
        </Card>
      )}

      <div className="mt-9">
        <SectionHeading title="Watchlist" />
        <Card className="overflow-hidden p-1.5">
          {!watchlist ? (
            <div className="space-y-1 p-2">
              {[0, 1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-14" />
              ))}
            </div>
          ) : watchlist.length === 0 ? (
            <p className="px-4 py-8 text-center text-[14px] text-muted">
              Your watchlist is empty.
            </p>
          ) : (
            watchlist.map((item, i) => (
              <div key={item.symbol}>
                {i > 0 && <div className="mx-4 h-px bg-line" />}
                <div className="flex items-center gap-3.5 rounded-2xl px-4 py-3 transition-colors hover:bg-surface-2">
                  <SymbolMark symbol={item.symbol} />
                  <div className="min-w-0 flex-1">
                    <p className="text-[15px] font-semibold text-ink">
                      {item.symbol}
                    </p>
                    {item.name && item.name !== item.symbol && (
                      <p className="truncate text-[12.5px] text-muted">
                        {item.name}
                      </p>
                    )}
                  </div>
                  <div className="text-right">
                    <p className="tnum text-[15px] font-semibold text-ink">
                      {money(item.price)}
                    </p>
                    <Delta value={item.pct_change} className="text-[12.5px]" />
                  </div>
                </div>
              </div>
            ))
          )}
        </Card>
      </div>
    </PageTransition>
  );
}
