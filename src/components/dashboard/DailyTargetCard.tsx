import { BentoCard, BentoCardHeader } from "@/components/ui/BentoCard";
import { CardError, CardSkeleton } from "@/components/ui/CardState";
import { CurrencyValue } from "@/components/ui/CurrencyValue";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { StatusIndicator } from "@/components/ui/StatusIndicator";
import type { ResourceStatus } from "@/hooks/useApiResource";
import { formatINR, formatPercent } from "@/lib/currency";
import {
  calculateProgressRatio,
  calculateRemaining,
  getDailyTargetStatus,
} from "@/lib/targetCalculations";
import type { DailyTargetStatus } from "@/types/trading";

const BAR_TONE: Record<
  DailyTargetStatus,
  "positive" | "caution" | "negative" | "neutral"
> = {
  achieved: "positive",
  "in-progress": "caution",
  loss: "negative",
  "not-started": "neutral",
};

export interface DailyTargetCardProps {
  /** `null` until both the target and today's session have been fetched. */
  dailyTarget: number | null;
  todayProfit: number | null;
  state: ResourceStatus;
  error?: string | null;
  offline?: boolean;
  onRetry?: () => void;
  order?: number;
  className?: string;
}

/**
 * Today's slice of the monthly goal. The progress bar clamps at 100% while the
 * headline percentage is free to exceed it.
 */
export function DailyTargetCard({
  dailyTarget,
  todayProfit,
  state,
  error,
  offline,
  onRetry,
  order,
  className,
}: DailyTargetCardProps) {
  if (state === "loading") {
    return (
      <BentoCard order={order} className={className} ariaLabel="Today's target">
        <BentoCardHeader title="Today's Target" />
        <CardSkeleton headline="h-8" lines={3} />
      </BentoCard>
    );
  }

  if (state === "error" || dailyTarget === null || todayProfit === null) {
    return (
      <BentoCard order={order} className={className} ariaLabel="Today's target">
        <BentoCardHeader title="Today's Target" />
        <CardError
          title="Target unavailable"
          message={error ?? null}
          offline={offline}
          onRetry={onRetry}
        />
      </BentoCard>
    );
  }

  const status = getDailyTargetStatus(todayProfit, dailyTarget);
  const ratio = calculateProgressRatio(todayProfit, dailyTarget);
  const remaining = calculateRemaining(todayProfit, dailyTarget);

  return (
    <BentoCard order={order} className={className} ariaLabel="Today's target">
      <BentoCardHeader title="Today's Target" />

      <div className="mt-4">
        <CurrencyValue
          value={dailyTarget}
          size="lg"
          className="tracking-[-0.02em]"
        />
      </div>

      <div className="mt-5 border-t border-hairline pt-5">
        <div className="flex items-baseline justify-between gap-3">
          <p className="text-[13px] text-ink-muted">Today&rsquo;s Profit</p>
          {dailyTarget > 0 && todayProfit > 0 ? (
            <p className="numeric text-[13px] font-medium text-ink-secondary">
              {formatPercent(ratio)}
            </p>
          ) : null}
        </div>

        <div className="mt-1.5">
          <CurrencyValue
            value={todayProfit}
            size="md"
            tone="auto"
            showSign
            className="tracking-[-0.01em]"
          />
        </div>

        <ProgressBar
          ratio={ratio}
          tone={BAR_TONE[status]}
          size="sm"
          label="Today's target progress"
          className="mt-4"
        />

        <div className="mt-3 flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
          <StatusIndicator status={status} />
          {status === "in-progress" && remaining > 0 ? (
            <span className="numeric text-[13px] text-ink-muted">
              {formatINR(remaining)} remaining
            </span>
          ) : null}
        </div>
      </div>

      <p className="mt-auto pt-5 text-xs text-ink-muted">
        Realized P&amp;L against today&rsquo;s share of the monthly target.
      </p>
    </BentoCard>
  );
}
