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

/**
 * Provenance flag the backend stamps on every payload.
 *
 * Mirrors `app.domain.enums.DataSource` in full, including the members the UI
 * does not yet render. An incomplete union here would be worse than useless:
 * TypeScript would narrow an unlisted value to `never` at a `switch`, so the
 * one source most important to distinguish — a development seed row arriving
 * where a broker reading was expected — would be the one the compiler assumed
 * could not happen.
 */
export type DataSource =
  | "mock"
  | "database"
  | "broker"
  | "simulation"
  | "development_seed"
  | "nse";

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

/**
 * Broker connection state.
 *
 * Note what is absent and must stay absent: no access token, refresh token,
 * feed token, API key, PIN or TOTP seed. `client_code` arrives already masked
 * by the backend — the frontend must never be given the full value to mask
 * itself, because anything the browser can render, the browser received.
 */
export interface WireBrokerStatus {
  broker: string;
  enabled: boolean;
  configured: boolean;
  connected: boolean;
  client_code: string | null;
  session_expires_at: string | null;
  live_trading_enabled: boolean;
  paper_trading_enabled: boolean;
  order_placement_available: false;
}

export interface WireBrokerConnectionTest {
  broker: string;
  connected: true;
  client_code: string;
  client_name: string | null;
  exchanges: string[];
  session_expires_at: string;
  checked_at: string;
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
