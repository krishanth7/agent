"""Login, session lifetime and token custody.

THE TOTP SEED NEVER LEAVES THIS MODULE
--------------------------------------
`angel_one_totp_secret` is the base32 seed from the authenticator enrolment.
Anyone holding it can mint valid codes forever, which makes it strictly more
dangerous than the six-digit code it produces — a code is worthless in thirty
seconds, the seed is worthless never. It is read here, converted to a code, and
is not stored on any object, passed to any other layer, or included in any
error message. The generated code is likewise never logged.

WHY SESSION EXPIRY IS COMPUTED, NOT PARSED
------------------------------------------
Angel One's login response carries no expiry field. What it has instead is a
published policy: tokens are valid until midnight IST, regardless of when they
were issued or how recently they were used. A session minted at 23:58 is good
for two minutes. So `expires_at` is the next IST midnight, computed — which
turns "should I re-authenticate?" into a comparison instead of a failed request
and a retry.

CONCURRENCY
-----------
An `asyncio.Lock` guards the whole authenticate path. Without it, ten
simultaneous requests arriving on a cold process would each see no session and
each start a login, against an endpoint that permits one call per second. The
lock means nine of them wait and then find the session the first one created.
"""

from __future__ import annotations

import asyncio
import datetime as dt

import pyotp
from pydantic import SecretStr

from app.brokers.angel_one.client import AngelOneHttpClient
from app.brokers.angel_one.constants import (
    ROUTE_GENERATE_TOKENS,
    ROUTE_LOGIN,
    ROUTE_LOGOUT,
)
from app.brokers.exceptions import BrokerAuthenticationError, BrokerDataError
from app.brokers.models import BrokerSession
from app.core.config import Settings
from app.core.constants import IST
from app.core.logging import get_logger

logger = get_logger(__name__)


def next_ist_midnight(instant: dt.datetime) -> dt.datetime:
    """The next 00:00 IST strictly after `instant`.

    Takes the instant rather than reading the clock so the boundary is
    testable: a caller can hand it 23:59:59 and assert the session it produces
    lasts one second.
    """
    local = instant.astimezone(IST)
    tomorrow = local.date() + dt.timedelta(days=1)
    return dt.datetime.combine(tomorrow, dt.time.min, tzinfo=IST)


def generate_totp(secret: str) -> str:
    """Current six-digit code for a base32 seed.

    A malformed seed raises here rather than at the broker. The distinction
    matters: a broker rejection looks like "your credentials are wrong", which
    would send an operator to check the PIN when the real fault is a seed that
    was pasted with a trailing space or copied from the wrong field.

    The exception message names the setting and nothing else. It must never
    contain the seed, and must never contain the code either.
    """
    try:
        return pyotp.TOTP(secret).now()
    # Broad by necessity: pyotp validates the seed lazily inside `now()` and
    # signals a bad one with whatever base32 decoding raises, which is not a
    # documented exception type. Narrowing this would mean guessing.
    except Exception as exc:
        raise BrokerAuthenticationError(
            "ANGEL_ONE_TOTP_SECRET is not a valid base32 TOTP seed."
        ) from exc


class AngelOneAuthenticator:
    """Owns the session for one Angel One account.

    Deliberately not a singleton and not module state: it is constructed with
    settings and a client, which is what makes it possible to test a session
    expiring without waiting for midnight, and what would make a second account
    a second instance rather than a rewrite.
    """

    def __init__(self, settings: Settings, client: AngelOneHttpClient) -> None:
        self._settings = settings
        self._client = client
        self._session: BrokerSession | None = None
        self._lock = asyncio.Lock()

    @property
    def session(self) -> BrokerSession | None:
        """The current session, without attempting to create one."""
        return self._session

    async def authenticate(self, *, now: dt.datetime | None = None) -> BrokerSession:
        """Return a valid session, logging in only if there is not one already.

        Safe to call on every request. The common path takes the lock, finds a
        live session and returns it without touching the network.
        """
        moment = now or dt.datetime.now(tz=IST)
        async with self._lock:
            current = self._session
            if current is not None and not current.is_expired(moment):
                return current
            return await self._login(moment)

    async def _login(self, moment: dt.datetime) -> BrokerSession:
        """Exchange credentials for tokens. Caller must hold the lock."""
        settings = self._settings
        # `angel_one_configured` is checked by the adapter before construction,
        # so reaching here with a missing credential is a programming error.
        # Asserting the invariant with explicit reads keeps mypy honest about
        # the Optionals without inventing a runtime fallback.
        if (
            settings.angel_one_client_code is None
            or settings.angel_one_pin is None
            or settings.angel_one_totp_secret is None
        ):
            raise BrokerAuthenticationError(
                "Angel One credentials are incomplete; cannot authenticate."
            )

        totp = generate_totp(settings.angel_one_totp_secret.get_secret_value())

        # Logged before the call so a hung login is attributable. The payload
        # is deliberately not logged: it contains the PIN and the TOTP.
        logger.info(
            "Authenticating with Angel One as %s", settings.angel_one_client_code
        )

        data = await self._client.request(
            "POST",
            ROUTE_LOGIN,
            json={
                "clientcode": settings.angel_one_client_code,
                "password": settings.angel_one_pin.get_secret_value(),
                "totp": totp,
            },
            authenticated=False,
        )

        session = self._session_from_payload(
            data, client_code=settings.angel_one_client_code, moment=moment
        )
        self._adopt(session)
        logger.info("Angel One session established, valid until %s", session.expires_at)
        return session

    async def refresh(self, *, now: dt.datetime | None = None) -> BrokerSession:
        """Mint a new access token from the refresh token.

        Cheaper than a full login and does not consume a TOTP, which matters
        because a code can only be used once within its window. Falls back to a
        full login when there is no refresh token to use — there is no session
        to refresh on a cold process.
        """
        moment = now or dt.datetime.now(tz=IST)
        async with self._lock:
            current = self._session
            if current is None:
                return await self._login(moment)

            data = await self._client.request(
                "POST",
                ROUTE_GENERATE_TOKENS,
                json={"refreshToken": current.refresh_token.get_secret_value()},
                authenticated=False,
            )
            session = self._session_from_payload(
                data, client_code=current.client_code, moment=moment
            )
            self._adopt(session)
            return session

    async def logout(self) -> None:
        """End the session at the broker, then discard it locally.

        The local tokens are cleared in a `finally`, so a failed logout call
        still leaves this process holding nothing. The alternative — keeping a
        token because the logout request timed out — means the next request
        uses a credential the broker may already have revoked.

        Never raises. Logout is what a caller does while already handling a
        failure, and a cleanup path that can fail turns one problem into two.
        """
        if self._session is None:
            return
        client_code = self._session.client_code
        try:
            await self._client.request(
                "POST", ROUTE_LOGOUT, json={"clientcode": client_code}
            )
        except Exception:
            logger.warning("Angel One logout call failed; clearing tokens anyway")
        finally:
            self._session = None
            self._client.set_access_token(None)

    def _adopt(self, session: BrokerSession) -> None:
        """Store a session and arm the transport with its access token."""
        self._session = session
        self._client.set_access_token(session.access_token.get_secret_value())

    @staticmethod
    def _session_from_payload(
        data: object, *, client_code: str, moment: dt.datetime
    ) -> BrokerSession:
        """Build a `BrokerSession` from a login or refresh payload.

        All three tokens are mandatory. A response missing one is a contract
        violation and fails the whole call — a session holding an empty feed
        token would authenticate successfully and then fail incomprehensibly
        the first time anything tried to stream.
        """
        if not isinstance(data, dict):
            raise BrokerDataError("Angel One login returned no session data.")

        tokens: dict[str, str] = {}
        for key in ("jwtToken", "refreshToken", "feedToken"):
            value = data.get(key)
            if not isinstance(value, str) or not value:
                # The key name is safe to log; the value is the secret, and
                # it is absent by definition in this branch.
                raise BrokerDataError(f"Angel One login response is missing '{key}'.")
            tokens[key] = value

        return BrokerSession(
            access_token=SecretStr(tokens["jwtToken"]),
            refresh_token=SecretStr(tokens["refreshToken"]),
            feed_token=SecretStr(tokens["feedToken"]),
            issued_at=moment,
            expires_at=next_ist_midnight(moment),
            client_code=client_code,
        )
