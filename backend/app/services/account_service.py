"""Account application service."""

from __future__ import annotations

from app.domain.calculations import quantize_money
from app.repositories.interfaces.account_repository import AccountRepository
from app.schemas.account import AccountSummaryResponse


class AccountService:
    """Turns a repository's funds snapshot into the API contract."""

    def __init__(self, repository: AccountRepository) -> None:
        self._repository = repository

    async def get_summary(self) -> AccountSummaryResponse:
        summary = await self._repository.get_summary()
        return AccountSummaryResponse(
            available_balance=quantize_money(summary.available_balance),
            used_margin=quantize_money(summary.used_margin),
            total_capital=quantize_money(summary.total_capital),
            source=summary.source,
        )
