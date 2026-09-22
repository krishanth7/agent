/**
 * Trading-agent status.
 *
 * In Phase 2 the agent is permanently `disabled` and every capability flag is
 * false. The endpoint exists so the UI can assert that fact from the server
 * rather than hard-coding it — the day an agent does exist, nothing in the
 * frontend has to learn a new contract.
 */

import { apiGet, type RequestOptions } from "@/lib/api/client";
import type { WireAgentStatus } from "@/lib/api/types";

export interface AgentStatusResult {
  state: string;
  mode: string;
  liveTradingEnabled: boolean;
  paperTradingEnabled: boolean;
  brokerConnected: boolean;
  marketDataConnected: boolean;
}

export async function fetchAgentStatus(
  options?: RequestOptions,
): Promise<AgentStatusResult> {
  const wire = await apiGet<WireAgentStatus>("/agent/status", options);
  return {
    state: wire.state,
    mode: wire.mode,
    liveTradingEnabled: wire.live_trading_enabled,
    paperTradingEnabled: wire.paper_trading_enabled,
    brokerConnected: wire.broker_connected,
    marketDataConnected: wire.market_data_connected,
  };
}
