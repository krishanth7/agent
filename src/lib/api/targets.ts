/**
 * The monthly profit target and the daily target derived from it.
 *
 * The daily figure is returned by the backend rather than recomputed here: the
 * rounding rule is a business rule, and it must have exactly one implementation
 * so the calendar, the cards and the API can never disagree about what
 * ₹10,000/month means.
 */

import { apiGet, apiPut, type RequestOptions } from "@/lib/api/client";
import type { WireMonthlyTarget } from "@/lib/api/types";

export interface MonthlyTargetResult {
  monthlyTarget: number;
  dailyTarget: number;
  calculationMode: string;
  currency: string;
}

/**
 * How many days the backend divided by, per `calculation_mode`.
 *
 * This exists purely so the "across N days" caption stays truthful. When the
 * denominator becomes remaining NSE sessions the backend will report a new
 * mode, and an unrecognised mode yields `null` — the caption then omits the
 * count rather than asserting a number that is no longer correct.
 */
const DAYS_BY_CALCULATION_MODE: Readonly<Record<string, number>> = {
  calendar_days_30: 30,
};

export function daysForCalculationMode(mode: string | null): number | null {
  if (mode === null) return null;
  return DAYS_BY_CALCULATION_MODE[mode] ?? null;
}

function toResult(wire: WireMonthlyTarget): MonthlyTargetResult {
  return {
    monthlyTarget: wire.monthly_target,
    dailyTarget: wire.daily_target,
    calculationMode: wire.calculation_mode,
    currency: wire.currency,
  };
}

export async function fetchMonthlyTarget(
  options?: RequestOptions,
): Promise<MonthlyTargetResult> {
  return toResult(await apiGet<WireMonthlyTarget>("/targets/monthly", options));
}

/**
 * Persists a new monthly target and returns the recalculated pair.
 *
 * Rejects with an `ApiError` carrying code `VALIDATION_ERROR` when the amount
 * is outside the accepted range, which the edit card surfaces inline.
 */
export async function updateMonthlyTarget(
  amount: number,
  options?: RequestOptions,
): Promise<MonthlyTargetResult> {
  const wire = await apiPut<WireMonthlyTarget>(
    "/targets/monthly",
    { monthly_target: amount },
    options,
  );
  return toResult(wire);
}
