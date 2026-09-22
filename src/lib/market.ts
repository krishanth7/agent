/**
 * NSE session metadata.
 *
 * The equity and F&O segments trade 09:15–15:30 IST, Monday to Friday. Weekends
 * are always closed, which is the only non-trading rule the frontend can derive
 * on its own.
 *
 * PRODUCTION NOTE: exchange holidays (and special muhurat sessions) are *not*
 * derivable client-side — they need the holiday calendar from the backend. Once
 * that exists, `isTradingDay` should also consult it rather than only checking
 * the weekday.
 */

export const SESSION_OPEN_LABEL = "9:15 AM";
export const SESSION_CLOSE_LABEL = "3:30 PM";
export const SESSION_TIMEZONE = "IST";

/** `9:15 AM – 3:30 PM IST` — the canonical session string shown in the header. */
export const SESSION_HOURS_LABEL = `${SESSION_OPEN_LABEL} – ${SESSION_CLOSE_LABEL} ${SESSION_TIMEZONE}`;

/** Saturday or Sunday — the market is closed and no session can exist. */
export function isWeekend(date: Date): boolean {
  const day = date.getDay();
  return day === 0 || day === 6;
}

/** A day the market can trade. Weekday-only in V1; see the production note. */
export function isTradingDay(date: Date): boolean {
  return !isWeekend(date);
}
