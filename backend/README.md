# NIFTY Trading Agent API — Phase 3

FastAPI backend serving the dashboard in the repository root, backed by
PostgreSQL 16 + TimescaleDB. Schema reference: [`../docs/database.md`](../docs/database.md).

> **Every figure this API returns is invented.** No broker is connected, no
> market-data feed is subscribed, no order can be placed, and no automated
> trading exists. Persistence makes a number durable, not real. Every payload
> carries a `source` field, and every seeded row carries
> `source = 'development_seed'`, so a demo number can never be mistaken for a
> real balance.

---

## Architecture

The dependency arrow points one way only:

```
HTTP route          api/v1/*.py        no business logic, no calculations
    ↓
Service             services/*.py      orchestration, validation, mapping
    ↓
Repository (Protocol)  repositories/interfaces/   the replaceable seam
    ↓
PostgreSQL             repositories/postgres/     SQLAlchemy 2.x async (default)
  or Mock              repositories/mock/         in-memory, REPOSITORY_BACKEND=mock
```

Pure business rules live in `domain/calculations.py` and are imported by
services. They are synchronous and side-effect free, which is why they can be
tested exhaustively without a client, an event loop, or a fixture.

`dependencies.py` is the only module that names a concrete repository, and the
only place the backend choice is made. Swapping in a broker adapter is an edit
there and nowhere else.

The backend choice is **configuration, not fallback**. Nothing catches a
connection error and quietly serves mock figures instead.

### Transactions

One request is one transaction. The session is opened and committed by the
dependency in `db/session.py`, never by a repository — repositories `flush()`
when they need a generated key and never `commit()`. Committing per repository
call would make a multi-write service operation partially durable, which for
financial records is worse than failing outright.

### Why the layers are shaped this way

| Decision | Reason |
| --- | --- |
| Repositories are `async` Protocols | Every future implementation does I/O. Making the seam async now means Phase 3 does not have to rewrite call sites. |
| Calculations are `sync` | They are CPU-only. `async` on a pure function is decoration that buys nothing and costs clarity. |
| Domain dataclasses separate from Pydantic schemas | The wire contract can change — field renames, versioning, camelCase — without dragging the business rules along. |
| Money is `Decimal` end to end | Binary floating point cannot represent `0.10`. A figure that drifts a paisa per operation is a defect that compounds silently. `NUMERIC(20,4)` in the database. |
| The engine is opened lazily, not at startup | An unreachable database becomes failing requests with a real error and a healthy `/health/live`, rather than a process that refuses to boot and is hard to diagnose from outside. |

---

## Endpoints

All routes are under `/api/v1`.

| Method | Path | Returns |
| --- | --- | --- |
| `GET` | `/health` | Service status, version, environment, database status |
| `GET` | `/health/live` | Process liveness only — never touches the database |
| `GET` | `/health/ready` | Readiness — `503` when the database is unreachable |
| `GET` | `/account/summary` | Available balance, used margin, total capital |
| `GET` | `/targets/monthly` | Monthly target + derived daily target |
| `PUT` | `/targets/monthly` | Sets the monthly target, returns the recalculated daily target |
| `GET` | `/performance/today` | Today's session against the daily target |
| `GET` | `/performance/monthly` | Month-to-date totals against the monthly target |
| `GET` | `/performance/calendar?year=&month=` | Every recorded session in a month |
| `GET` | `/performance/{date}` | One specific session |
| `GET` | `/agent/status` | Agent state and capability flags (all disabled) |

`PUT /targets/monthly` is the **only** write endpoint in the service.

### Deliberately absent

No `/buy`, `/sell`, `/trade`, `/execute`, `/order`, `/exit-all`, `/predict` or
`/ai-signal`. A test in `tests/test_health.py` walks the generated OpenAPI
document and fails the build if any route matching those shapes ever appears,
or if any method other than `GET`/`PUT` is registered.

---

## Business rules

### Daily target

```
daily_target = round_half_up(monthly_target / 30)
```

| Monthly | Daily |
| --- | --- |
| ₹10,000 | ₹333 |
| ₹10,010 | ₹334 |
| ₹15,000 | ₹500 |
| ₹20,000 | ₹667 |

Rounding is explicitly `ROUND_HALF_UP`. `Decimal`'s default is
`ROUND_HALF_EVEN`, which would turn ₹45 → ₹2 instead of ₹2 at the `.5` hinge
and quietly disagree with the frontend rule.

> **Phase 3 note:** the fixed 30-day denominator mirrors the Phase 1 frontend.
> It should eventually be replaced with the actual count of remaining NSE
> trading sessions, which needs the exchange holiday calendar. Only
> `ASSUMED_DAYS_PER_MONTH` and `calculate_daily_target` change.

### Session status

| Condition | Status |
| --- | --- |
| `realized_pnl < 0` | `loss` |
| `realized_pnl == 0` | `not_started` |
| `0 < realized_pnl < daily_target` | `in_progress` |
| `realized_pnl >= daily_target` | `achieved` |

Ordering matters: a loss reads as a loss even against a ₹0 target.

### Remaining to target

```
remaining_to_target = max(daily_target - realized_pnl, 0)
```

Measured from the **current** P&L, so a session at −₹120 against a ₹333 target
reports ₹453 — the ground that actually has to be made up. Floored at zero,
because surplus is already legible from the progress percentage.

### Progress percentage

Uncapped. Beating a target is information the API reports faithfully;
clamping is the progress bar's job, not the number's.

### Win rate

`wins / trades × 100`, returning `0.00` when there are no trades. Note it is
wins over *trades*, not wins over wins-plus-losses — that leaves room for a
breakeven outcome later.

---

## Money on the wire

Monetary values are `Decimal` throughout the application and are quantized to
two decimal places before reaching a schema. They are emitted as **JSON
numbers**, not strings, so the frontend consumes them without a parse step.

JSON has no concept of a trailing zero: `25000.00` and `25000.0` are the same
number and the encoder picks the byte form. What matters — and what
`tests/test_account.py` asserts — is that no binary floating-point artifact
(`25000.000000000004`) can appear. Quantizing to paise before encoding
guarantees that, because every such value is exactly representable. Display
formatting to two decimals is the frontend's job, via `Intl.NumberFormat`.

---

## Missing-data policy

The read paths answer "no record" differently, on purpose:

| Path | Behaviour |
| --- | --- |
| `GET /performance/{date}` | **404.** A specific historical session that was never recorded is a miss, and the caller should know. |
| `GET /performance/today` | **Zero-filled record.** The dashboard must always render today, and a day that has not traded yet is genuinely `not_started`. |
| `GET /performance/calendar` | **Omits** the date. Lets the UI distinguish "no session recorded" from "traded to flat" — different facts. |

---

## When the database is down

| Endpoint | Behaviour |
| --- | --- |
| `GET /health/live` | **200.** The process is alive; that is the entire question. A liveness probe that consults the database gets the container killed for a fault outside the container. |
| `GET /health` | **503**, body still rendered, `database.state: "down"`. A bare 503 tells an operator nothing about which dependency failed. |
| `GET /health/ready` | **503.** Not ready to take traffic. |
| Data endpoints | **503** `DATABASE_UNAVAILABLE`, and never a mock figure in place of a real one. |
| `GET /account/summary` | **200**, `source: "mock"` — it never touched the database. |

The 503 body is fixed text. The driver's own message is
`connection to server at "10.0.3.14", port 5432 failed: FATAL: password
authentication failed for user "trading_agent"` — a host, a port, a username and
the existence of a password, all in one string. It is logged, never returned;
`tests/test_error_handling.py` asserts each fragment is absent from the response.

---

## Setup

Requires Python 3.12+ and a running PostgreSQL with TimescaleDB.

```bash
docker compose up -d        # from the repository root

cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate

pip install -e ".[dev]"
cp .env.example .env        # optional; defaults work for local development

python -m alembic upgrade head    # create the schema
python -m app.db.seed             # optional demo data, development only
```

`REPOSITORY_BACKEND=mock` runs the API with no database at all — useful on a
machine without Docker, and what the unit test suite uses.

Dependencies are managed by `pyproject.toml` alone. There is no
`requirements.txt`, `Pipfile` or lockfile from another tool to drift out of
sync with it.

## Commands

| Command | Purpose |
| --- | --- |
| `uvicorn app.main:app --reload --port 8000` | Development server |
| `python -m alembic upgrade head` | Apply migrations |
| `python -m alembic downgrade -1` | Roll back the last migration |
| `python -m alembic check` | Fail if the models have drifted from the migrations |
| `python -m app.db.seed` | Load deterministic demo data (development only) |
| `pytest` | Test suite |
| `pytest -q --tb=short` | Test suite, compact output |
| `ruff check .` | Lint |
| `ruff format --check .` | Formatting check |
| `mypy app tests` | Type check (strict) |

### Tests

Two suites, one command. `tests/` runs against the mock backend and needs
nothing installed; `tests/integration/` creates and drops `trading_agent_test`,
builds its schema by running the **real** migrations, and exercises the
PostgreSQL path.

If no database is reachable the integration suite **skips**, loudly, with the
address it tried in the reason. A hard failure would make `pytest` red on a
machine without Docker, which trains people to ignore red; a silent pass would
report success for tests that never ran.

API documentation is at `http://localhost:8000/docs` (Swagger),
`/redoc`, and `/openapi.json`. All three are disabled when
`ENVIRONMENT=production`.

---

## Configuration

Settings are typed via pydantic-settings and read from the environment or
`backend/.env`. See `.env.example` for the full list.

Connection settings are supplied as **parts** — `POSTGRES_HOST`, `POSTGRES_PORT`,
`POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` — and assembled into a URL by
`Settings`, rather than read as one pre-built DSN. A password containing `@` or
`/` breaks a hand-assembled DSN silently; letting the URL type do the escaping
removes the class of bug. `safe_database_url` is the only form that is ever
logged or returned, and it masks the password.

`.env` is gitignored. `POSTGRES_PASSWORD` is the first real secret the project
has — there is still no broker and no authentication — and the loading path
established in Phase 2 is what it lands in, rather than source control.

CORS origins are explicit and never `*`; the middleware runs with credentials
enabled, for which the wildcard is invalid.

---

## Logging

One stdout handler, with a correlation ID injected into every record by a
logging filter. An inbound `X-Request-ID` is honoured (length-capped at 128
characters) so a trace can span the frontend and the API; otherwise one is
generated and echoed back on the response.

Each request logs method, path, status and duration. Headers, cookies, query
strings and bodies are **never** logged. That policy is set now, while there
is nothing sensitive to leak, because it is much harder to retrofit once
broker credentials exist.

---

## Current limitations

- All data is invented. Persistence makes a figure durable, not real — no
  broker has reported any of it.
- The account summary is deliberately **not** persisted (§42). A balance sitting
  in a database reads as authoritative in a way a literal in a mock module does
  not, and no broker has reported funds.
- The order, trade, position and option-chain tables exist, are migrated, and
  are **empty**. They are schema, not behaviour.
- The seeded journal is pinned to the current month so the demo story stays
  coherent; `get_reference_date()` is the seam where a real clock plugs in.
- No exchange holiday calendar. The frontend knows only the weekend rule.
- No authentication. The API assumes a single trusted local user.
- No rate limiting. That belongs with authentication and an ingress layer, not
  in an in-process limiter that cannot survive a second worker.

---

## Roadmap

Phases 2 and 3 exist so these can be added without restructuring:

```
Phase 3   PostgreSQL / TimescaleDB · persistent target · trade journal   ✅ done
Phase 4   Broker adapter · market data · option-chain ingestion
Phase 5   Feature engine · ML models · signal engine
Phase 6   Options selector · risk engine · execution engine · position manager
```

Phase 4 writes into tables that already exist. `orders`, `trades`, `positions`,
`option_contracts` and `option_quotes` were migrated in Phase 3 precisely so
that connecting a broker is an insert, not a schema redesign under time
pressure. The NSE holiday calendar is still outstanding.

### Financial safety architecture

A constraint for every later phase, recorded now while it is still free to
adopt:

```
Model → Signal → Options Selector → Risk Engine → Execution Validation → Broker Adapter
```

A model-generated signal must **never** reach a broker adapter directly. The
risk engine sits in the path and holds veto authority over every order. This is
documentation only — none of those components exist yet — but the
current architecture is shaped so none of them can be short-circuited later.

A `BrokerAdapter` abstraction is deliberately **not** defined yet. Writing an
interface for an integration nobody has attempted produces a contract shaped by
guesses rather than by a real broker's semantics. It belongs in Phase 4,
alongside the first concrete implementation that can validate it.
