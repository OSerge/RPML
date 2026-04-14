import { useMemo, useState } from 'react'
import { ArrowDownNarrowWide, ArrowUpRight, BadgePercent, CheckCircle, Sparkles } from 'lucide-react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { motion } from 'motion/react'

const LOAN_COLORS = ['#3b82f6', '#8b5cf6', '#ec4899', '#10b981', '#f59e0b', '#14b8a6', '#ef4444', '#6366f1']

const NON_DISPLAYABLE_FIXED_PAYMENT_MIN = 1e11

export type PaymentAnalyticsDebt = {
  id: number
  name: string
  principal?: number | null
  fixed_payment?: number | null
  default_rate_monthly?: number | null
}

function fixedPaymentLabel(v: number | null | undefined): string {
  if ((v ?? 0) >= NON_DISPLAYABLE_FIXED_PAYMENT_MIN) return '—'
  return `${(v ?? 0).toLocaleString('ru-RU', { maximumFractionDigits: 0 })} ₽/мес`
}

export type PaymentAnalyticsBaseline = {
  milp_total_cost: number
  avalanche_total_cost: number
  snowball_total_cost: number
  savings_vs_avalanche_abs?: number
  savings_vs_snowball_abs?: number
}

export type PaymentAnalyticsStrategyKey = 'milp' | 'avalanche' | 'snowball'

export type PaymentAnalyticsStrategyResult = {
  total_cost: number
  paymentsMatrix: number[][]
  balancesMatrix: number[][]
  savingsVector?: number[]
  budgetTrace?: Array<Record<string, unknown>>
}

export type PaymentAnalyticsPanelProps = {
  debts: PaymentAnalyticsDebt[]
  strategyResults: Partial<Record<PaymentAnalyticsStrategyKey, PaymentAnalyticsStrategyResult>> | null
  monthlyIncome: number[] | null
  horizonMonths: number
  baseline: PaymentAnalyticsBaseline | null
}

type TooltipPayloadEntry = {
  color?: string
  name?: string
  value?: number
}

function AnalyticsTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean
  payload?: TooltipPayloadEntry[]
  label?: string
}) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-xl border border-border bg-card/95 p-4 text-foreground shadow-lg backdrop-blur">
      <p className="mb-2 text-sm font-medium">Месяц {label}</p>
      {payload.map((entry, index) => (
        <p key={index} className="text-sm" style={{ color: entry.color }}>
          {entry.name}:{' '}
          {typeof entry.value === 'number' ? entry.value.toLocaleString('ru-RU', { maximumFractionDigits: 0 }) : entry.value}{' '}
          ₽
        </p>
      ))}
    </div>
  )
}

function loanColor(index: number): string {
  return LOAN_COLORS[index % LOAN_COLORS.length]
}

export function PaymentAnalyticsPanel({
  debts,
  strategyResults,
  monthlyIncome,
  horizonMonths,
  baseline,
}: PaymentAnalyticsPanelProps) {
  const [selectedStrategy, setSelectedStrategy] = useState<PaymentAnalyticsStrategyKey>('milp')

  const activeStrategyResult = useMemo(
    () => strategyResults?.[selectedStrategy] ?? strategyResults?.milp ?? null,
    [selectedStrategy, strategyResults],
  )

  const paymentsMatrix = activeStrategyResult?.paymentsMatrix ?? []
  const balancesMatrix = activeStrategyResult?.balancesMatrix ?? []
  const savingsVector = activeStrategyResult?.savingsVector ?? []
  const budgetTrace = activeStrategyResult?.budgetTrace ?? null
  const hasExactPenaltyTrace = Array.isArray(budgetTrace) && budgetTrace.length > 0

  const nLoans = debts.length
  const hasBalanceData =
    balancesMatrix.length === nLoans &&
    nLoans > 0 &&
    (balancesMatrix[0]?.length ?? 0) > 0 &&
    (balancesMatrix[0]?.length ?? 0) === (paymentsMatrix[0]?.length ?? 0)

  const T = Math.min(horizonMonths, paymentsMatrix[0]?.length ?? 0)

  const chartMonths = useMemo(() => {
    if (!T || T <= 0) return 0
    const trailingMonths = 3
    if (hasBalanceData) {
      const eps = 1e-2
      let latestPayoff = 0
      for (let j = 0; j < nLoans; j++) {
        const bal = balancesMatrix[j] ?? []
        let payoff = T
        for (let m = 0; m < Math.min(T, bal.length); m++) {
          if ((bal[m] ?? 0) <= eps) {
            payoff = m + 1
            break
          }
        }
        latestPayoff = Math.max(latestPayoff, payoff)
      }
      return Math.min(T, latestPayoff + trailingMonths)
    }
    let lastActive = 0
    for (let m = 0; m < T; m++) {
      let monthTotal = 0
      for (let j = 0; j < nLoans; j++) {
        monthTotal += paymentsMatrix[j]?.[m] ?? 0
      }
      if (monthTotal > 1e-6) {
        lastActive = m + 1
      }
    }
    return Math.min(T, Math.max(1, lastActive + trailingMonths))
  }, [T, balancesMatrix, hasBalanceData, nLoans, paymentsMatrix])

  const chartRows = useMemo(() => {
    if (!chartMonths || !nLoans) return []
    return Array.from({ length: chartMonths }, (_, i) => {
      const row: Record<string, number> = { month: i + 1 }
      let totalPay = 0
      let estimatedPenalty = 0
      for (let j = 0; j < nLoans; j++) {
        const p = paymentsMatrix[j]?.[i] ?? 0
        row[`pay${j}`] = p
        totalPay += p
        const bal = hasBalanceData ? (balancesMatrix[j]?.[i] ?? 0) : 0
        row[`bal${j}`] = bal
        const defaultRate = debts[j]?.default_rate_monthly ?? 0
        estimatedPenalty += bal * defaultRate
      }
      row.totalPayment = totalPay
      row.income = monthlyIncome?.[i] ?? 0
      row.estimatedPenalty = estimatedPenalty
      const budgetTracePenalty = budgetTrace?.[i]?.implied_penalty
      row.penaltyPaid =
        typeof budgetTracePenalty === 'number' && Number.isFinite(budgetTracePenalty)
          ? budgetTracePenalty
          : estimatedPenalty
      row.reserveEnd = Math.max(0, savingsVector[i] ?? row.income - totalPay)
      return row
    })
  }, [balancesMatrix, budgetTrace, chartMonths, debts, hasBalanceData, monthlyIncome, nLoans, paymentsMatrix, savingsVector])

  const reserveRows = useMemo(() => {
    if (!chartRows.length) return []
    return chartRows.map((row) => {
      const plannedPayment = row.totalPayment ?? 0
      const estimatedPenalty = row.penaltyPaid ?? row.estimatedPenalty ?? 0
      const reserveEnd = row.reserveEnd ?? Math.max(0, row.income - plannedPayment)
      return {
        month: row.month,
        plannedPayment,
        estimatedPenalty,
        reserveEnd,
      }
    })
  }, [chartRows])

  const payoffTimeline = useMemo(() => {
    return debts.map((debt, index) => {
      const bal = hasBalanceData ? (balancesMatrix[index] ?? []) : []
      const eps = 1e-2
      let payoffMonth = T
      if (hasBalanceData) {
        for (let m = 0; m < bal.length; m++) {
          if (bal[m] <= eps) {
            payoffMonth = m + 1
            break
          }
        }
      }
      return { ...debt, color: loanColor(index), payoffMonth }
    })
  }, [balancesMatrix, debts, hasBalanceData, T])

  const strategies = useMemo(() => {
    if (!baseline) return []
    const avDiff = baseline.avalanche_total_cost - baseline.milp_total_cost
    const snDiff = baseline.snowball_total_cost - baseline.milp_total_cost
    const avPct =
      baseline.avalanche_total_cost > 0 ? (avDiff / baseline.avalanche_total_cost) * 100 : 0
    const snPct =
      baseline.snowball_total_cost > 0 ? (snDiff / baseline.snowball_total_cost) * 100 : 0
    return [
      {
        name: 'MILP (оптимальная)',
        key: 'milp' as const,
        cost: baseline.milp_total_cost,
        icon: Sparkles,
        gradient: 'from-indigo-500 to-purple-600',
        savingsPct: 0,
        recommended: true,
      },
      {
        name: 'Аваланш (Avalanche)',
        key: 'avalanche' as const,
        cost: baseline.avalanche_total_cost,
        icon: BadgePercent,
        gradient: 'from-slate-600 to-slate-700',
        savingsPct: avPct,
      },
      {
        name: 'Сноуболл (Snowball)',
        key: 'snowball' as const,
        cost: baseline.snowball_total_cost,
        icon: ArrowDownNarrowWide,
        gradient: 'from-stone-600 to-stone-700',
        savingsPct: snPct,
      },
    ]
  }, [baseline])

  const threeCostsMatch = useMemo(() => {
    if (!baseline) return false
    const a = baseline.milp_total_cost
    const b = baseline.avalanche_total_cost
    const c = baseline.snowball_total_cost
    const tol = Math.max(1, Math.abs(a)) * 1e-9
    return Math.abs(a - b) < tol && Math.abs(a - c) < tol
  }, [baseline])

  const hasPaymentCharts = chartRows.length > 0 && nLoans > 0
  const activeStrategyLabel = strategies.find((strategy) => strategy.key === selectedStrategy)?.name ?? 'MILP (оптимальная)'

  return (
    <div className="space-y-6">
      {strategies.length > 0 ? (
        <div>
          <h2 className="mb-4 text-foreground">Сравнение стратегий погашения</h2>
          <p className="mb-3 text-sm text-muted-foreground">
            Нажмите на карточку стратегии: графики, распределение платежей и сроки погашения ниже переключаются вместе с
            выбранной стратегией.
          </p>
          {threeCostsMatch ? (
            <p className="mb-4 text-sm text-amber-800 dark:text-amber-200/90">
              Сейчас три суммы совпадают (с учётом округления). Проверьте ненулевые разные ставки по займам и сценарий без
              полного запрета досрочки, если нужно визуально развести стратегии.
            </p>
          ) : null}
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            {strategies.map((strategy, index) => (
              <motion.button
                key={strategy.key}
                type="button"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.1, duration: 0.4 }}
                className="group relative h-full text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2"
                aria-pressed={selectedStrategy === strategy.key}
                onClick={() => setSelectedStrategy(strategy.key)}
              >
                <div
                  className={`relative flex h-full min-h-[184px] flex-col justify-between rounded-2xl border-2 bg-card/80 p-6 backdrop-blur-xl transition-all duration-300 ${
                    selectedStrategy === strategy.key
                      ? 'border-indigo-500 shadow-xl'
                      : 'border-border hover:border-indigo-300'
                  }`}
                >
                  <div className="mb-4 flex items-center gap-3">
                    <div
                      className={`flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br ${strategy.gradient}`}
                    >
                      <strategy.icon className="h-6 w-6 text-white" />
                    </div>
                    <div className="space-y-1">
                      <h3 className="text-sm font-medium text-foreground">{strategy.name}</h3>
                      {strategy.recommended ? (
                        <span className="inline-flex items-center gap-1 rounded-full border border-indigo-200 bg-indigo-50 px-2 py-0.5 text-[11px] font-medium text-indigo-700 dark:border-indigo-900/70 dark:bg-indigo-950/40 dark:text-indigo-200">
                          <CheckCircle className="h-3 w-3" />
                          Оптимум
                        </span>
                      ) : null}
                    </div>
                  </div>

                  <div className="space-y-2">
                    <div>
                      <p className="text-xs text-muted-foreground">Общая стоимость</p>
                      <p className="text-2xl font-semibold text-foreground">
                        {strategy.cost.toLocaleString('ru-RU', { maximumFractionDigits: 0 })} ₽
                      </p>
                    </div>

                    <div className="flex min-h-5 items-center">
                      {strategy.savingsPct !== 0 && !strategy.recommended ? (
                        <div
                          className={`flex items-center gap-1 text-sm ${
                            strategy.savingsPct > 0 ? 'text-red-600 dark:text-red-400' : 'text-green-600 dark:text-green-400'
                          }`}
                        >
                          <ArrowUpRight className="h-4 w-4" />
                          <span>
                            {strategy.savingsPct > 0 ? '+' : ''}
                            {strategy.savingsPct.toFixed(1)}% к MILP
                          </span>
                        </div>
                      ) : null}
                    </div>
                  </div>
                </div>
              </motion.button>
            ))}
          </div>
        </div>
      ) : null}

      {nLoans > 0 ? (
        <div>
          <h2 className="mb-4 text-foreground">Детали кредитов</h2>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
            {debts.map((loan, index) => (
              <motion.div
                key={loan.id}
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ delay: index * 0.1, duration: 0.3 }}
                className="group relative"
              >
                <div
                  className="absolute -inset-0.5 rounded-2xl opacity-0 blur transition duration-500 group-hover:opacity-100"
                  style={{
                    background: `linear-gradient(135deg, ${loanColor(index)}40, transparent)`,
                  }}
                />

                <div className="relative rounded-2xl border border-border bg-card/80 p-5 shadow-lg backdrop-blur-xl">
                  <div className="mb-3 flex items-center gap-2">
                    <div className="h-3 w-3 rounded-full" style={{ backgroundColor: loanColor(index) }} />
                    <h3 className="text-sm font-medium text-foreground">{loan.name}</h3>
                  </div>

                  <div className="space-y-2">
                    <div>
                      <p className="text-xs text-muted-foreground">Начальная сумма</p>
                      <p className="text-lg font-semibold text-foreground">
                        {(loan.principal ?? 0).toLocaleString('ru-RU', { maximumFractionDigits: 0 })} ₽
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground">Фикс. платеж</p>
                      <p className="text-sm text-muted-foreground">{fixedPaymentLabel(loan.fixed_payment)}</p>
                    </div>
                  </div>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      ) : null}

      {!hasPaymentCharts ? (
        <div className="rounded-2xl border border-border bg-muted/30 p-6 text-sm text-muted-foreground">
          Нет данных для графиков. Запустите оптимизацию с горизонтом, совпадающим с профилем сценария.
        </div>
      ) : (
        <>
          <div className="grid gap-4 xl:grid-cols-2">
            {hasBalanceData ? (
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                className="relative rounded-2xl border border-border bg-card/80 p-6 shadow-lg backdrop-blur-xl"
              >
                <div className="mb-6">
                  <h2 className="mb-1 text-foreground">График погашения долгов</h2>
                  <p className="text-sm text-muted-foreground">
                    {activeStrategyLabel}: динамика остатка по каждому кредиту отдельно, без накопления в общий график
                    (первые {chartMonths} мес. из {T})
                  </p>
                </div>

                <div className="h-[360px] w-full min-w-0">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={chartRows}>
                      <CartesianGrid strokeDasharray="3 3" className="stroke-border" opacity={0.5} />
                      <XAxis
                        dataKey="month"
                        tick={{ fill: '#94a3b8', fontSize: 12 }}
                        label={{ value: 'Месяц', position: 'insideBottom', offset: -4, fill: '#94a3b8' }}
                      />
                      <YAxis
                        tick={{ fill: '#94a3b8', fontSize: 12 }}
                        tickFormatter={(value) => `${(value / 1000).toFixed(0)}k`}
                        label={{
                          value: 'Остаток (₽)',
                          angle: -90,
                          position: 'insideLeft',
                          fill: '#94a3b8',
                        }}
                      />
                      <Tooltip content={<AnalyticsTooltip />} />
                      <Legend wrapperStyle={{ paddingTop: 16 }} />
                      {debts.map((loan, index) => (
                        <Line
                          key={loan.id}
                          type="linear"
                          dataKey={`bal${index}`}
                          name={loan.name}
                          stroke={loanColor(index)}
                          strokeWidth={2}
                          dot={false}
                        />
                      ))}
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </motion.div>
            ) : (
              <div className="rounded-2xl border border-border bg-muted/20 p-4 text-sm text-muted-foreground">
                Матрица остатков недоступна для этого запуска — график остатков скрыт. Платежи и сравнение стратегий ниже.
              </div>
            )}

            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1 }}
              className="relative rounded-2xl border border-border bg-card/80 p-6 shadow-lg backdrop-blur-xl"
            >
              <div className="mb-6">
                <h2 className="mb-1 text-foreground">Распределение платежей</h2>
                <p className="text-sm text-muted-foreground">
                  {activeStrategyLabel}: платежи по кредитам помесячно (первые {chartMonths} мес.)
                </p>
              </div>

              <div className="h-[360px] w-full min-w-0">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chartRows}>
                    <CartesianGrid strokeDasharray="3 3" className="stroke-border" opacity={0.5} />
                    <XAxis
                      dataKey="month"
                      tick={{ fill: '#94a3b8', fontSize: 11 }}
                      interval={chartMonths > 36 ? 5 : 2}
                    />
                    <YAxis
                      tick={{ fill: '#94a3b8', fontSize: 12 }}
                      tickFormatter={(value) => `${(value / 1000).toFixed(0)}k`}
                      label={{
                        value: 'Платеж (₽)',
                        angle: -90,
                        position: 'insideLeft',
                        fill: '#94a3b8',
                      }}
                    />
                    <Tooltip content={<AnalyticsTooltip />} />
                    <Legend wrapperStyle={{ paddingTop: 16 }} />
                    {debts.map((loan, index) => (
                      <Bar
                        key={loan.id}
                        dataKey={`pay${index}`}
                        name={loan.name}
                        stackId="pay"
                        fill={loanColor(index)}
                        radius={index === nLoans - 1 ? [4, 4, 0, 0] : [0, 0, 0, 0]}
                      />
                    ))}
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </motion.div>

            {monthlyIncome && monthlyIncome.length > 0 ? (
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.2 }}
                className="relative rounded-2xl border border-border bg-card/80 p-6 shadow-lg backdrop-blur-xl"
              >
                <div className="mb-6">
                  <h2 className="mb-1 text-foreground">Доход и платежи</h2>
                  <p className="text-sm text-muted-foreground">
                    Доход из профиля сценария и суммарный платеж {activeStrategyLabel} по месяцам
                  </p>
                </div>

                <div className="h-[360px] w-full min-w-0">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={chartRows}>
                      <CartesianGrid strokeDasharray="3 3" className="stroke-border" opacity={0.5} />
                      <XAxis dataKey="month" tick={{ fill: '#94a3b8', fontSize: 12 }} />
                      <YAxis tick={{ fill: '#94a3b8', fontSize: 12 }} tickFormatter={(value) => `${(value / 1000).toFixed(0)}k`} />
                      <Tooltip content={<AnalyticsTooltip />} />
                      <Legend wrapperStyle={{ paddingTop: 16 }} />
                      <Line type="monotone" dataKey="income" name="Доход" stroke="#10b981" strokeWidth={2} dot={false} />
                      <Line
                        type="monotone"
                        dataKey="totalPayment"
                        name="Платежи (сумма)"
                        stroke="#ef4444"
                        strokeWidth={2}
                        dot={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </motion.div>
            ) : null}

            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.25 }}
              className="relative rounded-2xl border border-border bg-card/80 p-6 shadow-lg backdrop-blur-xl"
            >
              <div className="mb-6">
                <h2 className="mb-1 text-foreground">Выплаты, штраф и резерв</h2>
                <p className="text-sm text-muted-foreground">
                  Помесячно видно, сколько бюджет реально ушел в выплаты и сколько осталось в резерве.{' '}
                  {hasExactPenaltyTrace
                    ? 'Штрафы берутся из динамики модели RPML.'
                    : 'Штрафы показаны как приближенная оценка, потому что точная помесячная трассировка для этой стратегии недоступна.'}
                </p>
              </div>

              <div className="h-[360px] w-full min-w-0">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={reserveRows}>
                    <CartesianGrid strokeDasharray="3 3" className="stroke-border" opacity={0.5} />
                    <XAxis dataKey="month" tick={{ fill: '#94a3b8', fontSize: 11 }} interval={chartMonths > 36 ? 5 : 2} />
                    <YAxis tick={{ fill: '#94a3b8', fontSize: 12 }} tickFormatter={(value) => `${(value / 1000).toFixed(0)}k`} />
                    <Tooltip content={<AnalyticsTooltip />} />
                    <Legend wrapperStyle={{ paddingTop: 16 }} />
                    <Bar dataKey="plannedPayment" name="Выплаты" fill="#22d3ee" radius={[4, 4, 0, 0]} />
                    <Bar
                      dataKey="estimatedPenalty"
                      name={hasExactPenaltyTrace ? 'Штраф (по модели)' : 'Штраф (оценка)'}
                      fill="#d946ef"
                      radius={[4, 4, 0, 0]}
                    />
                    <Bar dataKey="reserveEnd" name="Накопления (резерв)" fill="#22c55e" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </motion.div>
          </div>

          {hasBalanceData ? (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.3 }}
              className="relative rounded-2xl border border-border bg-card/80 p-6 shadow-lg backdrop-blur-xl"
            >
              <div className="mb-6">
                <h2 className="mb-1 text-foreground">Сроки погашения</h2>
                <p className="text-sm text-muted-foreground">Оценка месяца обнуления остатка по стратегии {activeStrategyLabel}</p>
              </div>

              <div className="space-y-4">
                {payoffTimeline.map((loan, index) => {
                  const progress = T > 0 ? Math.min(100, (loan.payoffMonth / T) * 100) : 0
                  const years = Math.floor((loan.payoffMonth - 1) / 12)
                  const months = (loan.payoffMonth - 1) % 12

                  return (
                    <div key={loan.id} className="relative">
                      <div className="mb-2 flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <div className="h-3 w-3 rounded-full" style={{ backgroundColor: loan.color }} />
                          <span className="text-sm font-medium text-foreground">{loan.name}</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-sm text-muted-foreground">
                            {years > 0 ? `${years} г. ` : ''}
                            {months >= 0 ? `${months} мес.` : ''}
                            <span className="text-muted-foreground/80"> (мес. {loan.payoffMonth})</span>
                          </span>
                          <CheckCircle className="h-4 w-4 text-green-500" />
                        </div>
                      </div>

                      <div className="h-3 overflow-hidden rounded-full border border-border bg-muted/60">
                        <motion.div
                          initial={{ width: 0 }}
                          animate={{ width: `${progress}%` }}
                          transition={{ duration: 0.8, delay: index * 0.08, ease: 'easeOut' }}
                          className="h-full rounded-full"
                          style={{ backgroundColor: loan.color }}
                        />
                      </div>
                    </div>
                  )
                })}
              </div>
            </motion.div>
          ) : null}
        </>
      )}
    </div>
  )
}
