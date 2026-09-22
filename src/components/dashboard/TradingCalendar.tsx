"use client";

import { addMonths, isSameMonth } from "date-fns";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { motion } from "motion/react";

import { BentoCard } from "@/components/ui/BentoCard";
import { STATUS_META } from "@/components/ui/StatusIndicator";
import { formatINR } from "@/lib/currency";
import {
  WEEKDAY_LABELS,
  buildCalendarWeeks,
  canGoToNextMonth,
  canGoToPreviousMonth,
  formatAccessibleDate,
  formatMonthTitle,
  toDateKey,
} from "@/lib/dates";
import { SESSION_HOURS_LABEL, isWeekend } from "@/lib/market";
import { cn } from "@/lib/utils";
import type { DailyTargetStatus, DailyTradingPerformance } from "@/types/trading";

const WEEKDAY_FULL_NAMES = [
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
  "Sunday",
] as const;

/** Column indices of Saturday and Sunday in a Monday-first grid. */
const WEEKEND_COLUMNS = new Set([5, 6]);

const LEGEND: ReadonlyArray<{ label: string; dot: string }> = [
  { label: "Target met", dot: STATUS_META.achieved.dot },
  { label: "Below target", dot: STATUS_META["in-progress"].dot },
  { label: "Loss", dot: STATUS_META.loss.dot },
  { label: "No trade", dot: STATUS_META["not-started"].dot },
];

export interface TradingCalendarProps {
  monthAnchor: Date;
  onMonthChange: (next: Date) => void;
  selectedDateKey: string;
  onSelectDate: (dateKey: string) => void;
  todayKey: string;
  /** Session data for a date, or `null` when nothing was recorded. */
  getPerformance: (dateKey: string) => DailyTradingPerformance | null;
  /** Status derived from the session and the current daily target. */
  getStatus: (dateKey: string) => DailyTargetStatus | null;
  order?: number;
  className?: string;
}

/**
 * Month view of agent performance. Markers are intentionally quiet — a single
 * dot per session, with the written detail deferred to the summary card.
 *
 * Saturdays and Sundays are rendered as non-trading days: the market is closed,
 * so they can never hold a session and are not selectable.
 */
export function TradingCalendar({
  monthAnchor,
  onMonthChange,
  selectedDateKey,
  onSelectDate,
  todayKey,
  getPerformance,
  getStatus,
  order,
  className,
}: TradingCalendarProps) {
  const weeks = buildCalendarWeeks(monthAnchor);
  const canGoBack = canGoToPreviousMonth(monthAnchor);
  const canGoForward = canGoToNextMonth(monthAnchor);
  const monthTitle = formatMonthTitle(monthAnchor);

  return (
    <BentoCard order={order} className={className} ariaLabel="Trading calendar">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <h2 className="eyebrow text-ink-secondary">Trading Calendar</h2>
          <p
            aria-live="polite"
            className="mt-1 text-[15px] font-semibold tracking-[-0.01em] text-ink"
          >
            {monthTitle}
          </p>
        </div>

        <div className="flex shrink-0 items-center gap-0.5 rounded-lg border border-hairline bg-canvas-raised p-0.5">
          <NavButton
            label="Previous month"
            disabled={!canGoBack}
            onClick={() => onMonthChange(addMonths(monthAnchor, -1))}
          >
            <ChevronLeft aria-hidden="true" className="size-4" />
          </NavButton>
          <NavButton
            label="Next month"
            disabled={!canGoForward}
            onClick={() => onMonthChange(addMonths(monthAnchor, 1))}
          >
            <ChevronRight aria-hidden="true" className="size-4" />
          </NavButton>
        </div>
      </div>

      <table className="mt-4 w-full table-fixed border-separate border-spacing-[3px]">
        <caption className="sr-only">
          {`Daily trading performance for ${monthTitle}. Select a past or current weekday to view its summary. The market is closed on Saturdays and Sundays.`}
        </caption>
        <thead>
          <tr>
            {WEEKDAY_LABELS.map((day, index) => (
              <th
                key={day}
                scope="col"
                className={cn(
                  "pb-1.5 text-[10.5px] font-semibold tracking-[0.06em] uppercase",
                  WEEKEND_COLUMNS.has(index)
                    ? "text-ink-muted/60"
                    : "text-ink-muted",
                )}
              >
                <span aria-hidden="true">{day}</span>
                <span className="sr-only">
                  {WEEKDAY_FULL_NAMES[index]}
                  {WEEKEND_COLUMNS.has(index) ? " (market closed)" : ""}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <motion.tbody
          key={monthTitle}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.15 }}
        >
          {weeks.map((week) => (
            <tr key={toDateKey(week[0] ?? monthAnchor)}>
              {week.map((day) => {
                const dateKey = toDateKey(day);
                const inMonth = isSameMonth(day, monthAnchor);
                const isFuture = dateKey > todayKey;
                const weekend = isWeekend(day);
                const hasSession = inMonth && !isFuture && !weekend;

                return (
                  <td key={dateKey} className="p-0 align-top">
                    <CalendarDay
                      day={day}
                      dateKey={dateKey}
                      inMonth={inMonth}
                      isFuture={isFuture}
                      isWeekend={weekend}
                      isToday={dateKey === todayKey}
                      isSelected={dateKey === selectedDateKey}
                      status={hasSession ? getStatus(dateKey) : null}
                      performance={hasSession ? getPerformance(dateKey) : null}
                      onSelect={onSelectDate}
                    />
                  </td>
                );
              })}
            </tr>
          ))}
        </motion.tbody>
      </table>

      <div className="mt-auto border-t border-hairline pt-3">
        <ul className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
          {LEGEND.map(({ label, dot }) => (
            <li key={label} className="flex items-center gap-1.5">
              <span
                aria-hidden="true"
                className={cn("size-1.5 rounded-full", dot)}
              />
              <span className="text-[10.5px] text-ink-muted">{label}</span>
            </li>
          ))}
          <li className="flex items-center gap-1.5">
            <span
              aria-hidden="true"
              className="size-1.5 rounded-[2px] bg-hairline-strong"
            />
            <span className="text-[10.5px] text-ink-muted">Market closed</span>
          </li>
        </ul>
        <p className="numeric mt-2 text-[10.5px] text-ink-muted">
          Sessions run {SESSION_HOURS_LABEL} · closed Sat &amp; Sun
        </p>
      </div>
    </BentoCard>
  );
}

interface NavButtonProps {
  label: string;
  disabled: boolean;
  onClick: () => void;
  children: React.ReactNode;
}

function NavButton({ label, disabled, onClick, children }: NavButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      className={cn(
        "focus-ring grid size-7 place-items-center rounded-md text-ink-secondary transition-colors duration-150",
        "hover:bg-surface-sunken hover:text-ink",
        "disabled:pointer-events-none disabled:opacity-30",
      )}
    >
      {children}
    </button>
  );
}

interface CalendarDayProps {
  day: Date;
  dateKey: string;
  inMonth: boolean;
  isFuture: boolean;
  isWeekend: boolean;
  isToday: boolean;
  isSelected: boolean;
  status: DailyTargetStatus | null;
  performance: DailyTradingPerformance | null;
  onSelect: (dateKey: string) => void;
}

const CELL_BASE =
  "flex h-9 w-full flex-col items-center justify-center rounded-inner sm:h-10";

function CalendarDay({
  day,
  dateKey,
  inMonth,
  isFuture,
  isWeekend: weekend,
  isToday,
  isSelected,
  status,
  performance,
  onSelect,
}: CalendarDayProps) {
  const dayNumber = day.getDate();

  // Padding days, weekends and future sessions carry no data and never select.
  if (!inMonth || weekend || isFuture) {
    const isClosedTradingDay = inMonth && weekend;

    return (
      <div
        aria-hidden={!inMonth}
        title={isClosedTradingDay ? "Market closed" : undefined}
        className={cn(
          CELL_BASE,
          isClosedTradingDay && "bg-surface-sunken",
          isToday && "ring-1 ring-hairline-strong ring-inset",
        )}
      >
        <span
          className={cn(
            "numeric text-[12px] leading-none",
            !inMonth && "text-ink-muted/30",
            inMonth && weekend && "text-ink-muted/55",
            inMonth && !weekend && "text-ink-muted/70",
          )}
        >
          {dayNumber}
        </span>
        <span className="sr-only">
          {inMonth
            ? weekend
              ? ` ${formatAccessibleDate(day)}. Market closed.`
              : ` ${formatAccessibleDate(day)}. Upcoming session.`
            : ""}
        </span>
        <span
          aria-hidden="true"
          className={cn(
            "mt-1 size-1.5",
            isClosedTradingDay && "rounded-[2px] bg-hairline-strong",
          )}
        />
      </div>
    );
  }

  const meta = status ? STATUS_META[status] : null;
  const pnlLabel = performance
    ? `${meta?.label ?? "No trades"}, realized ${formatINR(performance.realizedPnl, { showSign: true })}`
    : "No session data";

  return (
    <button
      type="button"
      onClick={() => onSelect(dateKey)}
      aria-pressed={isSelected}
      aria-current={isToday ? "date" : undefined}
      aria-label={`${formatAccessibleDate(day)}. ${pnlLabel}.`}
      className={cn(
        CELL_BASE,
        "focus-ring ring-inset transition-colors duration-150 hover:bg-surface-sunken",
        isToday && !isSelected && "ring-1 ring-hairline-strong",
        isSelected && "bg-selected shadow-[0_1px_2px_rgba(0,0,0,0.08)] ring-1 ring-ink/30",
      )}
    >
      <span
        className={cn(
          "numeric text-[12px] leading-none",
          isToday || isSelected
            ? "font-semibold text-ink"
            : "font-medium text-ink-secondary",
        )}
      >
        {dayNumber}
      </span>
      <span
        aria-hidden="true"
        className={cn(
          "mt-1 size-1.5 rounded-full",
          meta ? meta.dot : "bg-transparent",
        )}
      />
    </button>
  );
}
