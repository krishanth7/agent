import type {
  AccountSummary,
  DailyTradingPerformance,
  MarketStatus,
} from "@/types/trading";

/**
 * Single source of mock data for frontend V1.
 *
 * BACKEND NOTE: each export below maps to one future data source —
 *   `MOCK_ACCOUNT_SUMMARY`  → broker funds/margin endpoint
 *   `MOCK_DAILY_PERFORMANCE`→ agent trade-journal endpoint
 *   `MOCK_MARKET_STATUS`    → exchange session/holiday service
 * Components never read literals directly, so swapping in real fetches is a
 * change to this module and the call sites that provide it — not to the UI.
 */

/**
 * The dashboard is pinned to a fixed "today" so the mock September 2026 data
 * always tells a coherent story. Production replaces this with `new Date()`.
 */
export const MOCK_TODAY_KEY = "2026-09-22";

export const MOCK_MARKET_STATUS: MarketStatus = "closed";

export const MOCK_ACCOUNT_SUMMARY: AccountSummary = {
  availableBalance: 25000,
  usedMargin: 0,
  totalCapital: 25000,
};

/** Fallback goal before the user configures (and we persist) their own. */
export const DEFAULT_MONTHLY_TARGET = 10000;

/**
 * Realized sessions for September 2026 through the 22nd, covering every state
 * the calendar renders: target achieved, profit below target, loss, and a
 * no-trade day (07 Sep). Month-to-date total is ₹4,280.
 */
export const MOCK_DAILY_PERFORMANCE: readonly DailyTradingPerformance[] = [
  { date: "2026-09-01", realizedPnl: 410, trades: 3, wins: 2, losses: 1 },
  { date: "2026-09-02", realizedPnl: 185, trades: 2, wins: 1, losses: 1 },
  { date: "2026-09-03", realizedPnl: -240, trades: 3, wins: 1, losses: 2 },
  { date: "2026-09-04", realizedPnl: 520, trades: 4, wins: 3, losses: 1 },
  { date: "2026-09-07", realizedPnl: 0, trades: 0, wins: 0, losses: 0 },
  { date: "2026-09-08", realizedPnl: 365, trades: 2, wins: 2, losses: 0 },
  { date: "2026-09-09", realizedPnl: 295, trades: 3, wins: 2, losses: 1 },
  { date: "2026-09-10", realizedPnl: -150, trades: 2, wins: 0, losses: 2 },
  { date: "2026-09-11", realizedPnl: 610, trades: 4, wins: 3, losses: 1 },
  { date: "2026-09-14", realizedPnl: 340, trades: 3, wins: 2, losses: 1 },
  { date: "2026-09-15", realizedPnl: 95, trades: 2, wins: 1, losses: 1 },
  { date: "2026-09-16", realizedPnl: -310, trades: 3, wins: 1, losses: 2 },
  { date: "2026-09-17", realizedPnl: 455, trades: 3, wins: 2, losses: 1 },
  { date: "2026-09-18", realizedPnl: 825, trades: 5, wins: 4, losses: 1 },
  { date: "2026-09-21", realizedPnl: 460, trades: 3, wins: 2, losses: 1 },
  { date: "2026-09-22", realizedPnl: 420, trades: 3, wins: 2, losses: 1 },
] as const;

const performanceByDate = new Map(
  MOCK_DAILY_PERFORMANCE.map((session) => [session.date, session]),
);

/** Returns the session for a `yyyy-MM-dd` key, or `null` when none was recorded. */
export function getPerformanceForDate(
  dateKey: string,
): DailyTradingPerformance | null {
  return performanceByDate.get(dateKey) ?? null;
}

/** Sessions belonging to a given `yyyy-MM` prefix, in chronological order. */
export function getPerformanceForMonth(
  monthKey: string,
): DailyTradingPerformance[] {
  return MOCK_DAILY_PERFORMANCE.filter((session) =>
    session.date.startsWith(monthKey),
  );
}
