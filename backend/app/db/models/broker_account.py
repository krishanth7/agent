"""Point-in-time observations of a broker account.

WHAT THIS IS FOR
----------------
A row here is an answer to "what did the broker say our funds were, and when?"
It is an append-only audit log of observations, not a mutable account record.
Nothing in the application derives an authoritative balance from this table:
the broker is authoritative, and this is the history of what it told us.

That framing is the reason for several choices below. There is no `balance`
column that gets updated, no unique key on `(broker, client_code)` that would
force one row per account, and `captured_at` is a timestamp of *observation*
rather than a business date.

WHY THE CLIENT CODE IS STORED AND THE TOKENS ARE NOT
----------------------------------------------------
The client code identifies which account an observation belongs to, and without
it a multi-account deployment cannot tell two accounts' balances apart. It is
an account identifier, not a credential.

The access, refresh and feed tokens are deliberately absent. They are
credentials, they expire daily, they have no analytical value, and a bearer
token in a database row is a bearer token in every backup and every
`pg_dump` — which is how a read-only audit table becomes the way an account is
compromised. Sessions live in memory for the process lifetime; see
`app.brokers.angel_one.auth`.

WHY EVERY FIGURE IS NULLABLE EXCEPT THE THREE THAT ARE NOT
----------------------------------------------------------
`net`, `available_cash` and `used_margin` are what the RMS endpoint always
returns, and the mapper already refuses to default them. The remainder are
genuinely absent for some account types, and `NULL` says "the broker did not
report this" while `0` would assert a fact the broker never stated. This is the
same rule the broker models follow, carried into storage so the distinction
survives a round trip.

NOT A HYPERTABLE
----------------
One row per poll per account. At a minute's cadence that is a few hundred rows
a day — five orders of magnitude below `option_quotes`. Chunking it would add
planning overhead to a table that will not outgrow a plain B-tree index this
decade, and a hypertable cannot be converted back.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import CheckConstraint, DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Money, Source, created_at_column, enum_check, uuid_pk
from app.domain.enums import DataSource


class BrokerAccountSnapshot(Base):
    """One observation of a broker account's funds and margin.

    Append-only, so it carries `created_at` but no `updated_at`: an observation
    of a past moment is never edited, and a row that changed would make the
    audit trail worthless.
    """

    __tablename__ = "broker_account_snapshots"

    id: Mapped[uuid.UUID] = uuid_pk()

    #: Which broker made the statement, e.g. `angel_one`. A plain string rather
    #: than an enum: the vocabulary is open by design, and adding a second
    #: broker should not require a migration to record its name.
    broker: Mapped[str] = mapped_column(String(32), nullable=False)

    #: The broker's own account identifier. Not a credential — see the module
    #: docstring on why no token is stored beside it.
    client_code: Mapped[str] = mapped_column(String(32), nullable=False)

    #: When the observation was made, as an instant. `TIMESTAMPTZ`, because a
    #: funds figure is meaningful only against the moment it was true, and a
    #: naive timestamp loses that the first time a host changes region.
    captured_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # -- The three figures the RMS endpoint always returns --------------------

    #: Total account value as the broker computes it.
    net: Mapped[Money] = mapped_column(nullable=False)
    #: Cash available to deploy.
    available_cash: Mapped[Money] = mapped_column(nullable=False)
    #: Margin currently blocked against open positions.
    used_margin: Mapped[Money] = mapped_column(nullable=False)

    # -- Components the broker reports for some account types only -----------
    #
    # NULL means "not reported", never zero. An unrealized M2M of zero is a
    # flat book; an unrealized M2M of NULL is an unanswered question.

    unrealized_mtm: Mapped[Money | None] = mapped_column(nullable=True)
    realized_mtm: Mapped[Money | None] = mapped_column(nullable=True)
    collateral: Mapped[Money | None] = mapped_column(nullable=True)
    utilised_span: Mapped[Money | None] = mapped_column(nullable=True)
    utilised_option_premium: Mapped[Money | None] = mapped_column(nullable=True)
    utilised_exposure: Mapped[Money | None] = mapped_column(nullable=True)

    #: Provenance. Non-nullable, and the reason this table can be audited: a
    #: development seed row and a genuine broker reading must never be
    #: indistinguishable. See `app.domain.enums.DataSource`.
    source: Mapped[Source] = mapped_column(nullable=False)

    created_at: Mapped[dt.datetime] = created_at_column()

    __table_args__ = (
        # The access pattern is "the latest snapshot for this account", so the
        # time column is indexed descending. An ascending index would still be
        # usable but makes the planner walk to the far end for every read.
        Index(
            "ix_broker_account_snapshots_account_captured",
            "broker",
            "client_code",
            captured_at.desc(),
        ),
        CheckConstraint(enum_check("source", DataSource), name="source"),
        # Cash and blocked margin cannot be negative. `net` deliberately can:
        # an account in debit is a real state, and a constraint forbidding it
        # would reject the very reading someone most needs to see.
        CheckConstraint("available_cash >= 0", name="available_cash_non_negative"),
        CheckConstraint("used_margin >= 0", name="used_margin_non_negative"),
    )
