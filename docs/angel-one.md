# Angel One SmartAPI — integration, decisions and limits

A read-only broker foundation. This document explains what the integration can
do, what it structurally cannot do, how to configure it, and the reasoning
behind the choices that are not obvious from the code.

> **This integration cannot place, modify or cancel an order.** That is not a
> disabled feature or a flag set to false. There is no `place_order` method on
> the adapter protocol, no order-placement route constant in the Angel One
> constants module, and no order endpoint on this API. The guarantee is the
> absence of any code that could transmit an order — see
> [Read-only, structurally](#read-only-structurally).

> **Connecting a broker does not make the dashboard's figures real.** Every
> performance number the API currently serves carries `source = "mock"` or
> `source = "development_seed"`, and it keeps carrying it with a live broker
> session attached. There is a test that asserts exactly this.

---

## Contents

- [What this phase built](#what-this-phase-built)
- [Read-only, structurally](#read-only-structurally)
- [Configuration](#configuration)
- [The three states of a connection](#the-three-states-of-a-connection)
- [API endpoints](#api-endpoints)
- [Architecture](#architecture)
- [Authentication and session lifetime](#authentication-and-session-lifetime)
- [Secret handling](#secret-handling)
- [Errors](#errors)
- [Rate limits](#rate-limits)
- [Historical data](#historical-data)
- [The market-data feed](#the-market-data-feed)
- [Persistence](#persistence)
- [Testing](#testing)
- [Known limits and UNVERIFIED values](#known-limits-and-unverified-values)

---

## What this phase built

| Area | Module | What it is |
| ---- | ------ | ---------- |
| Contract | `app/brokers/base.py` | `BrokerAdapter` — a `Protocol`, not an ABC |
| Records | `app/brokers/models.py` | Broker-neutral frozen dataclasses, `Decimal` throughout |
| Errors | `app/brokers/exceptions.py` | Eight-way taxonomy organised by operator remedy |
| Vendor literals | `app/brokers/angel_one/constants.py` | Every route, interval, code and limit, in one place |
| Transport | `app/brokers/angel_one/client.py` | `httpx.AsyncClient` over the documented REST routes |
| Session | `app/brokers/angel_one/auth.py` | TOTP login, IST-midnight expiry, `asyncio.Lock` |
| Translation | `app/brokers/angel_one/mapper.py` | SmartAPI payloads to broker-neutral records |
| Adapter | `app/brokers/angel_one/adapter.py` | The `BrokerAdapter` implementation |
| History | `app/brokers/angel_one/history.py` | Range planner for the per-interval span caps |
| Feed | `app/brokers/angel_one/feed.py`, `feed_codec.py` | SmartWebSocketV2 client and binary tick decoder |
| Service | `app/services/broker_service.py` | Status and connection test, client-code masking |
| API | `app/api/v1/broker.py` | Two `GET` routes |
| Storage | `app/db/models/broker_account.py` | `broker_account_snapshots`, append-only |
| UI | `src/components/dashboard/BrokerStatusCard.tsx` | The operator's view of all of the above |

---

## Read-only, structurally

The prohibition is enforced in five independent places, none of which is a
runtime check that could be bypassed:

1. **The protocol has no order member.** `BrokerAdapter` declares
   `authenticate`, `logout`, `get_profile`, `get_funds`, `get_positions`,
   `get_order_book`, `get_trade_book`, `get_ltp`, `get_historical_candles`,
   `get_historical_oi` and `get_option_metrics`. Nothing else. A method that
   existed but raised would still be a method a future call site could find.
2. **The constants module has no order route.** A route string is the first
   half of a call site; this system has neither half.
3. **The API has no order path.** `POST /api/v1/broker/order` returns **404**,
   not 405 — the path does not exist, rather than existing with the verb
   disallowed. A test asserts 404 on every verb.
4. **CORS allows `GET`, `PUT` and `OPTIONS` only.** No browser on an allowed
   origin can issue a `POST` or `DELETE` to this API at all.
5. **The response schema makes the claim unrepresentable.**
   `order_placement_available` is typed `Literal[False]`, so a payload
   asserting otherwise fails response validation rather than reaching a browser.

`get_order_book` and `get_trade_book` read orders placed by other means —
including by hand in Angel One's own app. That is a window, not a lever.

`LIVE_TRADING_ENABLED` and `PAPER_TRADING_ENABLED` exist so the status
endpoints can state the fact explicitly rather than leaving "can this thing
trade?" to be inferred from the absence of a button. Setting either to `true`
changes nothing, because there is no order code for them to permit.

---

## Configuration

All settings are optional. **The application starts, serves the entire
dashboard and passes its test suite with none of them set** — a broker is
something this system talks to, not something it needs permission from in order
to boot.

| Variable | Default | Notes |
| -------- | ------- | ----- |
| `ANGEL_ONE_ENABLED` | `false` | Master switch, off by default |
| `ANGEL_ONE_API_KEY` | — | `SecretStr`; from the SmartAPI app registration |
| `ANGEL_ONE_CLIENT_CODE` | — | Masked to `******56` before any response |
| `ANGEL_ONE_PIN` | — | `SecretStr`; a **string**, since a PIN may start with `0` |
| `ANGEL_ONE_TOTP_SECRET` | — | `SecretStr`; the base32 **seed**, not a six-digit code |
| `ANGEL_ONE_REDIRECT_URL` | — | Declared so it is not hard-coded; unused this phase |
| `ANGEL_ONE_POSTBACK_URL` | — | Likewise |
| `ANGEL_ONE_PRIMARY_STATIC_IP` | — | Likewise |
| `ANGEL_ONE_SECONDARY_STATIC_IP` | — | Likewise |
| `ANGEL_ONE_TIMEOUT` | `10.0` | Per-request ceiling; a hung-socket guard, not a limiter |
| `LIVE_TRADING_ENABLED` | `false` | Stated, not enforced — see above |
| `PAPER_TRADING_ENABLED` | `false` | Likewise |

**A blank value reads as absent, not as empty.** `ANGEL_ONE_PIN=` in a copied
template becomes `None`, not `SecretStr('')`. Without that rule an operator who
filled in three of four keys would be told their *credentials were rejected* —
sending them to reset a PIN that was never wrong — instead of being told the
integration is not configured. Whitespace-only values are treated the same way,
because a secret pasted with a trailing newline is blank in every sense that
matters.

**No Angel One value may be given a `NEXT_PUBLIC_` prefix.** Anything under
that prefix is compiled into the JavaScript bundle and served to every visitor.
The browser receives a masked client code, a session expiry and three booleans.

---

## The three states of a connection

`enabled`, `configured` and `connected` are reported separately because they
have different remedies. Collapsing them into one boolean would tell an
operator that something is wrong without telling them which thing.

| `enabled` | `configured` | `connected` | Means | What to do |
| --------- | ------------ | ----------- | ----- | ---------- |
| `false` | `false` | `false` | Switched off | Nothing has been sent to a broker |
| `true` | `false` | `false` | Credentials incomplete | Fill in the missing `.env` line |
| `true` | `true` | `false` | Never logged in, or the session lapsed | Run the connection test |
| `true` | `true` | `true` | A read-only session is live | — |

`configured` includes the switch, so credentials that are complete but disabled
report `configured: false` with a non-null `client_code`. The dashboard can
therefore say "you have set this up but not turned it on" rather than sending
an operator to re-check credentials that are fine.

**A lapsed session reports `connected: false`**, not a past `session_expires_at`.
The badge must not assert a live connection on a credential the broker has
already stopped accepting.

---

## API endpoints

Both are `GET`. Neither is a control surface.

### `GET /api/v1/broker/status`

Touches no network beyond this process. Safe to poll, and safe to call before
anything is configured — which is precisely the case where a status endpoint
matters most, and the case a careless refactor is most likely to break, because
it is the one where every optional setting is `None` and the adapter cannot be
constructed at all.

```json
{
  "broker": "angel_one",
  "enabled": false,
  "configured": false,
  "connected": false,
  "client_code": null,
  "session_expires_at": null,
  "live_trading_enabled": false,
  "paper_trading_enabled": false,
  "order_placement_available": false
}
```

### `GET /api/v1/broker/connection-test`

Authenticates against Angel One and reads the account profile back. Runs only
when a human asks for it: a card that tested on mount would log in to a broker
every time someone opened a browser tab.

**Why a `GET` for something that authenticates.** The reflex is `POST`, and the
reflex is arguable here — a remote login is a side effect. Two facts decided it
the other way. First, the authenticator caches the session, so repeated calls
do not mean repeated logins; there is a test that makes two connection tests
and asserts the login route was hit once. Second, the CORS policy allows `GET`,
`PUT` and `OPTIONS`, and adding `POST` for one diagnostic would widen the write
surface of the entire API. The reasoning is recorded on the route itself.

Failure modes are distinguished rather than collapsed into a falsy field:

| Status | Code | Meaning |
| ------ | ---- | ------- |
| `409` | `BROKER_NOT_CONFIGURED` | Nothing is broken; setup is incomplete |
| `502` | `BROKER_AUTHENTICATION_FAILED` | Credentials rejected — stop and tell someone |
| `503` | `BROKER_UNAVAILABLE` | The broker is up but refusing service |
| `504` | `BROKER_UNREACHABLE` | Transient; a bounded retry is reasonable |

---

## Architecture

```
app/api/v1/broker.py          routes — no logic
        │
app/services/broker_service.py  status, connection test, masking
        │
app/brokers/angel_one/adapter.py  BrokerAdapter implementation
        │           │
     auth.py     client.py  →  mapper.py  →  app/brokers/models.py
   (session)   (transport)    (translation)   (broker-neutral records)
```

**Composition, not inheritance.** The adapter owns a transport, an
authenticator and a set of mapping functions, and its own body is mostly
wiring. The interesting logic — classifying an error, refusing a malformed
price, splitting a date range — lives in modules that can be tested without
constructing an adapter at all.

**Why not the official SDK.** `smartapi-python` is synchronous and built on
`requests`; inside an async FastAPI worker one such call blocks the event loop
for its full duration, stalling every other request the process is serving,
health checks included. Its constructor also has side effects before any call
is made: it resolves the machine's public IP over the network and reads the
host's MAC address. So this integration speaks to the documented REST routes
directly over `httpx`. The routes, headers and payload shapes are the SDK's and
the documentation's; only the transport is ours.

**Why a `Protocol` rather than an ABC.** Nothing needs to inherit from
`BrokerAdapter` to conform, so a test double is a small class with the right
methods rather than a subclass dragging in real constructor behaviour — and
`mypy` still checks the double and the real adapter against the same shape.

**Every method is async**, even where an implementation might not need to await
anything, so that a future synchronous implementation cannot quietly block the
loop.

**The service is cached on `app.state`**, not in an `lru_cache` and not in a
module global. `Settings` is not hashable, and a global leaks between tests; app
state scopes the service to the app, so a test that builds a second app gets its
own service for free. The adapter is constructed lazily inside it, because
`AngelOneAdapter.__init__` raises `BrokerConfigurationError` without credentials
and the status endpoint has to work in exactly that case.

---

## Authentication and session lifetime

**The TOTP seed never leaves `auth.py`.** Anyone holding the base32 seed can
mint valid codes forever, which makes it strictly more dangerous than the
six-digit code it produces — a code is worthless in thirty seconds, a seed is
worthless never. It is read, converted to a code, and is not stored on any
object, passed to any other layer, or included in any error message. The
generated code is not logged either.

A malformed seed raises locally rather than at the broker. The distinction
matters: a broker rejection reads as "your credentials are wrong", which sends
an operator to check the PIN when the real fault is a seed pasted with a
trailing space.

**Session expiry is computed, not parsed.** Angel One's login response carries
no expiry field. What it has instead is a published policy: tokens are valid
until midnight IST regardless of when they were issued. A session minted at
23:58 is good for two minutes. So `expires_at` is the next IST midnight,
computed — which turns "should I re-authenticate?" into a comparison instead of
a failed request and a retry.

**An `asyncio.Lock` guards the whole authenticate path.** Without it, ten
simultaneous requests on a cold process would each see no session and each start
a login, against an endpoint that permits one call per second. Nine wait and
then find the session the first one created.

**Session expiry is retried exactly once.** Not a loop. Tokens die at midnight
IST, so a single refresh covers the expected daily case; if the second attempt
also reports an expired session, something is wrong that retrying will not fix,
and hammering a login endpoint limited to 1/s is how a transient problem becomes
a locked account.

---

## Secret handling

| Value | Where it lives | Where it does not |
| ----- | -------------- | ----------------- |
| API key, PIN, TOTP seed | `Settings`, as `SecretStr` | Any repr, log, traceback, response |
| Access / refresh / feed tokens | `BrokerSession`, as `SecretStr`, in memory | Any database row, any response |
| Client code | `Settings`; stored in snapshots | Any response **unmasked** |

- **`SecretStr` everywhere** means the worst case for a mistaken interpolation
  is `**********` rather than a live credential in a log aggregator.
- **Masking happens on the server.** The frontend is never given a full client
  code to mask itself, because anything the browser can render, the browser
  received. A code short enough that masking would hide nothing is masked
  *completely* rather than partially — returning a two-character code unchanged
  because it happens to be short is how a redaction helper becomes a leak.
- **Tokens are never persisted.** They are credentials, they expire daily, they
  have no analytical value, and a bearer token in a database row is a bearer
  token in every backup and every `pg_dump`.
- **The response schema is `extra="forbid"`**, so a field that is not declared
  cannot be smuggled into a response by a future change.
- **`order_placement_available` is not copied from the payload** on the
  frontend. It is hard-coded `false` in `src/lib/api/broker.ts`; reading it
  through would turn a server-side guarantee into a value a component renders
  on trust.

---

## Errors

Every broker failure is translated into one of eight types before it leaves
`app.brokers`. The taxonomy is organised around *what the caller should do*,
which is the only distinction that matters at a call site.

| Exception | HTTP | Code | Remedy |
| --------- | ---- | ---- | ------ |
| `BrokerConfigurationError` | 409 | `BROKER_NOT_CONFIGURED` | Nothing to do; setup is incomplete |
| `BrokerAuthenticationError` | 502 | `BROKER_AUTHENTICATION_FAILED` | Credentials are wrong; stop and tell someone |
| `BrokerSessionExpiredError` | 502 | `BROKER_SESSION_EXPIRED` | Re-authenticate once, then continue |
| `BrokerAuthorizationError` | 502 | `BROKER_NOT_AUTHORIZED` | The account lacks the entitlement; asking again will not grant it |
| `BrokerRateLimitError` | 429 | `BROKER_RATE_LIMITED` | Back off and retry later |
| `BrokerNetworkError` | 504 | `BROKER_UNREACHABLE` | Transient; a bounded retry is reasonable |
| `BrokerDataError` | 502 | `BROKER_DATA_ERROR` | The response broke its contract; do not persist, do not guess |
| `BrokerUnavailableError` | 503 | `BROKER_UNAVAILABLE` | The broker is up but refusing service |

502 is the honest default: the request reached us and we did our part, but an
upstream dependency did not hold up its end. 409 is the exception, because
nothing is broken when an operator simply has not finished configuring.

Nothing above `app.brokers` should ever catch an `httpx` exception or a
`KeyError` from a JSON payload. If it has to, the adapter has failed at its job.

Two details worth knowing:

- **The envelope key is `errorcode` on most endpoints and `errorCode` on
  `getMarketData`.** Both are read. An error that goes unrecognised because of
  a capital letter is an error reported as a data fault.
- **There is deliberately no rate-limit or authorization code set.** An earlier
  draft had both, populated from plausible-looking guesses; checking found three
  of five were simply wrong. Inventing a mapping is worse than having none,
  because a wrong classification sends the caller down a recovery path that
  cannot work. Throttling and permission failures are classified from the HTTP
  status instead, which the transport can read without interpretation.

---

## Rate limits

Angel One's published per-second limits, tabulated in `constants.py`:

| Route | req/s | | Route | req/s |
| ----- | ----- |-| ----- | ----- |
| `loginByPassword` | 1 | | `getLtpData` | 10 |
| `getProfile` | 3 | | `getMarketData` | 10 |
| `getRMS` | 2 | | `getCandleData` | 3 |
| `getOrderBook` | 1 | | `getOIData` | 3 *(UNVERIFIED)* |
| `getTradeBook` | 1 | | `optionGreek` | 1 |
| `getPosition` | 1 | | `searchScrip` | 1 |

**Nothing enforces these yet.** The table is the broker's figures recorded in
one place; a limiter added later must read from it rather than restate it. The
login limit of 1/s is the reason `authenticate` caches and is guarded by a lock.

---

## Historical data

Angel One caps the **calendar** span of a single historical request, and the cap
depends on the interval. Exceeding it is rejected outright rather than
truncated.

| Timeframe | Angel interval | Max days |
| --------- | -------------- | -------- |
| `1m` | `ONE_MINUTE` | 30 |
| `3m` | `THREE_MINUTE` | 60 |
| `5m` | `FIVE_MINUTE` | 100 |
| `15m` | `FIFTEEN_MINUTE` | 200 |
| `30m` | `THIRTY_MINUTE` | 200 |
| `1h` | `ONE_HOUR` | 400 |
| `1d` | `ONE_DAY` | 2000 |

`app/brokers/angel_one/history.py` splits a wider range into conforming chunks.
It **returns a list, not a generator**, so a caller can see how many requests it
is about to make before making the first one — "this will be 340 calls against a
3/s limit" is a decision someone should be able to take, and a lazy sequence
hides it until the loop is already running.

Chunks are **inclusive at both ends**, because that is how Angel One interprets
`fromdate`/`todate`. Re-deriving the convention at each call site is how a
half-open assumption silently drops the last bar of every chunk.

**Gaps are real, not errors.** A weekend, a holiday or a contract that had not
yet listed all produce fewer bars than a naive calculation expects. Nothing pads
a gap with synthetic bars.

Angel One also publishes `TEN_MINUTE`. There is deliberately no `10m` in the
`Timeframe` enum: adding a member means altering the CHECK constraint on
`ohlcv_candles.timeframe` by migration, and nothing requests ten-minute bars.
The omission is a decision, not an oversight.

---

## The market-data feed

`app/brokers/angel_one/feed.py` implements a SmartWebSocketV2 client. **Nothing
in this phase subscribes to it** — it is architecture, tested against a fake
server, waiting for a consumer.

- **Subscriptions are state, not calls.** `subscribe()` records a token in a set
  and, if connected, sends a frame. On reconnect the whole recorded set is
  re-sent, because the server remembers nothing across a dropped socket — and a
  client that only replays what it sent since the last disconnect comes back
  subscribed to a subset of what the caller asked for, silently.
- **Reconnect is bounded and jittered.** Exponential backoff from one second to
  a cap. The cap matters because an unbounded backoff eventually means a feed
  that reconnects tomorrow; the jitter matters because without it every client
  that dropped during the same network blip retries in lockstep and re-creates
  the outage.
- **Reconnection stops permanently on an authentication failure.** A bad token
  does not become good by being retried.
- **Heartbeat every 10 s.** The server drops a connection silent for about a
  minute; ten seconds gives five chances to miss one.
- **Streamed prices are integers in paise.** Dividing by 100 — as `Decimal`,
  never as `float` — is the single most consequential line in the decoder: get
  it wrong and every price is off by two orders of magnitude in a way that still
  looks like a plausible number.
- **The REST API speaks exchange strings, the socket speaks integers**, and the
  two do not cover the same set. `EXCHANGE_TO_FEED_TYPE` is the only mapping
  between them.
- **It cannot place orders.** The order-update socket is a separate endpoint
  this module does not connect to, and receiving an order update would not
  constitute placing one in any case.

---

## Persistence

`broker_account_snapshots` is an **append-only log of observations**, not a
mutable account record. A row answers "what did the broker say our funds were,
and when?" Nothing derives an authoritative balance from it: the broker is
authoritative, and this is the history of what it told us.

That framing explains the shape — no updatable `balance` column, no unique key
on `(broker, client_code)` forcing one row per account, and `captured_at` is a
timestamp of *observation* rather than a business date.

Every figure is nullable except `net`, `available_cash` and `used_margin`, which
the RMS endpoint always returns. `NULL` says "the broker did not report this";
`0` would assert a fact the broker never stated.

It is **not a hypertable**. One row per poll per account is a few hundred rows a
day — five orders of magnitude below `option_quotes`. Chunking would add
planning overhead to a table that will not outgrow a B-tree index this decade,
and a hypertable cannot be converted back.

See [`database.md`](./database.md) for the schema as a whole.

---

## Testing

174 tests cover the broker integration, plus 18 integration tests for the
snapshot table that require a running TimescaleDB.

| File | Tests | Covers |
| ---- | ----- | ------ |
| `tests/test_broker.py` | 47 | The two routes, end to end, through the real service |
| `tests/brokers/test_adapter.py` | 33 | Session handling, retries, every read method |
| `tests/brokers/test_feed.py` | 32 | Subscription state, reconnect, heartbeat |
| `tests/brokers/test_feed_codec.py` | 25 | Binary tick decoding, paise conversion |
| `tests/brokers/test_mapper.py` | 22 | Payload translation, refusal of malformed data |
| `tests/brokers/test_history.py` | 15 | Range planning, boundaries, inverted ranges |
| `tests/integration/test_broker_snapshots.py` | 18 | The snapshot table against real PostgreSQL |

**No test touches Angel One.** The route tests drive FastAPI through
`ASGITransport` and the broker through `httpx.MockTransport`, so both fakes sit
at the outermost layer on each side and everything between them is production
code — dependency resolution, response-model validation, the service, the
authenticator, the mapper, and the error handler that renders a `BrokerError`.

What the security tests **can** establish: none of the fake credentials the test
itself configured appear in any response body. What they **cannot** establish:
that no future field leaks something these tests never set. The defences for
that are structural rather than assertions — `extra="forbid"` on the schema, and
`SecretStr` on every token.

```bash
cd backend
.venv/Scripts/python -m pytest tests/brokers tests/test_broker.py -q
.venv/Scripts/python -m pytest tests/integration -q   # needs docker compose up
```

---

## Known limits and UNVERIFIED values

Nothing here has been exercised against a live Angel One account. Values taken
from the published documentation and the official SDK are marked UNVERIFIED in
the source where the two sources disagree or where the documentation is silent.
**An UNVERIFIED value is one that must be confirmed against a live account
before anything depends on it for money.**

Currently marked UNVERIFIED:

- `getOIData` rate limit — assumed equal to `getCandleData` (3/s), the
  conservative direction to guess in.
- `AngelFeedMode.DEPTH` — present in the SDK, absent from the published mode
  table, payload layout unknown. Nothing subscribes to it.
- `AB1007` is classified as an authentication failure. Angel One's own login
  documentation lists it as the invalid-credential response, but community
  reports also see it for an expired token and for an MPIN lockout. It is read
  as authentication because that is the reading that fails *safely*: treating a
  genuine lockout as a refreshable session would drive a retry loop straight
  into the lockout that produced it.

Other limits of this phase:

- **No rate limiter.** The published limits are tabulated but not enforced.
- **No instrument master.** `SCRIP_MASTER_URL` is recorded; nothing downloads
  or indexes the ~40 MB contract file yet.
- **No feed consumer.** The websocket client is tested but nothing subscribes.
- **No scheduled polling.** Nothing writes a `broker_account_snapshots` row on
  a timer; the table and its repository exist, the caller does not.
- **The API has no authentication of its own.** Do not expose it beyond
  localhost.
