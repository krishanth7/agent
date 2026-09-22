"use client";

import { startOfMonth } from "date-fns";
import { MotionConfig } from "motion/react";
import { useCallback, useMemo, useState } from "react";

import { AccountBalanceCard } from "@/components/dashboard/AccountBalanceCard";
import { DailyTargetCard } from "@/components/dashboard/DailyTargetCard";
import { DashboardHeader } from "@/components/dashboard/DashboardHeader";
import { MonthlyProgressCard } from "@/components/dashboard/MonthlyProgressCard";
import { MonthlyTargetCard } from "@/components/dashboard/MonthlyTargetCard";
import { TradingCalendar } from "@/components/dashboard/TradingCalendar";
import { TradingSummaryCard } from "@/components/dashboard/TradingSummaryCard";
import { TooltipProvider } from "@/components/ui/Tooltip";
import { MOCK_MARKET_STATUS } from "@/data/mockTradingData";
import { useApiResource, type ResourceStatus } from "@/hooks/useApiResource";
import { useMonthlyTarget } from "@/hooks/useMonthlyTarget";
import { fetchAccountSummary } from "@/lib/api/account";
import {
  fetchCalendar,
  fetchMonthlyPerformance,
  fetchTodayPerformance,
  type CalendarResult,
} from "@/lib/api/performance";
import { formatMonthTitle, fromDateKey } from "@/lib/dates";
import { calculateAveragePerSession } from "@/lib/targetCalculations";
import type { DailyTargetStatus, DailyTradingPerformance } from "@/types/trading";

/**
 * Combines several load states into the one a card should render.
 *
 * A card fed by two requests is only trustworthy when both have landed, and is
 * broken the moment either fails — there is no useful half-state to show.
 */
function combine(...states: ResourceStatus[]): ResourceStatus {
  if (states.includes("error")) return "error";
  if (states.includes("loading")) return "loading";
  return "ready";
}

/**
 * Client orchestrator for the dashboard.
 *
 * Owns the two pieces of interactive state (the monthly target and the selected
 * calendar date) and derives everything else. Every figure now comes from the
 * Phase 2 API: this component decides *what* to request and *when*, while
 * `src/lib/api/` owns how, and the cards own how each state looks.
 */
export function Dashboard() {
  const target = useMonthlyTarget();

  const loadAccount = useCallback(
    (signal: AbortSignal) => fetchAccountSummary({ signal }),
    [],
  );
  const account = useApiResource(loadAccount, []);

  const loadToday = useCallback(
    (signal: AbortSignal) => fetchTodayPerformance({ signal }),
    [],
  );
  const today = useApiResource(loadToday, []);

  // The backend owns the notion of "today" so the calendar, the summary and
  // the journal can never disagree about which session is the current one.
  const todayKey = today.data?.date ?? null;

  // `null` overrides mean "follow the backend's reference date"; once the user
  // navigates or selects, their choice takes over. Deriving rather than
  // syncing in an effect avoids a render pass showing the wrong month.
  const [monthOverride, setMonthOverride] = useState<Date | null>(null);
  const [selectedOverride, setSelectedOverride] = useState<string | null>(null);

  const monthAnchor = useMemo(() => {
    if (monthOverride) return monthOverride;
    return todayKey ? startOfMonth(fromDateKey(todayKey)) : null;
  }, [monthOverride, todayKey]);

  const selectedDateKey = selectedOverride ?? todayKey;

  const anchorYear = monthAnchor?.getFullYear() ?? null;
  const anchorMonth = monthAnchor ? monthAnchor.getMonth() + 1 : null;

  // Both the calendar and the monthly aggregate are re-fetched when the target
  // changes: every day's status is measured against the daily target, so a new
  // goal re-colours the whole month.
  const loadCalendar = useCallback(
    (signal: AbortSignal): Promise<CalendarResult | null> => {
      if (anchorYear === null || anchorMonth === null) {
        return Promise.resolve(null);
      }
      return fetchCalendar(anchorYear, anchorMonth, { signal });
    },
    [anchorYear, anchorMonth],
  );
  const calendar = useApiResource(loadCalendar, [
    anchorYear,
    anchorMonth,
    target.revision,
  ]);

  const loadMonthly = useCallback(
    (signal: AbortSignal) => fetchMonthlyPerformance(undefined, { signal }),
    [],
  );
  const monthly = useApiResource(loadMonthly, [target.revision]);

  // Sessions are indexed once per fetch rather than scanned per calendar cell.
  const sessionsByDate = useMemo(() => {
    const index = new Map<
      string,
      { performance: DailyTradingPerformance; status: DailyTargetStatus }
    >();
    for (const day of calendar.data?.days ?? []) {
      index.set(day.date, {
        performance: {
          date: day.date,
          realizedPnl: day.realizedPnl,
          trades: day.trades,
          wins: day.wins,
          losses: day.losses,
        },
        status: day.status,
      });
    }
    return index;
  }, [calendar.data]);

  const getPerformance = useCallback(
    (dateKey: string): DailyTradingPerformance | null =>
      sessionsByDate.get(dateKey)?.performance ?? null,
    [sessionsByDate],
  );

  const getStatus = useCallback(
    (dateKey: string): DailyTargetStatus | null =>
      sessionsByDate.get(dateKey)?.status ?? null,
    [sessionsByDate],
  );

  const calendarState: ResourceStatus =
    monthAnchor === null ? combine(today.status, "loading") : calendar.status;

  // Never fall back to `new Date()`. The trading date belongs to the exchange,
  // not to the browser, and substituting the local clock would also produce a
  // server/client hydration mismatch on every render.
  const todayDate = todayKey ? fromDateKey(todayKey) : null;
  const selectedDate = selectedDateKey ? fromDateKey(selectedDateKey) : null;
  const selectedPerformance = selectedDateKey
    ? getPerformance(selectedDateKey)
    : null;

  const monthlyTotals = monthly.data?.totals ?? null;
  const averagePerSession = monthlyTotals
    ? calculateAveragePerSession(monthlyTotals)
    : 0;

  // The month view is anchored on the backend's reference date, so retrying it
  // has to retry `today` as well — otherwise a failed reference-date fetch can
  // never recover and the calendar stays anchorless.
  const reloadMonthView = useCallback(() => {
    today.reload();
    calendar.reload();
    monthly.reload();
  }, [today, calendar, monthly]);

  const reloadCalendar = useCallback(() => {
    today.reload();
    calendar.reload();
  }, [today, calendar]);

  return (
    <MotionConfig reducedMotion="user">
      <TooltipProvider delayDuration={200}>
        <div className="mx-auto w-full max-w-[1440px] px-4 py-6 sm:px-6 sm:py-8 lg:px-10 lg:py-9">
          <DashboardHeader marketStatus={MOCK_MARKET_STATUS} date={todayDate} />

          {/*
            Bento grid, two rows at desktop width:
              row 1 — Balance (5) · Monthly Target (4) · Session Summary (3)
              row 2 — Today's Target (3) · Monthly Progress (4) · Calendar (5)
            The 5-4-3 / 3-4-5 mirror keeps both rows on the same column rhythm
            while giving the calendar a deliberately compact footprint.
          */}
          <main className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-6 lg:mt-7 lg:grid-cols-12 lg:gap-5">
            <AccountBalanceCard
              account={
                account.data
                  ? {
                      availableBalance: account.data.availableBalance,
                      usedMargin: account.data.usedMargin,
                      totalCapital: account.data.totalCapital,
                    }
                  : null
              }
              status={account.status}
              error={account.error}
              offline={account.offline}
              onRetry={account.reload}
              order={0}
              className="md:col-span-6 lg:col-span-5"
            />
            <MonthlyTargetCard
              monthlyTarget={target.monthlyTarget}
              dailyTarget={target.dailyTarget}
              calculationMode={target.calculationMode}
              status={target.status}
              loadError={target.error}
              offline={target.offline}
              onRetry={target.reload}
              onSave={target.save}
              order={1}
              className="md:col-span-3 lg:col-span-4"
            />
            <TradingSummaryCard
              selectedDate={selectedDate}
              performance={selectedPerformance}
              dailyTarget={target.dailyTarget}
              isToday={selectedDateKey !== null && selectedDateKey === todayKey}
              state={combine(calendarState, target.status)}
              error={calendar.error ?? today.error ?? target.error}
              offline={calendar.offline || today.offline || target.offline}
              onRetry={reloadMonthView}
              order={2}
              className="md:col-span-3 lg:col-span-3"
            />
            <DailyTargetCard
              dailyTarget={target.dailyTarget}
              todayProfit={today.data?.realizedPnl ?? null}
              state={combine(today.status, target.status)}
              error={today.error ?? target.error}
              offline={today.offline || target.offline}
              onRetry={today.reload}
              order={3}
              className="md:col-span-2 lg:col-span-3"
            />
            <MonthlyProgressCard
              monthlyTarget={target.monthlyTarget}
              totals={monthlyTotals}
              averagePerSession={averagePerSession}
              periodLabel={todayDate ? formatMonthTitle(todayDate) : "This month"}
              state={combine(monthly.status, target.status)}
              error={monthly.error ?? target.error}
              offline={monthly.offline || target.offline}
              onRetry={monthly.reload}
              order={4}
              className="md:col-span-4 lg:col-span-4"
            />
            <TradingCalendar
              monthAnchor={monthAnchor}
              onMonthChange={setMonthOverride}
              selectedDateKey={selectedDateKey ?? ""}
              onSelectDate={setSelectedOverride}
              todayKey={todayKey ?? ""}
              getPerformance={getPerformance}
              getStatus={getStatus}
              state={calendarState}
              error={calendar.error ?? today.error}
              offline={calendar.offline || today.offline}
              onRetry={reloadCalendar}
              order={5}
              className="md:col-span-6 lg:col-span-5"
            />
          </main>
        </div>
      </TooltipProvider>
    </MotionConfig>
  );
}
