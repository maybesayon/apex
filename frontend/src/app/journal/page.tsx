"use client";

import { Plus } from "lucide-react";
import { useState } from "react";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  Input,
  PageTransition,
  SectionHeading,
  Skeleton,
} from "@/components/ui";
import { api } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import { cn, money, percent } from "@/lib/utils";

const STRATEGIES = ["Momentum", "Short Squeeze", "Earnings", "Breakout", "Mean Reversion"];

function LogTrade({ onSaved }: { onSaved: () => void }) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({
    symbol: "",
    date: new Date().toISOString().slice(0, 10),
    strategy: STRATEGIES[0],
    entry: "",
    exit: "",
    shares: "",
    note: "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  async function save(e: React.FormEvent) {
    e.preventDefault();
    const entry = Number(form.entry);
    const exit = Number(form.exit);
    const shares = Number(form.shares);
    if (!form.symbol.trim()) return setError("Enter a ticker.");
    if (!(entry > 0) || !(exit > 0)) return setError("Prices must be greater than zero.");
    if (!(shares > 0)) return setError("Shares must be greater than zero.");

    setBusy(true);
    setError(null);
    try {
      await api.journal(); // warm the session before the write
      const res = await fetch("/api/journal", {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token":
            document.cookie.split("; ").find((c) => c.startsWith("apex_csrf="))?.split("=")[1] ?? "",
        },
        body: JSON.stringify({
          date: form.date,
          symbol: form.symbol.trim().toUpperCase(),
          strategy: form.strategy,
          entry,
          exit,
          shares,
          note: form.note,
        }),
      });
      if (!res.ok) throw new Error((await res.json())?.detail ?? "Could not save");
      setForm({ ...form, symbol: "", entry: "", exit: "", shares: "", note: "" });
      setOpen(false);
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save");
    } finally {
      setBusy(false);
    }
  }

  if (!open)
    return (
      <Button onClick={() => setOpen(true)}>
        <Plus className="size-4" />
        Log a trade
      </Button>
    );

  return (
    <Card className="mt-4 p-5">
      <form onSubmit={save} className="grid gap-3 sm:grid-cols-3">
        <Input label="Ticker" name="symbol" placeholder="NVDA" value={form.symbol} onChange={set("symbol")} autoFocus />
        <Input label="Date" name="date" type="date" value={form.date} onChange={set("date")} />
        <div className="w-full">
          <label htmlFor="strategy" className="mb-1.5 block text-[13px] font-medium text-muted">Strategy</label>
          <select
            id="strategy"
            value={form.strategy}
            onChange={set("strategy")}
            className="w-full rounded-xl border border-line-strong bg-surface px-3.5 py-2.5 text-[15px] text-ink focus:border-accent focus:outline-none focus:ring-[3.5px] focus:ring-accent-soft"
          >
            {STRATEGIES.map((s) => <option key={s}>{s}</option>)}
          </select>
        </div>
        <Input label="Entry price" name="entry" type="number" step="any" min="0" value={form.entry} onChange={set("entry")} />
        <Input label="Exit price" name="exit" type="number" step="any" min="0" value={form.exit} onChange={set("exit")} />
        <Input label="Shares" name="shares" type="number" step="any" min="0" value={form.shares} onChange={set("shares")} />
        <div className="sm:col-span-3">
          <label htmlFor="note" className="mb-1.5 block text-[13px] font-medium text-muted">Notes and lessons</label>
          <textarea
            id="note"
            rows={3}
            value={form.note}
            onChange={set("note")}
            className="w-full rounded-xl border border-line-strong bg-surface px-3.5 py-2.5 text-[15px] text-ink placeholder:text-faint focus:border-accent focus:outline-none focus:ring-[3.5px] focus:ring-accent-soft"
            placeholder="What worked, what didn't, what you'd do differently."
          />
        </div>
        {error && <p className="text-[13px] text-down sm:col-span-3">{error}</p>}
        <div className="flex gap-2 sm:col-span-3">
          <Button type="submit" variant="primary" loading={busy}>Save trade</Button>
          <Button type="button" variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
        </div>
      </form>
    </Card>
  );
}

export default function JournalPage() {
  const entries = useAsync(() => api.journal(), []);
  const stats = useAsync(() => api.journalStats(), []);

  function reload() {
    entries.reload();
    stats.reload();
  }

  if (entries.error) return <ErrorState message={entries.error} onRetry={reload} />;

  const rows = entries.data ?? [];

  return (
    <PageTransition>
      <SectionHeading title="Trade journal" action={rows.length > 0 ? <LogTrade onSaved={reload} /> : undefined} />

      {stats.data && stats.data.trades > 0 && (
        <div className="mb-6 grid gap-2.5 sm:grid-cols-3">
          <Card className="p-4">
            <p className="text-[10.5px] font-semibold uppercase tracking-[0.05em] text-faint">Trades</p>
            <p className="tnum mt-1.5 text-[19px] font-semibold text-ink">{stats.data.trades}</p>
          </Card>
          <Card className="p-4">
            <p className="text-[10.5px] font-semibold uppercase tracking-[0.05em] text-faint">Win rate</p>
            <p className="tnum mt-1.5 text-[19px] font-semibold text-ink">{stats.data.win_rate?.toFixed(0)}%</p>
            <p className="mt-0.5 text-[12px] text-muted">{stats.data.wins} won · {stats.data.losses} lost</p>
          </Card>
          <Card className="p-4">
            <p className="text-[10.5px] font-semibold uppercase tracking-[0.05em] text-faint">Realised P&amp;L</p>
            <p className={cn("tnum mt-1.5 text-[19px] font-semibold", stats.data.total_pnl >= 0 ? "text-up" : "text-down")}>
              {money(stats.data.total_pnl)}
            </p>
          </Card>
        </div>
      )}

      {entries.loading ? (
        <Card className="space-y-1 p-2">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-16" />)}</Card>
      ) : rows.length === 0 ? (
        <>
          <EmptyState title="No trades logged yet" body="Logging trades is what turns the win rate from a guess into a measurement." />
          <div className="mt-4"><LogTrade onSaved={reload} /></div>
        </>
      ) : (
        <Card className="overflow-hidden p-1.5">
          {rows.map((t, i) => (
            <div key={`${t.date}-${t.symbol}-${i}`}>
              {i > 0 && <div className="mx-4 h-px bg-line" />}
              <div className="flex items-start gap-3.5 rounded-2xl px-4 py-3.5 transition-colors hover:bg-surface-2">
                <span className={cn("mt-1 size-2.5 shrink-0 rounded-full", t.win ? "bg-up" : "bg-down")} aria-hidden />
                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline gap-2">
                    <span className="text-[15px] font-semibold text-ink">{t.symbol}</span>
                    <span className="text-[12px] text-faint">{t.date}</span>
                    {t.strategy && <span className="text-[12px] text-muted">· {t.strategy}</span>}
                  </div>
                  <p className="tnum mt-0.5 text-[12.5px] text-muted">
                    {t.shares} × {money(t.entry)} → {money(t.exit)}
                  </p>
                  {t.note && <p className="mt-1.5 text-[13px] text-muted">{t.note}</p>}
                </div>
                <div className="shrink-0 text-right">
                  <p className={cn("tnum text-[15px] font-semibold", t.win ? "text-up" : "text-down")}>{money(t.pnl)}</p>
                  <p className={cn("tnum text-[12.5px]", t.win ? "text-up" : "text-down")}>{percent(t.pnl_pct, 1)}</p>
                </div>
              </div>
            </div>
          ))}
        </Card>
      )}
    </PageTransition>
  );
}
