/** Realized trading performance: a day, a month, and the calendar grid. */

import { apiGet, type RequestOptions } from "@/lib/api/client";
import {
  toDailyTargetStatus,
  type DataSource,
  type WireCalendar,
  type WireDailyPerformance,
  type WireMonthlyPerformance,
} from "@/lib/api/types";
import type {
  DailyTargetStatus,
  DailyTradingPerformance,
  PerformanceTotals,
} from "@/types/trading";

/** A session plus the target-relative figures the backend already computed. */
export interface DailyPerformanceResult extends DailyTradingPerformance {
  dailyTarget: number;
  remainingToTarget: number;
  progressPercentage: number;
  status: DailyTargetStatus;
  winRate: number;
  source: DataSource;
}

export interface MonthlyPerformanceResult {
  year: number;
  month: number;
  monthlyTarget: number;
  remainingToTarget: number;
  progressPercentage: number;
  totals: PerformanceTotals;
  source: DataSource;
}

/** One calendar cell: the session plus its status under the current target. */
export interface CalendarDayResult extends DailyTradingPerformance {
  dailyTarget: number;
  status: DailyTargetStatus;
}

export interface CalendarResult {
  year: number;
  month: number;
  days: CalendarDayResult[];
  source: DataSource;
}

function toDaily(wire: WireDailyPerformance): DailyPerformanceResult {
  return {
    date: wire.date,
    realizedPnl: wire.realized_pnl,
    trades: wire.trades,
    wins: wire.wins,
    losses: wire.losses,
    dailyTarget: wire.daily_target,
    remainingToTarget: wire.remaining_to_target,
    progressPercentage: wire.progress_percentage,
    status: toDailyTargetStatus(wire.status),
    winRate: wire.win_rate,
    source: wire.source,
  };
}

export async function fetchTodayPerformance(
  options?: RequestOptions,
): Promise<DailyPerformanceResult> {
  return toDaily(
    await apiGet<WireDailyPerformance>("/performance/today", options),
  );
}

/**
 * Fetches one dated session.
 *
 * A date with no recorded session is a 404 by design — an absent record is a
 * miss, not a zero — so callers must decide whether that means "no trading
 * that day" or "data unavailable".
 */
export async function fetchPerformanceForDate(
  dateKey: string,
  options?: RequestOptions,
): Promise<DailyPerformanceResult> {
  return toDaily(
    await apiGet<WireDailyPerformance>(`/performance/${dateKey}`, options),
  );
}

export async function fetchMonthlyPerformance(
  period?: { year: number; month: number },
  options?: RequestOptions,
): Promise<MonthlyPerformanceResult> {
  const wire = await apiGet<WireMonthlyPerformance>(
    "/performance/monthly",
    options,
    period ? { year: period.year, month: period.month } : undefined,
  );

  return {
    year: wire.year,
    month: wire.month,
    monthlyTarget: wire.monthly_target,
    remainingToTarget: wire.remaining_to_target,
    progressPercentage: wire.progress_percentage,
    totals: {
      realizedPnl: wire.realized_pnl,
      trades: wire.trades,
      wins: wire.wins,
      losses: wire.losses,
      activeSessions: wire.active_sessions,
    },
    source: wire.source,
  };
}

export async function fetchCalendar(
  year: number,
  month: number,
  options?: RequestOptions,
): Promise<CalendarResult> {
  const wire = await apiGet<WireCalendar>("/performance/calendar", options, {
    year,
    month,
  });

  return {
    year: wire.year,
    month: wire.month,
    source: wire.source,
    days: wire.days.map((day) => ({
      date: day.date,
      realizedPnl: day.realized_pnl,
      trades: day.trades,
      wins: day.wins,
      losses: day.losses,
      dailyTarget: day.daily_target,
      status: toDailyTargetStatus(day.status),
    })),
  };
}
