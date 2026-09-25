/**
 * NSE trading holidays.
 *
 * WHY THIS LIVES IN THE FRONTEND AND NOT BEHIND THE API
 * -----------------------------------------------------
 * The exchange publishes its holiday list once a year, months in advance. It is
 * a fixed, public, low-cardinality fact — not a measurement, not a figure that
 * can go stale between two requests, and not something a broker reports. Making
 * the calendar ask a server before it can grey out Republic Day would mean the
 * grid cannot render at all while the backend is down, which is precisely the
 * failure this module exists to remove. Sixteen dates are cheaper to ship in the
 * bundle than to fetch.
 *
 * That is a different judgement from the one made about P&L. A number that
 * describes what an account actually did must come from storage; a date the
 * exchange announced in advance does not.
 *
 * SOURCE AND SCOPE
 * ----------------
 * The 2026 list for the equity and F&O segments. Every weekday label below was
 * verified against the actual calendar date rather than copied on trust.
 *
 * Diwali Laxmi Pujan (8 November 2026) falls on a Sunday and is recorded as a
 * `muhurat` entry rather than a holiday: the market is closed for the regular
 * session, as it is every Sunday, but the exchange holds a special ceremonial
 * session whose timings it announces separately each year. Calling it a
 * "holiday" would be wrong in both directions.
 *
 * MAINTENANCE
 * -----------
 * This is a dated artefact. `HOLIDAY_CALENDAR_YEAR` exists so the UI can say
 * "no published calendar" for a year it does not have, rather than silently
 * implying every day of 2027 is a trading day.
 */

import { toDateKey } from "@/lib/dates";

/** The only year for which a published list is bundled. */
export const HOLIDAY_CALENDAR_YEAR = 2026;

export type MarketClosureKind =
  /** A full trading holiday: no regular session. */
  | "holiday"
  /** A ceremonial session on an otherwise non-trading day. */
  | "muhurat";

export interface ExchangeHoliday {
  /** `yyyy-MM-dd`, the same key shape the rest of the app indexes dates by. */
  readonly date: string;
  /** Weekday name, verified against the date rather than transcribed. */
  readonly weekday: string;
  readonly description: string;
  readonly kind: MarketClosureKind;
}

/**
 * NSE trading holidays for 2026, in date order.
 *
 * Ordered so the list can be rendered directly and so an out-of-order insertion
 * is visible in review.
 */
export const NSE_HOLIDAYS_2026: readonly ExchangeHoliday[] = [
  {
    date: "2026-01-15",
    weekday: "Thursday",
    description: "Municipal Corporation Election — Maharashtra",
    kind: "holiday",
  },
  {
    date: "2026-01-26",
    weekday: "Monday",
    description: "Republic Day",
    kind: "holiday",
  },
  {
    date: "2026-03-03",
    weekday: "Tuesday",
    description: "Holi",
    kind: "holiday",
  },
  {
    date: "2026-03-26",
    weekday: "Thursday",
    description: "Shri Ram Navami",
    kind: "holiday",
  },
  {
    date: "2026-03-31",
    weekday: "Tuesday",
    description: "Shri Mahavir Jayanti",
    kind: "holiday",
  },
  {
    date: "2026-04-03",
    weekday: "Friday",
    description: "Good Friday",
    kind: "holiday",
  },
  {
    date: "2026-04-14",
    weekday: "Tuesday",
    description: "Dr. Baba Saheb Ambedkar Jayanti",
    kind: "holiday",
  },
  {
    date: "2026-05-01",
    weekday: "Friday",
    description: "Maharashtra Day",
    kind: "holiday",
  },
  {
    date: "2026-05-28",
    weekday: "Thursday",
    description: "Bakri Id",
    kind: "holiday",
  },
  {
    date: "2026-06-26",
    weekday: "Friday",
    description: "Muharram",
    kind: "holiday",
  },
  {
    date: "2026-09-14",
    weekday: "Monday",
    description: "Ganesh Chaturthi",
    kind: "holiday",
  },
  {
    date: "2026-10-02",
    weekday: "Friday",
    description: "Mahatma Gandhi Jayanti",
    kind: "holiday",
  },
  {
    date: "2026-10-20",
    weekday: "Tuesday",
    description: "Dussehra",
    kind: "holiday",
  },
  {
    // A Sunday. The regular session is closed as it is every weekend; the
    // exchange announces the muhurat timings separately.
    date: "2026-11-08",
    weekday: "Sunday",
    description: "Diwali — Laxmi Pujan (Muhurat trading)",
    kind: "muhurat",
  },
  {
    date: "2026-11-10",
    weekday: "Tuesday",
    description: "Diwali — Balipratipada",
    kind: "holiday",
  },
  {
    date: "2026-11-24",
    weekday: "Tuesday",
    description: "Prakash Gurpurb Sri Guru Nanak Dev",
    kind: "holiday",
  },
  {
    date: "2026-12-25",
    weekday: "Friday",
    description: "Christmas",
    kind: "holiday",
  },
];

/**
 * Date key → holiday. Built once at module load.
 *
 * A `Map` rather than a linear scan because the calendar asks this question
 * ~42 times per month render, and a lookup that is obviously O(1) removes the
 * temptation to memoize it at every call site.
 */
const BY_DATE_KEY: ReadonlyMap<string, ExchangeHoliday> = new Map(
  NSE_HOLIDAYS_2026.map((holiday) => [holiday.date, holiday]),
);

/** The holiday falling on a date key, or `null`. Includes muhurat entries. */
export function getHolidayByKey(dateKey: string): ExchangeHoliday | null {
  return BY_DATE_KEY.get(dateKey) ?? null;
}

/** The holiday falling on a `Date`, or `null`. */
export function getHoliday(date: Date): ExchangeHoliday | null {
  return getHolidayByKey(toDateKey(date));
}

/**
 * Whether the regular session is cancelled for an exchange holiday.
 *
 * A muhurat entry is deliberately excluded: it does not close anything that was
 * otherwise open, and treating it as a closure would mark a Sunday twice.
 */
export function isExchangeHoliday(date: Date): boolean {
  return getHoliday(date)?.kind === "holiday";
}

/** Whether a published holiday list exists for the given year. */
export function hasPublishedCalendar(year: number): boolean {
  return year === HOLIDAY_CALENDAR_YEAR;
}

/** Holidays falling in a given month, in date order. `month` is 1-indexed. */
export function holidaysInMonth(
  year: number,
  month: number,
): readonly ExchangeHoliday[] {
  const prefix = `${year}-${String(month).padStart(2, "0")}-`;
  return NSE_HOLIDAYS_2026.filter((holiday) => holiday.date.startsWith(prefix));
}
