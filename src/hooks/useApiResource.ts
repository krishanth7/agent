"use client";

import { useCallback, useEffect, useState } from "react";

import { ApiError } from "@/lib/api/client";

/**
 * A single remote value with its loading and failure states made explicit.
 *
 * Every card that reads from the backend renders one of these four states, so
 * "we don't know yet" can never be silently rendered as a number. That is the
 * whole point: a stale or absent balance must look absent, not like ₹25,000.
 */
export type ResourceStatus = "loading" | "ready" | "error";

export interface Resource<T> {
  status: ResourceStatus;
  /** Populated only when `status === "ready"`. */
  data: T | null;
  /** Human-readable failure reason, safe to show in the UI. */
  error: string | null;
  /** True when the backend could not be reached at all. */
  offline: boolean;
  reload: () => void;
}

/** A finished request, tagged with the request it answered. */
type Settled<T> =
  | { key: string; status: "ready"; data: T }
  | { key: string; status: "error"; error: string; offline: boolean };

function describe(error: unknown): { message: string; offline: boolean } {
  if (error instanceof ApiError) {
    return { message: error.message, offline: error.isOffline };
  }
  return { message: "Something went wrong loading this data.", offline: false };
}

/**
 * Runs `load` on mount and whenever `deps` change, aborting any in-flight
 * request first.
 *
 * `load` must be a stable reference (wrap it in `useCallback`).
 *
 * The loading state is *derived*, not stored: a request is identified by a key
 * built from `deps`, and anything whose key doesn't match the current one is
 * by definition not yet answered. That keeps every `setState` inside an async
 * callback — no synchronous state updates from an effect body, and no window
 * in which a previous month's data is shown under the current month's heading.
 */
export function useApiResource<T>(
  load: (signal: AbortSignal) => Promise<T>,
  deps: readonly unknown[],
): Resource<T> {
  const [nonce, setNonce] = useState(0);
  const [settled, setSettled] = useState<Settled<T> | null>(null);

  // A plain string, recomputed each render and compared by value — so it is
  // stable without memoisation. `nonce` participates so that `reload()`
  // invalidates the current answer and forces a fresh request.
  const key = `${JSON.stringify(deps)}:${nonce}`;

  useEffect(() => {
    const controller = new AbortController();

    void load(controller.signal)
      .then((value) => {
        if (controller.signal.aborted) return;
        setSettled({ key, status: "ready", data: value });
      })
      .catch((cause: unknown) => {
        // An aborted request was superseded or unmounted; its result is moot.
        if (controller.signal.aborted) return;
        const { message, offline } = describe(cause);
        setSettled({ key, status: "error", error: message, offline });
      });

    return () => controller.abort();
  }, [key, load]);

  const reload = useCallback(() => setNonce((value) => value + 1), []);

  // An answer to a superseded request is not an answer to this one.
  const current = settled?.key === key ? settled : null;

  if (current === null) {
    return { status: "loading", data: null, error: null, offline: false, reload };
  }

  if (current.status === "error") {
    return {
      status: "error",
      data: null,
      error: current.error,
      offline: current.offline,
      reload,
    };
  }

  return {
    status: "ready",
    data: current.data,
    error: null,
    offline: false,
    reload,
  };
}
