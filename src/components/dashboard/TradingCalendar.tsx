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

const LEGEND: ReadonlyArray<{ status: DailyTargetStatus; label: string }> = [
  { status: "achieved", label: "Target met" },
  { status: "in-progress", label: "Below target" },
  { status: "loss", label: "Loss" },
  { status: "not-started", label: "No trade" },
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
        <h2
          aria-live="polite"
          className="text-[15px] font-semibold tracking-[-0.01em] text-ink"
        >
          {monthTitle}
        </h2>

        <div className="flex items-center gap-1">
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

      <table className="mt-5 w-full table-fixed border-separate border-spacing-0.5">
        <caption className="sr-only">
          {`Daily trading performance for ${monthTitle}. Select a past or current date to view its summary.`}
        </caption>
        <thead>
          <tr>
            {WEEKDAY_LABELS.map((day, index) => (
              <th
                key={day}
                scope="col"
                className="pb-2 text-[11px] font-medium text-ink-muted"
              >
                <span aria-hidden="true">{day}</span>
                <span className="sr-only">{WEEKDAY_FULL_NAMES[index]}</span>
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

                return (
                  <td key={dateKey} className="p-0 align-top">
                    <CalendarDay
                      day={day}
                      dateKey={dateKey}
                      inMonth={inMonth}
                      isFuture={isFuture}
                      isToday={dateKey === todayKey}
                      isSelected={dateKey === selectedDateKey}
                      status={inMonth && !isFuture ? getStatus(dateKey) : null}
                      performance={inMonth && !isFuture ? getPerformance(dateKey) : null}
                      onSelect={onSelectDate}
                    />
                  </td>
                );
              })}
            </tr>
          ))}
        </motion.tbody>
      </table>

      <ul className="mt-5 flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-hairline pt-4">
        {LEGEND.map(({ status, label }) => (
          <li key={status} className="flex items-center gap-1.5">
            <span
              aria-hidden="true"
              className={cn("size-1.5 rounded-full", STATUS_META[status].dot)}
            />
            <span className="text-[11px] text-ink-muted">{label}</span>
          </li>
        ))}
      </ul>
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
        "focus-ring grid size-8 place-items-center rounded-lg text-ink-secondary transition-colors duration-150",
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
  isToday: boolean;
  isSelected: boolean;
  status: DailyTargetStatus | null;
  performance: DailyTradingPerformance | null;
  onSelect: (dateKey: string) => void;
}

function CalendarDay({
  day,
  dateKey,
  inMonth,
  isFuture,
  isToday,
  isSelected,
  status,
  performance,
  onSelect,
}: CalendarDayProps) {
  const dayNumber = day.getDate();

  // Padding days and future sessions carry no data and are not selectable.
  if (!inMonth || isFuture) {
    return (
      <div
        aria-hidden={!inMonth}
        className="flex h-10 flex-col items-center justify-center rounded-inner sm:h-11"
      >
        <span
          className={cn(
            "numeric text-[13px]",
            inMonth ? "text-ink-muted/70" : "text-ink-muted/35",
          )}
        >
          {dayNumber}
        </span>
        <span className="mt-1 size-1.5" />
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
        "focus-ring flex h-10 w-full flex-col items-center justify-center rounded-inner ring-inset transition-all duration-150 sm:h-11",
        "hover:bg-white/60",
        isToday && !isSelected && "ring-1 ring-hairline-strong",
        isSelected
          ? "bg-white shadow-[0_1px_2px_rgba(30,26,22,0.07)] ring-1 ring-ink/25"
          : null,
      )}
    >
      <span
        className={cn(
          "numeric text-[13px] leading-none",
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
          "mt-1.5 size-1.5 rounded-full",
          meta ? meta.dot : "bg-transparent",
        )}
      />
    </button>
  );
}
