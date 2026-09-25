"""Broker connection service.

WHAT THIS OWNS
--------------
The adapter's lifetime. An Angel One session is process state: it costs a login
against a one-per-second endpoint to create, it consumes a TOTP code that cannot
be reused inside its window, and it stays valid until midnight IST regardless of
activity. Constructing an adapter per request would therefore mean logging in per
request, which locks the account rather than serving the dashboard.

So the adapter is built lazily, once, and kept. Lazily because `AngelOneAdapter`
refuses to construct without a complete credential set — and the status endpoint
must keep working precisely when credentials are absent, since saying so is its
job.

WHAT THIS DELIBERATELY DOES NOT DO
----------------------------------
It never logs in on behalf of `get_status`. Status is answered from settings and
from whatever session already exists, with no network call at all. A status
endpoint that authenticates is a status endpoint that can hang for ten seconds
on a broker timeout, and that fires a login every time a dashboard polls it.

It also has no method that places, modifies or cancels an order, because the
adapter it wraps has none to call.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable

from app.brokers.angel_one.adapter import AngelOneAdapter
from app.brokers.models import BrokerSession
from app.core.config import Settings
from app.core.constants import IST
from app.schemas.broker import BrokerConnectionTestResponse, BrokerStatusResponse

#: How many trailing characters of a client code survive masking.
#:
#: Two, which is enough for an operator to recognise their own account and not
#: enough to be worth harvesting. Angel One client codes are short, so revealing
#: a prefix as well would leave very little masked.
_VISIBLE_SUFFIX = 2

#: The broker this service talks to. One broker in this phase; the field exists
#: in the response so that a second one does not change the contract.
BROKER_NAME = "angel_one"


def mask_client_code(client_code: str) -> str:
    """Replace all but the last few characters with asterisks.

    A code short enough that masking would not hide anything is masked
    completely rather than partially. Returning a two-character code unchanged
    because it happens to be short is the kind of edge case that turns a
    redaction helper into a leak.
    """
    if len(client_code) <= _VISIBLE_SUFFIX:
        return "*" * len(client_code)
    return "*" * (len(client_code) - _VISIBLE_SUFFIX) + client_code[-_VISIBLE_SUFFIX:]


class BrokerService:
    """Reports broker connection state and performs an explicit connection test.

    `adapter_factory` exists so a test can supply an adapter built over an
    `httpx.MockTransport`. That keeps the tests running the *real* auth flow,
    mapper and error translation with only the socket replaced — a hand-written
    fake adapter would assert that this service works against a fiction.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        adapter_factory: Callable[[], AngelOneAdapter] | None = None,
    ) -> None:
        self._settings = settings
        self._adapter_factory = adapter_factory or (lambda: AngelOneAdapter(settings))
        self._adapter: AngelOneAdapter | None = None

    @property
    def settings(self) -> Settings:
        """The configuration this service was built against.

        Read by the dependency provider to decide whether a cached instance
        still belongs to the app making the request.
        """
        return self._settings

    def _get_adapter(self) -> AngelOneAdapter:
        """The adapter, constructing it on first use.

        Raises `BrokerConfigurationError` from the adapter's own constructor
        when credentials are incomplete. Not caught here: "not configured" is a
        409 with a message telling the operator what to set, which is more
        useful than any fallback this service could invent.
        """
        if self._adapter is None:
            self._adapter = self._adapter_factory()
        return self._adapter

    async def aclose(self) -> None:
        """Release the adapter's connection pool, if one was ever opened.

        Does not log out. Closing a socket and ending a broker session are
        separate decisions — see `AngelOneAdapter.aclose`.
        """
        if self._adapter is not None:
            await self._adapter.aclose()
            self._adapter = None

    async def get_status(self) -> BrokerStatusResponse:
        """Report configuration and session state without touching the network.

        `async` to match every other service method, not because it awaits
        anything. A caller should not have to know which status checks happen to
        need I/O today.
        """
        settings = self._settings
        session = self._current_session()

        return BrokerStatusResponse(
            broker=BROKER_NAME,
            enabled=settings.angel_one_enabled,
            configured=settings.angel_one_configured,
            connected=session is not None,
            client_code=(
                mask_client_code(settings.angel_one_client_code)
                if settings.angel_one_client_code is not None
                else None
            ),
            session_expires_at=session.expires_at if session is not None else None,
            live_trading_enabled=settings.live_trading_enabled,
            paper_trading_enabled=settings.paper_trading_enabled,
        )

    def _current_session(self) -> BrokerSession | None:
        """The live session, or `None` — including when one has lapsed.

        An expired session is reported as no session. The adapter would silently
        re-authenticate on the next data call, so treating a lapsed token as
        "connected" would have the status endpoint assert a live connection on
        the strength of a credential the broker has already stopped accepting.

        Reads the adapter only if one has been built. Building one here would
        raise when unconfigured, which is the one case this must survive.
        """
        if self._adapter is None:
            return None
        session = self._adapter.session
        if session is None or session.is_expired(dt.datetime.now(tz=IST)):
            return None
        return session

    async def test_connection(self) -> BrokerConnectionTestResponse:
        """Authenticate if necessary, then read the profile back.

        Two steps, because either alone proves less than it appears to. A login
        that succeeds says the credentials are good but not that the account can
        be read; a profile read alone cannot run without a session. Together
        they establish that this deployment can actually talk to this account.

        Nothing is written and nothing is persisted. The heaviest thing this
        does at the broker is create a session that was going to be created by
        the first data call anyway.
        """
        adapter = self._get_adapter()
        session = await adapter.authenticate()
        profile = await adapter.get_profile()

        return BrokerConnectionTestResponse(
            broker=BROKER_NAME,
            # From the profile, not from settings: the point of the round trip
            # is to report the account the *broker* says we reached. Echoing the
            # configured value back would make a successful login against the
            # wrong account indistinguishable from one against the right one.
            client_code=mask_client_code(profile.client_code),
            client_name=profile.name,
            exchanges=profile.exchanges,
            session_expires_at=session.expires_at,
            checked_at=dt.datetime.now(tz=IST),
        )
