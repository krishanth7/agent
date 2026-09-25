"use client";

import { addMonths, isSameMonth } from "date-fns";
import { ChevronLeft, ChevronRight, WifiOff } from "lucide-react";
import { motion } from "motion/react";

import { BentoCard } from "@/components/ui/BentoCard";
import { CardSkeleton } from "@/components/ui/CardState";
import { Popover, PopoverPanel, PopoverTrigger } from "@/components/ui/Popover";
import { STATUS_META } from "@/components/ui/StatusIndicator";
import { Tooltip } from "@/components/ui/Tooltip";
import type { ResourceStatus } from "@/hooks/useApiResource";
import { formatINR } from "@/lib/currency";
import {
  WEEKDAY_LABELS,
  buildCalendarWeeks,
  canGoToNextMonth,
  canGoToPreviousMonth,
  formatAccessibleDate,
  formatLongDate,
  formatMonthTitle,
  toDateKey,
} from "@/lib/dates";
import {
  getHolidayByKey,
  hasPublishedCalendar,
  holidaysInMonth,
  type ExchangeHoliday,
} from "@/lib/holidays";
import { AGENT_WINDOW_LABEL, SESSION_HOURS_LABEL, isWeekend } from "@/lib/market";
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
  /** `null` until the backend's reference date establishes the current month. */
  monthAnchor: Date | null;
  onMonthChange: (next: Date) => void;
  selectedDateKey: string;
  onSelectDate: (dateKey: string) => void;
  todayKey: string;
  /** Session data for a date, or `null` when nothing was recorded. */
  getPerformance: (dateKey: string) => DailyTradingPerformance | null;
  /** Status derived from the session and the current daily target. */
  getStatus: (dateKey: string) => DailyTargetStatus | null;
  /** Load state of the month currently being displayed. */
  state: ResourceStatus;
  error?: string | null;
  offline?: boolean;
  onRetry?: () => void;
  order?: number;
  className?: string;
}

/**
 * Month view of agent performance. Markers are intentionally quiet — a single
 * dot per session, with the written detail deferred to the summary card.
 *
 * NON-TRADING DAYS
 * ----------------
 * Two rules, both resolved in the browser. Saturdays and Sundays come from the
 * weekday; exchange holidays come from the bundled NSE calendar in
 * `lib/holidays`. Neither asks the API — the grid, the weekends and the
 * holidays are all derivable from the date alone, so they stay correct and
 * legible while the backend is unreachable. Only the coloured session dots
 * depend on the network, and only those go missing when it fails.
 */
export function TradingCalendar({
  monthAnchor,
  onMonthChange,
  selectedDateKey,
  onSelectDate,
  todayKey,
  getPerformance,
  getStatus,
  state,
  error,
  offline,
  onRetry,
  order,
  className,
}: TradingCalendarProps) {
  // The anchor is now supplied by the client clock, so this is only ever `null`
  // for the single paint before hydration — not for the whole time the API is
  // down. A skeleton is the right answer for that paint; an error is not.
  if (monthAnchor === null) {
    return (
      <BentoCard order={order} className={className} ariaLabel="Trading calendar">
        <h2 className="eyebrow text-ink-secondary">Trading Calendar</h2>
        <CardSkeleton headline="h-5" lines={5} />
      </BentoCard>
    );
  }

  const weeks = buildCalendarWeeks(monthAnchor);
  const canGoBack = canGoToPreviousMonth(monthAnchor);
  const canGoForward = canGoToNextMonth(monthAnchor);
  const monthTitle = formatMonthTitle(monthAnchor);

  const anchorYear = monthAnchor.getFullYear();
  const publishedCalendar = hasPublishedCalendar(anchorYear);
  const holidayCount = holidaysInMonth(
    anchorYear,
    monthAnchor.getMonth() + 1,
  ).filter((entry) => entry.kind === "holiday").length;

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

      {/*
        The grid, the weekends and the holidays are derivable from the date
        alone, so they stay rendered in every state — including failure. Only
        the coloured session dots come from the API.

        A failure used to replace the whole card, on the reasoning that an empty
        calendar reads as "no trades" rather than "no data". That reasoning was
        right about the risk and wrong about the remedy: it threw away the
        holiday and weekend information, which is still perfectly good, to avoid
        an ambiguity that a one-line notice resolves outright.
      */}
      {state === "error" ? (
        <InlineNotice
          message={
            offline
              ? "Session data unavailable — the trading API is not responding."
              : (error ?? "Session data could not be loaded.")
          }
          onRetry={onRetry}
        />
      ) : null}

      <table
        aria-busy={state === "loading"}
        className={cn(
          "mt-4 w-full table-fixed border-separate border-spacing-[3px] transition-opacity duration-200",
          state === "loading" && "opacity-60",
        )}
      >
        <caption className="sr-only">
          {`Daily trading performance for ${monthTitle}. Select a past or current weekday to view its summary. The market is closed on Saturdays, Sundays and exchange holidays; select a holiday to see which one.`}
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
                const isFuture = todayKey !== "" && dateKey > todayKey;
                const weekend = isWeekend(day);
                const holiday = getHolidayByKey(dateKey);
                const closedForHoliday = holiday?.kind === "holiday";
                const hasSession =
                  inMonth && !isFuture && !weekend && !closedForHoliday;

                return (
                  <td key={dateKey} className="p-0 align-top">
                    <CalendarDay
                      day={day}
                      dateKey={dateKey}
                      inMonth={inMonth}
                      isFuture={isFuture}
                      isWeekend={weekend}
                      holiday={holiday}
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
            <span className="text-[10.5px] text-ink-muted">Weekend</span>
          </li>
          <li className="flex items-center gap-1.5">
            <span aria-hidden="true" className="size-1.5 rotate-45 bg-caution" />
            <span className="text-[10.5px] text-ink-muted">Holiday</span>
          </li>
        </ul>
        <p className="numeric mt-2 text-[10.5px] text-ink-muted">
          Sessions run {SESSION_HOURS_LABEL} · agent trades {AGENT_WINDOW_LABEL}
        </p>
        <p className="mt-1 text-[10.5px] leading-snug text-ink-muted">
          {holidayCount > 0
            ? `${holidayCount} exchange ${holidayCount === 1 ? "holiday" : "holidays"} this month — select one for details.`
            : publishedCalendar
              ? "No exchange holidays this month."
              : `Holiday list bundled for 2026 only; ${anchorYear} is not covered.`}
        </p>
      </div>
    </BentoCard>
  );
}

interface InlineNoticeProps {
  message: string;
  onRetry?: () => void;
}

/**
 * A strip, not a replacement.
 *
 * Used where part of a card failed but the rest is still worth showing. It
 * states which part is missing so the surviving content cannot be misread as
 * complete.
 */
function InlineNotice({ message, onRetry }: InlineNoticeProps) {
  return (
    <div
      role="status"
      className="mt-3 flex items-center gap-2 rounded-inner border border-hairline bg-surface-sunken px-2.5 py-2"
    >
      <WifiOff aria-hidden="true" className="size-3.5 shrink-0 text-ink-muted" />
      <p className="min-w-0 flex-1 text-[11.5px] leading-snug text-ink-secondary">
        {message}
      </p>
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="focus-ring shrink-0 rounded-md px-1.5 py-0.5 text-[11.5px] font-medium text-ink underline-offset-2 transition-colors duration-150 hover:bg-hairline"
        >
          Retry
        </button>
      ) : null}
    </div>
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
  /** The published holiday or muhurat entry for this date, if any. */
  holiday: ExchangeHoliday | null;
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
  holiday,
  isToday,
  isSelected,
  status,
  performance,
  onSelect,
}: CalendarDayProps) {
  const dayNumber = day.getDate();

  // An exchange holiday is the one non-trading day worth interacting with: it
  // has a *reason*, and "why is the 14th blank?" is a question the grid should
  // be able to answer itself. Weekends need no explanation, so they stay inert.
  if (inMonth && holiday) {
    return (
      <HolidayCell
        day={day}
        dateKey={dateKey}
        dayNumber={dayNumber}
        holiday={holiday}
        isToday={isToday}
        isSelected={isSelected}
        onSelect={onSelect}
      />
    );
  }

  // Padding days, weekends and future sessions carry no data and never select.
  if (!inMonth || weekend || isFuture) {
    const isClosedTradingDay = inMonth && weekend;

    return (
      <div
        aria-hidden={!inMonth}
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

interface HolidayCellProps {
  day: Date;
  dateKey: string;
  dayNumber: number;
  holiday: ExchangeHoliday;
  isToday: boolean;
  isSelected: boolean;
  onSelect: (dateKey: string) => void;
}

/**
 * A non-trading day the exchange announced in advance.
 *
 * Two affordances, deliberately: the tooltip answers "what is this?" without a
 * click, and the click opens the full entry for anyone who wants the date, the
 * weekday and what it means for the agent. The tooltip alone would be
 * unreachable on touch; the popover alone would hide the name behind an
 * interaction nobody knows is there.
 *
 * It also selects, like every other in-month cell. The summary card is the
 * detail panel for whichever date was last clicked, and leaving it showing a
 * different day's figures after the user clicked this one would be a quiet lie
 * about what they are looking at.
 */
function HolidayCell({
  day,
  dateKey,
  dayNumber,
  holiday,
  isToday,
  isSelected,
  onSelect,
}: HolidayCellProps) {
  const closed = holiday.kind === "holiday";

  return (
    <Popover>
      <Tooltip
        side="top"
        label={
          <span className="block">
            <span className="block font-semibold">{holiday.description}</span>
            <span className="block text-canvas/70">
              {closed ? "Exchange holiday — no session" : "Special session"}
            </span>
          </span>
        }
      >
        <PopoverTrigger
          aria-label={`${formatAccessibleDate(day)}. ${holiday.description}. ${
            closed ? "Exchange holiday, no trading session." : "Special session."
          }`}
          aria-pressed={isSelected}
          onClick={() => onSelect(dateKey)}
          className={cn(
            CELL_BASE,
            "focus-ring ring-inset transition-colors duration-150",
            closed
              ? "bg-caution-soft hover:bg-caution/20"
              : "bg-surface-sunken hover:bg-hairline",
            isSelected && "ring-2 ring-caution",
            !isSelected && isToday && "ring-1 ring-hairline-strong",
          )}
        >
          <span
            className={cn(
              "numeric text-[12px] leading-none",
              closed ? "font-medium text-caution" : "text-ink-muted/70",
            )}
          >
            {dayNumber}
          </span>
          <span
            aria-hidden="true"
            className={cn(
              "mt-1 size-1.5 rotate-45",
              closed ? "bg-caution" : "bg-hairline-strong",
            )}
          />
        </PopoverTrigger>
      </Tooltip>

      <PopoverPanel title={holiday.description} side="top" align="center">
        <div className="pr-6">
          <p className="eyebrow text-ink-muted">
            {closed ? "Exchange Holiday" : "Special Session"}
          </p>
          <h3 className="mt-1 text-[15px] font-semibold leading-snug tracking-[-0.01em] text-ink">
            {holiday.description}
          </h3>
          <p className="numeric mt-1 text-[12px] text-ink-secondary">
            {formatLongDate(day)} · {holiday.weekday}
          </p>

          <p className="mt-3 border-t border-hairline pt-2.5 text-[12px] leading-snug text-ink-secondary">
            {closed
              ? "The NSE equity and F&O segments are closed. There is no session to record, and the agent does not run."
              : "The regular session is closed. The exchange holds a ceremonial session whose timings it announces separately each year."}
          </p>
          <p className="numeric mt-2 text-[10.5px] text-ink-muted">
            Agent window on trading days · {AGENT_WINDOW_LABEL}
          </p>
        </div>
      </PopoverPanel>
    </Popover>
  );
}
