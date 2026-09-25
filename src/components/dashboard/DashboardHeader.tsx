"use client";

import { MarketStatusPill } from "@/components/dashboard/MarketStatusPill";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import { Tooltip } from "@/components/ui/Tooltip";
import { formatCompactDate } from "@/lib/dates";
import { getHolidayByKey } from "@/lib/holidays";
import type { MarketSnapshot } from "@/lib/market";
import { cn } from "@/lib/utils";

export interface DashboardHeaderProps {
  /**
   * Live exchange clock, or `null` for the first paint.
   *
   * This is the only source of the header's date now. It used to wait for the
   * backend's reference date, which meant a database outage blanked the date as
   * well as the figures — and the date is not a figure. Today's date in IST is
   * derivable from the browser's instant and a time-zone database, so it is.
   */
  snapshot: MarketSnapshot | null;
}

export function DashboardHeader({ snapshot }: DashboardHeaderProps) {
  const holiday = snapshot ? getHolidayByKey(snapshot.dateKey) : null;

  // Built from the IST date key, not from `new Date()`, so the header shows the
  // exchange's date even when the browser's own calendar has already rolled
  // over or has not yet.
  const date = snapshot ? new Date(`${snapshot.dateKey}T00:00:00`) : null;

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
        <MarketStatusPill snapshot={snapshot} />

        {date && snapshot ? (
          <Tooltip
            side="bottom"
            label={
              holiday
                ? `${holiday.description} — ${holiday.kind === "muhurat" ? "special session" : "exchange holiday"}`
                : `Trading date, ${snapshot.isTradingDay ? "a scheduled session" : "no session scheduled"}`
            }
          >
            <time
              dateTime={snapshot.dateKey}
              className={cn(
                "numeric hidden cursor-default text-[13px] font-medium md:block",
                holiday?.kind === "holiday"
                  ? "text-caution"
                  : "text-ink-secondary",
              )}
            >
              {formatCompactDate(date)}
            </time>
          </Tooltip>
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
