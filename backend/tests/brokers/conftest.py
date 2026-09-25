"""Fixtures for the Angel One adapter suite.

NO NETWORK, EVER
----------------
Nothing in this package opens a socket. Every test drives the adapter through
`httpx.MockTransport`, which substitutes the transport layer *underneath*
`httpx` — so the real client code runs: real headers, real JSON bodies, real
status-code handling, real envelope parsing. Only the wire is fake.

That distinction matters. Stubbing `AngelOneAdapter.get_funds` would prove the
test double returns what the test double was told to return. Stubbing the
transport proves the header block is well-formed, the route is correct, the
error classifier fires on the right envelope, and the mapper rejects the right
malformed payloads.

The credentials below are obvious fakes. `TOTP_SECRET` is a valid base32 string
so `pyotp` accepts it; it is not, and must never be, a real enrolment seed.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from app.brokers.angel_one.adapter import AngelOneAdapter
from app.core.config import Settings
from pydantic import SecretStr

#: Base32, 16 characters — the shape pyotp expects. Entirely invented.
TOTP_SECRET = "JBSWY3DPEHPK3PXP"

JWT_TOKEN = "fake-jwt-token"
REFRESH_TOKEN = "fake-refresh-token"
FEED_TOKEN = "fake-feed-token"


def broker_settings(**overrides: Any) -> Settings:
    """Settings with a complete, fake Angel One credential set."""
    base: dict[str, Any] = {
        "environment": "development",
        "log_level": "WARNING",
        "repository_backend": "mock",
        "angel_one_enabled": True,
        "angel_one_api_key": SecretStr("fake-api-key"),
        "angel_one_client_code": "T0000001",
        "angel_one_pin": SecretStr("0000"),
        "angel_one_totp_secret": SecretStr(TOTP_SECRET),
    }
    base.update(overrides)
    return Settings(**base)


def envelope(data: Any, *, status: bool = True, errorcode: str = "") -> dict[str, Any]:
    """The SmartAPI response envelope every route wraps its payload in."""
    return {
        "status": status,
        "message": "SUCCESS" if status else "ERROR",
        "errorcode": errorcode,
        "data": data,
    }


LOGIN_DATA = {
    "jwtToken": JWT_TOKEN,
    "refreshToken": REFRESH_TOKEN,
    "feedToken": FEED_TOKEN,
    "state": "",
}


class RecordingRouter:
    """Routes mock responses by path and records what was sent.

    Recording the requests is the point: several tests assert on the *outgoing*
    side — that the login payload carries a six-digit TOTP, that a wide date
    range became four requests rather than one, that an authenticated route
    carried a bearer token. None of that is visible from the response.
    """

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self._handlers: dict[str, Callable[[httpx.Request], httpx.Response]] = {}

    def on(
        self, route: str, handler: Callable[[httpx.Request], httpx.Response]
    ) -> None:
        self._handlers[route] = handler

    def json_response(
        self, route: str, payload: dict[str, Any], *, status_code: int = 200
    ) -> None:
        """Always answer `route` with one fixed payload."""
        self.on(route, lambda _: httpx.Response(status_code, json=payload))

    def sequence(self, route: str, payloads: list[dict[str, Any]]) -> None:
        """Answer `route` with each payload in turn, repeating the last.

        Needed for the session-refresh test, where the same route must fail
        once and then succeed — which is exactly the behaviour a single fixed
        response cannot express.
        """
        remaining = list(payloads)

        def handler(_: httpx.Request) -> httpx.Response:
            payload = remaining.pop(0) if len(remaining) > 1 else remaining[0]
            return httpx.Response(200, json=payload)

        self.on(route, handler)

    def bodies_for(self, route: str) -> list[dict[str, Any]]:
        """Decoded JSON bodies of every recorded request to `route`."""
        return [
            json.loads(request.content)
            for request in self.requests
            if request.url.path == route and request.content
        ]

    def paths(self) -> list[str]:
        return [request.url.path for request in self.requests]

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        handler = self._handlers.get(request.url.path)
        if handler is None:
            # Loud rather than a 404. An unrouted path means the adapter called
            # somewhere the test did not anticipate, and a plausible-looking
            # error response would let that pass as a handled failure.
            raise AssertionError(f"Unexpected request to {request.url.path}")
        return handler(request)


@pytest.fixture
def router() -> RecordingRouter:
    """A router pre-wired for a successful login.

    Login is set up by default because almost every test needs a session
    before it can reach the route it actually cares about, and repeating the
    setup would bury the assertion under boilerplate.
    """
    routes = RecordingRouter()
    routes.json_response(
        "/rest/auth/angelbroking/user/v1/loginByPassword", envelope(LOGIN_DATA)
    )
    return routes


@pytest.fixture
def adapter(router: RecordingRouter) -> AngelOneAdapter:
    return AngelOneAdapter(broker_settings(), transport=httpx.MockTransport(router))
