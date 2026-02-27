import { CreditCard, Home, Car, Wallet } from 'lucide-react'
import type { DebtCardData } from '../types/debt'

interface DebtCardsProps {
  debts: DebtCardData[]
}

export function DebtCards({ debts }: DebtCardsProps) {
  const getIcon = (type: DebtCardData['type']) => {
    switch (type) {
      case 'mortgage':
        return Home
      case 'car':
        return Car
      case 'credit_card':
        return CreditCard
      case 'consumer':
        return Wallet
    }
  }

  const getColor = (type: DebtCardData['type']) => {
    switch (type) {
      case 'mortgage':
        return 'from-blue-500 to-cyan-500'
      case 'car':
        return 'from-purple-500 to-pink-500'
      case 'credit_card':
        return 'from-orange-500 to-red-500'
      case 'consumer':
        return 'from-green-500 to-emerald-500'
    }
  }

  if (debts.length === 0) {
    return (
      <div className="bg-white dark:bg-slate-800 rounded-2xl p-8 border border-slate-200 dark:border-slate-700 text-center">
        <p className="text-slate-500 dark:text-slate-400">
          Нет добавленных долгов. Начните с добавления первого долга через API.
        </p>
      </div>
    )
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {debts.map((debt) => {
        const Icon = getIcon(debt.type)
        const progress = ((debt.totalAmount - debt.remainingAmount) / debt.totalAmount) * 100
        const daysUntilPayment = Math.ceil(
          (new Date(debt.nextPaymentDate).getTime() - new Date().getTime()) / (1000 * 60 * 60 * 24)
        )

        return (
          <div
            key={debt.id}
            className="bg-white dark:bg-slate-800 rounded-2xl p-6 border border-slate-200 dark:border-slate-700 hover:shadow-lg transition-shadow"
          >
            <div className="flex items-start justify-between mb-4">
              <div className="flex items-center gap-3">
                <div className={`w-12 h-12 rounded-xl bg-gradient-to-br ${getColor(debt.type)} flex items-center justify-center`}>
                  <Icon className="w-6 h-6 text-white" />
                </div>
                <div>
                  <h3 className="text-slate-900 dark:text-white font-medium">{debt.name}</h3>
                  <p className="text-sm text-slate-500 dark:text-slate-400">{debt.rate}% годовых</p>
                </div>
              </div>
              {daysUntilPayment <= 7 && (
                <span className="px-2 py-1 bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400 text-xs rounded-full">
                  {daysUntilPayment} дн.
                </span>
              )}
            </div>

            <div className="space-y-3">
              <div>
                <div className="flex justify-between text-sm mb-2">
                  <span className="text-slate-500 dark:text-slate-400">Прогресс погашения</span>
                  <span className="text-slate-900 dark:text-white">{progress.toFixed(1)}%</span>
                </div>
                <div className="h-2 bg-slate-100 dark:bg-slate-700 rounded-full overflow-hidden">
                  <div
                    className={`h-full bg-gradient-to-r ${getColor(debt.type)} transition-all`}
                    style={{ width: `${progress}%` }}
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4 pt-2">
                <div>
                  <p className="text-sm text-slate-500 dark:text-slate-400">Осталось</p>
                  <p className="text-slate-900 dark:text-white font-medium">
                    {debt.remainingAmount.toLocaleString('ru-RU')} ₽
                  </p>
                </div>
                <div>
                  <p className="text-sm text-slate-500 dark:text-slate-400">Платеж</p>
                  <p className="text-slate-900 dark:text-white font-medium">
                    {debt.monthlyPayment.toLocaleString('ru-RU')} ₽
                  </p>
                </div>
              </div>

              <div className="pt-2 border-t border-slate-100 dark:border-slate-700">
                <p className="text-sm text-slate-500 dark:text-slate-400">
                  Следующий платеж:{' '}
                  <span className="text-slate-900 dark:text-white">
                    {new Date(debt.nextPaymentDate).toLocaleDateString('ru-RU', {
                      day: 'numeric',
                      month: 'long',
                    })}
                  </span>
                </p>
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}
