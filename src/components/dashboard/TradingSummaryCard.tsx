import { BentoCard, BentoCardHeader } from "@/components/ui/BentoCard";
import { CardError, CardSkeleton } from "@/components/ui/CardState";
import { CurrencyValue } from "@/components/ui/CurrencyValue";
import { StatRow } from "@/components/ui/StatRow";
import { StatusIndicator } from "@/components/ui/StatusIndicator";
import type { ResourceStatus } from "@/hooks/useApiResource";
import { formatINR, formatPercent } from "@/lib/currency";
import { formatLongDate, toDateKey } from "@/lib/dates";
import { getHolidayByKey } from "@/lib/holidays";
import { SESSION_HOURS_LABEL, isWeekend } from "@/lib/market";
import {
  calculateWinRate,
  getDailyTargetStatus,
} from "@/lib/targetCalculations";
import type { DailyTradingPerformance } from "@/types/trading";

export interface TradingSummaryCardProps {
  /** `null` until the backend's reference date is known. */
  selectedDate: Date | null;
  /** `null` means "no session recorded", which is distinct from "not loaded". */
  performance: DailyTradingPerformance | null;
  dailyTarget: number | null;
  isToday: boolean;
  state: ResourceStatus;
  error?: string | null;
  offline?: boolean;
  onRetry?: () => void;
  order?: number;
  className?: string;
}

/**
 * Contextual detail for the date selected in the calendar. Shows today by
 * default and swaps content in place — no modal for basic inspection.
 */
export function TradingSummaryCard({
  selectedDate,
  performance,
  dailyTarget,
  isToday,
  state,
  error,
  offline,
  onRetry,
  order,
  className,
}: TradingSummaryCardProps) {
  const longDate = selectedDate ? formatLongDate(selectedDate) : undefined;
  const title = isToday ? "Today" : "Selected Session";

  // Why the exchange was shut, if it was — answered entirely on the client
  // from the weekday and the published holiday list. Neither fact is a
  // measurement, so neither needs the API to be reachable.
  const holiday = selectedDate ? getHolidayByKey(toDateKey(selectedDate)) : null;
  const closedReason: string | null = !selectedDate
    ? null
    : holiday?.kind === "holiday"
      ? `${holiday.description} — the exchange is closed, so there is no session to record.`
      : isWeekend(selectedDate)
        ? `The market is closed on weekends. Sessions run ${SESSION_HOURS_LABEL}, Monday to Friday.`
        : null;

  // A closed exchange is settled before any request is made, so this branch
  // outranks both the error and the loading states: retrying a fetch cannot
  // change the fact that 14 August was a holiday. Showing "Session
  // unavailable" here would blame the backend for the calendar.
  if (closedReason) {
    return (
      <BentoCard
        variant="secondary"
        order={order}
        className={className}
        ariaLabel="Session summary"
      >
        <BentoCardHeader title={title} description={longDate} />
        <div className="mt-6 flex flex-1 items-start">
          <p className="text-[13px] leading-relaxed text-ink-muted">
            {closedReason}
          </p>
        </div>
        <dl className="mt-auto border-t border-hairline pt-1.5">
          <StatRow
            label="Daily Target"
            value={
              <span className="numeric">
                {dailyTarget === null ? "—" : formatINR(dailyTarget)}
              </span>
            }
          />
        </dl>
      </BentoCard>
    );
  }

  // The error branch is checked first on purpose. `selectedDate` is derived
  // from the backend's reference date, so when the API is unreachable it is
  // also `null` — treating that as "still loading" would leave the card
  // spinning indefinitely instead of admitting the failure.
  if (state === "error") {
    return (
      <BentoCard
        variant="secondary"
        order={order}
        className={className}
        ariaLabel="Session summary"
      >
        <BentoCardHeader title={title} description={longDate} />
        <CardError
          title="Session unavailable"
          message={error ?? null}
          offline={offline}
          onRetry={onRetry}
        />
      </BentoCard>
    );
  }

  if (state === "loading" || selectedDate === null) {
    return (
      <BentoCard
        variant="secondary"
        order={order}
        className={className}
        ariaLabel="Session summary"
      >
        <BentoCardHeader title={title} description={longDate} />
        <CardSkeleton headline="h-8" lines={4} />
      </BentoCard>
    );
  }

  if (!performance || dailyTarget === null) {
    return (
      <BentoCard
        variant="secondary"
        order={order}
        className={className}
        ariaLabel="Session summary"
      >
        <BentoCardHeader title={title} description={longDate} />
        <div className="mt-6 flex flex-1 items-start">
          <p className="text-[13px] leading-relaxed text-ink-muted">
            No session was recorded on this date.
          </p>
        </div>
        <dl className="mt-auto border-t border-hairline pt-1.5">
          <StatRow
            label="Daily Target"
            value={
              <span className="numeric">
                {dailyTarget === null ? "—" : formatINR(dailyTarget)}
              </span>
            }
          />
        </dl>
      </BentoCard>
    );
  }

  const status = getDailyTargetStatus(performance.realizedPnl, dailyTarget);
  const winRate = calculateWinRate(performance.wins, performance.trades);

  return (
    <BentoCard
      variant="secondary"
      order={order}
      className={className}
      ariaLabel="Session summary"
    >
      <BentoCardHeader title={title} description={longDate} />

      <div className="mt-5">
        <p className="text-[11px] text-ink-muted">Realized P&amp;L</p>
        <div className="mt-1">
          <CurrencyValue
            value={performance.realizedPnl}
            size="lg"
            tone="auto"
            showSign
            className="tracking-[-0.02em]"
          />
        </div>
      </div>

      <div className="mt-3">
        <StatusIndicator status={status} />
      </div>

      <dl className="mt-auto divide-y divide-hairline border-t border-hairline pt-1">
        <StatRow
          label="Trades"
          value={<span className="numeric">{performance.trades}</span>}
        />
        <StatRow
          label="Wins"
          value={<span className="numeric">{performance.wins}</span>}
        />
        <StatRow
          label="Losses"
          value={<span className="numeric">{performance.losses}</span>}
        />
        <StatRow
          label="Win rate"
          value={
            <span className="numeric">
              {performance.trades > 0 ? formatPercent(winRate) : "—"}
            </span>
          }
        />
        <StatRow
          label="Daily Target"
          value={<span className="numeric">{formatINR(dailyTarget)}</span>}
        />
      </dl>
    </BentoCard>
  );
}
