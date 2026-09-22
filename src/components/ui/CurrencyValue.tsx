import { formatINR } from "@/lib/currency";
import { cn } from "@/lib/utils";

type CurrencySize = "xs" | "sm" | "md" | "lg" | "xl";
type CurrencyTone = "default" | "muted" | "positive" | "negative" | "auto";

const SIZE_STYLES: Record<CurrencySize, string> = {
  xs: "text-sm font-medium",
  sm: "text-base font-medium",
  md: "text-xl font-semibold sm:text-2xl",
  lg: "text-[26px] leading-tight font-semibold sm:text-3xl",
  xl: "text-[34px] leading-none font-semibold sm:text-[42px]",
};

const TONE_STYLES: Record<Exclude<CurrencyTone, "auto">, string> = {
  default: "text-ink",
  muted: "text-ink-secondary",
  positive: "text-positive",
  negative: "text-negative",
};

function resolveTone(
  tone: CurrencyTone,
  value: number,
): Exclude<CurrencyTone, "auto"> {
  if (tone !== "auto") return tone;
  if (value > 0) return "positive";
  if (value < 0) return "negative";
  return "default";
}

export interface CurrencyValueProps {
  value: number;
  size?: CurrencySize;
  tone?: CurrencyTone;
  decimals?: number;
  showSign?: boolean;
  className?: string;
}

/** Renders an INR amount with tabular figures so digits never shift position. */
export function CurrencyValue({
  value,
  size = "md",
  tone = "default",
  decimals = 0,
  showSign = false,
  className,
}: CurrencyValueProps) {
  const formatted = formatINR(value, { decimals, showSign });

  return (
    <span
      className={cn(
        "numeric inline-block",
        SIZE_STYLES[size],
        TONE_STYLES[resolveTone(tone, value)],
        className,
      )}
    >
      {formatted}
    </span>
  );
}
