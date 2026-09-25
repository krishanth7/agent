"""ORM model registry.

Importing this package is what populates `Base.metadata`. Alembic imports it
for autogenerate, and the test harness imports it to create a schema — a model
that is not re-exported here is invisible to both, which shows up as a
migration that silently forgets a table.
"""

from __future__ import annotations

from app.db.models.broker_account import BrokerAccountSnapshot
from app.db.models.daily_performance import DailyPerformance
from app.db.models.instrument import MarketInstrument
from app.db.models.market_data import IndiaVix, OhlcvCandle
from app.db.models.monthly_target import MonthlyTarget, MonthlyTargetHistory
from app.db.models.option_chain import OptionChainSnapshot, OptionQuote
from app.db.models.trading import Execution, Order, Position, Trade, TradeJournal
from app.db.models.trading_session import TradingSession

__all__ = [
    "BrokerAccountSnapshot",
    "DailyPerformance",
    "Execution",
    "IndiaVix",
    "MarketInstrument",
    "MonthlyTarget",
    "MonthlyTargetHistory",
    "OhlcvCandle",
    "OptionChainSnapshot",
    "OptionQuote",
    "Order",
    "Position",
    "Trade",
    "TradeJournal",
    "TradingSession",
]
