import { BentoCard, BentoCardHeader } from "@/components/ui/BentoCard";
import { CurrencyValue } from "@/components/ui/CurrencyValue";
import { StatRow } from "@/components/ui/StatRow";
import { StatusIndicator } from "@/components/ui/StatusIndicator";
import { formatINR, formatPercent } from "@/lib/currency";
import { formatLongDate } from "@/lib/dates";
import {
  calculateWinRate,
  getDailyTargetStatus,
} from "@/lib/targetCalculations";
import type { DailyTradingPerformance } from "@/types/trading";

export interface TradingSummaryCardProps {
  selectedDate: Date;
  performance: DailyTradingPerformance | null;
  dailyTarget: number;
  isToday: boolean;
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
  order,
  className,
}: TradingSummaryCardProps) {
  const longDate = formatLongDate(selectedDate);

  if (!performance) {
    return (
      <BentoCard
        variant="secondary"
        order={order}
        className={className}
        ariaLabel="Session summary"
      >
        <BentoCardHeader
          title={isToday ? "Today" : "Selected Day"}
          description={longDate}
        />
        <div className="mt-6 flex flex-1 items-center">
          <p className="text-[13px] text-ink-muted">
            No session was recorded on this date.
          </p>
        </div>
        <dl className="mt-auto border-t border-hairline pt-2">
          <StatRow label="Daily Target" value={formatINR(dailyTarget)} />
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
      <BentoCardHeader
        title={isToday ? "Today" : "Selected Day"}
        description={longDate}
      />

      <div className="mt-5">
        <p className="text-[13px] text-ink-muted">Realized P&amp;L</p>
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

      <div className="mt-4">
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
