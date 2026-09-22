# NIFTY Agent — Dashboard

Monitoring dashboard for an autonomous NIFTY options trading agent.

The repository now contains **two applications**: a Next.js frontend
(`src/`) and a FastAPI backend (`backend/`). Every figure on screen is fetched
from the backend over HTTP — the frontend no longer reads a local mock module.

The backend's own data is still mock data, served from in-memory repositories
behind a Protocol boundary. **There is no broker connection, no live market
data, no order placement and no automatic trading.** Every response is tagged
`"source": "mock"` so a consumer can never mistake it for real money.

| Phase       | Scope                                                      |
| ----------- | ---------------------------------------------------------- |
| **Phase 1** | Frontend, design system, bento layout, calendar — mock data |
| **Phase 2** | FastAPI backend + full frontend integration — mock data     |

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

The toggle itself is a two-position segmented track rather than a single
morphing icon — the user can see both states and which one is active, so it
reads as an explicit setting instead of a mystery-meat button. The thumb is a
shared layout element, so selection glides between positions in one motion.

---

## Market sessions

NSE equity and F&O trade **9:15 AM – 3:30 PM IST, Monday to Friday**. The
session string appears in the header next to the market status, and again in the
calendar footer.

Saturdays and Sundays are rendered as non-trading days throughout:

- weekend columns are tinted and dimmed, and carry a square "market closed"
  marker rather than a round session dot
- weekend cells are plain `<div>`s, not buttons — they can never be selected
- screen readers get "Saturday, 5 September 2026. Market closed."
- selecting nothing on a weekend is impossible, but the summary card still has a
  weekend empty state for completeness

> **Production note:** exchange *holidays* are not derivable client-side. V1
> only knows the weekend rule. Once the backend exposes the holiday calendar,
> `isTradingDay()` in `src/lib/market.ts` should consult it too.

---

## Scope of this phase

**Implemented**

- Account balance summary (read-only), served by the backend
- User-defined monthly target with inline editing, persisted by the backend
- Automatically derived daily target (computed server-side, in `Decimal`)
- Today's progress against the daily target
- Month-to-date progress against the monthly target
- Custom September 2026 trading calendar with per-session markers
- Weekend / market-closed handling and NSE session hours
- Contextual summary for the selected date
- Light and dark themes with a persisted, no-flash toggle
- Responsive 12-column bento layout, 360px → 1920px

**Deliberately not implemented** (out of scope for Phase 2)

Broker API integration (Angel One / Zerodha / Upstox / Dhan) · broker
authentication · live prices · option chains · WebSocket market feed · order
placement or execution · automatic or paper trading · machine learning,
signals or strategy logic · API authentication · persistent database ·
Redis / Kafka / Celery · Docker / Kubernetes · exchange holiday calendar.

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

Two processes. The backend must be running on port 8000 — it is the only origin
the frontend is configured to call, and port 3000 is the only origin the backend
allows through CORS.

```bash
# terminal 1 — backend
cd backend
python -m venv .venv && .venv/Scripts/activate   # Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000        # http://localhost:8000/docs

# terminal 2 — frontend
npm install
cp .env.example .env.local
npm run dev                                      # http://localhost:3000
```

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
      DashboardHeader.tsx   Identity, market status + hours, date, theme toggle
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
      Tooltip.tsx
    ui/
      CardState.tsx         Shared loading skeleton + error/offline state
  hooks/
    useApiResource.ts       Generic fetch-with-state hook (loading/ready/error)
    useMonthlyTarget.ts     Backend-backed target: read, save, revision counter
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
    market.ts               NSE session hours + trading-day rules
    theme.ts                Theme constants + pre-paint init script
    utils.ts                cn()
  data/
    mockTradingData.ts      Single source of mock data
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

## Backend — Phase 2

A typed, asynchronous FastAPI service. It owns every number the dashboard
displays, including the notion of "today" — so the calendar, the summary card
and the daily target can never disagree about which session is current.

### Architecture

```
HTTP  →  API route        thin; parses and serialises, no business logic
      →  Service          orchestration and domain rules
      →  Repository       a typing.Protocol — the seam a broker slots into
      →  Mock provider    deterministic in-memory data
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
    dependencies.py       DI wiring; cached repositories + reset hook
    api/v1/               health, account, targets, performance, agent routes
    services/             target, account, performance, agent services
    domain/               enums, models, Decimal calculations
    schemas/              Pydantic v2 request/response models
    repositories/         Protocol interfaces + mock implementations
    core/                 settings, logging, exceptions, constants, time
  tests/                  114 tests: unit (domain) + API (httpx ASGITransport)
  pyproject.toml          deps + ruff/mypy/pytest config — no setup.py
```

### Tech

Python 3.12 · FastAPI · Uvicorn · Pydantic v2 · pydantic-settings · httpx ·
pytest + pytest-asyncio · Ruff · mypy (`strict`). Times are timezone-aware and
centralised on `Asia/Kolkata` via `zoneinfo`.

### Endpoints

All under `/api/v1`. JSON is `snake_case`; money is `Decimal` internally and a
plain JSON number on the wire.

| Method | Path                       | Purpose                                 |
| ------ | -------------------------- | --------------------------------------- |
| GET    | `/health`                  | Liveness, service name, version         |
| GET    | `/account/summary`         | Available balance, used margin, capital |
| GET    | `/targets/monthly`         | Monthly target + derived daily target   |
| PUT    | `/targets/monthly`         | Set the monthly target                  |
| GET    | `/performance/today`       | The current session                     |
| GET    | `/performance/monthly`     | Month-to-date totals                    |
| GET    | `/performance/calendar`    | One month of sessions (`?year=&month=`) |
| GET    | `/performance/{date}`      | A specific session                      |
| GET    | `/agent/status`            | Agent state — only `DISABLED` operative |

Interactive docs: `/docs` (Swagger), `/redoc`, `/openapi.json`.

**There are deliberately no `/buy`, `/sell`, `/trade`, `/execute`, `/order` or
`/exit-all` endpoints, and no `/predict`, `/ai-signal` or `/next-trade`.** The
service cannot place an order or fabricate a prediction, because the routes to
do so do not exist.

### Environment

Configuration is `pydantic-settings`; copy `backend/.env.example` to
`backend/.env`. Real `.env` files are gitignored and must never be committed.

| Variable       | Default                   | Notes                            |
| -------------- | ------------------------- | -------------------------------- |
| `ENVIRONMENT`  | `development`             | Hides docs when `production`     |
| `CORS_ORIGINS` | `http://localhost:3000`   | Explicit list; never `*`         |
| `LOG_LEVEL`    | `INFO`                    | Structured logs with request IDs |

CORS is scoped to one explicit origin and to `GET, PUT, OPTIONS` only. Every
response carries an `X-Request-ID`; logs include it for correlation and never
contain secrets, auth headers or cookies.

### Errors

A single envelope, with no stack traces, file paths or internals leaked:

```json
{ "error": { "code": "VALIDATION_ERROR", "message": "monthly_target: Input should be greater than 0" } }
```

### Testing

```bash
cd backend
.venv/Scripts/python -m pytest      # 114 tests
.venv/Scripts/python -m ruff check .
.venv/Scripts/python -m mypy .      # strict, 53 files
```

API tests run in-process through `httpx.ASGITransport` — no socket, no port.

### Limitations

Data is mock and in-memory, so **the monthly target resets when the process
restarts**. The 30-day denominator for the daily target is a simplification;
the real figure is remaining NSE trading sessions, which needs an exchange
holiday calendar. There is no authentication, no rate limiting and no database.

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

**Backend** — 114 tests pass, `ruff check` and `ruff format --check` clean,
`mypy --strict` clean across 53 files. Verified against a live Uvicorn server,
not only the test suite: OpenAPI schema, `PUT 15000 → 500`, `20000 → 667`,
`10010 → 334`, `-5000 → 422` with the error envelope and no traceback, and a
404 probe confirming the order and prediction routes genuinely do not exist.

**Frontend** — `npm run lint`, `npx tsc --noEmit` and `npm run build` all pass
clean, with **zero console warnings, errors or exceptions** in the browser
(including no React hydration mismatches — no `new Date()` is evaluated during
render; the trading date comes from the backend).

**Integration**, checked in a real browser against the running API:

- All six cards render live backend data on load
- Editing the monthly target to ₹30,000 recalculates the whole dashboard:
  daily target → ₹1,000, today's +₹420 flips from *Target achieved* to
  *Below target* with ₹580 remaining, monthly progress → 14.3%, and the
  calendar re-colours every session against the new target
- With the backend stopped, all six cards show *unavailable* with offline copy
  and a Retry button — **never a stale or default figure**, never `NaN` or
  `undefined` — and Retry recovers every card in place once it is back up

Checked in both themes: layout at 360 / 768 / 1024 / 1280 / 1440px with no
horizontal overflow, INR formatting, calendar accuracy against the real 2026
calendar, weekend non-interactivity, theme persistence across reload and over
the OS preference, and edge cases (zero / negative / non-numeric / oversized).
