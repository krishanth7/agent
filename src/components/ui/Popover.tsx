"use client";

import * as PopoverPrimitive from "@radix-ui/react-popover";
import { X } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export const Popover = PopoverPrimitive.Root;
export const PopoverTrigger = PopoverPrimitive.Trigger;
export const PopoverAnchor = PopoverPrimitive.Anchor;

export interface PopoverPanelProps {
  children: ReactNode;
  /** Announced when the panel opens; required, since it is a dialog. */
  title: string;
  side?: "top" | "right" | "bottom" | "left";
  align?: "start" | "center" | "end";
  className?: string;
}

/**
 * Click-opened detail panel.
 *
 * A popover rather than a tooltip because the content is substantial and the
 * user needs to be able to read, scroll and dismiss it deliberately — a hover
 * hint that vanishes when the pointer moves is the wrong shape for a timetable.
 * Radix is doing the work that makes it a real dialog: focus is trapped and
 * restored, `Escape` and outside-click dismiss, and the trigger carries the
 * `aria-expanded`/`aria-controls` pair.
 */
export function PopoverPanel({
  children,
  title,
  side = "bottom",
  align = "end",
  className,
}: PopoverPanelProps) {
  return (
    <PopoverPrimitive.Portal>
      <PopoverPrimitive.Content
        side={side}
        align={align}
        sideOffset={8}
        collisionPadding={12}
        aria-label={title}
        className={cn(
          // `glass-panel` carries its own border and shadow, so neither is
          // repeated here — a `border-hairline` on top would draw a second
          // edge just inside the glass one.
          "glass-panel z-50 w-[min(21rem,calc(100vw-1.5rem))] rounded-card",
          "p-4 text-ink outline-none",
          "data-[state=open]:animate-in data-[state=closed]:animate-out",
          className,
        )}
      >
        {children}
        <PopoverPrimitive.Close
          aria-label="Close"
          className={cn(
            "focus-ring absolute right-2.5 top-2.5 grid size-6 place-items-center rounded-md",
            "text-ink-muted transition-colors duration-150 hover:bg-surface-sunken hover:text-ink",
          )}
        >
          <X aria-hidden="true" className="size-3.5" />
        </PopoverPrimitive.Close>
        {/*
          No arrow, deliberately. An SVG arrow cannot inherit the panel's
          `backdrop-filter` — it would render as an opaque triangle pinned to a
          translucent panel, and no fixed fill can match it, because the glass
          takes its apparent colour from whatever is behind it. The `sideOffset`
          and the trigger's `aria-controls` pair already establish the
          relationship, for sighted and assistive users respectively.
        */}
      </PopoverPrimitive.Content>
    </PopoverPrimitive.Portal>
  );
}
