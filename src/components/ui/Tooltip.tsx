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
            // Glass rather than the former inverted solid. The text colour has
            // to flip with it: `text-canvas` was legible only because the fill
            // was `bg-ink`, and over glass it would be near-invisible.
            //
            // `font-semibold` rather than `font-medium` because this is the
            // smallest text in the app and the highest-risk contrast case on a
            // translucent surface — weight is the cheapest way to buy back
            // legibility without growing the tooltip.
            "glass-panel z-50 max-w-[15rem] rounded-lg px-2.5 py-1.5",
            "text-xs font-semibold text-ink",
            "data-[state=delayed-open]:animate-in data-[state=closed]:animate-out",
            className,
          )}
        >
          {label}
          {/* No arrow — see `PopoverPanel` for why glass cannot have one. */}
        </TooltipPrimitive.Content>
      </TooltipPrimitive.Portal>
    </TooltipPrimitive.Root>
  );
}
