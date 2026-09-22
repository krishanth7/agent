# NIFTY Trading Agent API — Phase 2

FastAPI backend serving the dashboard in the repository root.

> **All figures this API returns are mock data.** No broker is connected, no
> market-data feed is subscribed, no order can be placed, and no automated
> trading exists. Every payload carries a `source` field stating its
> provenance so a demo number can never be mistaken for a real balance.

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
Mock implementation    repositories/mock/         deterministic demo data
```

Pure business rules live in `domain/calculations.py` and are imported by
services. They are synchronous and side-effect free, which is why they can be
tested exhaustively without a client, an event loop, or a fixture.

`dependencies.py` is the only module that names a concrete repository. Swapping
the mocks for PostgreSQL or a broker adapter is an edit there and nowhere else.

### Why the layers are shaped this way

| Decision | Reason |
| --- | --- |
| Repositories are `async` Protocols | Every future implementation does I/O. Making the seam async now means Phase 3 does not have to rewrite call sites. |
| Calculations are `sync` | They are CPU-only. `async` on a pure function is decoration that buys nothing and costs clarity. |
| Domain dataclasses separate from Pydantic schemas | The wire contract can change — field renames, versioning, camelCase — without dragging the business rules along. |
| Money is `Decimal` end to end | Binary floating point cannot represent `0.10`. A figure that drifts a paisa per operation is a defect that compounds silently. |

---

## Endpoints

All routes are under `/api/v1`.

| Method | Path | Returns |
| --- | --- | --- |
| `GET` | `/health` | Service status, version, environment |
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

## Setup

Requires Python 3.12+.

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate

pip install -e ".[dev]"
cp .env.example .env        # optional; defaults work for local development
```

Dependencies are managed by `pyproject.toml` alone. There is no
`requirements.txt`, `Pipfile` or lockfile from another tool to drift out of
sync with it.

## Commands

| Command | Purpose |
| --- | --- |
| `uvicorn app.main:app --reload --port 8000` | Development server |
| `pytest` | Test suite |
| `pytest -q --tb=short` | Test suite, compact output |
| `ruff check .` | Lint |
| `ruff format --check .` | Formatting check |
| `mypy app` | Type check (strict) |

API documentation is at `http://localhost:8000/docs` (Swagger),
`/redoc`, and `/openapi.json`. All three are disabled when
`ENVIRONMENT=production`.

---

## Configuration

Settings are typed via pydantic-settings and read from the environment or
`backend/.env`. See `.env.example` for the full list.

`.env` is gitignored. No secret exists in this phase — there is no broker, no
database and no authentication — but the loading path is established now so
credentials have somewhere to live that is not source control.

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

- All data is mock and deterministic. Nothing reflects a real account.
- The monthly target lives in process memory. Restarting the server resets it
  to ₹10,000. Introducing a database purely to persist one integer would be the
  wrong trade for this phase.
- The demo journal is pinned to September 2026 so the mock story stays
  coherent; `get_reference_date()` is the seam where a real clock plugs in.
- No exchange holiday calendar. The frontend knows only the weekend rule.
- No authentication. The API assumes a single trusted local user.
- No rate limiting. That belongs with authentication and an ingress layer, not
  in an in-process limiter that cannot survive a second worker.

---

## Roadmap

Phase 2 exists so these can be added without restructuring:

```
Phase 3   PostgreSQL / TimescaleDB · real trade journal · NSE holiday calendar
Phase 4   Broker adapter · market data · option-chain ingestion
Phase 5   Feature engine · ML models · signal engine
Phase 6   Options selector · risk engine · execution engine · position manager
```

### Financial safety architecture

A constraint for every later phase, recorded now while it is still free to
adopt:

```
Model → Signal → Options Selector → Risk Engine → Execution Validation → Broker Adapter
```

A model-generated signal must **never** reach a broker adapter directly. The
risk engine sits in the path and holds veto authority over every order. This is
documentation only in Phase 2 — none of those components exist yet — but the
current architecture is shaped so none of them can be short-circuited later.

A `BrokerAdapter` abstraction is deliberately **not** defined yet. Writing an
interface for an integration nobody has attempted produces a contract shaped by
guesses rather than by a real broker's semantics. It belongs in Phase 4,
alongside the first concrete implementation that can validate it.
