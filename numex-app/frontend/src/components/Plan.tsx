import { useState } from 'react'
import { Calendar, TrendingDown, AlertCircle, Zap } from 'lucide-react'
import { DebtCards } from './DebtCards'
import { PaymentCalendar } from './PaymentCalendar'
import { OptimizationPanel } from './OptimizationPanel'
import { DebtTimeline } from './DebtTimeline'
import { useDebtCards } from '../hooks/useDebts'

export function Plan() {
  const [selectedMonth] = useState(new Date())
  const { data: debts, isLoading, isError } = useDebtCards()

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-slate-500 dark:text-slate-400">Загрузка данных...</div>
      </div>
    )
  }

  if (isError) {
    return (
      <div className="bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800 rounded-2xl p-6">
        <p className="text-red-900 dark:text-red-100">
          Ошибка загрузки данных. Проверьте подключение к API.
        </p>
      </div>
    )
  }

  const totalDebt = debts.reduce((sum, debt) => sum + debt.remainingAmount, 0)
  const monthlyPayment = debts.reduce((sum, debt) => sum + debt.monthlyPayment, 0)
  const averageRate = debts.length > 0
    ? debts.reduce((sum, debt) => sum + (debt.rate * debt.remainingAmount), 0) / totalDebt
    : 0

  return (
    <div className="space-y-6">
      {/* Stats Overview */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-white dark:bg-slate-800 rounded-2xl p-6 border border-slate-200 dark:border-slate-700">
          <div className="flex items-center gap-2 mb-2">
            <div className="w-10 h-10 rounded-xl bg-red-100 dark:bg-red-900/30 flex items-center justify-center">
              <TrendingDown className="w-5 h-5 text-red-600 dark:text-red-400" />
            </div>
            <span className="text-sm text-slate-500 dark:text-slate-400">Всего долгов</span>
          </div>
          <div className="text-2xl font-bold text-slate-900 dark:text-white">
            {totalDebt.toLocaleString('ru-RU')} ₽
          </div>
        </div>

        <div className="bg-white dark:bg-slate-800 rounded-2xl p-6 border border-slate-200 dark:border-slate-700">
          <div className="flex items-center gap-2 mb-2">
            <div className="w-10 h-10 rounded-xl bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center">
              <Calendar className="w-5 h-5 text-blue-600 dark:text-blue-400" />
            </div>
            <span className="text-sm text-slate-500 dark:text-slate-400">Платеж в месяц</span>
          </div>
          <div className="text-2xl font-bold text-slate-900 dark:text-white">
            {monthlyPayment.toLocaleString('ru-RU')} ₽
          </div>
        </div>

        <div className="bg-white dark:bg-slate-800 rounded-2xl p-6 border border-slate-200 dark:border-slate-700">
          <div className="flex items-center gap-2 mb-2">
            <div className="w-10 h-10 rounded-xl bg-amber-100 dark:bg-amber-900/30 flex items-center justify-center">
              <AlertCircle className="w-5 h-5 text-amber-600 dark:text-amber-400" />
            </div>
            <span className="text-sm text-slate-500 dark:text-slate-400">Средняя ставка</span>
          </div>
          <div className="text-2xl font-bold text-slate-900 dark:text-white">
            {averageRate.toFixed(1)}%
          </div>
        </div>

        <div className="bg-white dark:bg-slate-800 rounded-2xl p-6 border border-slate-200 dark:border-slate-700">
          <div className="flex items-center gap-2 mb-2">
            <div className="w-10 h-10 rounded-xl bg-green-100 dark:bg-green-900/30 flex items-center justify-center">
              <Zap className="w-5 h-5 text-green-600 dark:text-green-400" />
            </div>
            <span className="text-sm text-slate-500 dark:text-slate-400">Активных кредитов</span>
          </div>
          <div className="text-2xl font-bold text-slate-900 dark:text-white">
            {debts.length}
          </div>
        </div>
      </div>

      {/* Debt Cards */}
      <DebtCards debts={debts} />

      {/* Main Content Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Calendar & Payments */}
        <div className="lg:col-span-2">
          <PaymentCalendar debts={debts} selectedMonth={selectedMonth} />
        </div>

        {/* Optimization Panel */}
        <div className="lg:col-span-1">
          <OptimizationPanel debts={debts} />
        </div>
      </div>

      {/* Debt Timeline */}
      <DebtTimeline debts={debts} />
    </div>
  )
}
