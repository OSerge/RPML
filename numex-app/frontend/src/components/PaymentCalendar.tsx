import { useState } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import type { DebtCardData } from '../types/debt'

interface PaymentCalendarProps {
  debts: DebtCardData[]
  selectedMonth: Date
}

export function PaymentCalendar({ debts, selectedMonth }: PaymentCalendarProps) {
  const [currentMonth, setCurrentMonth] = useState(selectedMonth)

  const getDaysInMonth = (date: Date) => {
    const year = date.getFullYear()
    const month = date.getMonth()
    const firstDay = new Date(year, month, 1)
    const lastDay = new Date(year, month + 1, 0)
    const daysInMonth = lastDay.getDate()
    const startingDayOfWeek = firstDay.getDay()

    return { daysInMonth, startingDayOfWeek, year, month }
  }

  const { daysInMonth, startingDayOfWeek, year, month } = getDaysInMonth(currentMonth)

  const getPaymentsForDay = (day: number) => {
    const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`
    return debts.filter((debt) => debt.nextPaymentDate === dateStr)
  }

  const weekDays = ['Вс', 'Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб']

  const previousMonth = () => {
    setCurrentMonth(new Date(currentMonth.getFullYear(), currentMonth.getMonth() - 1, 1))
  }

  const nextMonth = () => {
    setCurrentMonth(new Date(currentMonth.getFullYear(), currentMonth.getMonth() + 1, 1))
  }

  return (
    <div className="bg-white dark:bg-slate-800 rounded-2xl p-6 border border-slate-200 dark:border-slate-700">
      {/* Calendar Header */}
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl text-slate-900 dark:text-white font-semibold">
          {currentMonth.toLocaleDateString('ru-RU', { month: 'long', year: 'numeric' })}
        </h2>
        <div className="flex gap-2">
          <button
            onClick={previousMonth}
            className="w-10 h-10 rounded-xl bg-slate-100 dark:bg-slate-700 hover:bg-slate-200 dark:hover:bg-slate-600 flex items-center justify-center transition-colors"
          >
            <ChevronLeft className="w-5 h-5 text-slate-600 dark:text-slate-300" />
          </button>
          <button
            onClick={nextMonth}
            className="w-10 h-10 rounded-xl bg-slate-100 dark:bg-slate-700 hover:bg-slate-200 dark:hover:bg-slate-600 flex items-center justify-center transition-colors"
          >
            <ChevronRight className="w-5 h-5 text-slate-600 dark:text-slate-300" />
          </button>
        </div>
      </div>

      {/* Calendar Grid */}
      <div className="grid grid-cols-7 gap-2">
        {/* Week day headers */}
        {weekDays.map((day) => (
          <div key={day} className="text-center text-sm text-slate-500 dark:text-slate-400 py-2">
            {day}
          </div>
        ))}

        {/* Empty cells for days before month starts */}
        {Array.from({ length: startingDayOfWeek === 0 ? 6 : startingDayOfWeek - 1 }).map((_, idx) => (
          <div key={`empty-${idx}`} className="aspect-square" />
        ))}

        {/* Calendar days */}
        {Array.from({ length: daysInMonth }).map((_, idx) => {
          const day = idx + 1
          const payments = getPaymentsForDay(day)
          const isToday = 
            day === new Date().getDate() &&
            month === new Date().getMonth() &&
            year === new Date().getFullYear()

          return (
            <div
              key={day}
              className={`aspect-square rounded-xl border ${
                isToday
                  ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-950/30'
                  : 'border-slate-200 dark:border-slate-700'
              } p-2 hover:bg-slate-50 dark:hover:bg-slate-700/50 transition-colors cursor-pointer`}
            >
              <div className="h-full flex flex-col">
                <span className={`text-sm ${isToday ? 'text-indigo-600 dark:text-indigo-400 font-semibold' : 'text-slate-900 dark:text-white'}`}>
                  {day}
                </span>
                <div className="flex-1 mt-1 space-y-1 overflow-hidden">
                  {payments.map((payment) => (
                    <div
                      key={payment.id}
                      className="text-xs px-1 py-0.5 bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400 rounded truncate"
                      title={`${payment.name}: ${payment.monthlyPayment.toLocaleString('ru-RU')} ₽`}
                    >
                      {payment.monthlyPayment.toLocaleString('ru-RU', { notation: 'compact' })}
                    </div>
                  ))}
                  {day === 1 && (
                    <div className="text-xs px-1 py-0.5 bg-green-100 dark:bg-green-900/30 text-green-600 dark:text-green-400 rounded truncate">
                      ЗП
                    </div>
                  )}
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {/* Legend */}
      <div className="mt-6 pt-4 border-t border-slate-200 dark:border-slate-700 flex flex-wrap gap-4 text-sm">
        <div className="flex items-center gap-2">
          <div className="w-4 h-4 rounded bg-green-100 dark:bg-green-900/30" />
          <span className="text-slate-600 dark:text-slate-400">Доход</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-4 h-4 rounded bg-red-100 dark:bg-red-900/30" />
          <span className="text-slate-600 dark:text-slate-400">Платеж по кредиту</span>
        </div>
      </div>
    </div>
  )
}
