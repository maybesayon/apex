"use client";

/**
 * Scrolling price strip.
 *
 * Built from our own /quotes endpoint rather than TradingView's embed.
 * The embed painted a white background in dark mode while using its
 * dark-theme (pale) text — unreadable — and being an iframe it could not
 * be themed, audited for contrast, or made keyboard-navigable. This uses
 * the same tokens as the rest of the app, links through to each stock,
 * and is real text.
 *
 * The list is duplicated once so the marquee can loop seamlessly: the
 * animation translates by exactly -50%, at which point the second copy
 * sits where the first started.
 */

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type Quote } from "@/lib/api";
import { cn, money, percent } from "@/lib/utils";

const REFRESH_MS = 60_000;

function TapeItem({ quote }: { quote: Quote }) {
  const up = quote.pct_change >= 0;
  return (
    <Link
      href={`/stocks/${quote.symbol}`}
      className="flex shrink-0 items-baseline gap-2 px-4 py-2 transition-colors hover:bg-surface-2"
    >
      <span className="text-[13px] font-semibold text-ink">{quote.symbol}</span>
      <span className="tnum text-[13px] text-muted">{money(quote.price)}</span>
      <span
        className={cn(
          "tnum text-[12.5px] font-medium",
          up ? "text-up" : "text-down",
        )}
      >
        {percent(quote.pct_change)}
      </span>
    </Link>
  );
}

export function TickerTape({ symbols }: { symbols: string[] }) {
  const [quotes, setQuotes] = useState<Quote[] | null>(null);

  useEffect(() => {
    if (symbols.length === 0) {
      setQuotes([]);
      return;
    }
    let cancelled = false;
    const load = () =>
      api
        .quotes(symbols)
        .then((q) => {
          if (!cancelled) setQuotes(q);
        })
        .catch(() => {
          if (!cancelled) setQuotes([]);
        });

    void load();
    const timer = window.setInterval(load, REFRESH_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [symbols.join(",")]);

  // Reserve the height while loading so the page does not jump.
  if (!quotes || quotes.length === 0) {
    return <div className="h-[38px] border-b border-line" aria-hidden />;
  }

  // Duration scales with item count so the speed feels constant whether
  // the user follows four stocks or twenty.
  const duration = Math.max(28, quotes.length * 5);

  return (
    <div
      className="group relative -mx-4 overflow-hidden border-b border-line md:-mx-8"
      role="region"
      aria-label="Live prices"
    >
      <div
        className="flex w-max animate-[tape_linear_infinite] group-hover:[animation-play-state:paused]"
        style={{ animationDuration: `${duration}s` }}
      >
        {/* Duplicated for the seamless loop; the copy is hidden from
            assistive tech so prices are not announced twice. */}
        {[0, 1].map((copy) => (
          <div key={copy} className="flex" aria-hidden={copy === 1}>
            {quotes.map((q) => (
              <TapeItem key={`${copy}-${q.symbol}`} quote={q} />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
