"use client";

import { useCallback, useState } from "react";

import { ApiError } from "@/lib/api/client";
import {
  fetchMonthlyTarget,
  updateMonthlyTarget,
  type MonthlyTargetResult,
} from "@/lib/api/targets";
import { useApiResource, type ResourceStatus } from "@/hooks/useApiResource";

export interface UseMonthlyTargetResult {
  /** `null` until the backend answers, so callers cannot render a guess. */
  monthlyTarget: number | null;
  /** Derived server-side; the rounding rule has exactly one implementation. */
  dailyTarget: number | null;
  /** How the backend split the month, e.g. `calendar_days_30`. */
  calculationMode: string | null;
  status: ResourceStatus;
  error: string | null;
  offline: boolean;
  /** Resolves to an error message to display, or `null` on success. */
  save: (next: number) => Promise<string | null>;
  /**
   * Bumped after every successful save. Downstream resources depend on it so
   * the calendar and the progress cards re-derive against the new target
   * without any of them knowing that a target exists to be saved.
   */
  revision: number;
  reload: () => void;
}

/**
 * The monthly goal, owned by the backend.
 *
 * Phase 1 kept this in localStorage. It now lives behind `/targets/monthly`:
 * two competing stores would eventually disagree, and the daily-target rounding
 * rule belongs to the domain layer, not to the browser.
 */
export function useMonthlyTarget(): UseMonthlyTargetResult {
  const [revision, setRevision] = useState(0);
  const [saved, setSaved] = useState<MonthlyTargetResult | null>(null);

  const load = useCallback(
    (signal: AbortSignal) => fetchMonthlyTarget({ signal }),
    [],
  );
  const resource = useApiResource(load, []);

  // A completed save is newer than whatever the initial GET returned.
  const current = saved ?? resource.data;

  const save = useCallback(async (next: number): Promise<string | null> => {
    try {
      const result = await updateMonthlyTarget(next);
      setSaved(result);
      setRevision((value) => value + 1);
      return null;
    } catch (cause) {
      if (cause instanceof ApiError) return cause.message;
      return "That target could not be saved.";
    }
  }, []);

  return {
    monthlyTarget: current?.monthlyTarget ?? null,
    dailyTarget: current?.dailyTarget ?? null,
    calculationMode: current?.calculationMode ?? null,
    status: saved ? "ready" : resource.status,
    error: resource.error,
    offline: resource.offline,
    save,
    revision,
    reload: resource.reload,
  };
}
