import { BentoCard, BentoCardHeader } from "@/components/ui/BentoCard";
import { CurrencyValue } from "@/components/ui/CurrencyValue";
import type { AccountSummary } from "@/types/trading";

export interface AccountBalanceCardProps {
  account: AccountSummary;
  order?: number;
  className?: string;
}

/**
 * Capital available to the agent. Read-only by design — this figure belongs to
 * the broker and will be replaced by a funds API response, never user input.
 */
export function AccountBalanceCard({
  account,
  order,
  className,
}: AccountBalanceCardProps) {
  return (
    <BentoCard order={order} className={className} ariaLabel="Available balance">
      <BentoCardHeader title="Available Balance" description="Trading account" />

      <div className="mt-5 sm:mt-6">
        <CurrencyValue
          value={account.availableBalance}
          size="xl"
          decimals={2}
          className="tracking-[-0.02em]"
        />
      </div>

      <dl className="mt-auto grid grid-cols-2 gap-3 pt-6 sm:gap-4">
        <div className="rounded-inner bg-surface-sunken px-3.5 py-3">
          <dt className="text-xs text-ink-muted">Used margin</dt>
          <dd className="mt-1">
            <CurrencyValue value={account.usedMargin} size="sm" decimals={2} />
          </dd>
        </div>
        <div className="rounded-inner bg-surface-sunken px-3.5 py-3">
          <dt className="text-xs text-ink-muted">Total capital</dt>
          <dd className="mt-1">
            <CurrencyValue value={account.totalCapital} size="sm" decimals={2} />
          </dd>
        </div>
      </dl>
    </BentoCard>
  );
}
