# Phase 3 — Angel One SmartAPI integration foundation

> **This phase cannot place an order.** Not "is configured not to" — *cannot*.
> There is no order method on the adapter protocol, no order route constant in
> the Angel One constants module, no `POST` route anywhere in the API, and no
> BUY/SELL control in the interface. The two trading flags exist so the status
> endpoint can state the fact, not to gate code that would otherwise run.

> **Connecting a broker does not make the dashboard's figures real.** The
> account balance shown on the dashboard is still the mock figure by
> deliberate choice; see *Known limits*.

Every number in this report was produced by a command actually executed
against this repository. Where something was not run — and one important thing
was not — it is named as unverified rather than omitted.

---

## 1. Objective and scope

Build a secure, tested, extensible **read-only** foundation for talking to
Angel One SmartAPI, so that a later phase has somewhere to plug live market
data in, without this phase acquiring the ability to trade.

In scope: configuration, a broker-agnostic abstraction, an Angel One
implementation of it (auth, HTTP client, symbol mapping, historical candles,
market-data feed), a persistence table for account snapshots, two read-only
API routes, a dashboard card, tests, and documentation.

Explicitly out of scope and **not** built: order placement of any kind, paper
trading, machine learning of any kind, strategy signals (EMA/RSI/MACD/
Supertrend/CE-PE prediction), autonomous execution, and any scheduler that
acts without a human request.

## 2. What was built

| Module | Responsibility |
| --- | --- |
| `app/brokers/base.py` | `BrokerAdapter` — a `@runtime_checkable` `Protocol` with read-only methods only |
| `app/brokers/models.py` | Frozen, `extra="forbid"` domain models shared by every broker |
| `app/brokers/exceptions.py` | Eight-way error taxonomy, each carrying an HTTP status and a stable code |
| `app/brokers/angel_one/constants.py` | Base URL, route paths, rate limits, interval caps — no logic |
| `app/brokers/angel_one/auth.py` | TOTP generation, login, session lifetime, `asyncio.Lock` |
| `app/brokers/angel_one/client.py` | `httpx.AsyncClient` wrapper, header assembly, error translation |
| `app/brokers/angel_one/mapper.py` | SmartAPI payload → domain model, `Decimal` throughout |
| `app/brokers/angel_one/history.py` | Historical range planner — splits a request into per-interval-legal windows |
| `app/brokers/angel_one/feed.py` | WebSocket market-data feed: subscription model, reconnect policy |
| `app/brokers/angel_one/feed_codec.py` | Binary tick frame decoding and normalisation |
| `app/brokers/angel_one/adapter.py` | `AngelOneAdapter` — the `BrokerAdapter` implementation |
| `app/db/models/broker_account.py` | `broker_account_snapshots` table |
| `app/api/v1/broker.py` | `GET /broker/status`, `GET /broker/connection-test` |
| `src/components/dashboard/BrokerStatusCard.tsx` | The dashboard surface for the above |

## 3. Read-only, enforced structurally

Five independent points, each sufficient on its own:

1. **The protocol has no order method.** `BrokerAdapter` declares only
   read verbs. A type-checked implementation cannot add one and still satisfy
   a call site that does not know about it.
2. **No order route constant exists.** `constants.py` contains no
   `placeOrder`/`modifyOrder`/`cancelOrder` path. The five routes whose URL
   happens to contain `/order/v1/` are `getPosition`, `getOrderBook`,
   `getTradeBook`, `searchScrip` and `getLtpData` — all reads.
3. **No mutating route exists.** `grep -rn "@router\.\(post\|delete\|patch\)" app/`
   returns nothing. The application declares twelve `GET` routes and exactly
   one `PUT` (the monthly target). Both broker routes are `GET`.
4. **CORS allows only `GET`, `PUT`, `OPTIONS`** (`app/main.py:117`).
5. **The interface has no BUY/SELL control**, and the broker card renders
   status only.

The status schema reports `live_trading_enabled` and `paper_trading_enabled`
as plain booleans — they reflect configuration, and configuration can change.
But it also carries `order_placement_available: Literal[False]`, which is a
statement about the *code*, not about a setting: a future change that tried to
report order placement as available would fail type-checking rather than
silently ship. The same technique is used in the opposite direction on the
connection-test response, where `connected: Literal[True]` encodes that the
model is only ever reached on success — a failure propagates as a `BrokerError`
with a status code that says what to do about it, so a rejected credential is
never indistinguishable from a working one to anything that checks status.

## 4. Configuration and secrets

Every credential is a `SecretStr`, so it renders as `**********` in any repr,
log line, traceback or crash report. All Angel One fields are **optional**:
the API boots, serves the whole dashboard and passes its suite with none of
them set. A broker is something this system talks to, not something it needs
permission from in order to start.

| Setting | Default | Note |
| --- | --- | --- |
| `ANGEL_ONE_ENABLED` | `false` | Master switch; off so a half-filled `.env` cannot cause a surprise outbound login |
| `ANGEL_ONE_API_KEY` | unset | `SecretStr` |
| `ANGEL_ONE_CLIENT_CODE` | unset | Masked to `******56` before it reaches any response body |
| `ANGEL_ONE_PIN` | unset | `SecretStr`, typed as a **string** — a PIN may begin with a zero |
| `ANGEL_ONE_TOTP_SECRET` | unset | The base32 *seed*, not a six-digit code. Read once, converted inside `auth.py`, never stored or logged |
| `ANGEL_ONE_TIMEOUT` | `10.0` | Guard against a hung socket, not a rate limiter |
| `LIVE_TRADING_ENABLED` | `false` | No code path reads this as permission to act |
| `PAPER_TRADING_ENABLED` | `false` | Likewise |

`.get_secret_value()` is called in exactly three files — `auth.py`,
`adapter.py` and `config.py` (the last only to build the database URL). No
plaintext credential crosses a layer boundary.

**No credential is prefixed `NEXT_PUBLIC_`.** Anything under that prefix is
compiled into the JavaScript bundle and served to every visitor. The browser
receives a masked client code and three booleans, and nothing else.

## 5. The three states of a connection

The system distinguishes **enabled**, **configured** and **connected** and
reports all three separately, because they need very different responses from
an operator:

| enabled | configured | connected | Meaning |
| --- | --- | --- | --- |
| `false` | — | `false` | Integration switched off. Nothing has been sent to a broker |
| `true` | `false` | `false` | You have not finished setting this up |
| `true` | `true` | `false` | Credentials present but the last attempt failed |
| `true` | `true` | `true` | A session was established |

## 6. Root-cause bug found and fixed

A blank credential in a copied template — `ANGEL_ONE_PIN=` — parsed to
`SecretStr('')`, which is not `None`. With `ANGEL_ONE_ENABLED=true`, the
`angel_one_configured` property therefore reported `True`, the status endpoint
claimed the integration was configured, and the connection test sent a blank
PIN to the broker and came back `502 BROKER_AUTHENTICATION_FAILED`.

That is the wrong diagnosis pointed at the wrong person: *"your credentials
were rejected"* sends an operator to reset a PIN that was never wrong, while
*"not configured"* sends them to the line they left blank.

Fixed at the root — in `Settings`, not in the service — with a `mode="before"`
validator (`_blank_credential_is_absent`) that reads a blank or whitespace-only
credential as absent. The whole system therefore sees `None` and reports
`409 BROKER_NOT_CONFIGURED`. Covered by a regression test
(`test_a_blank_credential_reads_as_absent_not_as_empty`), which asserts both
the settings-level values and the endpoint response.

## 7. Error taxonomy

Eight exception types, each with a stable machine-readable code and an HTTP
status, so the frontend branches on a code rather than on prose:
`BROKER_NOT_CONFIGURED` (409), `BROKER_AUTHENTICATION_FAILED` (502),
`BROKER_NOT_AUTHORIZED` (502), `BROKER_UNREACHABLE`, rate-limit, timeout,
invalid-response and a generic broker error. The full table with statuses is
in `docs/angel-one.md`.

## 8. Testing

**346 tests pass in 130.50 s.** 192 of them are broker-related:

| File | Tests |
| --- | --- |
| `tests/test_broker.py` (routes, status, config) | 47 |
| `tests/brokers/test_adapter.py` | 33 |
| `tests/brokers/test_feed.py` | 32 |
| `tests/brokers/test_feed_codec.py` | 25 |
| `tests/brokers/test_mapper.py` | 22 |
| `tests/brokers/test_history.py` | 15 |
| `tests/integration/test_broker_snapshots.py` | 18 |

Every broker test runs against an injected `httpx.MockTransport`; API tests
run in-process through `httpx.ASGITransport`. No test opens a socket to Angel
One, and no test is skipped to make the suite pass.

## 9. Validation performed

All commands below were executed in this session and their real output is
quoted.

| Command | Result |
| --- | --- |
| `pytest` | `346 passed in 130.50s` |
| `ruff check app tests alembic` | `All checks passed!` |
| `ruff format --check app tests alembic` | `107 files already formatted` |
| `mypy app tests` | `Success: no issues found in 104 source files` |
| `tsc --noEmit` | clean |
| `eslint .` | clean |
| `next build` | `✓ Compiled successfully in 3.3s`, TypeScript finished, 4/4 static pages |
| `docker ps` | `nifty_agent_postgres :: Up (healthy)` |

## 10. Secret scan

| Check | Result |
| --- | --- |
| `NEXT_PUBLIC_*` in `src/` | Only `NEXT_PUBLIC_API_BASE_URL` (`src/lib/api/client.ts:50`) |
| `.env.local` keys | `NEXT_PUBLIC_API_BASE_URL` only |
| Credential names in `.next/static`, `.next/server` | none |
| `backend/.env` tracked by git | no — ignored by `.gitignore:35` (`.env*`) |
| Env files tracked by git | `.env.example`, `backend/.env.example` only |
| Hard-coded secret literals in `app/` | none |

## 11. Interface

A seventh dashboard card (`BrokerStatusCard`) was seated without breaking the
documented bento rhythm: the calendar took `lg:row-span-2` and the broker card
`lg:col-span-7`, so sparse auto-placement puts the calendar in columns 8–12
across rows 2–3 and the broker in columns 1–7 of row 3. Verified numerically,
not just by eye: broker width 785 px = today's-target 325 + gap 20 +
monthly-progress 440, and the calendar's bottom edge 993 px ≈ the broker's 994.

**Glass surfaces** (the requested 20% transparent / fully blurred treatment)
were verified by reading computed style on the running app, in both themes,
because a screenshot cannot prove opacity or blur:

- fill `rgba(255, 255, 255, 0.2)` light, `rgba(20, 20, 20, 0.2)` dark
- `backdrop-filter: blur(32px) saturate(1.8)` on the card, the popover **and**
  the tooltip
- an `@supports not` fallback trades the effect for an opaque surface where
  `backdrop-filter` is unavailable, rather than shipping unreadable text

## 12. Known limits and unverified claims

- **Nothing here has been exercised against a live Angel One account.** No
  credentials were available. Every broker test uses a mocked transport. The
  request/response shapes were taken from SmartAPI documentation, and the
  values marked UNVERIFIED in `docs/angel-one.md` — interval caps, exact
  rate-limit ceilings, binary tick frame offsets — should be confirmed against
  a real session before anyone relies on them.
- **The dashboard's account balance is still the mock figure**, by choice. The
  snapshot table and the adapter exist; wiring the displayed balance to a live
  broker read is a later decision, not an oversight.
- **There is no client-side rate limiter.** `ANGEL_ONE_TIMEOUT` guards against
  a hung socket; it does not throttle. Angel One's own limits are tabulated in
  `constants.py` but not yet enforced in code.
- **There is no authentication on this API itself.** Unchanged from Phase 2,
  and still the largest gap before any non-local deployment.

## 13. Definition of Done

| # | Item | Status |
| --- | --- | --- |
| 1 | Broker abstraction defined as a `Protocol` | ✅ |
| 2 | Protocol is `@runtime_checkable` | ✅ |
| 3 | Protocol exposes read verbs only | ✅ |
| 4 | Angel One adapter implements the protocol | ✅ |
| 5 | Domain models frozen and `extra="forbid"` | ✅ |
| 6 | `Decimal` used for all money | ✅ |
| 7 | Error taxonomy with stable codes | ✅ |
| 8 | Each error carries an HTTP status | ✅ |
| 9 | All credentials optional | ✅ |
| 10 | All credentials `SecretStr` | ✅ |
| 11 | PIN typed as string (leading zero safe) | ✅ |
| 12 | Blank credential reads as absent | ✅ (bug found and fixed) |
| 13 | Master enable switch, default off | ✅ |
| 14 | `live_trading_enabled` false | ✅ |
| 15 | `paper_trading_enabled` false | ✅ |
| 16 | `order_placement_available` typed `Literal[False]` in the schema | ✅ |
| 17 | No order method on the adapter | ✅ |
| 18 | No order route constant | ✅ |
| 19 | No `POST`/`PATCH`/`DELETE` route anywhere | ✅ verified by grep |
| 20 | No BUY/SELL control in the UI | ✅ |
| 21 | CORS restricted to `GET`/`PUT`/`OPTIONS` | ✅ |
| 22 | TOTP seed never stored or logged | ✅ |
| 23 | Session lifetime modelled (next IST midnight) | ✅ |
| 24 | `asyncio.Lock` around authenticate | ✅ |
| 25 | HTTP client uses injectable transport | ✅ |
| 26 | Per-request timeout configured | ✅ |
| 27 | Historical range planner splits by interval cap | ✅ |
| 28 | Interval caps tabulated in constants | ✅ |
| 29 | WebSocket feed architecture defined | ✅ |
| 30 | Tick decoding and normalisation implemented | ✅ |
| 31 | Reconnect policy implemented | ✅ |
| 32 | `broker_account_snapshots` table | ✅ |
| 33 | Alembic migration for it | ✅ |
| 34 | Integration tests against real TimescaleDB | ✅ 18 |
| 35 | `GET /broker/status` | ✅ |
| 36 | `GET /broker/connection-test` | ✅ |
| 37 | Client code masked in responses | ✅ |
| 38 | enabled/configured/connected reported separately | ✅ |
| 39 | Dashboard broker card | ✅ |
| 40 | Glass surfaces at 20% / blurred, both themes | ✅ verified by computed style |
| 41 | No `NEXT_PUBLIC_` credential | ✅ verified in `src/` and in the built bundle |
| 42 | `backend/.env` gitignored and untracked | ✅ |
| 43 | Full test suite green | ✅ 346 passed |
| 44 | Lint, format, type-check, build all clean | ✅ |
| 45 | Documentation written | ✅ `docs/angel-one.md`, README Phase 3 section |
| 46 | Unverified values labelled as such | ✅ |

## 14. Stopping point

Phase 3 is complete. Phase 4 has not been started.
