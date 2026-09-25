"use client";

import { motion } from "motion/react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

type BentoCardVariant = "primary" | "secondary" | "glass";

/**
 * `glass` brings its own border and shadow, so it also cancels the border the
 * base class sets — `border-transparent` rather than omitting it, because the
 * 1px still has to occupy layout or the glass variant would sit a pixel wider
 * than its neighbours in the same grid row.
 */
const VARIANT_STYLES: Record<BentoCardVariant, string> = {
  primary: "border-hairline bg-surface shadow-card",
  secondary: "border-hairline bg-surface-muted shadow-card",
  glass: "glass-panel border-transparent",
};

export interface BentoCardProps {
  children: ReactNode;
  variant?: BentoCardVariant;
  /** Stagger index for the entrance transition. */
  order?: number;
  className?: string;
  /** Accessible name for the card's region landmark. */
  ariaLabel?: string;
}

export function BentoCard({
  children,
  variant = "primary",
  order = 0,
  className,
  ariaLabel,
}: BentoCardProps) {
  return (
    <motion.section
      aria-label={ariaLabel}
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        duration: 0.25,
        delay: Math.min(order, 6) * 0.04,
        ease: [0.22, 0.61, 0.36, 1],
      }}
      className={cn(
        "relative flex flex-col rounded-card border p-5",
        "transition-[box-shadow,background-color,border-color] duration-200 hover:shadow-card-hover",
        VARIANT_STYLES[variant],
        className,
      )}
    >
      {children}
    </motion.section>
  );
}

export interface BentoCardHeaderProps {
  title: string;
  /** Small clarifying line under the title, e.g. "Trading account". */
  description?: string;
  /** Right-aligned slot for icon-only controls. */
  action?: ReactNode;
  className?: string;
}

export function BentoCardHeader({
  title,
  description,
  action,
  className,
}: BentoCardHeaderProps) {
  return (
    <div className={cn("flex items-start justify-between gap-3", className)}>
      <div className="min-w-0">
        <h2 className="eyebrow text-ink-secondary">{title}</h2>
        {description ? (
          <p className="mt-1 text-xs text-ink-muted">{description}</p>
        ) : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  );
}
