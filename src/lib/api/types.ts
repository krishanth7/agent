/**
 * Wire shapes exactly as the backend emits them, plus the boundary transforms.
 *
 * The API speaks snake_case and underscore-separated status strings; the
 * frontend domain in `src/types/trading.ts` speaks camelCase and hyphenated
 * ones. Both conventions are correct in their own half of the system, so the
 * translation is confined to this one file rather than being smeared across
 * components. Nothing outside `src/lib/api/` should ever see a `Wire*` type.
 */

import type { DailyTargetStatus } from "@/types/trading";

/** Provenance flag the backend stamps on every payload it derives from mocks. */
export type DataSource = "mock" | "database" | "broker" | "simulation";

/** Backend spelling of the status enum. Hyphenated on the frontend. */
export type WireDailyTargetStatus =
  | "not_started"
  | "in_progress"
  | "achieved"
  | "loss";

export interface WireAccountSummary {
  source: DataSource;
  currency: string;
  available_balance: number;
  used_margin: number;
  total_capital: number;
}

export interface WireMonthlyTarget {
  currency: string;
  monthly_target: number;
  daily_target: number;
  calculation_mode: string;
}

export interface WireDailyPerformance {
  source: DataSource;
  currency: string;
  date: string;
  realized_pnl: number;
  daily_target: number;
  remaining_to_target: number;
  progress_percentage: number;
  status: WireDailyTargetStatus;
  trades: number;
  wins: number;
  losses: number;
  win_rate: number;
}

export interface WireMonthlyPerformance {
  source: DataSource;
  currency: string;
  year: number;
  month: number;
  realized_pnl: number;
  monthly_target: number;
  remaining_to_target: number;
  progress_percentage: number;
  trades: number;
  wins: number;
  losses: number;
  active_sessions: number;
}

export interface WireCalendarDay {
  date: string;
  realized_pnl: number;
  trades: number;
  wins: number;
  losses: number;
  daily_target: number;
  status: WireDailyTargetStatus;
}

export interface WireCalendar {
  source: DataSource;
  currency: string;
  year: number;
  month: number;
  days: WireCalendarDay[];
}

export interface WireAgentStatus {
  state: string;
  mode: string;
  live_trading_enabled: boolean;
  paper_trading_enabled: boolean;
  broker_connected: boolean;
  market_data_connected: boolean;
}

/**
 * Maps the backend's underscored status onto the frontend's hyphenated union.
 *
 * Exhaustive by construction: a new backend member would fail to satisfy the
 * `Record` and break the build here rather than silently rendering a blank
 * calendar cell.
 */
const STATUS_BY_WIRE: Record<WireDailyTargetStatus, DailyTargetStatus> = {
  not_started: "not-started",
  in_progress: "in-progress",
  achieved: "achieved",
  loss: "loss",
};

export function toDailyTargetStatus(
  status: WireDailyTargetStatus,
): DailyTargetStatus {
  return STATUS_BY_WIRE[status];
}
