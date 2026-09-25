"use client";

import { useState } from "react";
import { OpportunityCard, ScanRunner, type Opportunity } from "@/components/opportunity";
import {
  Card,
  Delta,
  EmptyState,
  PageTransition,
  SectionHeading,
  Skeleton,
} from "@/components/ui";
import { api } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import { money } from "@/lib/utils";
import Link from "next/link";

const INDICES = ["SPY", "QQQ", "DIA", "IWM"];

export default function MarketsPage() {
  const [opps, setOpps] = useState<Opportunity[] | null>(null);
  const indices = useAsync(() => api.quotes(INDICES), []);

  return (
    <PageTransition>
      <SectionHeading title="Indices" />
      <div className="grid grid-cols-2 gap-2.5 lg:grid-cols-4">
        {indices.loading
          ? INDICES.map((s) => (
              <Skeleton key={s} className="h-[92px] rounded-[var(--radius-card)]" />
            ))
          : (indices.data ?? []).map((q) => (
              <Link key={q.symbol} href={`/stocks/${q.symbol}`}>
                <Card interactive className="p-4">
                  <p className="text-[13px] font-semibold text-ink">{q.symbol}</p>
                  <p className="tnum mt-1.5 text-[20px] font-semibold tracking-[-0.02em] text-ink">
                    {money(q.price)}
                  </p>
                  <Delta value={q.pct_change} className="mt-1 text-[12.5px]" />
                </Card>
              </Link>
            ))}
      </div>

      <div className="mt-9">
        <SectionHeading title="Opportunities" />
        <ScanRunner onResults={setOpps} />

        {opps !== null && (
          <div className="mt-4">
            {opps.length === 0 ? (
              <EmptyState
                title="Nothing cleared the bar"
                body="No stock scored above the confidence threshold in this scan."
              />
            ) : (
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                {opps.map((o) => (
                  <OpportunityCard key={o.symbol} opp={o} />
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </PageTransition>
  );
}
