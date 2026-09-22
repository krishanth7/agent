/**
 * Domain types for the NIFTY Options Agent dashboard.
 *
 * Every shape here is designed to be satisfied later by a broker/backend API
 * response without changing component code. Frontend V1 fulfils them with mock
 * data from `src/data/mockTradingData.ts`.
 */

/** Snapshot of the trading account. Sourced from a broker funds API in production. */
export interface AccountSummary {
  availableBalance: number;
  usedMargin: number;
  totalCapital: number;
}

/** A single trading session's realized outcome. `date` is an ISO `yyyy-MM-dd` key. */
export interface DailyTradingPerformance {
  date: string;
  realizedPnl: number;
  trades: number;
  wins: number;
  losses: number;
}

/** User-defined profit goal for the month. Persisted locally in V1. */
export interface MonthlyTradingTarget {
  amount: number;
}

/**
 * Progress of a session against its daily target. Derived, never stored, so a
 * single rule governs the cards and the calendar simultaneously.
 */
export type DailyTargetStatus =
  | "not-started"
  | "in-progress"
  | "achieved"
  | "loss";

export type MarketStatus = "open" | "closed" | "pre-open";

/** Aggregate of realized performance across a set of sessions. */
export interface PerformanceTotals {
  realizedPnl: number;
  trades: number;
  wins: number;
  losses: number;
  activeSessions: number;
}
