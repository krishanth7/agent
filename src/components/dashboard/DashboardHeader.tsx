import { ThemeToggle } from "@/components/ui/ThemeToggle";
import { formatCompactDate } from "@/lib/dates";
import { SESSION_HOURS_LABEL } from "@/lib/market";
import { cn } from "@/lib/utils";
import type { MarketStatus } from "@/types/trading";

const MARKET_META: Record<MarketStatus, { label: string; dot: string }> = {
  open: { label: "Market Open", dot: "bg-positive" },
  "pre-open": { label: "Pre-Open", dot: "bg-caution" },
  closed: { label: "Market Closed", dot: "bg-idle" },
};

export interface DashboardHeaderProps {
  marketStatus: MarketStatus;
  /**
   * The trading date, or `null` until the backend reports it.
   *
   * Deliberately not defaulted to `new Date()`: the browser's clock is not the
   * exchange's, and rendering it would both mislead and break hydration (the
   * server and client would stamp different instants).
   */
  date: Date | null;
}

export function DashboardHeader({ marketStatus, date }: DashboardHeaderProps) {
  const market = MARKET_META[marketStatus];

  return (
    <header className="flex flex-wrap items-center justify-between gap-x-6 gap-y-4 border-b border-hairline pb-5">
      <div className="flex items-center gap-3">
        <span
          aria-hidden="true"
          className="grid size-9 shrink-0 place-items-center rounded-[10px] bg-ink text-[15px] font-semibold text-canvas"
        >
          N
        </span>
        <div className="leading-tight">
          <p className="text-[15px] font-semibold tracking-[-0.01em] text-ink">
            NIFTY Agent
          </p>
          <p className="eyebrow mt-0.5 text-ink-muted">Dashboard</p>
        </div>
      </div>

      <div className="flex items-center gap-3 sm:gap-4">
        <div className="flex items-center gap-2.5 rounded-full border border-hairline bg-canvas-raised py-1.5 pl-3 pr-3.5">
          <span
            aria-hidden="true"
            className={cn("size-1.5 shrink-0 rounded-full", market.dot)}
          />
          <span className="text-[13px] font-medium text-ink-secondary">
            {market.label}
          </span>
          <span
            aria-hidden="true"
            className="h-3 w-px shrink-0 bg-hairline-strong"
          />
          <span className="numeric whitespace-nowrap text-[11px] text-ink-muted sm:text-[12px]">
            {SESSION_HOURS_LABEL}
          </span>
        </div>

        {date ? (
          <time
            dateTime={date.toISOString()}
            className="numeric hidden text-[13px] font-medium text-ink-secondary md:block"
          >
            {formatCompactDate(date)}
          </time>
        ) : (
          <span
            aria-hidden="true"
            className="hidden h-4 w-[5.5rem] animate-pulse rounded bg-surface-sunken md:block"
          />
        )}

        <ThemeToggle />
      </div>
    </header>
  );
}
