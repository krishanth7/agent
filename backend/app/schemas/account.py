"""Account API schemas."""

from __future__ import annotations

from app.schemas.common import ApiModel, CurrencyMixin, NonNegativeMoney, SourcedMixin


class AccountSummaryResponse(ApiModel, CurrencyMixin, SourcedMixin):
    """The trading account's funds snapshot.

    Read-only by design. This figure belongs to the broker; there is no
    endpoint to write it, and there never should be — a client that could set
    its own balance could not be trusted to report one.
    """

    available_balance: NonNegativeMoney
    used_margin: NonNegativeMoney
    total_capital: NonNegativeMoney
