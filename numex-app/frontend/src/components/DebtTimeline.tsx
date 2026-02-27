import { CheckCircle2, Circle } from 'lucide-react'
import type { DebtCardData } from '../types/debt'

interface DebtTimelineProps {
  debts: DebtCardData[]
}

export function DebtTimeline({ debts }: DebtTimelineProps) {
  const debtPayoffTimeline = debts.map((debt) => {
    const monthsToPayoff = Math.ceil(debt.remainingAmount / debt.monthlyPayment)
    const payoffDate = new Date()
    payoffDate.setMonth(payoffDate.getMonth() + monthsToPayoff)

    return {
      ...debt,
      monthsToPayoff,
      payoffDate,
    }
  }).sort((a, b) => a.payoffDate.getTime() - b.payoffDate.getTime())

  if (debts.length === 0) {
    return (
      <div className="bg-white dark:bg-slate-800 rounded-2xl p-8 border border-slate-200 dark:border-slate-700 text-center">
        <p className="text-slate-500 dark:text-slate-400">
          Нет долгов для отображения графика погашения
        </p>
      </div>
    )
  }

  return (
    <div className="bg-white dark:bg-slate-800 rounded-2xl p-6 border border-slate-200 dark:border-slate-700">
      <div className="mb-6">
        <h3 className="text-xl text-slate-900 dark:text-white mb-2 font-semibold">График освобождения от долгов</h3>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Прогноз полного погашения при текущих платежах
        </p>
      </div>

      <div className="relative">
        {/* Timeline line */}
        <div className="absolute left-6 top-0 bottom-0 w-0.5 bg-slate-200 dark:bg-slate-700" />

        <div className="space-y-6">
          {debtPayoffTimeline.map((debt, idx) => {
            const isCompleted = idx === 0 && debt.monthsToPayoff < 1

            return (
              <div key={debt.id} className="relative flex gap-4">
                {/* Timeline dot */}
                <div className="relative z-10 flex-shrink-0">
                  {isCompleted ? (
                    <div className="w-12 h-12 rounded-full bg-green-100 dark:bg-green-900/30 border-4 border-white dark:border-slate-800 flex items-center justify-center">
                      <CheckCircle2 className="w-6 h-6 text-green-600 dark:text-green-400" />
                    </div>
                  ) : (
                    <div className="w-12 h-12 rounded-full bg-white dark:bg-slate-800 border-4 border-slate-200 dark:border-slate-700 flex items-center justify-center">
                      <Circle className="w-6 h-6 text-slate-400 dark:text-slate-500" />
                    </div>
                  )}
                </div>

                {/* Content */}
                <div className="flex-1 pb-8">
                  <div className="flex items-start justify-between mb-2">
                    <div>
                      <h4 className="text-slate-900 dark:text-white mb-1 font-medium">{debt.name}</h4>
                      <p className="text-sm text-slate-500 dark:text-slate-400">
                        {debt.payoffDate.toLocaleDateString('ru-RU', {
                          month: 'long',
                          year: 'numeric',
                        })}
                      </p>
                    </div>
                    <span className="text-sm px-3 py-1 bg-slate-100 dark:bg-slate-700 rounded-full text-slate-600 dark:text-slate-400 font-medium">
                      {debt.monthsToPayoff} мес
                    </span>
                  </div>

                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-3">
                    <div>
                      <p className="text-xs text-slate-500 dark:text-slate-400">Осталось</p>
                      <p className="text-sm text-slate-900 dark:text-white font-medium">
                        {debt.remainingAmount.toLocaleString('ru-RU')} ₽
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-slate-500 dark:text-slate-400">Платеж/мес</p>
                      <p className="text-sm text-slate-900 dark:text-white font-medium">
                        {debt.monthlyPayment.toLocaleString('ru-RU')} ₽
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-slate-500 dark:text-slate-400">Ставка</p>
                      <p className="text-sm text-slate-900 dark:text-white font-medium">{debt.rate}%</p>
                    </div>
                    <div>
                      <p className="text-xs text-slate-500 dark:text-slate-400">Переплата</p>
                      <p className="text-sm text-red-600 dark:text-red-400 font-medium">
                        {((debt.monthlyPayment * debt.monthsToPayoff) - debt.remainingAmount).toLocaleString('ru-RU')} ₽
                      </p>
                    </div>
                  </div>

                  {/* Progress bar */}
                  <div className="mt-3">
                    <div className="h-2 bg-slate-100 dark:bg-slate-700 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-gradient-to-r from-indigo-500 to-purple-600 transition-all"
                        style={{
                          width: `${((debt.totalAmount - debt.remainingAmount) / debt.totalAmount) * 100}%`,
                        }}
                      />
                    </div>
                  </div>
                </div>
              </div>
            )
          })}
        </div>

        {/* Final celebration */}
        <div className="relative flex gap-4 mt-6">
          <div className="relative z-10 flex-shrink-0">
            <div className="w-12 h-12 rounded-full bg-gradient-to-br from-yellow-400 to-orange-500 border-4 border-white dark:border-slate-800 flex items-center justify-center">
              <span className="text-2xl">🎉</span>
            </div>
          </div>
          <div className="flex-1">
            <h4 className="text-slate-900 dark:text-white mb-1 font-semibold">Свобода от долгов!</h4>
            <p className="text-sm text-slate-500 dark:text-slate-400">
              Вы полностью освободитесь от всех долгов к{' '}
              {debtPayoffTimeline[debtPayoffTimeline.length - 1].payoffDate.toLocaleDateString('ru-RU', {
                month: 'long',
                year: 'numeric',
              })}
            </p>
            <div className="mt-3 p-4 bg-gradient-to-r from-green-50 to-emerald-50 dark:from-green-950/30 dark:to-emerald-950/30 rounded-xl border border-green-200 dark:border-green-800">
              <p className="text-sm text-green-900 dark:text-green-100">
                💡 Совет: При досрочных погашениях вы можете освободиться на 8-12 месяцев раньше
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
