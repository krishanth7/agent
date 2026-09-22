"use client";

import { format, startOfMonth } from "date-fns";
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
import {
  MOCK_ACCOUNT_SUMMARY,
  MOCK_MARKET_STATUS,
  MOCK_TODAY_KEY,
  getPerformanceForDate,
  getPerformanceForMonth,
} from "@/data/mockTradingData";
import { useMonthlyTarget } from "@/hooks/useMonthlyTarget";
import { formatMonthTitle, fromDateKey } from "@/lib/dates";
import {
  aggregatePerformance,
  calculateAveragePerSession,
  calculateDailyTarget,
  getDailyTargetStatus,
} from "@/lib/targetCalculations";
import type { DailyTargetStatus } from "@/types/trading";

/**
 * Client orchestrator for the dashboard.
 *
 * Owns the two pieces of interactive state (the monthly target and the selected
 * calendar date) and derives everything else. All data arrives from the mock
 * module — swapping in server fetches means changing only these imports.
 */
export function Dashboard() {
  const { monthlyTarget, setMonthlyTarget } = useMonthlyTarget();
  const [selectedDateKey, setSelectedDateKey] = useState(MOCK_TODAY_KEY);
  const [monthAnchor, setMonthAnchor] = useState(() =>
    startOfMonth(fromDateKey(MOCK_TODAY_KEY)),
  );

  const dailyTarget = calculateDailyTarget(monthlyTarget);

  const todayDate = useMemo(() => fromDateKey(MOCK_TODAY_KEY), []);
  const todayProfit = getPerformanceForDate(MOCK_TODAY_KEY)?.realizedPnl ?? 0;

  // Monthly progress always tracks the live month, independent of the month the
  // user happens to be browsing in the calendar.
  const currentMonthKey = format(todayDate, "yyyy-MM");
  const totals = useMemo(
    () => aggregatePerformance(getPerformanceForMonth(currentMonthKey)),
    [currentMonthKey],
  );
  const averagePerSession = calculateAveragePerSession(totals);

  const selectedDate = useMemo(
    () => fromDateKey(selectedDateKey),
    [selectedDateKey],
  );
  const selectedPerformance = getPerformanceForDate(selectedDateKey);

  const getStatus = useCallback(
    (dateKey: string): DailyTargetStatus | null => {
      const session = getPerformanceForDate(dateKey);
      if (!session) return null;
      return getDailyTargetStatus(session.realizedPnl, dailyTarget);
    },
    [dailyTarget],
  );

  return (
    <MotionConfig reducedMotion="user">
      <TooltipProvider delayDuration={200}>
        <div className="mx-auto w-full max-w-[1440px] px-4 py-6 sm:px-6 sm:py-8 lg:px-10 lg:py-10">
          <DashboardHeader marketStatus={MOCK_MARKET_STATUS} date={todayDate} />

          <main className="mt-7 grid grid-cols-1 gap-4 md:grid-cols-6 lg:mt-9 lg:grid-cols-12 lg:gap-5">
            <AccountBalanceCard
              account={MOCK_ACCOUNT_SUMMARY}
              order={0}
              className="md:col-span-3 lg:col-span-7"
            />
            <MonthlyTargetCard
              monthlyTarget={monthlyTarget}
              dailyTarget={dailyTarget}
              onSave={setMonthlyTarget}
              order={1}
              className="md:col-span-3 lg:col-span-5"
            />
            <DailyTargetCard
              dailyTarget={dailyTarget}
              todayProfit={todayProfit}
              order={2}
              className="md:col-span-2 lg:col-span-4"
            />
            <MonthlyProgressCard
              monthlyTarget={monthlyTarget}
              totals={totals}
              averagePerSession={averagePerSession}
              periodLabel={formatMonthTitle(todayDate)}
              order={3}
              className="md:col-span-4 lg:col-span-8"
            />
            <TradingCalendar
              monthAnchor={monthAnchor}
              onMonthChange={setMonthAnchor}
              selectedDateKey={selectedDateKey}
              onSelectDate={setSelectedDateKey}
              todayKey={MOCK_TODAY_KEY}
              getPerformance={getPerformanceForDate}
              getStatus={getStatus}
              order={4}
              className="md:col-span-6 lg:col-span-8"
            />
            <TradingSummaryCard
              selectedDate={selectedDate}
              performance={selectedPerformance}
              dailyTarget={dailyTarget}
              isToday={selectedDateKey === MOCK_TODAY_KEY}
              order={5}
              className="md:col-span-6 lg:col-span-4"
            />
          </main>
        </div>
      </TooltipProvider>
    </MotionConfig>
  );
}
