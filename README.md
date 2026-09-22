# NIFTY Agent — Dashboard (Frontend V1)

Monitoring dashboard for an autonomous NIFTY options trading agent.

This repository currently contains **the frontend only**. Every figure on screen
comes from a local mock module. The interface is architected so those values can
later be replaced by backend/broker APIs without touching component code.

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

- Account balance summary (read-only)
- User-defined monthly target with inline editing and local persistence
- Automatically derived daily target
- Today's progress against the daily target
- Month-to-date progress against the monthly target
- Custom September 2026 trading calendar with per-session markers
- Weekend / market-closed handling and NSE session hours
- Contextual summary for the selected date
- Light and dark themes with a persisted, no-flash toggle
- Responsive 12-column bento layout, 360px → 1920px

**Deliberately not implemented** (out of scope for V1)

Backend · broker API integration · authentication · order placement ·
automatic trading · machine learning · training pipelines · database ·
WebSocket market feed · real account balance retrieval · exchange holiday
calendar.

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

State is plain React state plus small hooks — no Redux. `localStorage` is used
for exactly two things: the user's monthly target and the colour theme.

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
  hooks/
    useMonthlyTarget.ts     Persisted target via useSyncExternalStore
    useTheme.ts             Persisted theme via useSyncExternalStore
  lib/
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

`npm run lint`, `npm run typecheck`, and `npm run build` all pass clean, and the
production build runs with **zero console warnings, errors or exceptions**.

Checked in both themes: layout at 360 / 768 / 1024 / 1280 / 1440px with no
horizontal overflow, INR formatting, calendar accuracy against the real 2026
calendar, weekend non-interactivity, target editing and persistence, theme
persistence across reload and over the OS preference, and edge cases
(zero / negative / non-numeric / oversized values).
