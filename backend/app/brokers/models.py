"""Broker-neutral records.

What an adapter returns. Nothing in here names Angel One, mentions a JSON key,
or repeats a vendor's spelling of a field — that translation is the adapter's
entire job, and if a vendor's vocabulary leaked up to here the abstraction
would be decorative.

Frozen dataclasses, matching `app.domain.models`: no validation or
serialization happens at this layer, and immutability means a snapshot handed
to three call sites cannot be mutated by one of them.

THREE RULES THAT ARE NOT NEGOTIABLE
-----------------------------------
1. **Every money, price, strike and Greek is a `Decimal`.** Brokers send these
   as decimal strings. Parsing `"1234.55"` through `float` introduces a binary
   rounding error before the value has even been stored, and P&L computed from
   such values disagrees with the broker's own figures by amounts that are
   small, non-deterministic and impossible to explain to anyone.

2. **`None` means "the broker did not tell us".** It never means zero. A field
   that is genuinely absent from a response stays `None` so a caller can say
   "unknown" rather than confidently displaying a fabricated 0.00. Mandatory
   fields are non-optional here precisely so that a missing one raises
   `BrokerDataError` in the mapper instead of arriving as a plausible default.

3. **Tokens are `SecretStr`.** A session object ends up in log lines, error
   contexts and tracebacks. Wrapping the tokens means the worst case is
   `**********` rather than a live credential sitting in a log aggregator.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from pydantic import SecretStr

from app.domain.enums import InstrumentType, OptionType, Timeframe


@dataclass(frozen=True, slots=True)
class BrokerInstrument:
    """Enough to ask a broker about one tradable contract.

    `token` is the broker's own numeric identifier, kept as a string because it
    is an opaque key and not a quantity — some are zero-padded, and none of
    them are ever arithmetic. `exchange_segment` is likewise the broker's
    spelling (`NSE`, `NFO`), since it is a routing value sent straight back.

    The option fields are `None` on an index or a future. They are carried here
    rather than looked up again later so that a candle request and the label
    printed beside it cannot disagree about which strike was fetched.
    """

    token: str
    symbol: str
    exchange_segment: str
    instrument_type: InstrumentType
    underlying: str | None = None
    expiry: date | None = None
    strike_price: Decimal | None = None
    option_type: OptionType | None = None
    lot_size: int | None = None
    tick_size: Decimal | None = None


@dataclass(frozen=True, slots=True)
class BrokerSession:
    """A live, authenticated broker session.

    `expires_at` is not read from the response: Angel One does not send an
    expiry, it publishes a policy — tokens die at midnight IST regardless of
    when they were issued or how recently they were used. The adapter computes
    the next IST midnight and stores it, so "is this session still good?" is a
    comparison rather than a failed request.
    """

    access_token: SecretStr
    refresh_token: SecretStr
    feed_token: SecretStr
    issued_at: datetime
    expires_at: datetime
    client_code: str

    def is_expired(self, now: datetime) -> bool:
        """Whether this session is past its published lifetime.

        Takes `now` rather than reading the clock so the caller owns time and a
        test can step over the boundary without waiting for midnight.
        """
        return now >= self.expires_at


@dataclass(frozen=True, slots=True)
class BrokerProfile:
    """Who the broker thinks we are.

    Deliberately thin. The profile response carries a bank account number, a
    PAN and a set of enabled exchanges; none of that is needed to render a
    connection status, and storing it would turn a status endpoint into a
    reason for a data-protection review. `exchanges` is kept because "your
    account is not enabled for NFO" is the single most common cause of a
    confusing authorization failure.
    """

    client_code: str
    name: str | None = None
    email: str | None = None
    broker_name: str | None = None
    exchanges: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BrokerFunds:
    """A funds and margin snapshot.

    The field names are ours, not the broker's. `net` is what the broker calls
    the account's net value; `available_cash` is what can actually be deployed.
    Everything below `used_margin` is optional because not every broker — and
    not every account type — reports the breakdown, and an absent component is
    genuinely unknown rather than zero.
    """

    net: Decimal
    available_cash: Decimal
    used_margin: Decimal
    available_intraday_payin: Decimal | None = None
    available_limit_margin: Decimal | None = None
    collateral: Decimal | None = None
    unrealized_mtm: Decimal | None = None
    realized_mtm: Decimal | None = None
    utilised_span: Decimal | None = None
    utilised_option_premium: Decimal | None = None
    utilised_exposure: Decimal | None = None
    utilised_holding_sales: Decimal | None = None
    utilised_turnover: Decimal | None = None
    utilised_payout: Decimal | None = None
    retrieved_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class BrokerPosition:
    """One open or closed position as the broker reports it.

    `net_quantity` is signed: negative is short. Carrying the sign rather than
    a separate side field means a portfolio sums with `sum()` and cannot be
    aggregated wrongly by a caller that forgot to check a direction flag.

    Note that quantities here are in *units*, not lots. Brokers differ on this
    and the mapper normalises to units, keeping `lot_size` alongside so a
    caller that wants lots can divide deliberately.
    """

    symbol: str
    token: str
    exchange_segment: str
    product_type: str
    net_quantity: int
    buy_quantity: int | None = None
    sell_quantity: int | None = None
    average_price: Decimal | None = None
    last_traded_price: Decimal | None = None
    realized_pnl: Decimal | None = None
    unrealized_pnl: Decimal | None = None
    lot_size: int | None = None


@dataclass(frozen=True, slots=True)
class BrokerOrder:
    """An entry in the broker's order book.

    READ ONLY. This type exists so the dashboard can *show* orders placed by
    any means — including by hand in the broker's own app. Nothing in this
    codebase constructs one to send anywhere; there is no order-placement path
    in this phase, by design and not by omission.

    `status` and `order_type` stay as the broker's own strings rather than
    being coerced into `OrderStatus` / `OrderType`. Those enums describe orders
    *this system* would create, and silently mapping an unrecognised broker
    status onto the nearest member would invent a fact about someone's money.
    """

    order_id: str
    symbol: str
    token: str
    exchange_segment: str
    transaction_type: str
    order_type: str
    product_type: str
    status: str
    quantity: int
    filled_quantity: int | None = None
    price: Decimal | None = None
    trigger_price: Decimal | None = None
    average_price: Decimal | None = None
    order_timestamp: datetime | None = None
    status_message: str | None = None


@dataclass(frozen=True, slots=True)
class BrokerTrade:
    """An entry in the broker's trade book — a fill, not an intention.

    Distinct from `BrokerOrder` because one order may produce several of these,
    and because a trade is the only one of the two that moved money.
    """

    trade_id: str
    order_id: str
    symbol: str
    token: str
    exchange_segment: str
    transaction_type: str
    product_type: str
    quantity: int
    price: Decimal
    trade_timestamp: datetime | None = None


@dataclass(frozen=True, slots=True)
class Candle:
    """One OHLCV bar.

    `timestamp` is the bar's *opening* instant and is always timezone-aware.
    Angel One returns `+05:30` offsets and this layer keeps them aware all the
    way to the database, because a naive datetime in a market-data table is a
    bug waiting for the first person who assumes it is UTC.

    `volume` is `int`: it is a count of contracts or shares, and no exchange
    has ever traded a fractional one.
    """

    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    timeframe: Timeframe


@dataclass(frozen=True, slots=True)
class OpenInterestObservation:
    """Open interest at an instant, for one F&O contract.

    Separate from `Candle` because the broker serves it from a separate
    endpoint with a different shape and different availability — OI is only
    published for live contracts, so a range that reaches back past an expiry
    returns nothing rather than failing. A caller must be able to tell those
    two apart, which it cannot do if OI is a nullable column on a candle.
    """

    timestamp: datetime
    open_interest: int


@dataclass(frozen=True, slots=True)
class OptionMetrics:
    """Broker-computed Greeks for one option contract.

    Computed by the broker, not by us. Stored with the expiry and strike that
    produced them because a Greek without its contract is meaningless, and
    because the broker's own model and inputs are not visible from here — two
    sources will not agree, so the source has to travel with the value.

    Every field below `option_type` is optional: the endpoint omits Greeks for
    contracts it has no live data for, and a `0.0` delta is a real, meaningful
    value that must never be used as a stand-in for a missing one.
    """

    underlying: str
    expiry: date
    strike_price: Decimal
    option_type: OptionType
    delta: Decimal | None = None
    gamma: Decimal | None = None
    theta: Decimal | None = None
    vega: Decimal | None = None
    implied_volatility: Decimal | None = None
    trade_volume: Decimal | None = None


@dataclass(frozen=True, slots=True)
class DepthLevel:
    """One side of one rung of the order book."""

    price: Decimal
    quantity: int
    orders: int


@dataclass(frozen=True, slots=True)
class BrokerQuote:
    """A point-in-time market quote.

    Used for both the REST quote endpoints and the normalised streaming tick,
    so a consumer written against one works unchanged against the other. That
    is the whole reason the fields are almost all optional: an LTP-mode tick
    carries a price and nothing else, a full snapshot carries everything, and
    the difference must be visible as `None` rather than smoothed over with
    zeros.
    """

    token: str
    exchange_segment: str
    last_traded_price: Decimal
    exchange_timestamp: datetime | None = None
    symbol: str | None = None
    last_traded_quantity: int | None = None
    average_traded_price: Decimal | None = None
    volume_traded: int | None = None
    total_buy_quantity: Decimal | None = None
    total_sell_quantity: Decimal | None = None
    open: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    close: Decimal | None = None
    open_interest: int | None = None
    upper_circuit: Decimal | None = None
    lower_circuit: Decimal | None = None
    fifty_two_week_high: Decimal | None = None
    fifty_two_week_low: Decimal | None = None
    best_bids: tuple[DepthLevel, ...] = field(default_factory=tuple)
    best_asks: tuple[DepthLevel, ...] = field(default_factory=tuple)
