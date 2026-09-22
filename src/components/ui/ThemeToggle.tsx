"use client";

import { Moon, Sun, type LucideIcon } from "lucide-react";
import { motion } from "motion/react";

import { Tooltip } from "@/components/ui/Tooltip";
import { useTheme } from "@/hooks/useTheme";
import { cn } from "@/lib/utils";
import type { Theme } from "@/lib/theme";

const OPTIONS: ReadonlyArray<{ theme: Theme; label: string; Icon: LucideIcon }> =
  [
    { theme: "light", label: "Light theme", Icon: Sun },
    { theme: "dark", label: "Dark theme", Icon: Moon },
  ];

export interface ThemeToggleProps {
  className?: string;
}

/**
 * Segmented light/dark control.
 *
 * A two-position track rather than a single morphing button: the user can see
 * both states and which one is active, which reads as an explicit setting
 * instead of a mystery-meat icon. The thumb is a shared layout element, so the
 * selection glides between positions in one continuous motion.
 */
export function ThemeToggle({ className }: ThemeToggleProps) {
  const { theme, setTheme } = useTheme();

  return (
    <div
      role="group"
      aria-label="Colour theme"
      className={cn(
        "relative inline-flex items-center gap-0.5 rounded-full border border-hairline bg-canvas-raised p-[3px]",
        className,
      )}
    >
      {OPTIONS.map(({ theme: option, label, Icon }) => {
        const isActive = theme === option;

        return (
          <Tooltip key={option} label={label}>
            <button
              type="button"
              onClick={() => setTheme(option)}
              aria-label={label}
              aria-pressed={isActive}
              className="focus-ring relative grid size-7 place-items-center rounded-full"
            >
              {isActive ? (
                <motion.span
                  layoutId="theme-toggle-thumb"
                  aria-hidden="true"
                  transition={{ type: "spring", stiffness: 520, damping: 40 }}
                  className="absolute inset-0 rounded-full bg-surface shadow-[0_1px_2px_rgba(0,0,0,0.12)] ring-1 ring-hairline-strong"
                />
              ) : null}
              <Icon
                aria-hidden="true"
                strokeWidth={2}
                className={cn(
                  "relative size-[15px] transition-colors duration-150",
                  isActive ? "text-ink" : "text-ink-muted hover:text-ink-secondary",
                )}
              />
            </button>
          </Tooltip>
        );
      })}
    </div>
  );
}
