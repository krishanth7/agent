import type {
  DailyTargetStatus,
  DailyTradingPerformance,
  PerformanceTotals,
} from "@/types/trading";

/**
 * Denominator for the daily target in frontend V1.
 *
 * PRODUCTION NOTE: replace this fixed 30 with the number of *remaining NSE
 * trading sessions* in the current month, which requires the exchange holiday
 * calendar and an expiry-aware session list from the backend. Intentionally out
 * of scope for this phase — only this constant and `calculateDailyTarget` need
 * to change.
 */
export const ASSUMED_DAYS_PER_MONTH = 30;

/**
 * Splits a monthly goal into a per-day goal.
 *
 * Rounding rule: fraction `< 0.5` rounds down, `>= 0.5` rounds up — exactly
 * `Math.round` for the non-negative inputs this function accepts.
 * `₹10,000 → ₹333`, `₹10,010 → ₹334`.
 */
export function calculateDailyTarget(monthlyTarget: number): number {
  if (!Number.isFinite(monthlyTarget) || monthlyTarget <= 0) return 0;
  return Math.round(monthlyTarget / ASSUMED_DAYS_PER_MONTH);
}

/**
 * Classifies a session against its daily target. The single source of truth for
 * status across the summary cards and the calendar markers.
 */
export function getDailyTargetStatus(
  todayProfit: number,
  dailyTarget: number,
): DailyTargetStatus {
  if (!Number.isFinite(todayProfit) || todayProfit === 0) return "not-started";
  if (todayProfit < 0) return "loss";

  // A missing or zero target is treated as a bar of ₹0, so any profit clears
  // it. Reporting "below target" against a ₹0 goal would be misleading.
  const target = Number.isFinite(dailyTarget) ? dailyTarget : 0;

  return todayProfit >= target ? "achieved" : "in-progress";
}

/** Unclamped completion ratio. Can exceed 1 when the target is beaten. */
export function calculateProgressRatio(value: number, target: number): number {
  if (!Number.isFinite(value) || !Number.isFinite(target) || target <= 0) return 0;
  return value / target;
}

/** Ratio clamped to `0..1` for progress-bar geometry. */
export function clampRatio(ratio: number): number {
  if (!Number.isFinite(ratio)) return 0;
  return Math.min(Math.max(ratio, 0), 1);
}

/** Amount still required to reach the target. Zero once the target is met. */
export function calculateRemaining(value: number, target: number): number {
  if (!Number.isFinite(value) || !Number.isFinite(target) || target <= 0) return 0;
  return Math.max(target - value, 0);
}

export function calculateWinRate(wins: number, trades: number): number {
  if (!Number.isFinite(wins) || !Number.isFinite(trades) || trades <= 0) return 0;
  return wins / trades;
}

/** Folds a set of sessions into month-to-date totals. */
export function aggregatePerformance(
  sessions: readonly DailyTradingPerformance[],
): PerformanceTotals {
  return sessions.reduce<PerformanceTotals>(
    (totals, session) => ({
      realizedPnl: totals.realizedPnl + session.realizedPnl,
      trades: totals.trades + session.trades,
      wins: totals.wins + session.wins,
      losses: totals.losses + session.losses,
      activeSessions: totals.activeSessions + (session.trades > 0 ? 1 : 0),
    }),
    { realizedPnl: 0, trades: 0, wins: 0, losses: 0, activeSessions: 0 },
  );
}

/** Mean realized P&L per session that actually traded. */
export function calculateAveragePerSession(totals: PerformanceTotals): number {
  if (totals.activeSessions <= 0) return 0;
  return totals.realizedPnl / totals.activeSessions;
}
