import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export interface StatRowProps {
  label: string;
  value: ReactNode;
  className?: string;
}

/** Label/value pair used for the compact metric lists inside cards. */
export function StatRow({ label, value, className }: StatRowProps) {
  return (
    <div
      className={cn(
        "flex items-baseline justify-between gap-4 py-2",
        className,
      )}
    >
      <dt className="text-[13px] text-ink-muted">{label}</dt>
      <dd className="text-[13px] font-medium text-ink">{value}</dd>
    </div>
  );
}
