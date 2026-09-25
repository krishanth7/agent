"use client";

import { useEffect, useState } from "react";

import { getMarketSnapshot, type MarketSnapshot } from "@/lib/market";

/**
 * How often the snapshot is recomputed.
 *
 * Every boundary in the timetable falls on a whole minute, so a 15-second tick
 * bounds the error at a quarter of a minute while costing four cheap
 * recomputations a minute. A one-second tick would re-render the whole header
 * sixty times a minute to change nothing.
 */
const TICK_MS = 15_000;

/**
 * The live NSE market state, or `null` before the first client tick.
 *
 * WHY IT STARTS AS `null`
 * -----------------------
 * There is no correct answer on the server. Rendering `Date.now()` during SSR
 * stamps the server's instant into the HTML, React then renders a different
 * instant on the client, and the result is a hydration mismatch — the exact
 * class of bug this dashboard already avoids elsewhere by refusing to call
 * `new Date()` during render. Returning `null` for one paint and filling in
 * after mount is honest: the client genuinely does not know the time yet.
 *
 * Callers should render a neutral placeholder for `null`, not "closed".
 * "Closed" is a claim; absence of a clock is not.
 */
export function useMarketClock(): MarketSnapshot | null {
  const [snapshot, setSnapshot] = useState<MarketSnapshot | null>(null);

  useEffect(() => {
    const update = () => setSnapshot(getMarketSnapshot(new Date()));

    update();
    const timer = window.setInterval(update, TICK_MS);

    // A laptop that was asleep across the open wakes up with a stale snapshot
    // and no interval tick to correct it until the next one fires. Recomputing
    // on visibility change closes that window immediately.
    const onVisible = () => {
      if (document.visibilityState === "visible") update();
    };
    document.addEventListener("visibilitychange", onVisible);

    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, []);

  return snapshot;
}
