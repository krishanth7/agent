"use client";

import { CircleCheck, CircleSlash, PlugZap, ShieldCheck } from "lucide-react";
import { useCallback, useState } from "react";

import { BentoCard, BentoCardHeader } from "@/components/ui/BentoCard";
import { CardError, CardSkeleton } from "@/components/ui/CardState";
import { Tooltip } from "@/components/ui/Tooltip";
import { useApiResource } from "@/hooks/useApiResource";
import {
  fetchBrokerStatus,
  testBrokerConnection,
  type BrokerStatusResult,
} from "@/lib/api/broker";
import { ApiError } from "@/lib/api/client";
import { cn } from "@/lib/utils";

/**
 * The four states this card distinguishes, in the order it checks them.
 *
 * Kept as a flat union rather than derived ad hoc in JSX, because the ordering
 * is the substance: "not configured" has to win over "not connected", or an
 * operator who has set nothing up is told their connection dropped.
 */
type ConnectionState = "disabled" | "unconfigured" | "idle" | "connected";

interface StateMeta {
  label: string;
  detail: string;
  text: string;
  chip: string;
}

const STATE_META: Record<ConnectionState, StateMeta> = {
  disabled: {
    label: "Disabled",
    detail:
      "The Angel One integration is switched off. Nothing has been sent to a broker.",
    text: "text-ink-muted",
    chip: "bg-surface-sunken",
  },
  unconfigured: {
    label: "Not configured",
    detail:
      "Credentials are incomplete. Set them in the backend environment, then enable the integration.",
    text: "text-ink-muted",
    chip: "bg-surface-sunken",
  },
  idle: {
    label: "Not connected",
    detail:
      "Credentials are present but no session has been established. Run a connection test to verify them.",
    text: "text-caution",
    chip: "bg-caution-soft",
  },
  connected: {
    label: "Connected",
    detail: "A read-only session is live.",
    text: "text-positive",
    chip: "bg-positive-soft",
  },
};

function toState(status: BrokerStatusResult): ConnectionState {
  if (!status.enabled) return "disabled";
  if (!status.configured) return "unconfigured";
  return status.connected ? "connected" : "idle";
}

/** Local outcome of the on-demand test. Distinct from the polled status. */
type TestOutcome =
  | { kind: "idle" }
  | { kind: "running" }
  | { kind: "ok"; account: string; exchanges: string[] }
  | { kind: "failed"; message: string };

export interface BrokerStatusCardProps {
  order?: number;
  className?: string;
}

/**
 * Broker connection state, and a button to verify it.
 *
 * WHY THIS CARD EXISTS AT ALL
 * ---------------------------
 * Every other card on this dashboard shows mock figures. Once a broker *can* be
 * connected, an operator needs somewhere to see whether one actually is —
 * otherwise "is this number real?" is answered by guesswork. The card states
 * the three conditions separately because they have different remedies, and it
 * states the read-only guarantee outright rather than leaving it to be inferred
 * from the absence of a trade button.
 *
 * THE TEST IS DELIBERATE, NOT AUTOMATIC
 * -------------------------------------
 * The status above it is polled on mount and is free — it touches no network
 * beyond this app's own backend. The connection test authenticates against
 * Angel One, so it runs only when a user asks for it. A card that tested on
 * mount would log in to a broker every time someone opened a browser tab.
 */
export function BrokerStatusCard({ order, className }: BrokerStatusCardProps) {
  const load = useCallback(
    (signal: AbortSignal) => fetchBrokerStatus({ signal }),
    [],
  );
  const status = useApiResource(load, []);

  const [outcome, setOutcome] = useState<TestOutcome>({ kind: "idle" });

  const runTest = useCallback(async () => {
    setOutcome({ kind: "running" });
    try {
      const result = await testBrokerConnection();
      setOutcome({
        kind: "ok",
        account: result.clientCode,
        exchanges: result.exchanges,
      });
      // The status above is now stale: a session exists that did not a moment
      // ago. Re-reading it is cheaper and more honest than patching the cached
      // value locally, which would make the card's two halves disagree if the
      // backend saw it differently.
      status.reload();
    } catch (error) {
      setOutcome({
        kind: "failed",
        message:
          error instanceof ApiError
            ? error.message
            : "The connection test could not be completed.",
      });
    }
  }, [status]);

  const header = (
    <BentoCardHeader title="Broker" description="Angel One SmartAPI" />
  );

  if (status.status === "loading") {
    return (
      <BentoCard
        variant="glass"
        order={order}
        className={className}
        ariaLabel="Broker connection"
      >
        {header}
        <CardSkeleton headline="h-7" lines={2} />
      </BentoCard>
    );
  }

  if (status.status === "error" || status.data === null) {
    return (
      <BentoCard
        variant="glass"
        order={order}
        className={className}
        ariaLabel="Broker connection"
      >
        {header}
        <CardError
          title="Broker status unavailable"
          message={status.error}
          offline={status.offline}
          onRetry={status.reload}
        />
      </BentoCard>
    );
  }

  const state = toState(status.data);
  const meta = STATE_META[state];
  const canTest = state === "idle" || state === "connected";

  return (
    <BentoCard
      variant="glass"
      order={order}
      className={className}
      ariaLabel="Broker connection"
    >
      {header}

      <div className="mt-5">
        <span
          className={cn(
            "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[13px] font-medium",
            meta.text,
            meta.chip,
          )}
        >
          {state === "connected" ? (
            <CircleCheck aria-hidden="true" className="size-3.5 shrink-0" />
          ) : (
            <CircleSlash aria-hidden="true" className="size-3.5 shrink-0" />
          )}
          <span>{meta.label}</span>
        </span>

        <p className="mt-3 max-w-[40ch] text-xs leading-relaxed text-ink-muted">
          {meta.detail}
        </p>
      </div>

      {status.data.clientCode ? (
        <dl className="mt-4 grid grid-cols-2 gap-2">
          <div className="min-w-0 rounded-inner bg-surface-sunken px-3 py-2.5">
            <dt className="text-[10.5px] text-ink-muted">Account</dt>
            <dd className="numeric mt-1 truncate text-[13px] text-ink">
              {/*
                Masked by the backend before it was sent. The tooltip says so,
                because a masked identifier with no explanation reads as a bug.
              */}
              <Tooltip label="Masked by the server. The full client code is never sent to the browser.">
                <span tabIndex={0} className="focus-ring">
                  {status.data.clientCode}
                </span>
              </Tooltip>
            </dd>
          </div>
          <div className="min-w-0 rounded-inner bg-surface-sunken px-3 py-2.5">
            <dt className="text-[10.5px] text-ink-muted">Session until</dt>
            <dd className="numeric mt-1 truncate text-[13px] text-ink">
              {status.data.sessionExpiresAt
                ? status.data.sessionExpiresAt.toLocaleTimeString([], {
                    hour: "2-digit",
                    minute: "2-digit",
                  })
                : "—"}
            </dd>
          </div>
        </dl>
      ) : null}

      <div className="mt-auto pt-5">
        {canTest ? (
          <button
            type="button"
            onClick={() => void runTest()}
            disabled={outcome.kind === "running"}
            className={cn(
              "focus-ring inline-flex items-center gap-1.5 rounded-lg border border-hairline-strong",
              "px-2.5 py-1.5 text-[13px] font-medium text-ink-secondary",
              "transition-colors duration-150 hover:bg-surface-sunken hover:text-ink",
              "disabled:cursor-not-allowed disabled:opacity-60",
            )}
          >
            <PlugZap aria-hidden="true" className="size-3.5" />
            {outcome.kind === "running" ? "Testing…" : "Test connection"}
          </button>
        ) : null}

        {/*
          `aria-live` so the outcome is announced rather than only drawn. The
          button gives no other feedback once it returns to its resting label.
        */}
        <div aria-live="polite" className="empty:hidden">
          {outcome.kind === "ok" ? (
            <p className="mt-2.5 text-xs leading-relaxed text-positive">
              Reached {outcome.account}
              {outcome.exchanges.length > 0
                ? ` · ${outcome.exchanges.join(", ")}`
                : ""}
            </p>
          ) : null}
          {outcome.kind === "failed" ? (
            <p className="mt-2.5 max-w-[40ch] text-xs leading-relaxed text-negative">
              {outcome.message}
            </p>
          ) : null}
        </div>

        {/*
          Stated, not implied. `order_placement_available` is `Literal[False]`
          on the server and there is no order route to call — this line is the
          user-facing half of that guarantee.
        */}
        <p className="mt-4 flex items-start gap-1.5 text-[11px] leading-relaxed text-ink-muted">
          <ShieldCheck
            aria-hidden="true"
            className="mt-px size-3.5 shrink-0 text-positive"
          />
          <span>
            Read-only access. This application cannot place, modify or cancel an
            order.
          </span>
        </p>
      </div>
    </BentoCard>
  );
}
