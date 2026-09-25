# NIFTY Agent — Dashboard

Monitoring dashboard for an autonomous NIFTY options trading agent.

The repository now contains **two applications**: a Next.js frontend
(`src/`) and a FastAPI backend (`backend/`). Every figure on screen is fetched
from the backend over HTTP — the frontend no longer reads a local mock module.

The backend now reads from PostgreSQL/TimescaleDB rather than from memory, so
the monthly target survives a restart. **The figures in that database are
still invented.** There is no broker connection, no live market data, no order
placement and no automatic trading. Persistence makes a number *durable*, not
*real* — so every response carries a `source` field (`database` or `mock`) and
every seeded row carries `source = 'development_seed'`.

| Phase       | Scope                                                       |
| ----------- | ----------------------------------------------------------- |
| **Phase 1** | Frontend, design system, bento layout, calendar — mock data  |
| **Phase 2** | FastAPI backend + full frontend integration — mock data      |
| **Phase 3** | Persistent data & time-series foundation — PostgreSQL/Timescale |

---

## The dashboard

**Light**

![NIFTY Agent dashboard — light theme](docs/dashboard-light.png)

**Dark**

![NIFTY Agent dashboard — dark theme](docs/dashboard-dark.png)

Both captures are the real production build at 1440×980. The screenshots are the
visual reference for this project: anything added later should match the density,
type scale, and restraint shown above.

---

## Design reference

The look is deliberately *institutional*, not *retail-trading*. If you are
extending the UI, these are the rules that produce it:

| Rule | Why |
| ---- | --- |
| One dominant figure per card, everything else subordinate | The eye should land on the number that matters, not scan six equal-weight stats |
| Micro-labels in uppercase 10.5px / `0.09em` tracking | Reads as a terminal field label; keeps titles from competing with figures |
| Inner metrics sit in *recessed* tiles, never raised ones | Elevation is reserved for the card itself, so depth stays meaningful |
| Colour is confirmation, never information | Every status carries an icon **and** a word; the hue only reinforces |
| Restrained green / red / amber, no neon, no gradients | Saturated colour on a financial figure reads as marketing, not data |
| Motion limited to 150–250ms entrances | Anything longer feels like a toy; anything bouncier feels like a game |
| `tabular-nums` on every figure | Digits must not shift column as values update |
| Generous whitespace over extra content | Empty space is what separates a dashboard from a spreadsheet |

The bento grid is the structural half of that: fixed rows of three, with a
deliberate size hierarchy rather than a uniform tile field.

**Responsive** — the same grid collapses to two columns at tablet width and one
at mobile, with no horizontal overflow at 360px.

<img src="docs/dashboard-mobile.png" alt="NIFTY Agent dashboard on mobile" width="300">

---

## Layout

Desktop is a 12-column bento grid, two rows, max width 1440px:

```
┌──────────────────────┬────────────────┬───────────┐
│ Available Balance  5 │ Monthly Target │  Today  3 │   row 1
│                      │              4 │           │
├───────────┬──────────┴───┬────────────┴───────────┤
│ Today's 3 │ Monthly    4 │ Trading Calendar     5 │   row 2
│ Target    │ Progress     │                        │
└───────────┴──────────────┴────────────────────────┘
```

Today's Target, Monthly Progress and the Trading Calendar share **a single row**
on desktop. The 5-4-3 / 3-4-5 mirror keeps both rows on the same column rhythm
while giving the calendar a compact footprint.

| Breakpoint | Columns | Behaviour |
| ---------- | ------- | --------- |
| `< 768px`  | 1  | Full stack, calendar cells stay ≥36px tall |
| `768px+`   | 6  | Balance full width, then 2-up rows, calendar full width |
| `1024px+`  | 12 | The two-row bento above |

---

## Theming

The dashboard ships light and dark themes, toggled from the control in the top
right of the header.

| | Canvas | Primary card | Body text |
| ---- | ------ | ------------ | --------- |
| Light | `#F9EDE3` | `rgba(255,255,255,0.72)` | `#1E1A16` |
| Dark  | `#1D1D1D` | `rgba(255,255,255,0.055)` | `#F2EFEB` |

How it works:

- Every colour utility resolves to a runtime CSS variable through Tailwind's
  `@theme inline`. Flipping `.dark` on `<html>` re-themes the entire app without
  a single `dark:` variant in component code.
- A tiny script inlined in `<head>` (`THEME_INIT_SCRIPT`) resolves the stored or
  OS preference **before first paint**, so a dark-theme load never flashes light.
- The preference is read through `useSyncExternalStore`, which keeps hydration
  clean and syncs across tabs and live OS theme changes.
- Dark mode inverts the elevation model: inner metric tiles use a *darker*
  recess (`rgba(0,0,0,0.2)`) rather than a lighter tint, because a lighter tint
  drops the 10.5px tile labels below 4.5:1.

### Glass surfaces

Popovers, tooltips and the broker card share one `.glass-panel` utility: a
**20% fill over a fully blurred backdrop** (`backdrop-filter: blur(32px)
saturate(180%)`).

- **The blur is load-bearing, not decoration.** A 20% tint on its own is
  unreadable over arbitrary content — over a calendar grid it would sit on top
  of digits and hairlines. Blurring first reduces the backdrop to a smooth
  local average, which a 20% tint can then shift far enough to carry text.
- **Dark mode tints dark, not white.** `rgba(20,20,20,0.2)`, because a white
  tint over `#1D1D1D` reads as fog and drops body text below 4.5:1.
- **Where the effect is unsupported, it is traded away rather than degraded.**
  An `@supports not` rule swaps in a near-opaque fill; 20% with no blur is not
  a lesser version of this, it is an unreadable one.
- **No arrows on any glass surface.** An SVG arrow cannot inherit
  `backdrop-filter`, so it would render as an opaque triangle pinned to a
  translucent panel — and no fixed fill can match, because glass takes its
  apparent colour from whatever is behind it.

The toggle itself is a two-position segmented track rather than a single
morphing icon — the user can see both states and which one is active, so it
reads as an explicit setting instead of a mystery-meat button. The thumb is a
shared layout element, so selection glides between positions in one motion.

---

## Market sessions

NSE equity and F&O trade **9:15 AM – 3:30 PM IST, Monday to Friday**.

The exchange timetable and the holiday calendar are **client-side facts, and
deliberately not API calls**. Both are published by the exchange ahead of time
and are the same for everyone, so they are arithmetic — not measurements of this
account. Making them fetches would mean a database outage could blank the date,
grey out the calendar, or claim the market was closed during a live session.
P&L is the opposite and always comes from storage.

### The clock

`src/lib/market.ts` derives the current phase from the instant, via
`Intl.DateTimeFormat` with `timeZone: "Asia/Kolkata"` — so the dashboard shows
the *exchange's* date and phase regardless of where the browser is:

| Phase | Window | Meaning |
| --- | --- | --- |
| `pre-open` | 09:00 – 09:15 | Call auction. No continuous trading yet. |
| `open` | 09:15 – 15:30 | Regular session. |
| `post-close` | 15:30 – 16:15 | Closed, but trades can still be modified. |
| `closed` | otherwise | Outside exchange hours, or a non-trading day. |

Clicking the session-hours label in the header opens the full timetable:
pre-open order entry (09:00–09:10, with the exchange's randomised close in the
final two minutes), matching and confirmation (09:10–09:12), the buffer
(09:12–09:15), the regular session, and both 16:15 post-close cutoffs.

`useMarketClock()` ticks every 15s and re-reads on tab focus. It starts `null`
and is filled after mount — never `new Date()` during render, which would
hydrate inconsistently. Callers render a neutral `—` until the first tick:
"closed" is a claim, and the absence of a clock is not evidence for it.

### The agent execution window

**9:15 AM – 3:00 PM IST** — deliberately 30 minutes narrower than the session.
The closing period is the least liquid part of the day and no unattended system
should be opening positions into it. It is shown as its own block in the
timetable panel, not as a fourth row, because it is a policy this system imposes
on itself rather than an exchange timing.

Both labels are derived from the `SCHEDULE` constant rather than typed out, so
the strings and the comparisons driving the status pill cannot drift apart.

### Non-trading days

`src/lib/holidays.ts` bundles the **17 published NSE holidays for 2026**.
Weekends and holidays are rendered differently on purpose:

- **Weekends** are tinted plain `<div>`s — never selectable, never focusable.
  They need no explanation, so they get no interaction.
- **Holidays** are buttons with an amber diamond marker. They answer "why is the
  14th blank?" themselves, via *both* a hover tooltip and a click popover
  naming the holiday — the tooltip alone is unreachable on touch, and the
  popover alone hides the name behind an interaction nobody knows is there.
  Clicking also selects the date, so the summary card explains the closure.
- **Muhurat trading** is modelled as its own kind. 8 November 2026 falls on a
  Sunday: the regular session is closed as it is every Sunday, but the exchange
  holds a special ceremonial session. Calling it a "holiday" would be wrong in
  both directions, so it is neither.

The calendar footer states how many holidays fall in the month on view, and says
plainly when a year is outside the bundled list rather than implying there are
none.

---

## Scope of this phase

**Implemented**

- Account balance summary (read-only), served by the backend — still mock,
  deliberately, because there is no broker to report funds
- User-defined monthly target with inline editing, **persisted in PostgreSQL**
  and unchanged by a restart, with every edit recorded in an audit table
- Automatically derived daily target (computed server-side, in `Decimal`)
- Today's progress against the daily target
- Month-to-date progress against the monthly target
- Custom trading calendar with per-session markers
- Live IST market clock — phase, session timetable and the agent execution
  window, all derived client-side
- Weekend and exchange-holiday handling, with the 2026 NSE holiday calendar
  bundled as a frontend constant and surfaced by tooltip and popover
- Contextual summary for the selected date, which names the holiday when the
  exchange was shut
- Light and dark themes with a persisted, no-flash toggle
- Responsive 12-column bento layout, 360px → 1920px

- Persistent PostgreSQL 16 + TimescaleDB schema, Alembic migrations, and a
  deterministic idempotent development seed
- Database health reporting, with a 503 — never a fabricated figure — when the
  data store is unreachable

- **Angel One SmartAPI foundation — read-only, and off by default.** A broker
  adapter behind a `Protocol`, TOTP login with IST-midnight session expiry, a
  typed error taxonomy, a historical-range planner, a tested websocket client,
  and two `GET` endpoints reporting whether a broker is connected. Full
  reference: **[`docs/angel-one.md`](docs/angel-one.md)**
- Broker status card on the dashboard, stating the read-only guarantee outright
  rather than leaving it to be inferred from the absence of a trade button

**Deliberately not implemented** (out of scope for Phase 3)

Order placement or execution · automatic or paper trading · a rate limiter for
the SmartAPI endpoints · an instrument master download · a live feed
subscription or any consumer of one · scheduled broker polling · other brokers
(Zerodha / Upstox / Dhan) · NSE scraping · machine learning, signals or strategy
logic · API authentication · Redis / Kafka / Celery · Kubernetes · a
server-side holiday calendar (the 2026 list is bundled client-side instead, and
only 2026 is covered).

Connecting a broker **does not make the dashboard's figures real**. Every
performance number still carries `source: "mock"` or `source:
"development_seed"`, and it keeps carrying it with a live session attached —
there is a test that asserts exactly that.

The order, execution, trade, position, option-chain and journal tables **exist
and are empty**. They are the structural landing ground for later phases; a
seeded row in `orders` would be a claim that an order was placed, and none was.

> The monthly target is a **user-defined goal**, not projected or guaranteed
> income. The UI language is intentionally framed as *target* and *progress*.

---

## Stack

| Concern    | Choice                                   |
| ---------- | ---------------------------------------- |
| Framework  | Next.js 16 (App Router)                  |
| UI runtime | React 19                                 |
| Language   | TypeScript, `strict` + `noUncheckedIndexedAccess` |
| Styling    | Tailwind CSS 4 (`@theme inline` design tokens) |
| Icons      | Lucide React                             |
| Motion     | Motion (`motion/react`)                  |
| Dates      | date-fns                                 |
| Tooltips   | Radix UI (shadcn-style wrapper)          |

State is plain React state plus small hooks — no Redux, and no data-fetching
library: `src/lib/api/` is a thin typed wrapper over native `fetch`.
`localStorage` is now used for exactly one thing, the colour theme. The monthly
target moved to the backend in Phase 2, because two competing stores would
eventually disagree and the rounding rule belongs to the domain layer.

---

## Getting started

Three things: a database, the backend on port 8000, and the frontend on 3000.
Port 8000 is the only origin the frontend is configured to call, and port 3000
is the only origin the backend allows through CORS.

```bash
# the database — TimescaleDB on localhost:5432, data on a named volume
docker compose up -d

# terminal 1 — backend
cd backend
python -m venv .venv && .venv/Scripts/activate   # Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"
.venv/Scripts/python -m alembic upgrade head     # create the schema
.venv/Scripts/python -m app.db.seed              # optional demo data
uvicorn app.main:app --reload --port 8000        # http://localhost:8000/docs

# terminal 2 — frontend
npm install
cp .env.example .env.local
npm run dev                                      # http://localhost:3000
```

No database to hand? `REPOSITORY_BACKEND=mock` runs the API entirely in memory.
That is a configuration switch, not a fallback — nothing selects it
automatically, and a failed connection is reported as an error rather than
quietly serving invented figures.

| Script              | Purpose                        |
| ------------------- | ------------------------------ |
| `npm run dev`       | Development server             |
| `npm run build`     | Production build               |
| `npm run start`     | Serve the production build     |
| `npm run lint`      | ESLint                         |
| `npm run typecheck` | `tsc --noEmit`                 |

---

## Project structure

```
src/
  app/
    layout.tsx              Root layout, fonts, metadata, pre-paint theme script
    page.tsx                Server entry → <Dashboard />
    globals.css             Light/dark tokens (@theme inline) + base styles
  components/
    dashboard/
      Dashboard.tsx         Client orchestrator; owns interactive state
      DashboardHeader.tsx   Identity, market status, IST date, theme toggle
      MarketStatusPill.tsx  Live phase + the session-timetable popover
      AccountBalanceCard.tsx
      MonthlyTargetCard.tsx
      DailyTargetCard.tsx
      MonthlyProgressCard.tsx
      TradingCalendar.tsx
      TradingSummaryCard.tsx
    ui/
      BentoCard.tsx         Card shell + header
      CurrencyValue.tsx     INR figure with tabular numerals
      ProgressBar.tsx       Clamped, accessible progress indicator
      StatusIndicator.tsx   Status → icon + label + tone mapping
      StatRow.tsx
      ThemeToggle.tsx       Segmented light/dark control
      Tooltip.tsx           Hover/focus hint (Radix)
      Popover.tsx           Click-opened detail panel (Radix, focus-trapped)
      CardState.tsx         Shared loading skeleton + error/offline state
  hooks/
    useApiResource.ts       Generic fetch-with-state hook (loading/ready/error)
    useMonthlyTarget.ts     Backend-backed target: read, save, revision counter
    useMarketClock.ts       IST clock, 15s tick + refresh on tab focus
    useTheme.ts             Persisted theme via useSyncExternalStore
  lib/
    api/
      client.ts             The only place that speaks HTTP; ApiError, timeouts
      types.ts              Wire shapes + snake_case → camelCase transforms
      account.ts            GET /account/summary
      targets.ts            GET | PUT /targets/monthly
      performance.ts        GET /performance/{today,monthly,calendar,:date}
      agent.ts              GET /agent/status
    currency.ts             INR formatting + input parsing
    targetCalculations.ts   Target maths and status derivation
    dates.ts                Calendar grid + date formatting
    market.ts               IST clock, session timetable, market phase
    holidays.ts             Published NSE holiday calendar (2026), no API
    theme.ts                Theme constants + pre-paint init script
    utils.ts                cn()
  types/
    trading.ts              Domain types
docs/
  dashboard-*.png           Reference screenshots used in this README
```

---

## Core logic

**Daily target** — computed **once, in the backend**, using `Decimal` with an
explicit `ROUND_HALF_UP`. The frontend displays the returned value and never
recomputes it, so there is exactly one implementation of the rule:

```python
daily_target = (monthly_target / 30).quantize(Decimal(1), ROUND_HALF_UP)
```

Fractions below `.5` round down, `.5` and above round up:

| Monthly   | Daily  |
| --------- | ------ |
| ₹10,000   | ₹333   |
| ₹10,010   | ₹334   |
| ₹15,000   | ₹500   |
| ₹20,000   | ₹667   |

> **Production note:** the fixed 30-day denominator is a simplification, which
> is why the response reports `"calculation_mode": "calendar_days_30"`. It
> should become the number of remaining NSE trading sessions, which requires an
> exchange holiday calendar. Only the domain calculation changes; the wire
> contract already carries the mode so clients can tell the two apart.

**Session status** — derived, never stored, so the cards and the calendar can
never disagree:

| Condition                           | Status        |
| ----------------------------------- | ------------- |
| `profit === 0`                      | `not-started` |
| `profit < 0`                        | `loss`        |
| `0 < profit < dailyTarget`          | `in-progress` |
| `profit >= dailyTarget`             | `achieved`    |

Progress bars clamp at 100% while the displayed percentage is free to exceed it.

---

## Backend

A typed, asynchronous FastAPI service. It owns every number the dashboard
displays, including the notion of "today" — so the calendar, the summary card
and the daily target can never disagree about which session is current.

### Architecture

```
HTTP  →  API route        thin; parses and serialises, no business logic
      →  Service          orchestration and domain rules
      →  Repository       a typing.Protocol — the seam a broker slots into
      →  PostgreSQL       SQLAlchemy 2.x async + asyncpg   (default)
         or Mock          deterministic in-memory data     (REPOSITORY_BACKEND=mock)
```

Domain models (`app/domain/`) are kept separate from API schemas
(`app/schemas/`) so the wire format can change without disturbing the maths,
and vice versa. Dependencies are injected with FastAPI's `Depends`; there is no
global mutable state, and the repository singletons are `lru_cache`d with an
explicit `reset_repositories()` used by the test fixtures.

```
backend/
  app/
    main.py               create_app(): lifespan, CORS, middleware, handlers
    dependencies.py       DI wiring; backend selection, per-request session
    api/v1/               health, account, targets, performance, agent, broker
    services/             target, account, performance, agent, broker services
    brokers/              BrokerAdapter Protocol, models, errors
      angel_one/          client, auth, mapper, adapter, history, feed
    domain/               enums, models, clock, Decimal calculations
    schemas/              Pydantic v2 request/response models
    repositories/         Protocol interfaces + postgres/ + mock/
    db/                   engine & session, models/, health probe, seed
    core/                 settings, logging, exceptions, constants, time
  alembic/                migration environment + versions/
  tests/                  unit (no database) + integration/ (real database)
  pyproject.toml          deps + ruff/mypy/pytest config — no setup.py
```

### Tech

Python 3.12 · FastAPI · Uvicorn · Pydantic v2 · pydantic-settings ·
SQLAlchemy 2.x (asyncio) · asyncpg · Alembic · PostgreSQL 16 + TimescaleDB ·
httpx · websockets · pyotp · pytest + pytest-asyncio · Ruff · mypy
(`strict`). Times are
timezone-aware and centralised on `Asia/Kolkata` via `zoneinfo`; money is
`Decimal` in Python and `NUMERIC` in the database, never `float`.

All database access is asynchronous. There is no synchronous session and no
legacy `session.query(...)` anywhere in the codebase.

### Endpoints

All under `/api/v1`. JSON is `snake_case`; money is `Decimal` internally and a
plain JSON number on the wire.

| Method | Path                       | Purpose                                 |
| ------ | -------------------------- | --------------------------------------- |
| GET    | `/health`                  | Service status + database state          |
| GET    | `/health/live`             | Process only — never touches the database |
| GET    | `/health/ready`            | Readiness, including the database        |
| GET    | `/account/summary`         | Available balance, used margin, capital |
| GET    | `/targets/monthly`         | Monthly target + derived daily target   |
| PUT    | `/targets/monthly`         | Set the monthly target                  |
| GET    | `/performance/today`       | The current session                     |
| GET    | `/performance/monthly`     | Month-to-date totals                    |
| GET    | `/performance/calendar`    | One month of sessions (`?year=&month=`) |
| GET    | `/performance/{date}`      | A specific session                      |
| GET    | `/agent/status`            | Agent state — only `DISABLED` operative |
| GET    | `/broker/status`           | Broker config and session state — no network call |
| GET    | `/broker/connection-test`  | Authenticate and read the account profile |

Interactive docs: `/docs` (Swagger), `/redoc`, `/openapi.json`.

**There are deliberately no `/buy`, `/sell`, `/trade`, `/execute`, `/order` or
`/exit-all` endpoints, and no `/predict`, `/ai-signal` or `/next-trade`.** The
service cannot place an order or fabricate a prediction, because the routes to
do so do not exist. `POST /api/v1/broker/order` returns **404** — the path does
not exist — rather than 405, and a test asserts that on every verb.

### Environment

Configuration is `pydantic-settings`; copy `backend/.env.example` to
`backend/.env`. Real `.env` files are gitignored and must never be committed.

| Variable              | Default                 | Notes                                |
| --------------------- | ----------------------- | ------------------------------------ |
| `ENVIRONMENT`         | `development`           | Hides docs when `production`         |
| `CORS_ORIGINS`        | `http://localhost:3000` | Explicit list; never `*`             |
| `LOG_LEVEL`           | `INFO`                  | Structured logs with request IDs     |
| `REPOSITORY_BACKEND`  | `postgres`              | `mock` runs with no database         |
| `POSTGRES_HOST/PORT`  | `localhost` / `5432`    |                                      |
| `POSTGRES_DB/USER`    | `trading_agent`         |                                      |
| `POSTGRES_PASSWORD`   | dev default             | `SecretStr`; masked when printed     |
| `DB_HEALTH_TIMEOUT`   | `5.0`                   | Ceiling on the health `SELECT 1`     |
| `ANGEL_ONE_ENABLED`   | `false`                 | Master switch for the broker         |
| `ANGEL_ONE_API_KEY`   | —                       | `SecretStr`; optional, like all four |
| `ANGEL_ONE_CLIENT_CODE` | —                     | Masked to `******56` in responses    |
| `ANGEL_ONE_PIN`       | —                       | `SecretStr`; a string, PINs may start `0` |
| `ANGEL_ONE_TOTP_SECRET` | —                     | `SecretStr`; the base32 **seed**, not a code |
| `LIVE_TRADING_ENABLED`  | `false`               | Stated, not enforced — no order code exists |
| `PAPER_TRADING_ENABLED` | `false`               | Likewise                             |

The connection URL is assembled from these parts rather than read as a single
DSN, because a URL in an environment variable is the classic way a password
ends up in a shell history, a log line or a crash report.

Every Angel One field is optional: the API boots, serves the whole dashboard
and passes its suite with none of them set. A blank value reads as **absent**,
not as an empty string, so a half-filled template reports "not configured"
rather than sending a blank PIN to the broker and reporting "credentials
rejected". No broker value may carry a `NEXT_PUBLIC_` prefix — anything under
it is compiled into the JavaScript bundle. See
[`docs/angel-one.md`](docs/angel-one.md#configuration).

CORS is scoped to one explicit origin and to `GET, PUT, OPTIONS` only. Every
response carries an `X-Request-ID`; logs include it for correlation and never
contain secrets, auth headers or cookies.

### Errors

A single envelope, with no stack traces, file paths or internals leaked:

```json
{ "error": { "code": "VALIDATION_ERROR", "message": "monthly_target: Input should be greater than 0" } }
```

A database failure is a **503**, not a 500, with a fixed message that carries
no host, port, username or driver text:

```json
{ "error": { "code": "DATABASE_UNAVAILABLE", "message": "The service is temporarily unable to reach its data store. No data has been changed. Please retry shortly." } }
```

503 says "this request would have worked, try again", which is true and is what
a load balancer and a retry policy key on. **There is no fallback to mock
figures** — a dashboard showing an invented ₹4,690 because the database was
unreachable is worse than one showing an error, because the user would act on a
number that describes nothing.

### Testing

```bash
cd backend
.venv/Scripts/python -m pytest                     # 346 tests
.venv/Scripts/python -m pytest tests/test_broker.py # broker only, 47 tests
.venv/Scripts/python -m pytest tests/integration   # database only
.venv/Scripts/python -m ruff check .
.venv/Scripts/python -m mypy app tests             # strict, 104 files
```

API tests run in-process through `httpx.ASGITransport` — no socket, no port.
Integration tests build a throwaway `trading_agent_test` database by running
the real migrations, and skip with a reason when no database is reachable
rather than failing. They never touch the development database.

### Limitations

The 30-day denominator for the daily target is a simplification; the real
figure is remaining NSE trading sessions, which needs an exchange holiday
calendar. Account balance is still mock, deliberately — the broker adapter can
read funds, but nothing wires that reading into `/account/summary`, and an
endpoint that switched between invented and real figures without saying which
it served would be worse than one that is consistently honest about being mock.
There is no API authentication and no rate limiting, on this service or against
Angel One's published per-endpoint limits.

Nothing in the Angel One integration has been exercised against a live account.
Values that the documentation and the official SDK disagree on, or are silent
about, are marked `UNVERIFIED` in the source and listed in
[`docs/angel-one.md`](docs/angel-one.md#known-limits-and-unverified-values).

### Roadmap — the trading pipeline

Documented, **not implemented**. The intended order, once a broker adapter
exists:

```
Model  →  Signal  →  Options Selector  →  Risk Engine  →  Execution Validation  →  Broker Adapter
```

The **Risk Engine holds veto authority**: it sits before execution validation
and can reject any proposed trade regardless of model confidence. No signal may
reach a broker adapter without passing it.

---

## Phase 3 — Data Foundation

Volatile development storage replaced with a persistent, professional data
layer. Full schema reference, rationale and operational notes:
**[`docs/database.md`](docs/database.md)**.

### What it adds

- **PostgreSQL 16 + TimescaleDB** via Docker Compose, with a healthcheck and a
  named volume (`nifty_agent_postgres_data`) that outlives the container
- **15 tables** — the application half in use today, the trading half defined
  and deliberately empty
- **Three hypertables** — `ohlcv_candles` (7-day chunks), `option_quotes`
  (1-day), `india_vix` (30-day), sized by expected write volume
- **Alembic migrations**, async, with the URL taken from settings so no
  password is ever written to a committed file
- **`python -m app.db.seed`** — deterministic, idempotent, non-destructive
- **Liveness / readiness split** and a 503 contract for database failure

### The decisions worth knowing

| Decision | Reason |
| --- | --- |
| Money is `NUMERIC(20,4)` / `Decimal` | Binary floating point cannot represent `0.10`. A paisa of drift per operation compounds silently. |
| UUID primary keys | Rows can be built before insert and merged from several producers. The seed derives UUIDv5 keys from natural keys, so a re-run reproduces the same identifiers. |
| `VARCHAR` + `CHECK`, not native enums | Adding a value to a PostgreSQL enum is an awkward, hard-to-reverse migration; an unconstrained `VARCHAR` lets `"BUYY"` through. A `CHECK` derived from the `StrEnum` gives the guarantee with a one-line swap. |
| Every FK is `ON DELETE RESTRICT` | Deleting an instrument must not silently take months of candles with it. There is no `DELETE` endpoint and no `POST /reset-database`. |
| `daily_target` stored per row | It records the goal actually in force that day. Deriving it from today's target would rewrite history on every edit, making a missed day look achieved. |
| Absence ≠ zero | A date with no row means *no trading*; that is a different fact from *traded and broke even*, and merging them corrupts the win-rate denominator. |
| Engine opened lazily | An unreachable database becomes failing requests with a real error and a healthy `/health/live`, not a process that refuses to boot. |

### Provenance

Two independent labels, answering different questions:

| Where | Values | Means |
| --- | --- | --- |
| API envelope `source` | `database`, `mock` | Where the **service** read the figure from |
| Row column `source` | `development_seed`, later `nse` | Where the **data** came from |

So a seeded P&L arrives as `source: database` in the envelope while the row
itself still says `development_seed` — invented data stays traceable even
after it is persisted. The account endpoint reports `source: mock` **even with
a database present, and even with a broker connected**, because no code path
reads a balance from the broker into it. There is a test that configures a
full credential set and asserts the account summary still says `mock`.

---

## Phase 3 — Angel One SmartAPI foundation

A secure, tested, **read-only** broker foundation. Full reference, including
every design decision and every unverified value:
**[`docs/angel-one.md`](docs/angel-one.md)**. What was built, what was
measured and what was deliberately left out:
**[`docs/phase-3-report.md`](docs/phase-3-report.md)**.

### What it adds

- **`BrokerAdapter`** — a `typing.Protocol` with eleven methods: two for the
  session, nine that read. None places, modifies or cancels anything.
  A test double is a small class with the right shape rather than
  a subclass dragging in real constructor behaviour, and `mypy` checks both
  against the same contract
- **Broker-neutral records** — frozen dataclasses, `Decimal` for every price
  and Greek, `SecretStr` for every token, `None` meaning "the broker did not
  say" and never zero
- **An eight-way error taxonomy** organised by *what the operator should do*,
  so "not configured" (409) never arrives dressed as "credentials rejected"
- **TOTP authentication** with the seed confined to one module, session expiry
  computed as the next IST midnight, an `asyncio.Lock` around the login path,
  and exactly one retry on session expiry
- **A historical-range planner** that splits a wide request into chunks Angel
  One will accept, returning a list rather than a generator so a caller can see
  "this is 340 requests" before issuing the first
- **A SmartWebSocketV2 client** with replayed subscriptions, jittered bounded
  reconnect, a 10-second heartbeat, and a binary tick decoder that converts
  paise as `Decimal`
- **`broker_account_snapshots`** — an append-only log of observations; tokens
  are deliberately never stored
- **`GET /broker/status`** and **`GET /broker/connection-test`**, plus a
  dashboard card that states the read-only guarantee in words

### The decisions worth knowing

| Decision | Reason |
| --- | --- |
| No `place_order` anywhere | Not "not yet implemented" — not present. A method that exists but raises is still a method a future call site can find, and the only reliable guarantee is the absence of any code that could transmit an order. |
| Not the official SDK | `smartapi-python` is synchronous `requests`, which blocks the whole event loop inside an async worker. Its constructor also resolves the machine's public IP and reads the host MAC before any call is made. |
| `enabled`, `configured`, `connected` reported separately | They have different remedies. One boolean tells an operator something is wrong without telling them which thing. |
| A blank credential reads as absent | `ANGEL_ONE_PIN=` in a copied template would otherwise report "configured", send a blank PIN, and come back as "credentials rejected" — the wrong diagnosis pointed at the wrong person. |
| The connection test is a `GET` | The session is cached, so repeated calls are not repeated logins (there is a test). CORS allows `GET, PUT, OPTIONS`, and adding `POST` for one diagnostic would widen the write surface of the entire API. |
| A lapsed session reports `connected: false` | Rather than a past `session_expires_at`. The badge must not assert a live connection on a credential the broker has already stopped accepting. |
| Client code masked server-side | The browser is never given the full value to mask itself; anything the browser can render, the browser received. |
| `order_placement_available` is `Literal[False]` | A payload claiming otherwise fails response validation. The frontend hard-codes it too rather than reading it through, so a server-side guarantee does not become a value a component renders on trust. |
| No rate-limit error-code set | An earlier draft guessed five codes; three were wrong. A wrong classification sends a caller down a recovery path that cannot work, which is worse than having none. |

---

## Accessibility

- Semantic landmarks, real `<button>` elements, `aria-label` on icon-only
  controls, visible focus rings
- A `<table>`-based calendar with weekday column headers and per-cell labels
  that read the date, status and signed P&L
- Status is conveyed by icon **and** text as well as colour
- Every text tone was measured against every surface it can land on — card,
  muted card, recessed tile, bare canvas — and clears **WCAG AA (4.5:1) in both
  themes**. Worst case is 4.64:1 (light) and 4.78:1 (dark).
- Motion is limited to ~150–250ms entrances and respects
  `prefers-reduced-motion`

---

## Verified

**Backend** — 346 tests pass (unit + integration against a real TimescaleDB),
`ruff check` and `ruff format --check` clean (107 files), `mypy --strict` clean
across 104 files. Verified against a live Uvicorn server, not only the test
suite: OpenAPI schema, `PUT 15000 → 500`, `20000 → 667`, `10010 → 334`,
`-5000 → 422` with the error envelope and no traceback, and a 404 probe
confirming the order and prediction routes genuinely do not exist.

**Broker (Phase 3)** — 47 of those tests cover the Angel One layer, every one
of them against a mocked transport; nothing in this repository has been run
against a live Angel One account. `GET /api/v1/broker/status` was probed on the
running server and reported `enabled: false, configured: false, connected:
false`. A blank credential (`ANGEL_ONE_PIN=`) was confirmed to read as *absent*
rather than as an empty PIN, so a half-filled `.env` reports "not configured"
instead of "credentials rejected". A grep of the built bundle (`.next/static`,
`.next/server`) for any Angel One credential name returns nothing; the only
`NEXT_PUBLIC_` variable in the project is `NEXT_PUBLIC_API_BASE_URL`. The
backend declares no `POST`, `PATCH` or `DELETE` route anywhere —
`grep -rn "@router\.\(post\|delete\|patch\)" app/` is empty, and the single
`PUT` in the application is the monthly target. Both broker routes are `GET`.

**Database**, verified against the running stack rather than assumed:

- **Durability** — `docker compose down` (which removes the container
  entirely) then `up -d`: the monthly target, all 17 seeded sessions and the
  Timescale chunk layout (`india_vix` 2 chunks, `ohlcv_candles` 4) were intact
  afterwards, on the named volume
- **Restart survival (§60)** — ₹15,000 set through the API yields ₹500/day, and
  a **separate Python process** reads back ₹15,000 unchanged
- **Determinism** — identical business-column checksums across a full wipe and
  reseed; re-running the seed leaves every row and the audit log untouched, and
  does not overwrite a manually edited target
- **Migrations** — every integration run drops the test database and rebuilds
  it from `alembic upgrade head`, so a broken migration fails the suite.
  `downgrade base` → `upgrade head` round-trips cleanly, and `alembic check`
  reports *no new upgrade operations*, so the models and the migration have not
  drifted apart
- **Database down** — liveness stays `200 alive`; `/health` and `/health/ready`
  return 503 `degraded`; data endpoints return 503 `DATABASE_UNAVAILABLE`; the
  account endpoint still returns `200` with `source: mock`; and no response
  body contains a host, port, username, driver name or traceback
- **Recovery** — three consecutive successes in the same process on the same
  pool after the container came back; `pool_pre_ping=True` heals it without a
  restart

The database-down path was found by actually stopping the container: a refused
TCP connection arrives as a bare `ConnectionRefusedError` from the event loop's
socket layer, which the original `SQLAlchemyError` handler never saw, and it
escaped as a 500 with a traceback. Both shapes are now handled and tested.

**Frontend** — `npm run lint`, `npm run typecheck` and `npm run build` all pass
clean, with **zero console warnings, errors or exceptions** in the browser.
No hydration mismatch: no `new Date()` is evaluated during render. The clock
starts `null` on the server and is filled by an effect after mount.

**Integration**, checked in a real browser against the running API:

- All six cards render live backend data on load
- Editing the monthly target to ₹30,000 recalculates the whole dashboard:
  daily target → ₹1,000, today's +₹420 flips from *Target achieved* to
  *Below target* with ₹580 remaining, monthly progress → 14.3%, and the
  calendar re-colours every session against the new target
- With the backend stopped, every *figure* shows as unavailable with offline
  copy and a Retry button — **never a stale or default figure**, never `NaN` or
  `undefined` — and Retry recovers every card in place once it is back up

**What survives a total API outage**, confirmed with the backend process stopped
(`fetch` to it refused) rather than simulated:

- the header date — `25 September 2026`, from the IST clock
- the market phase — `Market Open`, correctly, during the live session; the
  previous build was hardcoded to *Market Closed* at all times
- the full session-timetable popover, including the live `11:52 IST` reading
- the entire calendar grid: weekdays, weekends, and 14 September rendered as a
  holiday with `aria-label` *"Monday, 14 September 2026. Ganesh Chaturthi.
  Exchange holiday, no trading session."*
- clicking it opens the holiday popover **and** selects the date, and the
  summary card explains *"Ganesh Chaturthi — the exchange is closed, so there is
  no session to record"* instead of blaming the backend
- the footer's *"1 exchange holiday this month"*

Layout measured at 1512px: two rows, `5-4-3` over `3-4-5`, with Today's Target,
Monthly Progress and the Calendar sharing one row exactly as specified.

Checked in both themes: layout at 360 / 768 / 1024 / 1280 / 1440px with no
horizontal overflow, INR formatting, calendar accuracy against the real 2026
calendar, all 16 dated holiday weekday labels verified against the true
calendar, weekend non-interactivity, theme persistence across reload and over
the OS preference, and edge cases (zero / negative / non-numeric / oversized).
