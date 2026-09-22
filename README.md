# NIFTY Agent — Dashboard (Frontend V1)

Monitoring dashboard for an autonomous NIFTY options trading agent.

This repository currently contains **the frontend only**. Every figure on screen
comes from a local mock module. The interface is architected so those values can
later be replaced by backend/broker APIs without touching component code.

---

## Scope of this phase

**Implemented**

- Account balance summary (read-only)
- User-defined monthly target with inline editing and local persistence
- Automatically derived daily target
- Today's progress against the daily target
- Month-to-date progress against the monthly target
- Custom September 2026 trading calendar with per-session markers
- Contextual summary for the selected date
- Responsive 12-column bento layout, 360px → 1920px

**Deliberately not implemented** (out of scope for V1)

Backend · broker API integration · authentication · order placement ·
automatic trading · machine learning · training pipelines · database ·
WebSocket market feed · real account balance retrieval.

> The monthly target is a **user-defined goal**, not projected or guaranteed
> income. The UI language is intentionally framed as *target* and *progress*.

---

## Stack

| Concern    | Choice                                   |
| ---------- | ---------------------------------------- |
| Framework  | Next.js 16 (App Router)                  |
| UI runtime | React 19                                 |
| Language   | TypeScript, `strict` + `noUncheckedIndexedAccess` |
| Styling    | Tailwind CSS 4 (`@theme` design tokens)  |
| Icons      | Lucide React                             |
| Motion     | Motion (`motion/react`)                  |
| Dates      | date-fns                                 |
| Tooltips   | Radix UI (shadcn-style wrapper)          |

State is plain React state plus small hooks — no Redux. `localStorage` is used
for exactly one thing: the user's monthly target.

---

## Getting started

```bash
npm install
npm run dev     # http://localhost:3000
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
    layout.tsx              Root layout, fonts, metadata
    page.tsx                Server entry → <Dashboard />
    globals.css             Design tokens (@theme) + base styles
  components/
    dashboard/
      Dashboard.tsx         Client orchestrator; owns interactive state
      DashboardHeader.tsx
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
      Tooltip.tsx
  hooks/
    useMonthlyTarget.ts     Persisted target via useSyncExternalStore
  lib/
    currency.ts             INR formatting + input parsing
    targetCalculations.ts   Target maths and status derivation
    dates.ts                Calendar grid + date formatting
    utils.ts                cn()
  data/
    mockTradingData.ts      Single source of mock data
  types/
    trading.ts              Domain types
```

---

## Core logic

**Daily target**

```ts
calculateDailyTarget(monthlyTarget) === Math.round(monthlyTarget / 30)
```

Fractions below `.5` round down, `.5` and above round up:

| Monthly   | Daily  |
| --------- | ------ |
| ₹10,000   | ₹333   |
| ₹10,010   | ₹334   |
| ₹15,000   | ₹500   |
| ₹20,000   | ₹667   |

> **Production note:** the fixed 30-day denominator is a V1 simplification.
> It should be replaced with the actual number of remaining NSE trading
> sessions, which requires the exchange holiday calendar from the backend.
> Only `ASSUMED_DAYS_PER_MONTH` and `calculateDailyTarget` need to change.

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

## Replacing the mock data

`src/data/mockTradingData.ts` is the only place fake numbers live. Each export
maps to one future data source:

| Export                    | Future source                      |
| ------------------------- | ---------------------------------- |
| `MOCK_ACCOUNT_SUMMARY`    | Broker funds / margin endpoint     |
| `MOCK_DAILY_PERFORMANCE`  | Agent trade-journal endpoint       |
| `MOCK_MARKET_STATUS`      | Exchange session / holiday service |
| `MOCK_TODAY_KEY`          | `new Date()`                       |

Components read these through props supplied by `Dashboard.tsx`, so wiring in
real fetches means changing that one file plus the data module.

---

## Design

The canvas is fixed at `#F9EDE3`. Card surfaces are translucent warm whites
layered over it, keeping every elevation in the same temperature family.

- Page `#F9EDE3` · primary card `rgba(255,255,255,0.72)` · secondary `rgba(255,255,255,0.48)`
- Text tones tuned so all label sizes clear WCAG AA (4.5:1) on the card surface
- 22px card radius, 1px warm hairline borders, very soft shadows
- Restrained green / red / amber — no neon, no gradients
- `font-variant-numeric: tabular-nums` on all financial figures

Accessibility: semantic landmarks, real `<button>` elements, `aria-label` on
icon-only controls, visible focus rings, a `<table>`-based calendar with
weekday column headers, and status conveyed by icon + text as well as colour.
Motion is limited to ~150–250ms entrances and respects `prefers-reduced-motion`.

---

## Verified

`npm run lint`, `npm run typecheck`, and `npm run build` all pass clean.
Layout, INR formatting, calendar accuracy, target editing and persistence,
and edge cases (zero/negative/oversized values) were checked at 360, 768,
1024, and 1440px.
