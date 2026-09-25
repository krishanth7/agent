/**
 * NSE session metadata and the live market clock.
 *
 * WHY THIS IS COMPUTED IN THE BROWSER
 * -----------------------------------
 * "Is the market open right now?" is a question about the wall clock in
 * Asia/Kolkata and a published timetable. Both are things the browser already
 * has. Routing it through the API would add a network round trip, a staleness
 * window and a failure mode, and would buy nothing — the backend has no more
 * authority over the time of day than the client does.
 *
 * WHY THE BROWSER'S TIME ZONE IS NEVER USED
 * -----------------------------------------
 * The *instant* is trustworthy; the local calendar is not. A user in London
 * sees 09:15 IST as 03:45 local, and a naive `date.getHours()` would report the
 * market closed for the entire session. Every wall-clock reading below is taken
 * through `Intl.DateTimeFormat` pinned to `Asia/Kolkata`, so the dashboard
 * behaves identically from any machine on earth.
 *
 * WHAT THE AGENT WINDOW IS
 * ------------------------
 * The exchange trades until 15:30. The agent is only permitted to act between
 * 09:15 and 15:00, deliberately stopping half an hour early: the closing period
 * is the least liquid and most gap-prone part of the session, and an automated
 * system with no human watching it should not be opening positions into it.
 * This is a stated policy, not an exchange rule, and the UI labels it as such.
 */

import { getHolidayByKey } from "@/lib/holidays";

export const IST_TIME_ZONE = "Asia/Kolkata";

export const SESSION_TIMEZONE = "IST";

/**
 * Timetable, as minutes since IST midnight.
 *
 * Minutes rather than `Date`s because every comparison here is within one day
 * and integer arithmetic cannot drift across a DST boundary — India has none,
 * but the arithmetic should not depend on that remaining true.
 */
const MINUTE = 1;
const HOUR = 60 * MINUTE;

export const SCHEDULE = {
  /** Pre-open order entry opens. */
  preOpenStart: 9 * HOUR,
  /** Order entry closes — the exchange randomises the final two minutes. */
  preOpenEntryEnd: 9 * HOUR + 10 * MINUTE,
  /** Order matching and trade confirmation ends. */
  preOpenMatchEnd: 9 * HOUR + 12 * MINUTE,
  /** Regular session opens. */
  open: 9 * HOUR + 15 * MINUTE,
  /** The agent stops placing orders. */
  agentCutoff: 15 * HOUR,
  /** Regular session closes. */
  close: 15 * HOUR + 30 * MINUTE,
  /** Position-limit setup and trade-modification cutoff. */
  adminCutoff: 16 * HOUR + 15 * MINUTE,
} as const;

/**
 * `9:15 AM – 3:30 PM IST` — the canonical session string shown in the header.
 *
 * Derived from `SCHEDULE` rather than written out, so the label and the
 * comparisons that drive the status pill cannot drift apart. A hand-typed
 * label is a second source of truth that no test would ever catch disagreeing.
 */
export const SESSION_HOURS_LABEL = `${formatSessionTime(SCHEDULE.open)} – ${formatSessionTime(SCHEDULE.close)} ${SESSION_TIMEZONE}`;

/**
 * Agent execution window, deliberately narrower than the exchange session.
 *
 * The agent stands down 30 minutes before the close: the closing period is the
 * least liquid part of the session and no unattended system should be opening
 * positions into it.
 */
export const AGENT_WINDOW_LABEL = `${formatSessionTime(SCHEDULE.open)} – ${formatSessionTime(SCHEDULE.agentCutoff)} ${SESSION_TIMEZONE}`;

/**
 * Where the clock currently sits in the day.
 *
 * `post-close` is distinct from `closed` because the two are operationally
 * different: trades can still be modified until 16:15, and an operator looking
 * at the dashboard at 15:45 needs to know that.
 */
export type MarketPhase = "closed" | "pre-open" | "open" | "post-close";

/** Why the market is not trading today, when it is not. */
export type NonTradingReason = "weekend" | "holiday" | null;

export interface MarketSnapshot {
  /** `yyyy-MM-dd` in IST — the trading date, wherever the browser is. */
  readonly dateKey: string;
  /** IST minutes since midnight. */
  readonly minutes: number;
  /** `0` Sunday … `6` Saturday, in IST. */
  readonly weekday: number;
  readonly phase: MarketPhase;
  /** Whether the exchange holds a regular session on this date at all. */
  readonly isTradingDay: boolean;
  readonly nonTradingReason: NonTradingReason;
  /** Whether the agent is inside its permitted execution window right now. */
  readonly agentWindowOpen: boolean;
}

/**
 * IST wall-clock parts for an instant.
 *
 * `en-CA` is chosen for one reason: its date format is ISO (`2026-09-23`), so
 * the key this produces is the same shape the rest of the app indexes by,
 * without reassembling it from parts and re-introducing a padding bug.
 */
const IST_FORMATTER = new Intl.DateTimeFormat("en-CA", {
  timeZone: IST_TIME_ZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

interface IstWallClock {
  dateKey: string;
  minutes: number;
  weekday: number;
}

function istWallClock(instant: Date): IstWallClock {
  const parts = IST_FORMATTER.formatToParts(instant);
  const read = (type: Intl.DateTimeFormatPartTypes): string =>
    parts.find((part) => part.type === type)?.value ?? "00";

  const year = read("year");
  const month = read("month");
  const day = read("day");
  const dateKey = `${year}-${month}-${day}`;

  // The weekday is derived from the IST date rather than read from the
  // formatter, so it can never disagree with `dateKey` — and `Date.UTC` on a
  // date-only value has no time-zone component to get wrong.
  const weekday = new Date(
    Date.UTC(Number(year), Number(month) - 1, Number(day)),
  ).getUTCDay();

  return {
    dateKey,
    minutes: Number(read("hour")) * HOUR + Number(read("minute")),
    weekday,
  };
}

/** Saturday or Sunday — the market is closed and no session can exist. */
export function isWeekend(date: Date): boolean {
  const day = date.getDay();
  return day === 0 || day === 6;
}

/**
 * The market state at a given instant.
 *
 * Takes the instant as an argument rather than calling `Date.now()` internally
 * so it stays a pure function: the caller owns the clock, and a test can hand
 * it 09:14 and 09:16 without waiting two minutes.
 */
export function getMarketSnapshot(instant: Date): MarketSnapshot {
  const { dateKey, minutes, weekday } = istWallClock(instant);

  const weekend = weekday === 0 || weekday === 6;
  // Looked up by key, not by `Date`, so the holiday question is asked about the
  // IST calendar date and never about the browser's.
  const holiday = getHolidayByKey(dateKey)?.kind === "holiday";

  const tradingDay = !weekend && !holiday;
  const reason: NonTradingReason = weekend
    ? "weekend"
    : holiday
      ? "holiday"
      : null;

  let phase: MarketPhase = "closed";
  if (tradingDay) {
    if (minutes >= SCHEDULE.preOpenStart && minutes < SCHEDULE.open) {
      phase = "pre-open";
    } else if (minutes >= SCHEDULE.open && minutes < SCHEDULE.close) {
      phase = "open";
    } else if (minutes >= SCHEDULE.close && minutes < SCHEDULE.adminCutoff) {
      phase = "post-close";
    }
  }

  return {
    dateKey,
    minutes,
    weekday,
    phase,
    isTradingDay: tradingDay,
    nonTradingReason: reason,
    agentWindowOpen:
      tradingDay &&
      minutes >= SCHEDULE.open &&
      minutes < SCHEDULE.agentCutoff,
  };
}

/** `9:15 AM`-style label for minutes since midnight. */
export function formatSessionTime(minutes: number): string {
  const hour24 = Math.floor(minutes / HOUR);
  const minute = minutes % HOUR;
  const suffix = hour24 < 12 ? "AM" : "PM";
  const hour12 = hour24 % 12 === 0 ? 12 : hour24 % 12;
  return `${hour12}:${String(minute).padStart(2, "0")} ${suffix}`;
}

/** `15:30`-style label, which is how exchange circulars express timings. */
export function formatExchangeTime(minutes: number): string {
  const hour24 = Math.floor(minutes / HOUR);
  const minute = minutes % HOUR;
  return `${String(hour24).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
}
