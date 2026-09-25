"""The contract every broker adapter satisfies.

A `Protocol` rather than an abstract base class. Nothing needs to inherit from
this to conform, which means a test double is a small class with the right
methods rather than a subclass dragging in real constructor behaviour — and
`mypy` still checks both the double and the real adapter against the same
shape.

WHAT IS DELIBERATELY ABSENT
---------------------------
There is no `place_order`, no `modify_order`, no `cancel_order` and no
`square_off`. Not "not yet implemented" — not present. A method that exists but
raises is still a method a future call site can find, and the only reliable way
to guarantee this system cannot transmit an order is for there to be no
function anywhere in it that does so.

`get_order_book` and `get_trade_book` are read-only views of orders placed by
other means, including by hand in the broker's own app. Reading is not writing.

EVERY METHOD IS ASYNC
---------------------
Even where an implementation might not need to await anything. The application
is an async FastAPI service, and a synchronous broker call blocks the event
loop for the whole process — every other request included. Making the contract
async removes the option of getting that wrong.

ERRORS
------
Implementations raise only `app.brokers.exceptions.BrokerError` subclasses.
An SDK exception, an `httpx` error or a `KeyError` escaping an adapter is an
adapter bug, not a caller's problem.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from app.brokers.models import (
    BrokerFunds,
    BrokerInstrument,
    BrokerOrder,
    BrokerPosition,
    BrokerProfile,
    BrokerQuote,
    BrokerSession,
    BrokerTrade,
    Candle,
    OpenInterestObservation,
    OptionMetrics,
)
from app.domain.enums import Timeframe


@runtime_checkable
class BrokerAdapter(Protocol):
    """Read-only access to one broker account and its market data."""

    # -- Session ------------------------------------------------------------

    async def authenticate(self) -> BrokerSession:
        """Establish a session, or return the cached one if it is still valid.

        Idempotent by intent: callers are expected to call this freely rather
        than track session state themselves. Brokers rate-limit login far more
        aggressively than data endpoints — Angel One allows one per second —
        so an adapter that logs in on every call will lock itself out.

        Raises `BrokerConfigurationError` when credentials are absent, which is
        a different thing from `BrokerAuthenticationError` and must stay so:
        one is an operator who has not finished setup, the other is an operator
        whose credentials are wrong.
        """
        ...

    async def logout(self) -> None:
        """End the session at the broker and discard the local tokens.

        Must not raise if there was no session to end. Logout is the thing a
        caller does while already handling a failure, and a cleanup path that
        can itself fail turns one problem into two.
        """
        ...

    # -- Account ------------------------------------------------------------

    async def get_profile(self) -> BrokerProfile:
        """Account identity, plus the exchanges it is enabled for."""
        ...

    async def get_funds(self) -> BrokerFunds:
        """Current funds and margin utilisation."""
        ...

    async def get_positions(self) -> list[BrokerPosition]:
        """Open positions. An empty list means flat, and is not an error."""
        ...

    async def get_order_book(self) -> list[BrokerOrder]:
        """Today's orders, whoever or whatever placed them. Read-only."""
        ...

    async def get_trade_book(self) -> list[BrokerTrade]:
        """Today's fills. Read-only."""
        ...

    # -- Market data --------------------------------------------------------

    async def get_ltp(self, instrument: BrokerInstrument) -> BrokerQuote:
        """Last traded price for one instrument.

        Returns a `BrokerQuote` with most fields `None` rather than a bare
        `Decimal`, so a caller can be upgraded from LTP to a full quote without
        changing its own signature.
        """
        ...

    async def get_historical_candles(
        self,
        instrument: BrokerInstrument,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> list[Candle]:
        """OHLCV bars over a closed interval, ascending by timestamp.

        `start` and `end` must be timezone-aware. Brokers cap the span of a
        single request — Angel One's limit varies by interval, from 30 days at
        one minute to 2000 at one day — so an implementation is expected to
        split a wider range into conforming requests and stitch the results.
        That splitting is the adapter's problem, not the caller's.

        Gaps are real, not errors: a weekend, a holiday or a contract that had
        not yet listed all produce fewer bars than a naive calculation expects.
        An implementation must never pad a gap with synthetic bars.
        """
        ...

    async def get_historical_oi(
        self,
        instrument: BrokerInstrument,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> list[OpenInterestObservation]:
        """Open-interest history for one F&O contract, ascending.

        Only live contracts have this. An expired instrument returns an empty
        list — which is a fact about the contract, not a failure, and must not
        be raised as one.
        """
        ...

    async def get_option_metrics(
        self, underlying: str, expiry: datetime
    ) -> list[OptionMetrics]:
        """Broker-computed Greeks for a whole expiry's option chain.

        The broker computes these, and its model and inputs are not visible
        from here. Treat the values as that broker's opinion rather than as
        ground truth, and never mix them with Greeks from another source in the
        same series.
        """
        ...
