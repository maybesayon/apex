"use client";

/**
 * Symbol search.
 *
 * Matches on ticker or company name — "apple" and "AAPL" both find AAPL —
 * because the ranking already lives in the backend's symbols.py. This is a
 * thin, debounced view of it.
 */

import { AnimatePresence, motion } from "motion/react";
import { useRouter } from "next/navigation";
import { Search, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api, type SearchResult } from "@/lib/api";
import { SymbolMark } from "@/components/ui";
import { cn } from "@/lib/utils";

export function StockSearch({
  placeholder = "Search stocks, ETFs or companies…",
  autoFocus = false,
}: {
  placeholder?: string;
  autoFocus?: boolean;
}) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(0);
  const boxRef = useRef<HTMLDivElement>(null);

  // Debounced so typing "microsoft" is one request, not nine.
  useEffect(() => {
    const term = query.trim();
    if (!term) {
      setResults([]);
      return;
    }
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      try {
        const hits = await api.search(term, 8);
        setResults(hits);
        setHighlight(0);
      } catch {
        setResults([]);
      }
    }, 180);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [query]);

  useEffect(() => {
    function onClickAway(e: MouseEvent) {
      if (!boxRef.current?.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClickAway);
    return () => document.removeEventListener("mousedown", onClickAway);
  }, []);

  function go(symbol: string) {
    setOpen(false);
    setQuery("");
    router.push(`/stocks/${symbol}`);
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (!open || results.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlight((h) => (h + 1) % results.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlight((h) => (h - 1 + results.length) % results.length);
    } else if (e.key === "Enter") {
      e.preventDefault();
      go(results[highlight].symbol);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  }

  return (
    <div ref={boxRef} className="relative w-full">
      <div className="relative">
        <Search className="pointer-events-none absolute left-3.5 top-1/2 size-[17px] -translate-y-1/2 text-faint" />
        <input
          value={query}
          autoFocus={autoFocus}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKeyDown}
          placeholder={placeholder}
          aria-label="Search stocks"
          className={cn(
            "w-full rounded-full border border-line-strong bg-surface py-2.5 pl-11 pr-9",
            "text-[15px] text-ink placeholder:text-faint",
            "transition-[border-color,box-shadow] duration-200",
            "focus:border-accent focus:outline-none focus:ring-[3.5px] focus:ring-accent-soft",
          )}
        />
        {query && (
          <button
            onClick={() => setQuery("")}
            aria-label="Clear search"
            className="absolute right-3 top-1/2 -translate-y-1/2 text-faint hover:text-ink"
          >
            <X className="size-4" />
          </button>
        )}
      </div>

      <AnimatePresence>
        {open && results.length > 0 && (
          <motion.ul
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.18, ease: [0.32, 0.72, 0, 1] }}
            className="absolute z-50 mt-2 w-full overflow-hidden rounded-2xl border border-line bg-surface p-1.5 shadow-card-lg"
          >
            {results.map((r, i) => (
              <li key={r.symbol}>
                <button
                  onMouseEnter={() => setHighlight(i)}
                  onClick={() => go(r.symbol)}
                  className={cn(
                    "flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-colors",
                    i === highlight ? "bg-surface-2" : "hover:bg-surface-2",
                  )}
                >
                  <SymbolMark symbol={r.symbol} size={32} />
                  <span className="min-w-0 flex-1">
                    <span className="block text-[14.5px] font-semibold text-ink">
                      {r.symbol}
                    </span>
                    <span className="block truncate text-[12.5px] text-muted">
                      {r.name}
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </motion.ul>
        )}
      </AnimatePresence>
    </div>
  );
}
