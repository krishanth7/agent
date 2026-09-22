"use client";

import { RotateCw, WifiOff } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * The non-success states a backend-connected card can be in.
 *
 * Centralised so "loading" and "unavailable" look the same everywhere. The
 * design rule these encode is a financial one: an unknown figure must read as
 * unknown. A dashboard that quietly falls back to a plausible number is worse
 * than one that admits it cannot reach the API.
 */

export interface CardSkeletonProps {
  /** Tailwind height class for the headline placeholder. */
  headline?: string;
  /** Number of smaller placeholder lines beneath the headline. */
  lines?: number;
  className?: string;
}

export function CardSkeleton({
  headline = "h-9",
  lines = 2,
  className,
}: CardSkeletonProps) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={cn("mt-5 w-full sm:mt-6", className)}
    >
      <span className="sr-only">Loading</span>
      <div
        aria-hidden="true"
        className={cn("w-2/5 animate-pulse rounded-md bg-surface-sunken", headline)}
      />
      <div aria-hidden="true" className="mt-3 space-y-2">
        {Array.from({ length: lines }, (_, index) => (
          <div
            key={index}
            className="h-3 animate-pulse rounded bg-surface-sunken"
            style={{ width: `${88 - index * 22}%` }}
          />
        ))}
      </div>
    </div>
  );
}

export interface CardErrorProps {
  /** What is missing, in the card's own words, e.g. "Balance unavailable". */
  title: string;
  /** The reason, taken from the API error. */
  message: string | null;
  /** True when the API could not be reached at all. */
  offline?: boolean;
  onRetry?: () => void;
  className?: string;
}

export function CardError({
  title,
  message,
  offline = false,
  onRetry,
  className,
}: CardErrorProps) {
  return (
    <div role="alert" className={cn("mt-5 sm:mt-6", className)}>
      <div className="flex items-center gap-2">
        {offline ? (
          <WifiOff aria-hidden="true" className="size-4 shrink-0 text-ink-muted" />
        ) : null}
        <p className="text-[15px] font-semibold tracking-[-0.01em] text-ink">
          {title}
        </p>
      </div>

      <p className="mt-2 max-w-[38ch] text-xs leading-relaxed text-ink-muted">
        {offline
          ? "The trading API is not responding. Start the backend, then retry."
          : (message ?? "This data could not be loaded.")}
      </p>

      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="focus-ring mt-3 inline-flex items-center gap-1.5 rounded-lg border border-hairline-strong px-2.5 py-1.5 text-[13px] font-medium text-ink-secondary transition-colors duration-150 hover:bg-surface-sunken hover:text-ink"
        >
          <RotateCw aria-hidden="true" className="size-3.5" />
          Retry
        </button>
      ) : null}
    </div>
  );
}
