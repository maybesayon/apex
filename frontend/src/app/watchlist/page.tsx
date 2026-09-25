"use client";

import Link from "next/link";
import { Trash2 } from "lucide-react";
import { useState } from "react";
import { StockSearch } from "@/components/stock-search";
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
import { money } from "@/lib/utils";

export default function WatchlistPage() {
  const list = useAsync(() => api.watchlist(), []);
  const [removing, setRemoving] = useState<string | null>(null);

  async function remove(symbol: string) {
    setRemoving(symbol);
    try {
      await api.removeFromWatchlist(symbol);
      list.reload();
    } finally {
      setRemoving(null);
    }
  }

  if (list.error) return <ErrorState message={list.error} onRetry={list.reload} />;

  return (
    <PageTransition>
      <SectionHeading title="Watchlist" />
      <div className="mb-5 max-w-[520px]">
        <StockSearch placeholder="Find a stock to open or add…" />
      </div>

      {list.loading ? (
        <Card className="space-y-1 p-2">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-16" />
          ))}
        </Card>
      ) : (list.data ?? []).length === 0 ? (
        <EmptyState
          title="Your watchlist is empty"
          body="Search for a stock above, then add it from its page."
        />
      ) : (
        <Card className="overflow-hidden p-1.5">
          {(list.data ?? []).map((item, i) => (
            <div key={item.symbol}>
              {i > 0 && <div className="mx-4 h-px bg-line" />}
              <div className="group flex items-center gap-3.5 rounded-2xl px-4 py-3 transition-colors hover:bg-surface-2">
                <Link
                  href={`/stocks/${item.symbol}`}
                  className="flex min-w-0 flex-1 items-center gap-3.5"
                >
                  <SymbolMark symbol={item.symbol} />
                  <span className="min-w-0 flex-1">
                    <span className="block text-[15px] font-semibold text-ink">
                      {item.symbol}
                    </span>
                    {item.name && item.name !== item.symbol && (
                      <span className="block truncate text-[12.5px] text-muted">
                        {item.name}
                      </span>
                    )}
                  </span>
                  <span className="text-right">
                    <span className="tnum block text-[15px] font-semibold text-ink">
                      {money(item.price)}
                    </span>
                    <Delta value={item.pct_change} className="text-[12.5px]" />
                  </span>
                </Link>
                <button
                  onClick={() => remove(item.symbol)}
                  disabled={removing === item.symbol}
                  aria-label={`Remove ${item.symbol} from watchlist`}
                  className="rounded-full p-2 text-faint opacity-0 transition-opacity hover:text-down focus-visible:opacity-100 group-hover:opacity-100 disabled:opacity-40"
                >
                  <Trash2 className="size-[16px]" />
                </button>
              </div>
            </div>
          ))}
        </Card>
      )}
    </PageTransition>
  );
}
