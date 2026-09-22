import {
  Circle,
  CircleCheck,
  CircleDashed,
  CircleMinus,
  type LucideIcon,
} from "lucide-react";

import { cn } from "@/lib/utils";
import type { DailyTargetStatus } from "@/types/trading";

interface StatusMeta {
  label: string;
  Icon: LucideIcon;
  /** Text + icon colour. */
  text: string;
  /** Soft chip background. */
  chip: string;
  /** Calendar marker fill. */
  dot: string;
}

/**
 * Every status carries an icon and a label alongside its colour, so the state
 * is never communicated by hue alone.
 */
export const STATUS_META: Record<DailyTargetStatus, StatusMeta> = {
  achieved: {
    label: "Target achieved",
    Icon: CircleCheck,
    text: "text-positive",
    chip: "bg-positive-soft",
    dot: "bg-positive",
  },
  "in-progress": {
    label: "Below target",
    Icon: CircleDashed,
    text: "text-caution",
    chip: "bg-caution-soft",
    dot: "bg-caution",
  },
  loss: {
    label: "Loss",
    Icon: CircleMinus,
    text: "text-negative",
    chip: "bg-negative-soft",
    dot: "bg-negative",
  },
  "not-started": {
    label: "No trades",
    Icon: Circle,
    text: "text-ink-muted",
    chip: "bg-surface-sunken",
    dot: "bg-idle",
  },
};

export interface StatusIndicatorProps {
  status: DailyTargetStatus;
  /** Overrides the default copy, e.g. "Target achieved" → "In progress". */
  label?: string;
  variant?: "chip" | "inline";
  className?: string;
}

export function StatusIndicator({
  status,
  label,
  variant = "chip",
  className,
}: StatusIndicatorProps) {
  const meta = STATUS_META[status];
  const { Icon } = meta;

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 text-[13px] font-medium",
        meta.text,
        variant === "chip" && cn("rounded-full px-2.5 py-1", meta.chip),
        className,
      )}
    >
      <Icon aria-hidden="true" className="size-3.5 shrink-0" strokeWidth={2} />
      <span>{label ?? meta.label}</span>
    </span>
  );
}
