/** Account funding, as reported by the backend. */

import { apiGet, type RequestOptions } from "@/lib/api/client";
import type { DataSource, WireAccountSummary } from "@/lib/api/types";
import type { AccountSummary } from "@/types/trading";

/** The frontend's `AccountSummary` plus the provenance flag the UI surfaces. */
export interface AccountSummaryResult extends AccountSummary {
  source: DataSource;
  currency: string;
}

export async function fetchAccountSummary(
  options?: RequestOptions,
): Promise<AccountSummaryResult> {
  const wire = await apiGet<WireAccountSummary>("/account/summary", options);
  return {
    availableBalance: wire.available_balance,
    usedMargin: wire.used_margin,
    totalCapital: wire.total_capital,
    source: wire.source,
    currency: wire.currency,
  };
}
