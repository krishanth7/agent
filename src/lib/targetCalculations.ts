import type { DailyTargetStatus, PerformanceTotals } from "@/types/trading";

/**
 * Presentation-side maths only.
 *
 * The daily target is deliberately *not* computed here. It is derived by the
 * backend in `Decimal` and delivered alongside the monthly target, so the
 * rounding rule has exactly one implementation. A second copy in JavaScript
 * would drift the moment the denominator stops being a flat 30 days, and
 * float division would disagree with the server at the half-rupee boundary.
 *
 * What remains are pure display helpers: ratios for progress bars, and the
 * status classification, which the backend also sends per session but which is
 * recomputed locally for the *selected* date against the *current* target.
 */

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

/** Mean realized P&L per session that actually traded. */
export function calculateAveragePerSession(totals: PerformanceTotals): number {
  if (totals.activeSessions <= 0) return 0;
  return totals.realizedPnl / totals.activeSessions;
}
