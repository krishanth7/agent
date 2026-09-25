"""`broker_account_snapshots` against a real PostgreSQL.

WHY THESE CANNOT BE UNIT TESTS
------------------------------
Every assertion here is about something only the database enforces. A CHECK
constraint that PostgreSQL never evaluated is a comment; a NUMERIC(20,4) that
nothing round-tripped is a promise. The schema under test is built by the real
Alembic migration (see this package's conftest), so a migration that disagrees
with the model fails here rather than in production.

WHAT IS BEING PROTECTED
-----------------------
Two things, both about not lying. That a figure the broker never reported stays
NULL instead of becoming zero, and that a money column survives storage exactly
rather than approximately. The rest of the application is written assuming both,
and neither is visible from Python alone.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

import pytest
from app.db.models import BrokerAccountSnapshot
from app.domain.enums import DataSource
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio

CAPTURED_AT = dt.datetime(2026, 9, 25, 10, 15, tzinfo=dt.UTC)


def snapshot(**overrides: object) -> BrokerAccountSnapshot:
    """A minimal valid row: the three mandatory figures and provenance."""
    values: dict[str, object] = {
        "broker": "angel_one",
        "client_code": "T0000001",
        "captured_at": CAPTURED_AT,
        "net": Decimal("25000.50"),
        "available_cash": Decimal("20000.25"),
        "used_margin": Decimal("5000.25"),
        "source": DataSource.BROKER.value,
    }
    values.update(overrides)
    return BrokerAccountSnapshot(**values)


async def assert_rejected(session: AsyncSession, row: BrokerAccountSnapshot) -> None:
    """Assert the database refuses `row`, then leave the session usable.

    The rollback is not incidental. A failed flush marks the transaction
    unusable, and without this the *fixture teardown* raises
    `PendingRollbackError` — which reports as an error against a test that
    actually passed, and buries the real result.
    """
    session.add(row)
    with pytest.raises((IntegrityError, DBAPIError)):
        await session.commit()
    await session.rollback()


class TestRoundTrip:
    async def test_money_survives_storage_exactly(
        self, db_session: AsyncSession
    ) -> None:
        """The point of NUMERIC over FLOAT, asserted end to end.

        `0.1 + 0.2 != 0.3` in binary floating point. If any layer between the
        model and the column were a float, the equality below would fail by a
        fraction of a paisa — which is exactly the error that compounds
        silently across a month of aggregation.
        """
        db_session.add(
            snapshot(
                net=Decimal("0.1"),
                available_cash=Decimal("0.2"),
                used_margin=Decimal("0.0001"),
            )
        )
        await db_session.commit()

        stored = (await db_session.execute(select(BrokerAccountSnapshot))).scalar_one()
        assert stored.net + stored.available_cash == Decimal("0.3")
        # Scale 4 is what makes sub-paisa charges representable at all.
        assert stored.used_margin == Decimal("0.0001")

    async def test_unreported_components_stay_null(
        self, db_session: AsyncSession
    ) -> None:
        """NULL means "the broker did not say", and must not become zero.

        An unrealized M2M of zero is a flat book. An unrealized M2M of NULL is
        an unanswered question. Collapsing the two would let a dashboard state
        a fact the broker never reported.
        """
        db_session.add(snapshot())
        await db_session.commit()

        stored = (await db_session.execute(select(BrokerAccountSnapshot))).scalar_one()
        assert stored.unrealized_mtm is None
        assert stored.realized_mtm is None
        assert stored.collateral is None
        assert stored.utilised_span is None

    async def test_a_zero_component_is_stored_as_zero(
        self, db_session: AsyncSession
    ) -> None:
        """The other half of the same distinction.

        A genuine zero must round-trip as zero rather than as NULL, or the
        column cannot express "reported, and it was nothing".
        """
        db_session.add(snapshot(realized_mtm=Decimal("0")))
        await db_session.commit()

        stored = (await db_session.execute(select(BrokerAccountSnapshot))).scalar_one()
        assert stored.realized_mtm == Decimal("0")
        assert stored.realized_mtm is not None

    async def test_captured_at_keeps_its_instant(
        self, db_session: AsyncSession
    ) -> None:
        """TIMESTAMPTZ, so the moment survives rather than the wall clock.

        A naive column would read back as whatever the server's zone implies,
        which silently reattributes a funds reading to a different minute.
        """
        db_session.add(snapshot())
        await db_session.commit()

        stored = (await db_session.execute(select(BrokerAccountSnapshot))).scalar_one()
        assert stored.captured_at.tzinfo is not None
        assert stored.captured_at == CAPTURED_AT

    async def test_created_at_is_defaulted_by_the_database(
        self, db_session: AsyncSession
    ) -> None:
        """Server-side, so a row inserted by a migration or by psql has one."""
        row = snapshot()
        db_session.add(row)
        await db_session.commit()
        await db_session.refresh(row)
        assert row.created_at is not None


class TestConstraints:
    async def test_an_unknown_source_is_rejected(
        self, db_session: AsyncSession
    ) -> None:
        """Provenance is a closed vocabulary, enforced by the database.

        This is what makes the table auditable: a row cannot claim to have come
        from somewhere the `DataSource` enum does not define, so a seeded
        figure can never be mistaken for a live broker reading.
        """
        await assert_rejected(db_session, snapshot(source="totally-made-up"))

    async def test_negative_available_cash_is_rejected(
        self, db_session: AsyncSession
    ) -> None:
        await assert_rejected(db_session, snapshot(available_cash=Decimal("-1")))

    async def test_negative_used_margin_is_rejected(
        self, db_session: AsyncSession
    ) -> None:
        await assert_rejected(db_session, snapshot(used_margin=Decimal("-0.0001")))

    async def test_a_negative_net_is_allowed(self, db_session: AsyncSession) -> None:
        """An account in debit is a real state, not a data error.

        A constraint forbidding it would reject the one reading a user most
        needs to see. Asserted so nobody "tidies up" the sign constraints into
        covering `net` as well.
        """
        db_session.add(snapshot(net=Decimal("-1500.00")))
        await db_session.commit()

        stored = (await db_session.execute(select(BrokerAccountSnapshot))).scalar_one()
        assert stored.net == Decimal("-1500.00")

    @pytest.mark.parametrize(
        "missing", ["net", "available_cash", "used_margin", "source"]
    )
    async def test_the_mandatory_columns_are_not_nullable(
        self, db_session: AsyncSession, missing: str
    ) -> None:
        """A balance the broker always reports must never be absent.

        The mapper already refuses to default these; this asserts the database
        would refuse too, so a future writer that bypasses the mapper cannot
        insert an account summary with no balance in it.
        """
        row = snapshot()
        setattr(row, missing, None)
        await assert_rejected(db_session, row)


class TestAppendOnlyHistory:
    async def test_the_same_account_may_have_many_snapshots(
        self, db_session: AsyncSession
    ) -> None:
        """This is a log, not a current-state row.

        A unique key on (broker, client_code) would force one row per account
        and destroy the history the table exists to keep.
        """
        for minute in range(3):
            db_session.add(
                snapshot(
                    captured_at=CAPTURED_AT + dt.timedelta(minutes=minute),
                    net=Decimal("25000.50") + minute,
                )
            )
        await db_session.commit()

        rows = (await db_session.execute(select(BrokerAccountSnapshot))).scalars().all()
        assert len(rows) == 3

    async def test_two_accounts_are_distinguishable(
        self, db_session: AsyncSession
    ) -> None:
        """Without the client code a multi-account deployment could not tell
        two balances apart."""
        db_session.add(snapshot(client_code="T0000001", net=Decimal("100")))
        db_session.add(snapshot(client_code="T0000002", net=Decimal("200")))
        await db_session.commit()

        result = await db_session.execute(
            select(BrokerAccountSnapshot.net).where(
                BrokerAccountSnapshot.client_code == "T0000002"
            )
        )
        assert result.scalar_one() == Decimal("200")

    async def test_the_latest_snapshot_query_uses_captured_at(
        self, db_session: AsyncSession
    ) -> None:
        """The access pattern the descending index exists to serve."""
        for minute, amount in enumerate(("100", "200", "300")):
            db_session.add(
                snapshot(
                    captured_at=CAPTURED_AT + dt.timedelta(minutes=minute),
                    net=Decimal(amount),
                )
            )
        await db_session.commit()

        latest = await db_session.execute(
            select(BrokerAccountSnapshot)
            .where(
                BrokerAccountSnapshot.broker == "angel_one",
                BrokerAccountSnapshot.client_code == "T0000001",
            )
            .order_by(BrokerAccountSnapshot.captured_at.desc())
            .limit(1)
        )
        assert latest.scalar_one().net == Decimal("300")

    async def test_ids_are_generated_by_python_not_the_database(
        self, db_session: AsyncSession
    ) -> None:
        """A UUID from `uuid.uuid4`, applied at flush rather than by the server.

        Note what this does *not* claim: the id is not populated at
        construction. SQLAlchemy applies a Python-side `default` during flush,
        so `snapshot().id` is None until then. What matters is that the value
        comes from the application — the column has no server default to read
        back — so two rows written concurrently by different workers cannot
        collide, and no sequence needs coordinating between them.
        """
        row = snapshot()
        assert BrokerAccountSnapshot.__table__.c.id.server_default is None

        db_session.add(row)
        await db_session.flush()

        assert isinstance(row.id, uuid.UUID)
        other = snapshot(captured_at=CAPTURED_AT + dt.timedelta(minutes=1))
        db_session.add(other)
        await db_session.flush()
        assert other.id != row.id
        await db_session.commit()


class TestNoCredentialColumns:
    # `async` only to satisfy the module-level asyncio mark; this inspects the
    # table definition and touches no database.
    async def test_no_token_can_be_persisted_here(self) -> None:
        """A bearer token in a row is a bearer token in every backup.

        The columns simply do not exist, so there is nowhere for a well-meaning
        future writer to put one. Asserted rather than left to the docstring.
        """
        columns = set(BrokerAccountSnapshot.__table__.columns.keys())
        forbidden = {
            "access_token",
            "refresh_token",
            "feed_token",
            "jwt_token",
            "password",
            "pin",
            "totp_secret",
            "api_key",
        }
        assert columns & forbidden == set()
