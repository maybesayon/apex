"use client";

import Link from "next/link";
import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { StockSearch } from "@/components/stock-search";
import {
  Button,
  Card,
  Delta,
  EmptyState,
  ErrorState,
  Input,
  PageTransition,
  SectionHeading,
  Skeleton,
  SymbolMark,
} from "@/components/ui";
import { api } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import { cn, money, percent } from "@/lib/utils";

/** Recharts is the right tool here — allocation is a simple proportion. */
const SLICE_COLORS = [
  "#0a84ff",
  "#00a862",
  "#c77700",
  "#8e5cff",
  "#e0334b",
  "#00a3a3",
  "#d2691e",
  "#6e6e73",
];

function AddPosition({ onSaved }: { onSaved: () => void }) {
  const [open, setOpen] = useState(false);
  const [symbol, setSymbol] = useState("");
  const [shares, setShares] = useState("");
  const [cost, setCost] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    const s = Number(shares);
    const c = Number(cost);
    if (!symbol.trim()) return setError("Enter a ticker.");
    if (!(s > 0)) return setError("Shares must be greater than zero.");
    if (!(c > 0)) return setError("Average cost must be greater than zero.");

    setBusy(true);
    setError(null);
    try {
      await api.savePosition(symbol.trim().toUpperCase(), s, c);
      setSymbol("");
      setShares("");
      setCost("");
      setOpen(false);
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save");
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <Button onClick={() => setOpen(true)}>
        <Plus className="size-4" />
        Add position
      </Button>
    );
  }

  return (
    <Card className="mt-4 p-5">
      <form onSubmit={save} className="grid gap-3 sm:grid-cols-3">
        <Input
          label="Ticker"
          name="symbol"
          placeholder="AAPL"
          value={symbol}
          onChange={(e) => setSymbol(e.target.value)}
          autoFocus
        />
        <Input
          label="Shares"
          name="shares"
          type="number"
          step="any"
          min="0"
          value={shares}
          onChange={(e) => setShares(e.target.value)}
        />
        <Input
          label="Average cost"
          name="cost"
          type="number"
          step="any"
          min="0"
          value={cost}
          onChange={(e) => setCost(e.target.value)}
        />
        {error && (
          <p className="text-[13px] text-down sm:col-span-3">{error}</p>
        )}
        <div className="flex gap-2 sm:col-span-3">
          <Button type="submit" variant="primary" loading={busy}>
            Save
          </Button>
          <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
            Cancel
          </Button>
        </div>
      </form>
    </Card>
  );
}

export default function PortfolioPage() {
  const portfolio = useAsync(() => api.portfolio(), []);
  const stats = useAsync(() => api.journalStats(), []);
  const [removing, setRemoving] = useState<string | null>(null);

  async function remove(symbol: string) {
    setRemoving(symbol);
    try {
      await api.deletePosition(symbol);
      portfolio.reload();
    } finally {
      setRemoving(null);
    }
  }

  if (portfolio.error)
    return <ErrorState message={portfolio.error} onRetry={portfolio.reload} />;

  const data = portfolio.data;
  const positions = data?.positions ?? [];
  const allocation = positions.map((p, i) => ({
    name: p.symbol,
    value: p.value,
    fill: SLICE_COLORS[i % SLICE_COLORS.length],
  }));

  return (
    <PageTransition>
      <SectionHeading title="Portfolio" level={1} />

      {portfolio.loading ? (
        <Skeleton className="h-[150px] rounded-[var(--radius-lg)]" />
      ) : positions.length === 0 ? (
        <>
          <EmptyState
            title="No holdings yet"
            body="Add a position to track its value, profit and loss."
          />
          <div className="mt-4">
            <AddPosition onSaved={portfolio.reload} />
          </div>
        </>
      ) : (
        <>
          <Card className="rounded-[var(--radius-lg)] p-7">
            <p className="text-[13px] font-medium text-muted">
              Total portfolio value
            </p>
            <p className="tnum mt-2 text-[44px] font-semibold leading-none tracking-[-0.032em] text-ink">
              {money(data!.total_value)}
            </p>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <Delta value={data!.total_pnl_pct} showBackground />
              <span className="tnum text-[13.5px] text-muted">
                {money(data!.total_pnl)} unrealised
              </span>
            </div>
          </Card>

          <div className="mt-2.5 grid gap-2.5 sm:grid-cols-3">
            <Card className="p-4">
              <p className="text-[10.5px] font-semibold uppercase tracking-[0.05em] text-faint">
                Cost basis
              </p>
              <p className="tnum mt-1.5 text-[19px] font-semibold text-ink">
                {money(data!.total_cost)}
              </p>
            </Card>
            <Card className="p-4">
              <p className="text-[10.5px] font-semibold uppercase tracking-[0.05em] text-faint">
                Positions
              </p>
              <p className="tnum mt-1.5 text-[19px] font-semibold text-ink">
                {positions.length}
              </p>
            </Card>
            <Card className="p-4">
              <p className="text-[10.5px] font-semibold uppercase tracking-[0.05em] text-faint">
                Realised win rate
              </p>
              <p className="tnum mt-1.5 text-[19px] font-semibold text-ink">
                {stats.data?.win_rate == null
                  ? "—"
                  : `${stats.data.win_rate.toFixed(0)}%`}
              </p>
              <p className="mt-0.5 text-[12px] text-muted">
                {stats.data?.win_rate == null
                  ? "Log trades in the Journal"
                  : `${stats.data.wins} of ${stats.data.trades} trades`}
              </p>
            </Card>
          </div>

          <div className="mt-8 grid gap-4 lg:grid-cols-[1fr_320px]">
            <div>
              <SectionHeading
                title="Holdings"
                action={<AddPosition onSaved={portfolio.reload} />}
              />
              <Card className="overflow-hidden p-1.5">
                {positions.map((p, i) => (
                  <div key={p.symbol}>
                    {i > 0 && <div className="mx-4 h-px bg-line" />}
                    <div className="group flex items-center gap-3.5 rounded-2xl px-4 py-3 transition-colors hover:bg-surface-2">
                      <Link
                        href={`/stocks/${p.symbol}`}
                        className="flex min-w-0 flex-1 items-center gap-3.5"
                      >
                        <SymbolMark symbol={p.symbol} />
                        <span className="min-w-0 flex-1">
                          <span className="block text-[15px] font-semibold text-ink">
                            {p.symbol}
                          </span>
                          <span className="block truncate text-[12.5px] text-muted">
                            {p.shares} shares · avg {money(p.avg_cost)}
                          </span>
                        </span>
                        <span className="text-right">
                          <span className="tnum block text-[15px] font-semibold text-ink">
                            {money(p.value)}
                          </span>
                          <span
                            className={cn(
                              "tnum block text-[12.5px] font-medium",
                              p.pnl >= 0 ? "text-up" : "text-down",
                            )}
                          >
                            {money(p.pnl)} ({percent(p.pnl_pct)})
                          </span>
                        </span>
                      </Link>
                      <button
                        onClick={() => remove(p.symbol)}
                        disabled={removing === p.symbol}
                        aria-label={`Remove ${p.symbol}`}
                        className="rounded-full p-2 text-faint opacity-0 transition-opacity hover:text-down focus-visible:opacity-100 group-hover:opacity-100 disabled:opacity-40"
                      >
                        <Trash2 className="size-[16px]" />
                      </button>
                    </div>
                  </div>
                ))}
              </Card>
            </div>

            <div>
              <SectionHeading title="Allocation" />
              <Card className="p-4">
                <div style={{ height: 210 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={allocation}
                        dataKey="value"
                        nameKey="name"
                        innerRadius={56}
                        outerRadius={88}
                        paddingAngle={2}
                        stroke="none"
                      >
                        {allocation.map((slice) => (
                          <Cell key={slice.name} fill={slice.fill} />
                        ))}
                      </Pie>
                      <Tooltip
                        formatter={(v) => money(typeof v === "number" ? v : null)}
                        contentStyle={{
                          borderRadius: 12,
                          border: "1px solid var(--color-line)",
                          background: "var(--color-surface)",
                          fontSize: 13,
                        }}
                      />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
                <ul className="mt-3 flex flex-col gap-1.5">
                  {allocation.map((slice) => (
                    <li
                      key={slice.name}
                      className="flex items-center gap-2 text-[13px]"
                    >
                      <span
                        className="size-2.5 rounded-full"
                        style={{ background: slice.fill }}
                        aria-hidden
                      />
                      <span className="flex-1 text-ink">{slice.name}</span>
                      <span className="tnum text-muted">
                        {((slice.value / (data!.total_value || 1)) * 100).toFixed(
                          1,
                        )}
                        %
                      </span>
                    </li>
                  ))}
                </ul>
              </Card>
            </div>
          </div>
        </>
      )}
    </PageTransition>
  );
}
