import { TrendingUp, Zap, Target, Info } from 'lucide-react'
import { motion } from 'motion/react'
import { useMutation } from '@tanstack/react-query'
import { runOptimization } from '../services/api'
import type { DebtCardData } from '../types/debt'

interface OptimizationPanelProps {
  debts: DebtCardData[]
}

export function OptimizationPanel({ debts }: OptimizationPanelProps) {
  const optimizeMutation = useMutation({
    mutationFn: runOptimization,
  })

  const sortedDebts = [...debts].sort((a, b) => b.rate - a.rate)
  const highestRateDebt = sortedDebts[0]

  if (!highestRateDebt) {
    return (
      <div className="bg-white dark:bg-slate-800 rounded-2xl p-6 border border-slate-200 dark:border-slate-700">
        <p className="text-slate-500 dark:text-slate-400 text-center">
          Добавьте долги для начала оптимизации
        </p>
      </div>
    )
  }

  const monthlySavings = (highestRateDebt.remainingAmount * highestRateDebt.rate / 100) / 12
  const yearSavings = monthlySavings * 12

  const optimizationStrategies = [
    {
      id: '1',
      title: 'Метод снежного кома',
      description: 'Погашайте долг с наивысшей ставкой первым',
      priority: highestRateDebt.name,
      savings: yearSavings,
      months: 18,
    },
    {
      id: '2',
      title: 'Рефинансирование',
      description: 'Объедините все долги под ставку 11.9%',
      priority: 'Все кредиты',
      savings: 89000,
      months: 12,
    },
    {
      id: '3',
      title: 'Досрочное погашение',
      description: 'Доп. платежи по 10,000 ₽ в месяц',
      priority: highestRateDebt.name,
      savings: 156000,
      months: 24,
    },
  ]

  return (
    <div className="space-y-4">
      {/* AI Optimization Card */}
      <div className="bg-gradient-to-br from-indigo-500 to-purple-600 rounded-2xl p-6 text-white">
        <div className="flex items-center gap-2 mb-4">
          <Zap className="w-6 h-6" />
          <h3 className="font-semibold">AI Оптимизация</h3>
        </div>
        <p className="text-indigo-100 mb-4">
          Я проанализировал ваши долги и нашел способ сэкономить
        </p>
        <div className="text-3xl font-bold mb-2">{yearSavings.toLocaleString('ru-RU')} ₽</div>
        <p className="text-sm text-indigo-100 mb-4">
          за год при досрочном погашении {highestRateDebt.name}
        </p>
        <button
          onClick={() => optimizeMutation.mutate()}
          disabled={optimizeMutation.isPending}
          className="w-full bg-white text-indigo-600 px-4 py-2 rounded-xl hover:bg-indigo-50 transition-colors disabled:opacity-50 font-medium"
        >
          {optimizeMutation.isPending ? 'Расчет...' : 'Применить план'}
        </button>
        {optimizeMutation.isSuccess && (
          <p className="mt-2 text-sm text-indigo-100">
            ✓ План создан успешно
          </p>
        )}
        {optimizeMutation.isError && (
          <p className="mt-2 text-sm text-red-200">
            Ошибка при создании плана
          </p>
        )}
      </div>

      {/* Priority Payment */}
      <div className="bg-white dark:bg-slate-800 rounded-2xl p-6 border border-slate-200 dark:border-slate-700">
        <div className="flex items-center gap-2 mb-4">
          <Target className="w-5 h-5 text-red-600 dark:text-red-400" />
          <h3 className="text-slate-900 dark:text-white font-semibold">Приоритетный платеж</h3>
        </div>
        <div className="space-y-3">
          <div className="p-4 bg-red-50 dark:bg-red-950/30 rounded-xl border border-red-200 dark:border-red-800">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm text-red-900 dark:text-red-100 font-medium">{highestRateDebt.name}</span>
              <span className="px-2 py-0.5 bg-red-200 dark:bg-red-900/50 text-red-900 dark:text-red-100 text-xs rounded-full font-semibold">
                {highestRateDebt.rate}%
              </span>
            </div>
            <div className="text-2xl text-red-900 dark:text-red-100 mb-1 font-bold">
              {highestRateDebt.monthlyPayment.toLocaleString('ru-RU')} ₽
            </div>
            <p className="text-sm text-red-700 dark:text-red-300">
              Самая высокая ставка → приоритет №1
            </p>
          </div>

          <div className="flex items-start gap-2 p-3 bg-blue-50 dark:bg-blue-950/30 rounded-xl">
            <Info className="w-4 h-4 text-blue-600 dark:text-blue-400 mt-0.5 flex-shrink-0" />
            <p className="text-sm text-blue-900 dark:text-blue-100">
              Рекомендуем платить больше минимума, чтобы сэкономить {monthlySavings.toLocaleString('ru-RU')} ₽/мес на процентах
            </p>
          </div>
        </div>
      </div>

      {/* Optimization Strategies */}
      <div className="bg-white dark:bg-slate-800 rounded-2xl p-6 border border-slate-200 dark:border-slate-700">
        <div className="flex items-center gap-2 mb-4">
          <TrendingUp className="w-5 h-5 text-green-600 dark:text-green-400" />
          <h3 className="text-slate-900 dark:text-white font-semibold">Стратегии погашения</h3>
        </div>
        <div className="space-y-3">
          {optimizationStrategies.map((strategy, idx) => (
            <motion.div
              key={strategy.id}
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: idx * 0.1 }}
              className="p-4 border border-slate-200 dark:border-slate-700 rounded-xl hover:bg-slate-50 dark:hover:bg-slate-700/50 transition-colors cursor-pointer"
            >
              <div className="flex items-start justify-between mb-2">
                <div className="flex-1">
                  <h4 className="text-sm text-slate-900 dark:text-white mb-1 font-medium">{strategy.title}</h4>
                  <p className="text-xs text-slate-500 dark:text-slate-400">{strategy.description}</p>
                </div>
                <span className="text-xs px-2 py-1 bg-green-100 dark:bg-green-900/30 text-green-600 dark:text-green-400 rounded-full whitespace-nowrap ml-2 font-semibold">
                  -{strategy.savings.toLocaleString('ru-RU', { notation: 'compact' })} ₽
                </span>
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-500 dark:text-slate-400">{strategy.priority}</span>
                <span className="text-slate-500 dark:text-slate-400">{strategy.months} мес</span>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </div>
  )
}
