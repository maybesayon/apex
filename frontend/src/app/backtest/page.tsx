"use client";

import { useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  Button,
  Card,
  Input,
  PageTransition,
  SectionHeading,
} from "@/components/ui";
import { api } from "@/lib/api";
import { cn, money, percent } from "@/lib/utils";

type Trade = {
  entry_date: string; exit_date: string; entry_price: number; exit_price: number;
  shares: number; pnl: number; pnl_pct: number; exit_reason: string; win: boolean;
};
type Result = {
  total_return_pct: number; final_capital: number; initial_capital: number;
  total_trades: number; wins: number; losses: number; win_rate: number;
  max_drawdown_pct: number; equity_curve: number[]; trades: Trade[];
  open_at_end?: boolean;
};

export default function BacktestPage() {
  const [symbol, setSymbol] = useState("AAPL");
  const [capital, setCapital] = useState("1000");
  const [stop, setStop] = useState("17");
  const [rsiEntry, setRsiEntry] = useState("65");
  const [result, setResult] = useState<Result | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const r = await api.backtest({
        symbol: symbol.trim().toUpperCase(),
        capital: Number(capital),
        stop_loss_pct: Number(stop) / 100,
        rsi_entry: Number(rsiEntry),
      });
      setResult(r as unknown as Result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Backtest failed");
    } finally {
      setBusy(false);
    }
  }

  const curve = (result?.equity_curve ?? []).map((v, i) => ({ i, value: v }));

  return (
    <PageTransition>
      <SectionHeading title="Strategy backtester" />
      <p className="-mt-2 mb-4 max-w-2xl text-[13.5px] text-muted">
        Tests an RSI + MACD momentum strategy over two years of daily bars.
        Results are optimistic: entries transact at the same close that
        generated the signal, and there are no commissions or slippage.
      </p>

      <Card className="p-5">
        <form onSubmit={run} className="grid gap-3 sm:grid-cols-4">
          <Input label="Ticker" name="bt-symbol" value={symbol} onChange={(e) => setSymbol(e.target.value)} />
          <Input label="Capital ($)" name="bt-capital" type="number" min="1" value={capital} onChange={(e) => setCapital(e.target.value)} />
          <Input label="Stop loss (%)" name="bt-stop" type="number" min="1" max="99" value={stop} onChange={(e) => setStop(e.target.value)} />
          <Input
            label="RSI entry ceiling"
            name="bt-rsi"
            type="number"
            min="1"
            max="100"
            value={rsiEntry}
            onChange={(e) => setRsiEntry(e.target.value)}
          />
          <div className="sm:col-span-4">
            <Button type="submit" variant="primary" loading={busy}>Run backtest</Button>
          </div>
        </form>
        <p className="mt-3 text-[12.5px] text-faint">
          RSI entry is an overbought guard, not an oversold requirement. Set it
          too low and no trade can fire, because a bullish MACD cross means RSI
          has already recovered.
        </p>
      </Card>

      {error && (
        <Card className="mt-4 border-down/25 p-5">
          <p className="text-[14px] font-medium text-ink">No result</p>
          <p className="mt-1 text-[13.5px] text-muted">{error}</p>
        </Card>
      )}

      {result && (
        <>
          <div className="mt-6 grid gap-2.5 grid-cols-2 lg:grid-cols-5">
            {[
              { label: "Total return", value: percent(result.total_return_pct, 1), tone: result.total_return_pct >= 0 ? "text-up" : "text-down" },
              { label: "Final capital", value: money(result.final_capital), tone: "text-ink" },
              { label: "Win rate", value: `${result.win_rate}%`, tone: "text-ink" },
              { label: "Trades", value: String(result.total_trades), tone: "text-ink" },
              { label: "Max drawdown", value: `-${result.max_drawdown_pct}%`, tone: "text-down" },
            ].map((m) => (
              <Card key={m.label} className="p-4">
                <p className="text-[10.5px] font-semibold uppercase tracking-[0.05em] text-faint">{m.label}</p>
                <p className={cn("tnum mt-1.5 text-[19px] font-semibold", m.tone)}>{m.value}</p>
              </Card>
            ))}
          </div>

          <div className="mt-6">
            <SectionHeading title="Equity curve" />
            <Card className="p-4">
              <div style={{ height: 260 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={curve} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
                    <defs>
                      <linearGradient id="eq" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="var(--color-up)" stopOpacity={0.28} />
                        <stop offset="100%" stopColor="var(--color-up)" stopOpacity={0.02} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid stroke="var(--color-line)" vertical={false} />
                    <XAxis dataKey="i" tick={{ fontSize: 11, fill: "var(--color-faint)" }} axisLine={false} tickLine={false} />
                    <YAxis tick={{ fontSize: 11, fill: "var(--color-faint)" }} axisLine={false} tickLine={false} width={52} />
                    <Tooltip
                      formatter={(v) => money(typeof v === "number" ? v : null)}
                      labelFormatter={(l) => `Day ${l}`}
                      contentStyle={{ borderRadius: 12, border: "1px solid var(--color-line)", background: "var(--color-surface)", fontSize: 13 }}
                    />
                    <ReferenceLine y={result.initial_capital} stroke="var(--color-faint)" strokeDasharray="4 4" />
                    <Area type="monotone" dataKey="value" stroke="var(--color-up)" strokeWidth={2} fill="url(#eq)" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </Card>
          </div>

          <div className="mt-6">
            <SectionHeading title={`Trades (${result.trades.length})`} />
            <Card className="overflow-hidden p-1.5">
              {result.trades.map((t, i) => (
                <div key={i}>
                  {i > 0 && <div className="mx-4 h-px bg-line" />}
                  <div className="flex items-center gap-3 px-4 py-3">
                    <span className={cn("size-2.5 shrink-0 rounded-full", t.win ? "bg-up" : "bg-down")} aria-hidden />
                    <div className="min-w-0 flex-1">
                      <p className="tnum text-[13.5px] text-ink">
                        {t.entry_date} → {t.exit_date}
                      </p>
                      <p className="tnum text-[12.5px] text-muted">
                        {t.shares} × {money(t.entry_price)} → {money(t.exit_price)} · {t.exit_reason}
                      </p>
                    </div>
                    <div className="shrink-0 text-right">
                      <p className={cn("tnum text-[14px] font-semibold", t.win ? "text-up" : "text-down")}>{money(t.pnl)}</p>
                      <p className={cn("tnum text-[12px]", t.win ? "text-up" : "text-down")}>{percent(t.pnl_pct, 1)}</p>
                    </div>
                  </div>
                </div>
              ))}
            </Card>
          </div>
        </>
      )}
    </PageTransition>
  );
}
