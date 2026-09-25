"""SmartWebSocketV2 streaming client.

Architecture, and the reasoning behind each part.

SUBSCRIPTIONS ARE STATE, NOT CALLS
----------------------------------
`subscribe()` records a token in a set and, if connected, sends a frame. It
does not assume the connection survives. On reconnect the whole recorded set is
re-sent, because the server remembers nothing across a dropped socket — and a
client that only replays what it happened to send since the last disconnect
comes back subscribed to a subset of what the caller asked for, silently.

RECONNECT IS BOUNDED AND JITTERED
---------------------------------
Exponential backoff from one second to a cap, with jitter. The cap matters
because an unbounded backoff eventually means a feed that reconnects tomorrow;
the jitter matters because without it every client that dropped during the same
network blip retries in lockstep and re-creates the outage.

Reconnection stops permanently on an authentication failure. A bad token does
not become good by being retried, and a loop against a broker's auth endpoint
is how a wrong credential becomes a locked account.

HEARTBEAT
---------
The server drops a connection that has not spoken for about a minute. A "ping"
every ten seconds gives five chances to miss one before that happens.

WHAT THIS DOES NOT DO
---------------------
It does not persist ticks, and it does not subscribe to anything on its own.
Both are deliberate: the consumer decides what is worth storing, and a feed
that opened subscriptions by itself would be making a policy decision about
rate-limit quota that belongs to the caller.

It also cannot place orders. The order-update socket is a *separate* endpoint
which this module does not connect to, and receiving an order update would not
constitute placing one in any case.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import random
import secrets
from collections.abc import Awaitable, Callable
from typing import Final

import websockets
from websockets.asyncio.client import ClientConnection

from app.brokers.angel_one.constants import (
    FEED_HEARTBEAT_MESSAGE,
    FEED_HEARTBEAT_SECONDS,
    FEED_MAX_TOKENS,
    WEBSOCKET_URL,
    AngelFeedAction,
    AngelFeedExchangeType,
    AngelFeedMode,
)
from app.brokers.angel_one.feed_codec import decode_tick
from app.brokers.exceptions import BrokerDataError, BrokerError
from app.brokers.models import BrokerQuote
from app.core.logging import get_logger

logger = get_logger(__name__)

#: Backoff bounds for reconnection, in seconds.
#:
#: The cap is one minute rather than something larger: NSE sessions are six
#: hours long, and a feed that waits ten minutes between attempts can miss a
#: meaningful fraction of the trading day after a single blip.
_BACKOFF_INITIAL: Final = 1.0
_BACKOFF_CAP: Final = 60.0
_BACKOFF_FACTOR: Final = 2.0

TickHandler = Callable[[BrokerQuote], Awaitable[None]]


class SubscriptionRegistry:
    """What the caller has asked to receive, independent of any connection.

    Separated from the socket so that the "what should I be subscribed to?"
    question has an answer even while disconnected — which is precisely when
    it is needed, since that answer is what gets replayed on reconnect.

    Pure and synchronous, so the quota arithmetic can be tested without a
    WebSocket.
    """

    def __init__(self, *, max_tokens: int = FEED_MAX_TOKENS) -> None:
        self._max_tokens = max_tokens
        self._by_mode: dict[AngelFeedMode, dict[AngelFeedExchangeType, set[str]]] = {}

    @property
    def token_count(self) -> int:
        return sum(
            len(tokens)
            for segments in self._by_mode.values()
            for tokens in segments.values()
        )

    def add(
        self, mode: AngelFeedMode, segment: AngelFeedExchangeType, tokens: list[str]
    ) -> None:
        """Record tokens, refusing to exceed the broker's quota.

        The check happens before anything is added, so a batch that would
        overflow is rejected whole rather than partially applied. A registry
        holding half a request is worse than one holding none: the caller
        believes it is subscribed to instruments it is not receiving.
        """
        new = set(tokens) - self._by_mode.get(mode, {}).get(segment, set())
        if self.token_count + len(new) > self._max_tokens:
            raise BrokerError(
                f"Angel One permits {self._max_tokens} streaming tokens per "
                f"connection; this subscription would need "
                f"{self.token_count + len(new)}."
            )
        self._by_mode.setdefault(mode, {}).setdefault(segment, set()).update(new)

    def remove(
        self, mode: AngelFeedMode, segment: AngelFeedExchangeType, tokens: list[str]
    ) -> None:
        existing = self._by_mode.get(mode, {}).get(segment)
        if existing is None:
            return
        existing.difference_update(tokens)

    def request_frames(self, action: AngelFeedAction) -> list[dict[str, object]]:
        """Build one request frame per mode, as the protocol expects.

        Grouped by mode because the wire format carries a single mode per
        request with a list of segments beneath it — so a registry spanning
        three modes is three frames, not one.
        """
        frames: list[dict[str, object]] = []
        for mode, segments in self._by_mode.items():
            token_lists = [
                {"exchangeType": int(segment), "tokens": sorted(tokens)}
                for segment, tokens in segments.items()
                if tokens
            ]
            if not token_lists:
                continue
            frames.append(
                {
                    # A correlation ID the server echoes back, which is the
                    # only way to attribute a subscription error to the request
                    # that caused it.
                    "correlationID": secrets.token_hex(8),
                    "action": int(action),
                    "params": {"mode": int(mode), "tokenList": token_lists},
                }
            )
        return frames


class AngelOneFeed:
    """A reconnecting, heartbeating market-data stream.

    NOTE: the binary frame layout this depends on has not been verified against
    a live socket — see `feed_codec`. Nothing in this phase consumes the feed in
    production; it exists so the Phase 4 work extends a tested structure rather
    than starting from an empty file.
    """

    def __init__(
        self,
        *,
        api_key: str,
        client_code: str,
        feed_token: str,
        on_tick: TickHandler,
        url: str = WEBSOCKET_URL,
        max_tokens: int = FEED_MAX_TOKENS,
    ) -> None:
        self._api_key = api_key
        self._client_code = client_code
        self._feed_token = feed_token
        self._on_tick = on_tick
        self._url = url
        self._registry = SubscriptionRegistry(max_tokens=max_tokens)
        self._connection: ClientConnection | None = None
        self._stopping = asyncio.Event()

    @property
    def registry(self) -> SubscriptionRegistry:
        return self._registry

    @property
    def connected(self) -> bool:
        return self._connection is not None

    async def subscribe(
        self,
        mode: AngelFeedMode,
        segment: AngelFeedExchangeType,
        tokens: list[str],
    ) -> None:
        """Record a subscription and send it if a connection exists.

        Safe to call before `run()`. The registry is the source of truth, so a
        subscription made while disconnected takes effect as soon as the socket
        comes up.
        """
        self._registry.add(mode, segment, tokens)
        await self._send_registry(AngelFeedAction.SUBSCRIBE)

    async def unsubscribe(
        self,
        mode: AngelFeedMode,
        segment: AngelFeedExchangeType,
        tokens: list[str],
    ) -> None:
        connection = self._connection
        if connection is not None:
            frames = SubscriptionRegistry()
            frames.add(mode, segment, tokens)
            for frame in frames.request_frames(AngelFeedAction.UNSUBSCRIBE):
                await connection.send(json.dumps(frame))
        self._registry.remove(mode, segment, tokens)

    async def stop(self) -> None:
        """Ask `run()` to exit and close the socket."""
        self._stopping.set()
        connection = self._connection
        if connection is not None:
            await connection.close()

    async def run(self) -> None:
        """Connect, stream, and reconnect until stopped.

        Returns normally on `stop()`. Raises only for failures that retrying
        cannot fix.
        """
        backoff = _BACKOFF_INITIAL
        while not self._stopping.is_set():
            try:
                await self._session()
                backoff = _BACKOFF_INITIAL
            except websockets.InvalidStatus as exc:
                # A handshake rejection is about the credentials, not the
                # network. Retrying a rejected token only burns attempts
                # against an endpoint that will keep rejecting it.
                raise BrokerError(
                    f"Angel One refused the feed handshake "
                    f"({exc.response.status_code})."
                ) from exc
            except (OSError, websockets.WebSocketException) as exc:
                if self._stopping.is_set():
                    return
                logger.warning(
                    "Angel One feed disconnected (%s); reconnecting in %.1fs",
                    type(exc).__name__,
                    backoff,
                )
                await self._sleep_with_jitter(backoff)
                backoff = min(backoff * _BACKOFF_FACTOR, _BACKOFF_CAP)

    async def _sleep_with_jitter(self, backoff: float) -> None:
        """Wait, but not for exactly as long as everyone else.

        Without jitter every client that dropped during the same blip retries
        in lockstep and re-creates the outage it is recovering from.
        `random` is fine here: this is scheduling, not security.
        """
        delay = backoff * (0.5 + random.random() / 2)  # noqa: S311
        with contextlib.suppress(TimeoutError):
            # Waiting on the stop event rather than sleeping flat, so `stop()`
            # during a 60-second backoff returns promptly instead of hanging
            # for the remainder of the wait.
            await asyncio.wait_for(self._stopping.wait(), timeout=delay)

    async def _session(self) -> None:
        """One connection's lifetime: connect, replay, heartbeat, read."""
        headers = {
            "Authorization": self._feed_token,
            "x-api-key": self._api_key,
            "x-client-code": self._client_code,
            "x-feed-token": self._feed_token,
        }
        async with websockets.connect(
            self._url, additional_headers=headers
        ) as connection:
            self._connection = connection
            logger.info("Angel One feed connected")
            # Replayed unconditionally. The server remembers nothing across a
            # dropped socket, so anything not re-sent here is silently no
            # longer being received.
            await self._send_registry(AngelFeedAction.SUBSCRIBE)

            heartbeat = asyncio.create_task(self._heartbeat(connection))
            try:
                await self._read(connection)
            finally:
                heartbeat.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await heartbeat
                self._connection = None

    async def _heartbeat(self, connection: ClientConnection) -> None:
        while True:
            await asyncio.sleep(FEED_HEARTBEAT_SECONDS)
            await connection.send(FEED_HEARTBEAT_MESSAGE)

    async def _read(self, connection: ClientConnection) -> None:
        """Consume frames until the socket closes.

        A frame that fails to decode is logged and skipped rather than killing
        the connection. One malformed tick is not a reason to stop receiving
        the other nine hundred instruments — but it *is* logged, because a
        decoder silently discarding frames would look exactly like a quiet
        market.
        """
        async for message in connection:
            if isinstance(message, str):
                # Text frames are protocol chatter: heartbeat replies and
                # subscription errors. Neither is a tick.
                self._log_text_frame(message)
                continue
            try:
                await self._on_tick(decode_tick(message))
            except BrokerDataError as exc:
                logger.warning("Discarding an undecodable feed frame: %s", exc.message)

    @staticmethod
    def _log_text_frame(message: str) -> None:
        if message.strip().lower() in {"pong", FEED_HEARTBEAT_MESSAGE}:
            return
        logger.info("Angel One feed message: %s", message[:200])

    async def _send_registry(self, action: AngelFeedAction) -> None:
        connection = self._connection
        if connection is None:
            return
        for frame in self._registry.request_frames(action):
            await connection.send(json.dumps(frame))
