"use client";

import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export const TooltipProvider = TooltipPrimitive.Provider;

export interface TooltipProps {
  /**
   * Tooltip body. A `ReactNode` rather than a `string` so a richer hint — a
   * holiday name over its date, say — does not need a second primitive.
   */
  label: ReactNode;
  children: ReactNode;
  side?: "top" | "right" | "bottom" | "left";
  /** Override the provider's delay; `0` for hints that must feel instant. */
  delayDuration?: number;
  className?: string;
}

/**
 * Hover/focus hint for icon-only controls. Purely supplementary — triggers keep
 * their own `aria-label`, so the tooltip is never the sole affordance.
 */
export function Tooltip({
  label,
  children,
  side = "top",
  delayDuration,
  className,
}: TooltipProps) {
  return (
    <TooltipPrimitive.Root delayDuration={delayDuration}>
      <TooltipPrimitive.Trigger asChild>{children}</TooltipPrimitive.Trigger>
      <TooltipPrimitive.Portal>
        <TooltipPrimitive.Content
          side={side}
          sideOffset={6}
          collisionPadding={10}
          className={cn(
            "z-50 max-w-[15rem] rounded-lg bg-ink px-2.5 py-1.5 text-xs font-medium text-canvas shadow-card",
            "data-[state=delayed-open]:animate-in data-[state=closed]:animate-out",
            className,
          )}
        >
          {label}
          <TooltipPrimitive.Arrow className="fill-ink" width={10} height={5} />
        </TooltipPrimitive.Content>
      </TooltipPrimitive.Portal>
    </TooltipPrimitive.Root>
  );
}
