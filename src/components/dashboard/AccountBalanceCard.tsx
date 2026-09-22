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
