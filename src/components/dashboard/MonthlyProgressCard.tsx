import { BentoCard, BentoCardHeader } from "@/components/ui/BentoCard";
import { CurrencyValue } from "@/components/ui/CurrencyValue";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { formatINR, formatPercent } from "@/lib/currency";
import {
  calculateProgressRatio,
  calculateRemaining,
} from "@/lib/targetCalculations";
import type { PerformanceTotals } from "@/types/trading";

export interface MonthlyProgressCardProps {
  monthlyTarget: number;
  totals: PerformanceTotals;
  averagePerSession: number;
  /** Label for the period being summarised, e.g. "September 2026". */
  periodLabel: string;
  order?: number;
  className?: string;
}

/**
 * Month-to-date realized P&L measured against the user's goal. All figures are
 * derived from the session list so the card can never drift from the calendar.
 */
export function MonthlyProgressCard({
  monthlyTarget,
  totals,
  averagePerSession,
  periodLabel,
  order,
  className,
}: MonthlyProgressCardProps) {
  const ratio = calculateProgressRatio(totals.realizedPnl, monthlyTarget);
  const remaining = calculateRemaining(totals.realizedPnl, monthlyTarget);
  const hasTarget = monthlyTarget > 0;

  return (
    <BentoCard order={order} className={className} ariaLabel="Monthly progress">
      <BentoCardHeader title="Monthly Progress" description={periodLabel} />

      <div className="mt-5 flex flex-wrap items-end justify-between gap-x-6 gap-y-3 sm:mt-6">
        <div className="min-w-0">
          <div className="flex flex-wrap items-baseline gap-x-2.5">
            <CurrencyValue
              value={totals.realizedPnl}
              size="lg"
              tone="auto"
              className="tracking-[-0.02em]"
            />
            <span className="numeric text-base text-ink-muted">
              / {hasTarget ? formatINR(monthlyTarget) : "—"}
            </span>
          </div>
          <p className="mt-1 text-[13px] text-ink-muted">
            Realized this month
          </p>
        </div>

        <p className="numeric text-2xl font-semibold tracking-[-0.02em] text-ink">
          {hasTarget ? formatPercent(ratio) : "—"}
        </p>
      </div>

      <ProgressBar
        ratio={ratio}
        tone={totals.realizedPnl < 0 ? "negative" : "positive"}
        label="Monthly target progress"
        className="mt-5"
      />

      <dl className="mt-auto grid grid-cols-3 gap-2 pt-6">
        <div className="min-w-0 rounded-inner bg-surface-sunken px-3 py-2.5">
          <dt className="text-[10.5px] text-ink-muted">Remaining</dt>
          <dd className="mt-1">
            <CurrencyValue value={remaining} size="sm" />
          </dd>
        </div>
        <div className="min-w-0 rounded-inner bg-surface-sunken px-3 py-2.5">
          <dt className="text-[10.5px] text-ink-muted">Avg / session</dt>
          <dd className="mt-1">
            <CurrencyValue
              value={Math.round(averagePerSession)}
              size="sm"
              tone="auto"
              showSign
            />
          </dd>
        </div>
        <div className="min-w-0 rounded-inner bg-surface-sunken px-3 py-2.5">
          <dt className="text-[10.5px] text-ink-muted">Sessions</dt>
          <dd className="numeric mt-1 text-[15px] font-semibold text-ink">
            {totals.activeSessions}
          </dd>
        </div>
      </dl>
    </BentoCard>
  );
}
