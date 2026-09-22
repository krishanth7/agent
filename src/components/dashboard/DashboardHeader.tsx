import { formatCompactDate } from "@/lib/dates";
import { cn } from "@/lib/utils";
import type { MarketStatus } from "@/types/trading";

const MARKET_META: Record<MarketStatus, { label: string; dot: string }> = {
  open: { label: "Market Open", dot: "bg-positive" },
  "pre-open": { label: "Pre-Open", dot: "bg-caution" },
  closed: { label: "Market Closed", dot: "bg-idle" },
};

export interface DashboardHeaderProps {
  marketStatus: MarketStatus;
  date: Date;
}

export function DashboardHeader({ marketStatus, date }: DashboardHeaderProps) {
  const market = MARKET_META[marketStatus];

  return (
    <header className="flex flex-wrap items-center justify-between gap-x-6 gap-y-4">
      <div className="flex items-center gap-3">
        <span
          aria-hidden="true"
          className="grid size-9 shrink-0 place-items-center rounded-[11px] bg-ink text-[15px] font-semibold text-canvas"
        >
          N
        </span>
        <div className="leading-tight">
          <p className="text-[15px] font-semibold tracking-[-0.01em] text-ink">
            NIFTY Agent
          </p>
          <p className="text-xs text-ink-muted">Dashboard</p>
        </div>
      </div>

      <div className="flex items-center gap-3 sm:gap-4">
        <div className="flex items-center gap-2 rounded-full border border-hairline bg-surface-muted px-3 py-1.5">
          <span
            aria-hidden="true"
            className={cn("size-1.5 rounded-full", market.dot)}
          />
          <span className="text-[13px] font-medium text-ink-secondary">
            {market.label}
          </span>
        </div>

        <span aria-hidden="true" className="h-5 w-px bg-hairline" />

        <time
          dateTime={date.toISOString()}
          className="numeric text-[13px] font-medium text-ink-secondary"
        >
          {formatCompactDate(date)}
        </time>
      </div>
    </header>
  );
}
