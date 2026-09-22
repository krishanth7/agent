import {
  addMonths,
  eachDayOfInterval,
  endOfMonth,
  endOfWeek,
  format,
  isAfter,
  isBefore,
  parseISO,
  startOfMonth,
  startOfWeek,
} from "date-fns";

/** Trading week runs Monday-first, matching NSE session ordering. */
const WEEK_OPTIONS = { weekStartsOn: 1 } as const;

export const WEEKDAY_LABELS = [
  "Mon",
  "Tue",
  "Wed",
  "Thu",
  "Fri",
  "Sat",
  "Sun",
] as const;

/** V1 ships the 2026 calendar only; navigation is clamped to this range. */
export const CALENDAR_MIN_MONTH = new Date(2026, 0, 1);
export const CALENDAR_MAX_MONTH = new Date(2026, 11, 1);

/** Stable `yyyy-MM-dd` key used to index mock (later: API) performance data. */
export function toDateKey(date: Date): string {
  return format(date, "yyyy-MM-dd");
}

export function fromDateKey(key: string): Date {
  return parseISO(key);
}

/** `22 Sep 2026` — header and compact contexts. */
export function formatCompactDate(date: Date): string {
  return format(date, "d MMM yyyy");
}

/** `22 September 2026` — selected-day detail. */
export function formatLongDate(date: Date): string {
  return format(date, "d MMMM yyyy");
}

/** `September 2026` — calendar title. */
export function formatMonthTitle(date: Date): string {
  return format(date, "MMMM yyyy");
}

/** `Tuesday, 22 September 2026` — accessible labels for day buttons. */
export function formatAccessibleDate(date: Date): string {
  return format(date, "EEEE, d MMMM yyyy");
}

/**
 * Builds the Monday-first day matrix for a month, including the leading and
 * trailing days needed to complete the first and last weeks.
 */
export function buildCalendarWeeks(monthAnchor: Date): Date[][] {
  const gridStart = startOfWeek(startOfMonth(monthAnchor), WEEK_OPTIONS);
  const gridEnd = endOfWeek(endOfMonth(monthAnchor), WEEK_OPTIONS);
  const days = eachDayOfInterval({ start: gridStart, end: gridEnd });

  const weeks: Date[][] = [];
  for (let index = 0; index < days.length; index += 7) {
    weeks.push(days.slice(index, index + 7));
  }
  return weeks;
}

/** All dates within `monthAnchor`'s month, excluding grid padding. */
export function getMonthDays(monthAnchor: Date): Date[] {
  return eachDayOfInterval({
    start: startOfMonth(monthAnchor),
    end: endOfMonth(monthAnchor),
  });
}

export function canGoToPreviousMonth(monthAnchor: Date): boolean {
  return !isBefore(startOfMonth(addMonths(monthAnchor, -1)), CALENDAR_MIN_MONTH);
}

export function canGoToNextMonth(monthAnchor: Date): boolean {
  return !isAfter(startOfMonth(addMonths(monthAnchor, 1)), CALENDAR_MAX_MONTH);
}
