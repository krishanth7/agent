import { BentoCard, BentoCardHeader } from "@/components/ui/BentoCard";
import { CardError, CardSkeleton } from "@/components/ui/CardState";
import { CurrencyValue } from "@/components/ui/CurrencyValue";
import type { ResourceStatus } from "@/hooks/useApiResource";
import type { AccountSummary } from "@/types/trading";

export interface AccountBalanceCardProps {
  /** `null` while loading or when the API could not be reached. */
  account: AccountSummary | null;
  status: ResourceStatus;
  error?: string | null;
  offline?: boolean;
  onRetry?: () => void;
  order?: number;
  className?: string;
}

/**
 * Capital available to the agent. Read-only by design — this figure belongs to
 * the broker and will be replaced by a funds API response, never user input.
 *
 * When the API is unavailable the card says so outright. It must never fall
 * back to a remembered or default balance: a stale number here would be
 * indistinguishable from a real one, and the user would size positions against
 * money that may not exist.
 */
export function AccountBalanceCard({
  account,
  status,
  error,
  offline,
  onRetry,
  order,
  className,
}: AccountBalanceCardProps) {
  const header = (
    <BentoCardHeader title="Available Balance" description="Trading account" />
  );

  if (status === "loading") {
    return (
      <BentoCard
        order={order}
        className={className}
        ariaLabel="Available balance"
      >
        {header}
        <CardSkeleton headline="h-10" lines={2} />
      </BentoCard>
    );
  }

  if (status === "error" || account === null) {
    return (
      <BentoCard
        order={order}
        className={className}
        ariaLabel="Available balance"
      >
        {header}
        <CardError
          title="Balance unavailable"
          message={error ?? null}
          offline={offline}
          onRetry={onRetry}
        />
      </BentoCard>
    );
  }

  return (
    <BentoCard order={order} className={className} ariaLabel="Available balance">
      {header}

      <div className="mt-5 sm:mt-6">
        <CurrencyValue
          value={account.availableBalance}
          size="xl"
          decimals={2}
          className="tracking-[-0.02em]"
        />
        {/* Spelled out so the balance is never mistaken for profit or target. */}
        <p className="mt-3 max-w-[38ch] text-xs leading-relaxed text-ink-muted">
          Capital the agent can deploy. This is your account balance — not
          realized profit, and not a target.
        </p>
      </div>

      <dl className="mt-auto grid grid-cols-2 gap-2 pt-6">
        <div className="min-w-0 rounded-inner bg-surface-sunken px-3 py-2.5">
          <dt className="text-[10.5px] text-ink-muted">Used margin</dt>
          <dd className="mt-1">
            <CurrencyValue value={account.usedMargin} size="sm" decimals={2} />
          </dd>
        </div>
        <div className="min-w-0 rounded-inner bg-surface-sunken px-3 py-2.5">
          <dt className="text-[10.5px] text-ink-muted">Total capital</dt>
          <dd className="mt-1">
            <CurrencyValue value={account.totalCapital} size="sm" decimals={2} />
          </dd>
        </div>
      </dl>
    </BentoCard>
  );
}
