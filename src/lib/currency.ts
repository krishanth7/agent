const formatterCache = new Map<string, Intl.NumberFormat>();

function getFormatter(decimals: number, showSign: boolean): Intl.NumberFormat {
  const key = `${decimals}:${showSign}`;
  const cached = formatterCache.get(key);
  if (cached) return cached;

  const formatter = new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
    signDisplay: showSign ? "exceptZero" : "auto",
  });
  formatterCache.set(key, formatter);
  return formatter;
}

export interface FormatINROptions {
  /** Fraction digits to render. Headline balances use 2, targets and P&L use 0. */
  decimals?: number;
  /** Render a leading `+` for positive amounts. Zero stays unsigned. */
  showSign?: boolean;
}

/**
 * Formats a number as Indian Rupees with Indian digit grouping
 * (e.g. `₹10,00,000.00`). Non-finite input degrades to zero so a malformed
 * value can never surface as `₹NaN`.
 */
export function formatINR(value: number, options: FormatINROptions = {}): string {
  const { decimals = 0, showSign = false } = options;
  const safeValue = Number.isFinite(value) ? value : 0;
  return getFormatter(decimals, showSign).format(safeValue);
}

/** Percentage with one decimal, e.g. `42.8%`. */
export function formatPercent(ratio: number, fractionDigits = 1): string {
  const safeRatio = Number.isFinite(ratio) ? ratio : 0;
  return `${(safeRatio * 100).toFixed(fractionDigits)}%`;
}

/**
 * Extracts a positive integer amount from free-form user input, tolerating
 * spaces, `₹`, and thousands separators. Returns `null` when the input is not a
 * usable target.
 */
export function parseAmountInput(raw: string): number | null {
  const cleaned = raw.replace(/[₹,\s]/g, "");
  if (cleaned === "" || !/^\d*\.?\d*$/.test(cleaned)) return null;

  const parsed = Number.parseFloat(cleaned);
  if (!Number.isFinite(parsed) || parsed <= 0) return null;

  return Math.round(parsed);
}
