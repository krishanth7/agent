"""broker account snapshots

Adds `broker_account_snapshots`: an append-only log of what a broker said an
account's funds were, and when. See `app.db.models.broker_account` for why the
table is shaped this way — in particular why no token is stored and why most
figures are nullable.

NOT A HYPERTABLE, DELIBERATELY
------------------------------
The initial revision converts three tables with `create_hypertable`. This one
does not, and the omission is a decision rather than an oversight: one row per
poll per account is a few hundred rows a day, five orders of magnitude below
`option_quotes`. Chunking would add planning overhead for no exclusion benefit,
and the conversion is one-way.

FULLY REVERSIBLE
----------------
A plain table and one index, so `downgrade()` genuinely restores the prior
schema — unlike the initial revision, where dropping a hypertable is the only
available undo.

Revision ID: 5a8a33cf9950
Revises: 097a184c6dd8
Create Date: 2026-09-25 07:48:31.126136+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5a8a33cf9950"
down_revision: str | None = "097a184c6dd8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "broker_account_snapshots",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("broker", sa.String(length=32), nullable=False),
        sa.Column("client_code", sa.String(length=32), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("net", sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column("available_cash", sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column("used_margin", sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column("unrealized_mtm", sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column("realized_mtm", sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column("collateral", sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column("utilised_span", sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column(
            "utilised_option_premium",
            sa.Numeric(precision=20, scale=4),
            nullable=True,
        ),
        sa.Column(
            "utilised_exposure", sa.Numeric(precision=20, scale=4), nullable=True
        ),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source IN ('broker', 'database', 'development_seed', 'mock', 'nse', "
            "'simulation')",
            name=op.f("ck_broker_account_snapshots_source"),
        ),
        sa.CheckConstraint(
            "available_cash >= 0",
            name=op.f("ck_broker_account_snapshots_available_cash_non_negative"),
        ),
        sa.CheckConstraint(
            "used_margin >= 0",
            name=op.f("ck_broker_account_snapshots_used_margin_non_negative"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_broker_account_snapshots")),
    )
    # Descending on the time column: every read is "the most recent snapshot
    # for this account", and an ascending index makes the planner walk to the
    # far end of the range for each one.
    op.create_index(
        "ix_broker_account_snapshots_account_captured",
        "broker_account_snapshots",
        ["broker", "client_code", sa.literal_column("captured_at DESC")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_broker_account_snapshots_account_captured",
        table_name="broker_account_snapshots",
    )
    op.drop_table("broker_account_snapshots")
