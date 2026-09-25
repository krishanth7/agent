/**
 * Broker connection state.
 *
 * Both endpoints are reads. There is no function here that places, modifies or
 * cancels an order, because the backend exposes no route that would accept one
 * — see `backend/app/api/v1/broker.py`.
 *
 * `testConnection` is a `GET` despite authenticating, which looks wrong until
 * you know the backend caches the session: repeated calls do not mean repeated
 * logins. The reasoning is recorded on the route itself.
 */

import { apiGet, type RequestOptions } from "@/lib/api/client";
import type {
  WireBrokerConnectionTest,
  WireBrokerStatus,
} from "@/lib/api/types";

export interface BrokerStatusResult {
  broker: string;
  /** The master switch. Off means nothing has been attempted. */
  enabled: boolean;
  /** A complete credential set is present *and* the switch is on. */
  configured: boolean;
  /** A session exists and has not lapsed. */
  connected: boolean;
  /** Already masked by the backend, e.g. `******01`. `null` when unconfigured. */
  clientCode: string | null;
  /** `null` when there is no live session. Never a past timestamp. */
  sessionExpiresAt: Date | null;
  liveTradingEnabled: boolean;
  paperTradingEnabled: boolean;
  orderPlacementAvailable: false;
}

export interface BrokerConnectionTestResult {
  broker: string;
  clientCode: string;
  clientName: string | null;
  exchanges: string[];
  sessionExpiresAt: Date;
  checkedAt: Date;
}

export async function fetchBrokerStatus(
  options?: RequestOptions,
): Promise<BrokerStatusResult> {
  const wire = await apiGet<WireBrokerStatus>("/broker/status", options);
  return {
    broker: wire.broker,
    enabled: wire.enabled,
    configured: wire.configured,
    connected: wire.connected,
    clientCode: wire.client_code,
    sessionExpiresAt: wire.session_expires_at
      ? new Date(wire.session_expires_at)
      : null,
    liveTradingEnabled: wire.live_trading_enabled,
    paperTradingEnabled: wire.paper_trading_enabled,
    // Not copied from the payload. The backend types this `Literal[False]`, and
    // reading it through would turn a server-side guarantee into a value this
    // component renders on trust.
    orderPlacementAvailable: false,
  };
}

/**
 * Authenticate against the broker and read the account profile back.
 *
 * Rejects with an `ApiError` on failure rather than resolving with a "not
 * connected" result — the backend answers 409 for "not configured" and 502 for
 * "credentials rejected", and collapsing those into a falsy field would discard
 * the only thing that tells an operator which one to fix.
 */
export async function testBrokerConnection(
  options?: RequestOptions,
): Promise<BrokerConnectionTestResult> {
  const wire = await apiGet<WireBrokerConnectionTest>(
    "/broker/connection-test",
    options,
  );
  return {
    broker: wire.broker,
    clientCode: wire.client_code,
    clientName: wire.client_name,
    exchanges: wire.exchanges,
    sessionExpiresAt: new Date(wire.session_expires_at),
    checkedAt: new Date(wire.checked_at),
  };
}
