"use client";

import { Bot, ChevronDown } from "lucide-react";

import {
  Popover,
  PopoverPanel,
  PopoverTrigger,
} from "@/components/ui/Popover";
import { getHolidayByKey } from "@/lib/holidays";
import {
  AGENT_WINDOW_LABEL,
  SCHEDULE,
  SESSION_HOURS_LABEL,
  formatExchangeTime,
  type MarketPhase,
  type MarketSnapshot,
} from "@/lib/market";
import { cn } from "@/lib/utils";

const PHASE_META: Record<
  MarketPhase,
  { label: string; dot: string; detail: string }
> = {
  open: {
    label: "Market Open",
    dot: "bg-positive",
    detail: "Regular session in progress.",
  },
  "pre-open": {
    label: "Pre-Open",
    dot: "bg-caution",
    detail: "Call auction running. No continuous trading yet.",
  },
  "post-close": {
    label: "Post-Close",
    dot: "bg-caution",
    detail: "Session closed. Trade modification open until 16:15.",
  },
  closed: {
    label: "Market Closed",
    dot: "bg-idle",
    detail: "Outside exchange hours.",
  },
};

export interface MarketStatusPillProps {
  /** `null` before the first client tick — see `useMarketClock`. */
  snapshot: MarketSnapshot | null;
}

/**
 * Live market state, and the exchange timetable behind it.
 *
 * The pill reads the clock rather than a constant, so during a session it says
 * so. The session-hours label is a button: the summary on the pill is the one
 * fact most people want, and the full timetable — pre-open phases, the
 * post-close cutoffs, and the narrower window the agent is allowed to act in —
 * is one click away rather than crowding the header.
 */
export function MarketStatusPill({ snapshot }: MarketStatusPillProps) {
  const meta = snapshot ? PHASE_META[snapshot.phase] : null;
  const holiday = snapshot ? getHolidayByKey(snapshot.dateKey) : null;

  const reason =
    snapshot && !snapshot.isTradingDay
      ? snapshot.nonTradingReason === "holiday"
        ? (holiday?.description ?? "Exchange holiday")
        : "Weekend — the exchange is closed."
      : null;

  return (
    <div className="flex items-center gap-2.5 rounded-full border border-hairline bg-canvas-raised py-1.5 pl-3 pr-1.5">
      <span
        aria-hidden="true"
        className={cn(
          "size-1.5 shrink-0 rounded-full",
          meta ? meta.dot : "bg-idle/40",
        )}
      />
      <span
        className="text-[13px] font-medium text-ink-secondary"
        aria-live="polite"
      >
        {/*
          A neutral dash until the clock exists. Defaulting to "Market Closed"
          would be a claim the client cannot yet support, and would flicker to
          "Market Open" a frame later during a live session.
        */}
        {meta ? meta.label : "—"}
      </span>
      <span aria-hidden="true" className="h-3 w-px shrink-0 bg-hairline-strong" />

      <Popover>
        <PopoverTrigger
          className={cn(
            "focus-ring group flex items-center gap-1 rounded-full px-1.5 py-0.5",
            "transition-colors duration-150 hover:bg-surface-sunken",
          )}
          aria-label="Exchange session timings"
        >
          <span className="numeric whitespace-nowrap text-[11px] text-ink-muted sm:text-[12px]">
            {SESSION_HOURS_LABEL}
          </span>
          <ChevronDown
            aria-hidden="true"
            className="size-3 shrink-0 text-ink-muted transition-transform duration-200 group-data-[state=open]:rotate-180"
          />
        </PopoverTrigger>

        <PopoverPanel title="Exchange session timings">
          <SessionSchedule
            phase={snapshot?.phase ?? null}
            minutes={snapshot?.minutes ?? null}
            reason={reason}
            agentWindowOpen={snapshot?.agentWindowOpen ?? false}
          />
        </PopoverPanel>
      </Popover>
    </div>
  );
}

interface ScheduleRow {
  label: string;
  from: number;
  to: number | null;
  note?: string;
}

const PRE_OPEN_ROWS: readonly ScheduleRow[] = [
  {
    label: "Order entry",
    from: SCHEDULE.preOpenStart,
    to: SCHEDULE.preOpenEntryEnd,
    note: "Closure randomised in the last 2 minutes",
  },
  {
    label: "Matching & confirmation",
    from: SCHEDULE.preOpenEntryEnd,
    to: SCHEDULE.preOpenMatchEnd,
  },
  { label: "Buffer", from: SCHEDULE.preOpenMatchEnd, to: SCHEDULE.open },
];

const POST_CLOSE_ROWS: readonly ScheduleRow[] = [
  {
    label: "Position limit / collateral setup cutoff",
    from: SCHEDULE.adminCutoff,
    to: null,
  },
  {
    label: "Trade modification / exercise end",
    from: SCHEDULE.adminCutoff,
    to: null,
  },
];

interface SessionScheduleProps {
  phase: MarketPhase | null;
  minutes: number | null;
  reason: string | null;
  agentWindowOpen: boolean;
}

function SessionSchedule({
  phase,
  minutes,
  reason,
  agentWindowOpen,
}: SessionScheduleProps) {
  const meta = phase ? PHASE_META[phase] : null;

  return (
    <div className="pr-6">
      <h3 className="eyebrow text-ink-secondary">Exchange Timings</h3>
      <p className="mt-1 text-[13px] leading-snug text-ink">
        {meta ? meta.detail : "Reading the clock…"}
      </p>
      {reason ? (
        <p className="mt-1 text-[12px] leading-snug text-ink-muted">{reason}</p>
      ) : null}
      {minutes !== null ? (
        <p className="numeric mt-1 text-[11px] text-ink-muted">
          {formatExchangeTime(minutes)} IST
        </p>
      ) : null}

      <Section title="A · Pre-open session">
        {PRE_OPEN_ROWS.map((row) => (
          <Row key={row.label} row={row} active={phase === "pre-open"} />
        ))}
      </Section>

      <Section title="B · Regular trading session">
        <Row
          row={{ label: "Normal market", from: SCHEDULE.open, to: SCHEDULE.close }}
          active={phase === "open"}
        />
      </Section>

      <Section title="C · Post-close">
        {POST_CLOSE_ROWS.map((row) => (
          <Row key={row.label} row={row} active={phase === "post-close"} />
        ))}
      </Section>

      {/*
        Given its own block rather than a fourth row, because it is not an
        exchange timing at all — it is a policy this system imposes on itself,
        and flattening it into the circular's schedule would misattribute it.
      */}
      <div
        className={cn(
          "mt-3 rounded-inner border p-2.5",
          agentWindowOpen
            ? "border-positive/30 bg-positive-soft"
            : "border-hairline bg-surface-sunken",
        )}
      >
        <div className="flex items-center gap-1.5">
          <Bot
            aria-hidden="true"
            className={cn(
              "size-3.5 shrink-0",
              agentWindowOpen ? "text-positive" : "text-ink-muted",
            )}
          />
          <span className="eyebrow text-ink-secondary">Agent execution window</span>
        </div>
        <p className="numeric mt-1.5 text-[13px] font-semibold text-ink">
          {AGENT_WINDOW_LABEL}
        </p>
        <p className="mt-1 text-[11.5px] leading-snug text-ink-muted">
          The agent stops 30 minutes before the exchange does. The closing period
          is the least liquid part of the session, and no automated system should
          be opening positions into it unwatched.
        </p>
      </div>

      <p className="mt-3 border-t border-hairline pt-2 text-[10.5px] leading-snug text-ink-muted">
        Equity and F&amp;O segments, Monday to Friday, excluding exchange
        holidays. No order can be placed from this dashboard in any phase.
      </p>
    </div>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mt-3">
      <h4 className="eyebrow text-ink-muted">{title}</h4>
      <dl className="mt-1.5 space-y-1">{children}</dl>
    </section>
  );
}

function Row({ row, active }: { row: ScheduleRow; active: boolean }) {
  return (
    <div
      className={cn(
        "flex items-baseline justify-between gap-3 rounded-md px-1.5 py-1 -mx-1.5",
        active && "bg-surface-sunken",
      )}
    >
      <div className="min-w-0">
        <dt
          className={cn(
            "text-[12.5px] leading-tight",
            active ? "font-medium text-ink" : "text-ink-secondary",
          )}
        >
          {row.label}
        </dt>
        {row.note ? (
          <p className="mt-0.5 text-[10.5px] leading-tight text-ink-muted">
            {row.note}
          </p>
        ) : null}
      </div>
      <dd className="numeric shrink-0 text-[12px] tabular-nums text-ink-secondary">
        {row.to === null
          ? formatExchangeTime(row.from)
          : `${formatExchangeTime(row.from)} – ${formatExchangeTime(row.to)}`}
      </dd>
    </div>
  );
}
