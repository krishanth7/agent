"use client";

import { motion } from "motion/react";

import { clampRatio } from "@/lib/targetCalculations";
import { cn } from "@/lib/utils";

type ProgressTone = "positive" | "neutral" | "caution" | "negative";

const TONE_STYLES: Record<ProgressTone, string> = {
  positive: "bg-positive",
  neutral: "bg-ink-secondary",
  caution: "bg-caution",
  negative: "bg-negative",
};

export interface ProgressBarProps {
  /** Completion ratio. May exceed 1 — the bar clamps, the caller does not. */
  ratio: number;
  tone?: ProgressTone;
  size?: "sm" | "md";
  /** Accessible name, e.g. "Monthly target progress". */
  label: string;
  className?: string;
}

export function ProgressBar({
  ratio,
  tone = "positive",
  size = "md",
  label,
  className,
}: ProgressBarProps) {
  const fill = clampRatio(ratio);
  const percent = Math.round(fill * 100);

  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={percent}
      aria-valuetext={`${percent}% of target`}
      className={cn(
        "w-full overflow-hidden rounded-full bg-track",
        size === "sm" ? "h-1" : "h-1.5",
        className,
      )}
    >
      <motion.div
        initial={{ width: 0 }}
        animate={{ width: `${fill * 100}%` }}
        transition={{ duration: 0.45, ease: [0.22, 0.61, 0.36, 1] }}
        className={cn("h-full rounded-full", TONE_STYLES[tone])}
      />
    </div>
  );
}
