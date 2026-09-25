"""The streaming client: subscription state, replay, and reconnect policy.

NO SOCKET, BUT THE REAL CONTROL FLOW
------------------------------------
`websockets.connect` is replaced by a fake that hands out scripted
connections. Everything above it is the real code: the real `run()` loop, the
real backoff arithmetic, the real registry replay, the real frame
serialisation. What the fake removes is the network, not the logic.

The fake records every frame sent, because the assertions that matter are
about the *outgoing* side — that a reconnect re-sends the whole subscription
set rather than the delta, that an unsubscribe actually leaves the wire, that
the correlation ID is present. None of that is observable from the inbound
direction.

WHY NO TEST WAITS
-----------------
`_sleep_with_jitter` is stubbed out in the reconnect tests so the backoff
*schedule* can be asserted without spending 1 + 2 + 4 seconds proving it. The
sleep's own behaviour — the jitter bounds, and waking early on `stop()` — is
tested separately and directly.
"""

from __future__ import annotations

import asyncio
import json
import struct
from collections.abc import AsyncIterator, Awaitable, Callable
from decimal import Decimal
from typing import Any

import pytest
import websockets
from app.brokers.angel_one.constants import (
    AngelFeedAction,
    AngelFeedExchangeType,
    AngelFeedMode,
)
from app.brokers.angel_one.feed import AngelOneFeed, SubscriptionRegistry
from app.brokers.exceptions import BrokerError
from app.brokers.models import BrokerQuote
from websockets.http11 import Response

from tests.brokers.conftest import FEED_TOKEN

NSE_FO = AngelFeedExchangeType.NSE_FO
NSE_CM = AngelFeedExchangeType.NSE_CM


def ltp_frame(token: bytes = b"43215", *, paise: int = 2402550) -> bytes:
    """A minimal valid LTP tick. The codec's own tests cover the layout."""
    buffer = bytearray(51)
    buffer[0] = int(AngelFeedMode.LTP)
    buffer[1] = int(NSE_FO)
    buffer[2 : 2 + len(token)] = token
    struct.pack_into("<q", buffer, 43, paise)
    return bytes(buffer)


class FakeConnection:
    """One scripted connection: yields messages, records what was sent."""

    def __init__(
        self, messages: list[bytes | str] | None = None, *, drop: bool = True
    ) -> None:
        self.messages = list(messages or [])
        self.sent: list[str | bytes] = []
        self.closed = False
        self._drop = drop
        #: Awaited once the scripted messages run out. This is how a test ends
        #: `run()` after a known number of sessions: stopping the feed *before*
        #: calling `run()` would mean the loop never iterates and no connection
        #: is opened at all.
        self.on_exhausted: Callable[[], Awaitable[None]] | None = None

    async def send(self, message: str | bytes) -> None:
        self.sent.append(message)

    async def close(self) -> None:
        self.closed = True

    def __aiter__(self) -> AsyncIterator[bytes | str]:
        return self._iterate()

    async def _iterate(self) -> AsyncIterator[bytes | str]:
        for message in self.messages:
            yield message
        if self.on_exhausted is not None:
            await self.on_exhausted()
        if self._drop:
            # How a real socket ends when the network goes away, rather than a
            # clean StopAsyncIteration — the reconnect path is only exercised
            # by an exception.
            raise websockets.ConnectionClosedError(None, None)

    def frames(self) -> list[dict[str, Any]]:
        """The JSON request frames sent, ignoring heartbeat text."""
        decoded: list[dict[str, Any]] = []
        for message in self.sent:
            if isinstance(message, str) and message.startswith("{"):
                decoded.append(json.loads(message))
        return decoded

    def subscribed_tokens(self) -> set[str]:
        tokens: set[str] = set()
        for frame in self.frames():
            if frame["action"] != int(AngelFeedAction.SUBSCRIBE):
                continue
            for entry in frame["params"]["tokenList"]:
                tokens.update(entry["tokens"])
        return tokens


class FakeServer:
    """Hands out connections in order and records the handshake headers."""

    def __init__(self, connections: list[FakeConnection]) -> None:
        self._connections = list(connections)
        self.handed_out: list[FakeConnection] = []
        self.headers: list[dict[str, str]] = []
        self.urls: list[str] = []

    def __call__(self, url: str, **kwargs: Any) -> Any:
        self.urls.append(url)
        self.headers.append(dict(kwargs.get("additional_headers") or {}))
        if not self._connections:
            raise AssertionError("the feed opened more connections than scripted")
        connection = self._connections.pop(0)
        self.handed_out.append(connection)

        class _Context:
            async def __aenter__(self) -> FakeConnection:
                return connection

            async def __aexit__(self, *exc: object) -> bool:
                return False

        return _Context()


@pytest.fixture
def ticks() -> list[BrokerQuote]:
    return []


def make_feed(ticks: list[BrokerQuote], **overrides: Any) -> AngelOneFeed:
    async def on_tick(quote: BrokerQuote) -> None:
        ticks.append(quote)

    kwargs: dict[str, Any] = {
        "api_key": "fake-api-key",
        "client_code": "T0000001",
        "feed_token": FEED_TOKEN,
        "on_tick": on_tick,
    }
    kwargs.update(overrides)
    return AngelOneFeed(**kwargs)


def install(monkeypatch: pytest.MonkeyPatch, server: FakeServer) -> None:
    monkeypatch.setattr(
        "app.brokers.angel_one.feed.websockets.connect", server, raising=True
    )


async def run_until(feed: AngelOneFeed, last: FakeConnection) -> None:
    """Drive `run()` through to the end of `last`, then let it exit.

    The stop has to be armed from *inside* the session rather than before
    `run()`, because `run()` checks the stop event at the top of its loop —
    pre-stopping would return immediately without connecting.
    """
    last.on_exhausted = feed.stop
    await asyncio.wait_for(feed.run(), timeout=5)


def wire(frame: dict[str, object]) -> dict[str, Any]:
    """The frame as it would arrive at the broker.

    `request_frames` is typed `dict[str, object]`, so nested indexing needs a
    narrowing step anyway. Doing it by round-tripping through JSON rather than
    by casting means each assertion also proves the frame is serialisable —
    which is the actual requirement, since `_send_registry` calls
    `json.dumps` on it.
    """
    serialised: dict[str, Any] = json.loads(json.dumps(frame))
    return serialised


def no_sleep(monkeypatch: pytest.MonkeyPatch, feed: AngelOneFeed) -> list[float]:
    """Replace the backoff wait, recording the delays it was asked for."""
    delays: list[float] = []

    async def fake(backoff: float) -> None:
        delays.append(backoff)

    monkeypatch.setattr(feed, "_sleep_with_jitter", fake)
    return delays


class TestRegistryQuota:
    def test_a_batch_that_would_overflow_is_rejected_whole(self) -> None:
        """Partial application is worse than refusal.

        A registry holding half a request means the caller believes it is
        subscribed to instruments it will never receive, with nothing to
        indicate that.
        """
        registry = SubscriptionRegistry(max_tokens=10)
        registry.add(AngelFeedMode.LTP, NSE_FO, [str(n) for n in range(8)])
        with pytest.raises(BrokerError):
            registry.add(AngelFeedMode.LTP, NSE_FO, [str(n) for n in range(100, 110)])
        assert registry.token_count == 8

    def test_the_quota_is_counted_across_modes_and_segments(self) -> None:
        """The broker's limit is per connection, not per mode.

        Counting per mode would let three modes of 400 tokens through a
        1000-token cap.
        """
        registry = SubscriptionRegistry(max_tokens=5)
        registry.add(AngelFeedMode.LTP, NSE_FO, ["1", "2"])
        registry.add(AngelFeedMode.QUOTE, NSE_CM, ["3", "4"])
        assert registry.token_count == 4
        with pytest.raises(BrokerError):
            registry.add(AngelFeedMode.SNAP_QUOTE, NSE_FO, ["5", "6"])

    def test_resubscribing_the_same_token_does_not_consume_quota(self) -> None:
        """Otherwise a reconnect loop would exhaust the cap against itself."""
        registry = SubscriptionRegistry(max_tokens=2)
        for _ in range(5):
            registry.add(AngelFeedMode.LTP, NSE_FO, ["1", "2"])
        assert registry.token_count == 2

    def test_a_batch_exactly_filling_the_quota_is_allowed(self) -> None:
        """An off-by-one here would refuse the last legal subscription."""
        registry = SubscriptionRegistry(max_tokens=3)
        registry.add(AngelFeedMode.LTP, NSE_FO, ["1", "2", "3"])
        assert registry.token_count == 3

    def test_removing_frees_quota(self) -> None:
        registry = SubscriptionRegistry(max_tokens=2)
        registry.add(AngelFeedMode.LTP, NSE_FO, ["1", "2"])
        registry.remove(AngelFeedMode.LTP, NSE_FO, ["1"])
        registry.add(AngelFeedMode.LTP, NSE_FO, ["3"])
        assert registry.token_count == 2

    def test_removing_something_never_added_is_not_an_error(self) -> None:
        registry = SubscriptionRegistry()
        registry.remove(AngelFeedMode.LTP, NSE_FO, ["nope"])
        assert registry.token_count == 0


class TestRequestFrames:
    def test_one_frame_per_mode_with_segments_nested(self) -> None:
        """The wire format carries a single mode per request.

        So a registry spanning two modes is two frames — flattening them into
        one would send a mode that applies to tokens it was not requested for.
        """
        registry = SubscriptionRegistry()
        registry.add(AngelFeedMode.LTP, NSE_FO, ["1"])
        registry.add(AngelFeedMode.LTP, NSE_CM, ["2"])
        registry.add(AngelFeedMode.SNAP_QUOTE, NSE_FO, ["3"])

        frames = [
            wire(frame) for frame in registry.request_frames(AngelFeedAction.SUBSCRIBE)
        ]
        assert len(frames) == 2
        by_mode = {frame["params"]["mode"]: frame for frame in frames}
        assert set(by_mode) == {int(AngelFeedMode.LTP), int(AngelFeedMode.SNAP_QUOTE)}
        assert len(by_mode[int(AngelFeedMode.LTP)]["params"]["tokenList"]) == 2

    def test_every_frame_carries_a_distinct_correlation_id(self) -> None:
        """It is the only way to attribute a subscription error to a request."""
        registry = SubscriptionRegistry()
        registry.add(AngelFeedMode.LTP, NSE_FO, ["1"])
        registry.add(AngelFeedMode.QUOTE, NSE_FO, ["2"])
        ids = {
            frame["correlationID"]
            for frame in registry.request_frames(AngelFeedAction.SUBSCRIBE)
        }
        assert len(ids) == 2
        assert all(ids)

    def test_a_mode_emptied_by_removal_produces_no_frame(self) -> None:
        """An empty tokenList is a malformed request, not a no-op."""
        registry = SubscriptionRegistry()
        registry.add(AngelFeedMode.LTP, NSE_FO, ["1"])
        registry.remove(AngelFeedMode.LTP, NSE_FO, ["1"])
        assert registry.request_frames(AngelFeedAction.SUBSCRIBE) == []

    def test_the_action_is_carried_as_the_protocol_integer(self) -> None:
        registry = SubscriptionRegistry()
        registry.add(AngelFeedMode.LTP, NSE_FO, ["1"])
        frame = registry.request_frames(AngelFeedAction.UNSUBSCRIBE)[0]
        assert frame["action"] == int(AngelFeedAction.UNSUBSCRIBE) == 0

    def test_tokens_are_serialised_as_json_not_repr(self) -> None:
        """A set would not survive `json.dumps`; the sorted list must."""
        registry = SubscriptionRegistry()
        registry.add(AngelFeedMode.LTP, NSE_FO, ["9", "1", "5"])
        frame = registry.request_frames(AngelFeedAction.SUBSCRIBE)[0]
        assert json.loads(json.dumps(frame))["params"]["tokenList"][0]["tokens"] == [
            "1",
            "5",
            "9",
        ]


class TestSubscriptionLifecycle:
    @pytest.mark.asyncio
    async def test_subscribing_before_connecting_is_recorded_not_lost(
        self, ticks: list[BrokerQuote]
    ) -> None:
        """The registry is the source of truth, so this must not need a socket.

        Requiring `run()` first would make startup ordering load-bearing.
        """
        feed = make_feed(ticks)
        await feed.subscribe(AngelFeedMode.LTP, NSE_FO, ["43215"])
        assert feed.registry.token_count == 1
        assert not feed.connected

    @pytest.mark.asyncio
    async def test_the_registry_is_replayed_on_connect(
        self, ticks: list[BrokerQuote], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        feed = make_feed(ticks)
        await feed.subscribe(AngelFeedMode.LTP, NSE_FO, ["43215", "43216"])
        connection = FakeConnection([ltp_frame()], drop=False)
        server = FakeServer([connection])
        install(monkeypatch, server)
        no_sleep(monkeypatch, feed)

        await run_until(feed, connection)

        assert connection.subscribed_tokens() == {"43215", "43216"}

    @pytest.mark.asyncio
    async def test_unsubscribe_leaves_the_wire_and_the_registry(
        self, ticks: list[BrokerQuote], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Both, because either alone is a bug.

        Registry-only keeps the broker streaming tokens nobody wants against
        the quota; wire-only means a reconnect silently resubscribes them.
        """
        feed = make_feed(ticks)
        connection = FakeConnection([ltp_frame()], drop=False)
        install(monkeypatch, FakeServer([connection]))
        no_sleep(monkeypatch, feed)

        await feed.subscribe(AngelFeedMode.LTP, NSE_FO, ["1", "2"])

        # Unsubscribe from inside the session, so it goes through a live
        # socket rather than by assigning the private connection attribute.
        async def drop_one() -> None:
            await feed.unsubscribe(AngelFeedMode.LTP, NSE_FO, ["1"])
            await feed.stop()

        connection.on_exhausted = drop_one
        await asyncio.wait_for(feed.run(), timeout=5)

        actions = [frame["action"] for frame in connection.frames()]
        assert int(AngelFeedAction.UNSUBSCRIBE) in actions
        assert feed.registry.token_count == 1

    @pytest.mark.asyncio
    async def test_unsubscribing_while_disconnected_still_updates_state(
        self, ticks: list[BrokerQuote]
    ) -> None:
        """So the next connect does not resubscribe a dropped instrument."""
        feed = make_feed(ticks)
        await feed.subscribe(AngelFeedMode.LTP, NSE_FO, ["1", "2"])
        await feed.unsubscribe(AngelFeedMode.LTP, NSE_FO, ["1"])
        assert feed.registry.token_count == 1

    @pytest.mark.asyncio
    async def test_the_quota_error_propagates_to_the_caller(
        self, ticks: list[BrokerQuote]
    ) -> None:
        feed = make_feed(ticks, max_tokens=1)
        await feed.subscribe(AngelFeedMode.LTP, NSE_FO, ["1"])
        with pytest.raises(BrokerError):
            await feed.subscribe(AngelFeedMode.LTP, NSE_FO, ["2"])


class TestHandshake:
    @pytest.mark.asyncio
    async def test_the_feed_token_is_sent_in_the_documented_headers(
        self, ticks: list[BrokerQuote], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        feed = make_feed(ticks)
        connection = FakeConnection(drop=False)
        server = FakeServer([connection])
        install(monkeypatch, server)
        no_sleep(monkeypatch, feed)

        await run_until(feed, connection)

        headers = server.headers[0]
        assert headers["Authorization"] == FEED_TOKEN
        assert headers["x-feed-token"] == FEED_TOKEN
        assert headers["x-api-key"] == "fake-api-key"
        assert headers["x-client-code"] == "T0000001"

    @pytest.mark.asyncio
    async def test_a_rejected_handshake_is_fatal_not_retried(
        self, ticks: list[BrokerQuote], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A bad token does not become good by being retried.

        And a loop against a broker's auth endpoint is how a wrong credential
        becomes a locked account.
        """
        attempts = 0

        def reject(url: str, **kwargs: Any) -> Any:
            nonlocal attempts
            attempts += 1
            raise websockets.InvalidStatus(
                Response(401, "Unauthorized", websockets.Headers())
            )

        feed = make_feed(ticks)
        monkeypatch.setattr(
            "app.brokers.angel_one.feed.websockets.connect", reject, raising=True
        )
        delays = no_sleep(monkeypatch, feed)

        with pytest.raises(BrokerError, match="401"):
            await feed.run()

        assert attempts == 1
        assert delays == []


class TestReconnect:
    @pytest.mark.asyncio
    async def test_a_dropped_socket_replays_the_whole_registry(
        self, ticks: list[BrokerQuote], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Not the delta since the last disconnect — everything.

        The server remembers nothing across a dropped socket. A client that
        replays only what it sent recently comes back subscribed to a subset
        of what the caller asked for, and nothing says so.
        """
        feed = make_feed(ticks)
        await feed.subscribe(AngelFeedMode.LTP, NSE_FO, ["1", "2", "3"])

        first = FakeConnection([ltp_frame()], drop=True)
        second = FakeConnection([ltp_frame()], drop=False)
        server = FakeServer([first, second])
        install(monkeypatch, server)
        delays = no_sleep(monkeypatch, feed)

        # Stop at the end of the *second* session, so the reconnect actually
        # happens. Stopping during the first backoff would exit the loop before
        # the replay under test.
        await run_until(feed, second)

        assert delays == [1.0]
        assert first.subscribed_tokens() == {"1", "2", "3"}
        assert second.subscribed_tokens() == {"1", "2", "3"}

    @pytest.mark.asyncio
    async def test_backoff_grows_exponentially_and_stops_at_the_cap(
        self, ticks: list[BrokerQuote], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An unbounded backoff means a feed that reconnects tomorrow.

        NSE sessions are six hours; the cap is what keeps a single blip from
        costing a meaningful fraction of the trading day.
        """
        feed = make_feed(ticks)
        connections = [FakeConnection(drop=True) for _ in range(12)]
        server = FakeServer(connections)
        install(monkeypatch, server)

        delays: list[float] = []

        async def record(backoff: float) -> None:
            delays.append(backoff)
            if len(delays) >= 10:
                await feed.stop()

        monkeypatch.setattr(feed, "_sleep_with_jitter", record)
        await feed.run()

        assert delays[:7] == [1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 60.0]
        assert max(delays) == 60.0

    @pytest.mark.asyncio
    async def test_backoff_resets_after_a_healthy_session(
        self, ticks: list[BrokerQuote], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Otherwise an hour of occasional blips ends at the cap permanently.

        A session that connected and streamed is evidence the network is fine,
        so the next failure starts from one second again.
        """
        feed = make_feed(ticks)
        # drop, drop, then a session that ends cleanly, then drop again.
        server = FakeServer(
            [
                FakeConnection(drop=True),
                FakeConnection(drop=True),
                FakeConnection([ltp_frame()], drop=False),
                FakeConnection(drop=True),
            ]
        )
        install(monkeypatch, server)

        delays: list[float] = []
        sessions = 0

        async def record(backoff: float) -> None:
            nonlocal sessions
            delays.append(backoff)
            sessions += 1
            if sessions >= 3:
                await feed.stop()

        monkeypatch.setattr(feed, "_sleep_with_jitter", record)

        # The clean session returns from `_session` normally, which the run
        # loop treats as success; stop() is set inside `record` so the loop
        # terminates rather than consuming the whole script.
        await feed.run()

        assert delays[0] == 1.0
        assert delays[1] == 2.0
        # After the healthy third connection, back to the initial value.
        assert delays[2] == 1.0

    @pytest.mark.asyncio
    async def test_stop_during_a_session_exits_without_reconnecting(
        self, ticks: list[BrokerQuote], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        feed = make_feed(ticks)
        server = FakeServer([FakeConnection(drop=True)])
        install(monkeypatch, server)

        async def stop(_: float) -> None:
            await feed.stop()

        monkeypatch.setattr(feed, "_sleep_with_jitter", stop)
        await asyncio.wait_for(feed.run(), timeout=5)
        assert len(server.handed_out) == 1


class TestJitter:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("draw", [0.0, 0.5, 1.0])
    async def test_the_delay_stays_between_half_and_all_of_the_backoff(
        self, ticks: list[BrokerQuote], monkeypatch: pytest.MonkeyPatch, draw: float
    ) -> None:
        """Jitter that could exceed the cap would defeat the cap.

        And jitter that could reach zero would turn a backoff into a spin.
        """
        feed = make_feed(ticks)
        monkeypatch.setattr("app.brokers.angel_one.feed.random.random", lambda: draw)
        captured: list[float] = []

        # `**kwargs` rather than a named `timeout` parameter: this is a stub for
        # `asyncio.wait_for`, and declaring `timeout` on an async def trips
        # ASYNC109, which exists to discourage hand-rolled timeouts in real
        # code.
        async def fake_wait_for(awaitable: Any, **kwargs: Any) -> None:
            captured.append(float(kwargs["timeout"]))
            awaitable.close()  # the un-awaited coroutine would warn otherwise
            raise TimeoutError

        monkeypatch.setattr(
            "app.brokers.angel_one.feed.asyncio.wait_for", fake_wait_for
        )
        await feed._sleep_with_jitter(60.0)

        assert 30.0 <= captured[0] <= 60.0

    @pytest.mark.asyncio
    async def test_stop_wakes_the_backoff_early(self, ticks: list[BrokerQuote]) -> None:
        """A stop() during a 60-second backoff must not hang for the remainder.

        Waiting on the stop event rather than sleeping flat is what makes
        shutdown prompt; this asserts the wait is actually on the event.
        """
        feed = make_feed(ticks)
        await feed.stop()
        await asyncio.wait_for(feed._sleep_with_jitter(3600.0), timeout=2)


class TestReading:
    @pytest.mark.asyncio
    async def test_a_binary_frame_reaches_the_handler_as_a_quote(
        self, ticks: list[BrokerQuote], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        feed = make_feed(ticks)
        connection = FakeConnection([ltp_frame(paise=2402550)], drop=False)
        install(monkeypatch, FakeServer([connection]))
        no_sleep(monkeypatch, feed)

        await run_until(feed, connection)

        assert len(ticks) == 1
        # Compared as a value, not a string: `Decimal(2402550) / 100` is
        # `24025.5`, and asserting on `str` would be testing the trailing-zero
        # behaviour of Decimal rather than the price.
        assert ticks[0].last_traded_price == Decimal("24025.50")
        assert ticks[0].token == "43215"

    @pytest.mark.asyncio
    async def test_one_undecodable_frame_does_not_kill_the_connection(
        self, ticks: list[BrokerQuote], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """One malformed tick is not a reason to drop nine hundred instruments.

        The bad frame is skipped and the good one that follows still arrives.
        """
        feed = make_feed(ticks)
        connection = FakeConnection([b"\x01\x02short", ltp_frame()], drop=False)
        install(monkeypatch, FakeServer([connection]))
        no_sleep(monkeypatch, feed)

        await run_until(feed, connection)

        assert len(ticks) == 1

    @pytest.mark.asyncio
    async def test_text_frames_are_protocol_chatter_not_ticks(
        self, ticks: list[BrokerQuote], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A heartbeat reply is not a quote, and must not be decoded as one."""
        feed = make_feed(ticks)
        connection = FakeConnection(
            ["pong", '{"errorCode":"x"}', ltp_frame()], drop=False
        )
        install(monkeypatch, FakeServer([connection]))
        no_sleep(monkeypatch, feed)

        await run_until(feed, connection)

        assert len(ticks) == 1

    @pytest.mark.asyncio
    async def test_the_connection_is_released_when_the_session_ends(
        self, ticks: list[BrokerQuote], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A stale connection reference would let `subscribe` write to a dead
        socket and believe it had succeeded."""
        feed = make_feed(ticks)
        connection = FakeConnection(drop=False)
        install(monkeypatch, FakeServer([connection]))
        no_sleep(monkeypatch, feed)

        await run_until(feed, connection)

        assert not feed.connected


class TestReadOnly:
    def test_the_feed_cannot_place_an_order(self) -> None:
        """The order-update socket is a separate endpoint this does not touch.

        Asserted rather than commented, so the guarantee survives someone
        adding a method in good faith.
        """
        for name in (
            "place_order",
            "modify_order",
            "cancel_order",
            "square_off",
            "exit_position",
            "buy",
            "sell",
        ):
            assert not hasattr(AngelOneFeed, name)

    def test_the_feed_does_not_subscribe_to_anything_on_its_own(
        self, ticks: list[BrokerQuote]
    ) -> None:
        """Opening subscriptions unbidden would spend the caller's rate-limit
        quota on a policy decision the caller did not make."""
        feed = make_feed(ticks)
        assert feed.registry.token_count == 0
        assert feed.registry.request_frames(AngelFeedAction.SUBSCRIBE) == []
