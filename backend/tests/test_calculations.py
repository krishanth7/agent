"""Unit tests for the pure business rules.

These cover the rules the rest of the system is built on, so they are
exhaustive about boundaries: the exact rounding hinge, the zero cases, and the
sign transitions.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.domain.calculations import (
    calculate_daily_target,
    calculate_progress_percentage,
    calculate_remaining_to_target,
    calculate_win_rate,
    get_daily_target_status,
    quantize_money,
)
from app.domain.enums import DailyTargetStatus


class TestCalculateDailyTarget:
    @pytest.mark.parametrize(
        ("monthly", "expected"),
        [
            ("10000", 333),  # 333.33 -> down
            ("10010", 334),  # 333.67 -> up
            ("15000", 500),  # exact
            ("20000", 667),  # 666.67 -> up
            ("30000", 1000),
            ("1", 0),  # 0.033 -> down to zero
            ("15", 1),  # exactly 0.5 -> ROUND_HALF_UP -> 1
            ("45", 2),  # exactly 1.5 -> 2, not banker's 2
            ("75", 3),  # exactly 2.5 -> 3, not banker's 2
        ],
    )
    def test_rounds_half_up(self, monthly: str, expected: int) -> None:
        assert calculate_daily_target(Decimal(monthly)) == expected

    @pytest.mark.parametrize("monthly", ["0", "-1", "-10000"])
    def test_non_positive_yields_zero(self, monthly: str) -> None:
        assert calculate_daily_target(Decimal(monthly)) == 0

    def test_returns_int_not_decimal(self) -> None:
        assert isinstance(calculate_daily_target(Decimal("10000")), int)


class TestDailyTargetStatus:
    @pytest.mark.parametrize(
        ("pnl", "target", "expected"),
        [
            ("-120", "333", DailyTargetStatus.LOSS),
            ("-0.01", "333", DailyTargetStatus.LOSS),
            ("0", "333", DailyTargetStatus.NOT_STARTED),
            ("180", "333", DailyTargetStatus.IN_PROGRESS),
            ("332.99", "333", DailyTargetStatus.IN_PROGRESS),
            ("333", "333", DailyTargetStatus.ACHIEVED),
            ("420", "333", DailyTargetStatus.ACHIEVED),
        ],
    )
    def test_classification(
        self, pnl: str, target: str, expected: DailyTargetStatus
    ) -> None:
        assert get_daily_target_status(Decimal(pnl), Decimal(target)) is expected

    def test_zero_target_is_cleared_by_any_profit(self) -> None:
        assert (
            get_daily_target_status(Decimal("1"), Decimal("0"))
            is DailyTargetStatus.ACHIEVED
        )

    def test_loss_outranks_zero_target(self) -> None:
        """A loss reads as a loss even when no target is set."""
        assert (
            get_daily_target_status(Decimal("-50"), Decimal("0"))
            is DailyTargetStatus.LOSS
        )

    def test_flat_session_against_zero_target_is_not_started(self) -> None:
        assert (
            get_daily_target_status(Decimal("0"), Decimal("0"))
            is DailyTargetStatus.NOT_STARTED
        )


class TestRemainingToTarget:
    @pytest.mark.parametrize(
        ("pnl", "target", "expected"),
        [
            ("180", "333", "153.00"),
            ("420", "333", "0.00"),  # beaten -> floored at zero
            ("333", "333", "0.00"),  # exactly met
            ("-120", "333", "453.00"),  # measured from current P&L
            ("0", "333", "333.00"),
        ],
    )
    def test_values(self, pnl: str, target: str, expected: str) -> None:
        assert calculate_remaining_to_target(Decimal(pnl), Decimal(target)) == Decimal(
            expected
        )

    def test_zero_target_yields_zero(self) -> None:
        assert calculate_remaining_to_target(Decimal("100"), Decimal("0")) == Decimal(
            "0.00"
        )


class TestProgressPercentage:
    @pytest.mark.parametrize(
        ("value", "target", "expected"),
        [
            ("420", "333", "126.13"),
            ("180", "333", "54.05"),
            ("4280", "10000", "42.80"),
            ("0", "333", "0.00"),
            ("-120", "333", "-36.04"),
        ],
    )
    def test_values(self, value: str, target: str, expected: str) -> None:
        assert calculate_progress_percentage(
            Decimal(value), Decimal(target)
        ) == Decimal(expected)

    def test_exceeds_one_hundred_uncapped(self) -> None:
        """Beating a target must be reported, not clamped."""
        assert calculate_progress_percentage(
            Decimal("1000"), Decimal("100")
        ) == Decimal("1000.00")

    def test_zero_target_yields_zero(self) -> None:
        assert calculate_progress_percentage(Decimal("50"), Decimal("0")) == Decimal(
            "0.00"
        )


class TestWinRate:
    @pytest.mark.parametrize(
        ("wins", "trades", "expected"),
        [
            (2, 3, "66.67"),
            (0, 3, "0.00"),
            (3, 3, "100.00"),
            (1, 3, "33.33"),
        ],
    )
    def test_values(self, wins: int, trades: int, expected: str) -> None:
        assert calculate_win_rate(wins, trades) == Decimal(expected)

    def test_zero_trades_never_divides_by_zero(self) -> None:
        assert calculate_win_rate(0, 0) == Decimal("0.00")


class TestQuantizeMoney:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("25000", "25000.00"),
            ("420.005", "420.01"),  # half away from zero, not banker's 420.00
            ("0.125", "0.13"),
            ("-0.125", "-0.13"),
        ],
    )
    def test_rounds_half_up(self, value: str, expected: str) -> None:
        assert quantize_money(Decimal(value)) == Decimal(expected)

    def test_repeated_addition_does_not_drift(self) -> None:
        """The whole reason money is Decimal rather than float."""
        total = sum((Decimal("0.10") for _ in range(10)), Decimal("0"))
        assert total == Decimal("1.00")
        assert quantize_money(total) == Decimal("1.00")
