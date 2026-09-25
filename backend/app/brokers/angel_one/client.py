"""Async HTTP transport for SmartAPI.

WHY NOT THE OFFICIAL SDK
------------------------
`smartapi-python` is synchronous and built on `requests`. Inside an async
FastAPI worker, one such call blocks the event loop for its full duration —
not just the caller's request, but every other request the process is serving.
A ten-second broker timeout would stall the health endpoint with it.

Worse, its constructor has side effects before any call is made: it resolves
the machine's public IP over the network and reads the host's MAC address.
That is a blocking outbound request during object construction and a hardware
identifier collected without the operator asking for it.

So this module speaks to the documented REST routes directly over `httpx`.
The routes, headers and payload shapes are the SDK's and the documentation's;
only the transport is ours.

WHAT THIS LAYER IS RESPONSIBLE FOR
----------------------------------
Exactly two things: putting a well-formed request on the wire, and turning
whatever comes back into either a `dict` of business data or a `BrokerError`.
It does not know what a position is. Nothing above it should ever see an
`httpx` exception, a status code, or the broker's envelope.
"""

from __future__ import annotations

import socket
from types import TracebackType
from typing import Any, Final, NoReturn, Self

import httpx

from app.brokers.angel_one.constants import (
    API_ROOT,
    AUTHENTICATION_ERROR_CODES,
    ERROR_CODE_KEYS,
    SESSION_ERROR_CODES,
    UNAVAILABLE_ERROR_CODES,
)
from app.brokers.exceptions import (
    BrokerAuthenticationError,
    BrokerAuthorizationError,
    BrokerDataError,
    BrokerError,
    BrokerNetworkError,
    BrokerRateLimitError,
    BrokerSessionExpiredError,
    BrokerUnavailableError,
)
from app.core.logging import get_logger

logger = get_logger(__name__)

#: Sent as `X-MACAddress` and `X-ClientPublicIP` when nothing is configured.
#:
#: The official SDK reads the host's real MAC address and calls out to an
#: external service to learn the public IP. Both are identifiers about the
#: operator's machine, collected silently, for headers that SmartAPI requires
#: to be *present* rather than to be *correct*. Sending a constant keeps the
#: request well-formed without turning a broker client into a fingerprinter.
#:
#: If a deployment is IP-allowlisted and the header value starts mattering, set
#: `angel_one_primary_static_ip` and it is used instead.
_PLACEHOLDER_MAC: Final = "00:00:00:00:00:00"
_PLACEHOLDER_PUBLIC_IP: Final = "0.0.0.0"  # noqa: S104


def _local_ip() -> str:
    """The host's address on its own network, or a loopback if undiscoverable.

    Uses a UDP socket, which despite the `connect` call sends no packets and
    needs nothing at the other end — it only asks the routing table which
    interface would be used. Wrapped because a machine with no route at all is
    a perfectly normal state for a container at startup, and failing to fill in
    a cosmetic header is not a reason to fail a broker request.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("8.8.8.8", 80))
            address: str = probe.getsockname()[0]
            return address
    except OSError:
        return "127.0.0.1"


class AngelOneHttpClient:
    """A thin, session-aware HTTP client for one SmartAPI account.

    Holds the `httpx.AsyncClient` and the current access token. The token is
    set by the auth layer after a successful login and cleared on logout; this
    class never derives one itself, so there is no path by which credentials
    reach the transport.
    """

    def __init__(
        self,
        *,
        api_key: str,
        timeout: float,
        client_public_ip: str | None = None,
        mac_address: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._local_ip = _local_ip()
        self._public_ip = client_public_ip or _PLACEHOLDER_PUBLIC_IP
        self._mac_address = mac_address or _PLACEHOLDER_MAC
        self._access_token: str | None = None
        # `transport` is injectable purely so tests can supply
        # `httpx.MockTransport` and exercise the real request-building and
        # error-classification code rather than a stubbed stand-in of it.
        self._http = httpx.AsyncClient(
            base_url=API_ROOT,
            timeout=timeout,
            transport=transport,
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()

    def set_access_token(self, token: str | None) -> None:
        """Install or clear the bearer token used by authenticated routes."""
        self._access_token = token

    @property
    def has_access_token(self) -> bool:
        return self._access_token is not None

    def _headers(self, *, authenticated: bool) -> dict[str, str]:
        """The header block SmartAPI requires on every request.

        All of `X-UserType` through `X-PrivateKey` are mandatory; a request
        missing any of them is rejected before it reaches a handler. The values
        of the IP and MAC headers are not validated by the broker — see the
        placeholder constants above for why that matters.
        """
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-UserType": "USER",
            "X-SourceID": "WEB",
            "X-ClientLocalIP": self._local_ip,
            "X-ClientPublicIP": self._public_ip,
            "X-MACAddress": self._mac_address,
            "X-PrivateKey": self._api_key,
        }
        if authenticated:
            if self._access_token is None:
                # Not a broker error — a programming one. Reaching an
                # authenticated route with no token means the call sequence is
                # wrong, and pretending it is a session expiry would send the
                # caller into a refresh loop that cannot succeed.
                raise BrokerSessionExpiredError(
                    "No Angel One access token is present; authenticate first."
                )
            headers["Authorization"] = f"Bearer {self._access_token}"
        return headers

    async def request(
        self,
        method: str,
        route: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        authenticated: bool = True,
    ) -> Any:
        """Call one SmartAPI route and return its `data` payload.

        Returns whatever sits under `data` — a dict for most routes, a list for
        the book endpoints — or raises. `Any` is honest here: the shape varies
        per route and it is the mapper's job, not the transport's, to know
        which is which.
        """
        try:
            response = await self._http.request(
                method,
                route,
                json=json,
                params=params,
                headers=self._headers(authenticated=authenticated),
            )
        except httpx.TimeoutException as exc:
            raise BrokerNetworkError(
                f"Angel One did not respond within the timeout ({route})."
            ) from exc
        except httpx.TransportError as exc:
            # Covers DNS failure, refused connections, TLS errors and reset
            # sockets. All of them mean the same thing to a caller: no answer
            # arrived, and retrying may work.
            raise BrokerNetworkError(
                f"Angel One could not be reached ({route})."
            ) from exc

        return self._interpret(response, route)

    def _interpret(self, response: httpx.Response, route: str) -> Any:
        """Turn one HTTP response into business data or a typed failure."""
        # HTTP-level failures are classified first, because a 429 or a 503 may
        # carry an HTML error page rather than the JSON envelope, and trying to
        # parse it would report a throttle as a data fault.
        if response.status_code == httpx.codes.TOO_MANY_REQUESTS:
            raise BrokerRateLimitError()
        if response.status_code == httpx.codes.FORBIDDEN:
            # SmartAPI returns 403 both for a rate-limited caller and for a
            # genuinely forbidden action. The envelope distinguishes them when
            # there is one; without it, authorization is the safer report,
            # because it does not invite an immediate retry.
            raise BrokerAuthorizationError()
        if response.status_code >= httpx.codes.INTERNAL_SERVER_ERROR:
            raise BrokerUnavailableError(
                f"Angel One returned {response.status_code} for {route}."
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise BrokerDataError(
                f"Angel One returned a non-JSON body for {route}."
            ) from exc

        if not isinstance(payload, dict):
            raise BrokerDataError(
                f"Angel One returned {type(payload).__name__} rather than an "
                f"object for {route}."
            )

        if payload.get("status") is True:
            # `data` is absent on some success responses (logout, for one).
            # That is a valid success, not a missing field.
            return payload.get("data")

        self._raise_for_envelope(payload, route)

    def _raise_for_envelope(self, payload: dict[str, Any], route: str) -> NoReturn:
        """Translate a `status: false` envelope into the error taxonomy.

        The broker's own message is passed through, but the *code* drives the
        classification — a message is prose that can be reworded at any time,
        whereas a code is the contract.
        """
        code = ""
        for key in ERROR_CODE_KEYS:
            value = payload.get(key)
            if isinstance(value, str) and value:
                code = value
                break

        message = payload.get("message")
        detail = message if isinstance(message, str) and message else "no message"

        # Logged at the boundary because this is the only place the broker's
        # own code is visible. The envelope carries no token — `data` is null
        # on every failure — so logging the code and message leaks nothing,
        # and without it an operator has a generic 502 and no way to act.
        logger.warning(
            "Angel One rejected %s: code=%s message=%s",
            route,
            code or "<none>",
            detail,
        )

        if code in SESSION_ERROR_CODES:
            raise BrokerSessionExpiredError()
        if code in AUTHENTICATION_ERROR_CODES:
            raise BrokerAuthenticationError()
        if code in UNAVAILABLE_ERROR_CODES:
            raise BrokerUnavailableError()

        # An unrecognised code is reported as a generic broker failure rather
        # than guessed at. The specific code is in the log line above, which is
        # what an operator needs; picking a plausible category here would send
        # a caller down a recovery path chosen at random.
        raise BrokerError(f"Angel One rejected {route} (code {code or 'unknown'}).")
