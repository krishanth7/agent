"use client";

import { AnimatePresence, motion } from "motion/react";
import { PencilLine } from "lucide-react";
import { useEffect, useId, useRef, useState, type FormEvent } from "react";

import { BentoCard, BentoCardHeader } from "@/components/ui/BentoCard";
import { CurrencyValue } from "@/components/ui/CurrencyValue";
import { Tooltip } from "@/components/ui/Tooltip";
import { parseAmountInput } from "@/lib/currency";
import { ASSUMED_DAYS_PER_MONTH } from "@/lib/targetCalculations";

const TRANSITION = { duration: 0.18, ease: [0.22, 0.61, 0.36, 1] } as const;

export interface MonthlyTargetCardProps {
  monthlyTarget: number;
  dailyTarget: number;
  /** Returns `false` when the value was rejected by the persistence layer. */
  onSave: (next: number) => boolean;
  order?: number;
  className?: string;
}

/**
 * The user's self-defined monthly goal. Deliberately framed as a target rather
 * than expected income — it drives the daily split and nothing else.
 */
export function MonthlyTargetCard({
  monthlyTarget,
  dailyTarget,
  onSave,
  order,
  className,
}: MonthlyTargetCardProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const errorId = useId();

  useEffect(() => {
    if (isEditing) inputRef.current?.select();
  }, [isEditing]);

  function startEditing() {
    setDraft(String(monthlyTarget));
    setError(null);
    setIsEditing(true);
  }

  function cancelEditing() {
    setIsEditing(false);
    setError(null);
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const parsed = parseAmountInput(draft);
    if (parsed === null) {
      setError("Enter an amount greater than ₹0.");
      inputRef.current?.focus();
      return;
    }

    if (!onSave(parsed)) {
      setError("That target could not be saved.");
      return;
    }

    setIsEditing(false);
    setError(null);
  }

  return (
    <BentoCard order={order} className={className} ariaLabel="Monthly target">
      <BentoCardHeader
        title="Monthly Target"
        description="Your goal for this month"
        action={
          isEditing ? null : (
            <Tooltip label="Edit monthly target">
              <button
                type="button"
                onClick={startEditing}
                aria-label="Edit monthly target"
                className="focus-ring -m-1.5 grid size-9 place-items-center rounded-lg text-ink-muted transition-colors duration-150 hover:bg-surface-sunken hover:text-ink"
              >
                <PencilLine aria-hidden="true" className="size-4" />
              </button>
            </Tooltip>
          )
        }
      />

      <div className="mt-5 min-w-0 sm:mt-6">
        <AnimatePresence initial={false} mode="wait">
          {isEditing ? (
            <motion.form
              key="editing"
              onSubmit={handleSubmit}
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 4 }}
              transition={TRANSITION}
              onKeyDown={(event) => {
                if (event.key === "Escape") cancelEditing();
              }}
            >
              <div className="flex items-center gap-2 rounded-inner border border-hairline-strong bg-field px-3 py-2 focus-within:border-ink">
                <span aria-hidden="true" className="text-lg text-ink-muted">
                  ₹
                </span>
                <input
                  ref={inputRef}
                  value={draft}
                  onChange={(event) => {
                    // Numbers only — strip anything a user might paste in.
                    setDraft(event.target.value.replace(/[^\d.]/g, ""));
                    setError(null);
                  }}
                  inputMode="decimal"
                  autoComplete="off"
                  aria-label="Monthly target amount in rupees"
                  aria-invalid={error !== null}
                  aria-describedby={error ? errorId : undefined}
                  className="numeric w-full min-w-0 bg-transparent text-2xl font-semibold text-ink outline-none placeholder:text-ink-muted"
                  placeholder="10000"
                />
              </div>

              {error ? (
                <p id={errorId} role="alert" className="mt-2 text-xs text-negative">
                  {error}
                </p>
              ) : null}

              <div className="mt-3 flex items-center gap-1">
                <button
                  type="submit"
                  className="focus-ring rounded-lg bg-ink px-3 py-1.5 text-[13px] font-medium text-canvas transition-opacity duration-150 hover:opacity-85"
                >
                  Save
                </button>
                <button
                  type="button"
                  onClick={cancelEditing}
                  className="focus-ring rounded-lg px-3 py-1.5 text-[13px] font-medium text-ink-secondary transition-colors duration-150 hover:bg-surface-sunken hover:text-ink"
                >
                  Cancel
                </button>
              </div>
            </motion.form>
          ) : (
            <motion.div
              key="reading"
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 4 }}
              transition={TRANSITION}
            >
              <CurrencyValue
                value={monthlyTarget}
                size="xl"
                className="tracking-[-0.02em] break-words"
              />
              {/* Framed as a goal — never as projected or guaranteed income. */}
              <p className="mt-3 max-w-[38ch] text-xs leading-relaxed text-ink-muted">
                A goal you set for the agent to work towards. It is not
                projected, expected, or guaranteed income.
              </p>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      <p className="mt-auto pt-6 text-[13px] text-ink-muted">
        Splits to{" "}
        <span className="numeric font-medium text-ink-secondary">
          {dailyTarget > 0 ? `₹${dailyTarget.toLocaleString("en-IN")}` : "₹0"}
        </span>{" "}
        across {ASSUMED_DAYS_PER_MONTH} days
      </p>
    </BentoCard>
  );
}
