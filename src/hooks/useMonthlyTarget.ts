"use client";

import { useCallback, useSyncExternalStore } from "react";

import { DEFAULT_MONTHLY_TARGET } from "@/data/mockTradingData";

const STORAGE_KEY = "nifty-agent:monthly-target";

type Listener = () => void;

const listeners = new Set<Listener>();

function notify(): void {
  for (const listener of listeners) listener();
}

function subscribe(listener: Listener): () => void {
  listeners.add(listener);
  // Keep other tabs of the dashboard in sync.
  window.addEventListener("storage", listener);

  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", listener);
  };
}

function getSnapshot(): number {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw === null) return DEFAULT_MONTHLY_TARGET;

    const parsed = Number.parseFloat(raw);
    return Number.isFinite(parsed) && parsed > 0
      ? parsed
      : DEFAULT_MONTHLY_TARGET;
  } catch {
    // Private browsing or a blocked storage quota must not break the dashboard.
    return DEFAULT_MONTHLY_TARGET;
  }
}

function getServerSnapshot(): number {
  return DEFAULT_MONTHLY_TARGET;
}

export interface UseMonthlyTargetResult {
  monthlyTarget: number;
  /** Persists a new goal. Returns `false` for values that fail validation. */
  setMonthlyTarget: (next: number) => boolean;
}

/**
 * The user-defined monthly goal, persisted to localStorage.
 *
 * Backed by `useSyncExternalStore` so the server and the first client render
 * both emit `DEFAULT_MONTHLY_TARGET` — the stored value is adopted immediately
 * after hydration, with no markup mismatch and no state-setting effect.
 */
export function useMonthlyTarget(): UseMonthlyTargetResult {
  const monthlyTarget = useSyncExternalStore(
    subscribe,
    getSnapshot,
    getServerSnapshot,
  );

  const setMonthlyTarget = useCallback((next: number): boolean => {
    if (!Number.isFinite(next) || next <= 0) return false;

    try {
      window.localStorage.setItem(STORAGE_KEY, String(Math.round(next)));
    } catch {
      return false;
    }

    notify();
    return true;
  }, []);

  return { monthlyTarget, setMonthlyTarget };
}
