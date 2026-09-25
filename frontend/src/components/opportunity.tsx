"use client";

/**
 * Opportunity cards and the scan runner.
 *
 * A scan takes 21–46 seconds, so it runs as a background job: start it,
 * get an id, then poll for progress. Showing live progress is the whole
 * reason the job API exists — a 46-second spinner with no feedback is
 * indistinguishable from a hang.
 */

import { motion } from "motion/react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, type JobResponse } from "@/lib/api";
import { Button, Card, Pill, Spinner } from "@/components/ui";
import { cn, money } from "@/lib/utils";

export type Opportunity = {
  symbol: string;
  name: string;
  score: number;
  confidence: string;
  est_move: string;
  horizon: string;
  entry: number;
  target: number;
  stop: number;
  risk_reward: number;
  tags: string[];
};

export function OpportunityCard({ opp }: { opp: Opportunity }) {
  const strong = opp.score >= 70;
  return (
    <Link href={`/stocks/${opp.symbol}`} className="block">
      <Card interactive className="h-full p-5">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-[17px] font-semibold tracking-[-0.02em] text-ink">
              {opp.symbol}
            </p>
            <p className="truncate text-[12.5px] text-muted">{opp.name}</p>
          </div>
          <div className="shrink-0 text-right">
            <p
              className={cn(
                "tnum text-[24px] font-bold leading-none tracking-[-0.03em]",
                strong ? "text-up" : "text-warn",
              )}
            >
              {opp.score}
            </p>
            <p className="mt-0.5 text-[10px] uppercase tracking-[0.06em] text-faint">
              {opp.confidence}
            </p>
          </div>
        </div>

        <div className="my-4 flex gap-1" aria-hidden>
          {[0, 1, 2, 3, 4].map((i) => (
            <span
              key={i}
              className={cn(
                "h-1.5 flex-1 rounded-full",
                i < Math.floor(opp.score / 20) ? "bg-up" : "bg-line-strong",
              )}
            />
          ))}
        </div>

        <p
          className={cn(
            "text-[19px] font-semibold tracking-[-0.02em]",
            strong ? "text-up" : "text-warn",
          )}
        >
          {opp.est_move}
        </p>
        <p className="mt-0.5 text-[12.5px] text-muted">
          Estimated move · {opp.horizon}
        </p>

        {opp.tags?.length > 0 && (
          <div className="mt-3.5 flex flex-wrap gap-1.5">
            {opp.tags.slice(0, 3).map((t) => (
              <Pill key={t}>{t}</Pill>
            ))}
          </div>
        )}

        <div className="mt-4 flex gap-3 border-t border-line pt-3.5">
          {[
            { label: "Entry", value: opp.entry, tone: "text-ink" },
            { label: "Target", value: opp.target, tone: "text-up" },
            { label: "Stop", value: opp.stop, tone: "text-down" },
          ].map(({ label, value, tone }) => (
            <div key={label} className="flex-1">
              <p className="text-[10px] font-semibold uppercase tracking-[0.06em] text-faint">
                {label}
              </p>
              <p className={cn("tnum mt-0.5 text-[14px] font-semibold", tone)}>
                {money(value)}
              </p>
            </div>
          ))}
        </div>
      </Card>
    </Link>
  );
}

/**
 * Starts a scan job and polls it.
 *
 * Polling at 1.5s is plenty for a job measured in tens of seconds, and it
 * is far simpler than server-sent events for the same result.
 */
export function ScanRunner({
  onResults,
}: {
  onResults: (opps: Opportunity[]) => void;
}) {
  const [job, setJob] = useState<JobResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<number | null>(null);

  const stopPolling = useCallback(() => {
    if (timer.current !== null) {
      window.clearInterval(timer.current);
      timer.current = null;
    }
  }, []);

  useEffect(() => stopPolling, [stopPolling]);

  const poll = useCallback(
    (id: string) => {
      stopPolling();
      timer.current = window.setInterval(async () => {
        try {
          const next = await api.job(id);
          setJob(next);
          if (["finished", "failed", "cancelled"].includes(next.status)) {
            stopPolling();
            if (next.status === "finished") {
              const result = next.result as { results?: Opportunity[] } | null;
              onResults(result?.results ?? []);
            } else if (next.status === "failed") {
              setError(next.error ?? "The scan failed.");
            }
          }
        } catch (e) {
          stopPolling();
          setError(e instanceof Error ? e.message : "Lost contact with the scan");
        }
      }, 1500);
    },
    [onResults, stopPolling],
  );

  async function start(scope: "universe" | "broad") {
    setError(null);
    try {
      const started = await api.startScan(scope, 55);
      setJob(started);
      poll(started.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start the scan");
    }
  }

  async function cancel() {
    if (!job) return;
    try {
      await api.cancelJob(job.id);
    } catch {
      /* the poll will report the real state */
    }
  }

  const running = job?.status === "queued" || job?.status === "running";
  const pct = job?.progress?.pct ?? 0;

  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-[15px] font-semibold text-ink">Scan the market</p>
          <p className="mt-0.5 text-[12.5px] text-muted">
            Scores each stock on momentum, volume and trend. The broad scan
            pre-filters the S&amp;P 500 first and takes about a minute.
          </p>
        </div>
        {running ? (
          <Button onClick={cancel}>Cancel</Button>
        ) : (
          <div className="flex gap-2">
            <Button onClick={() => start("universe")}>Quick scan</Button>
            <Button variant="primary" onClick={() => start("broad")}>
              S&amp;P 500
            </Button>
          </div>
        )}
      </div>

      {running && (
        <div className="mt-4">
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-2">
            <motion.div
              className="h-full rounded-full bg-up"
              animate={{ width: `${pct}%` }}
              transition={{ duration: 0.4, ease: [0.32, 0.72, 0, 1] }}
            />
          </div>
          <div className="mt-2 flex items-center gap-2 text-[12.5px] text-muted">
            <Spinner className="size-3.5" />
            {job?.progress?.total
              ? `${job.progress.done} of ${job.progress.total}`
              : "Starting…"}
            {job?.progress?.label && (
              <span className="text-faint">· {job.progress.label}</span>
            )}
          </div>
        </div>
      )}

      {job?.status === "cancelled" && (
        <p className="mt-3 text-[12.5px] text-muted">Scan cancelled.</p>
      )}
      {error && <p className="mt-3 text-[12.5px] text-down">{error}</p>}
    </Card>
  );
}
