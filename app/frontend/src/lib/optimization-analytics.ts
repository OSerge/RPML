import type {
  OptimizationPlanResponse,
  OptimizationRunResponse,
} from '@/lib/api-client'
import type {
  PaymentAnalyticsBaseline,
  PaymentAnalyticsDebt,
  PaymentAnalyticsStrategyKey,
  PaymentAnalyticsStrategyResult,
} from '@/components/PaymentAnalytics'

type OptimizationAnalyticsResponse = OptimizationRunResponse | OptimizationPlanResponse

export type OptimizationBudgetMetrics = {
  totalAvailable: number | null
  totalSpent: number | null
  reserveEnd: number | null
  spentShare: number | null
}

export type OptimizationAnalyticsView = {
  debts: PaymentAnalyticsDebt[]
  strategyResults: Partial<Record<PaymentAnalyticsStrategyKey, PaymentAnalyticsStrategyResult>> | null
  monthlyIncome: number[] | null
  baseline: PaymentAnalyticsBaseline | null
  budgetMetrics: OptimizationBudgetMetrics
  horizonMonths: number
  ruModeActive: boolean
}

function asFiniteNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function normalizeStrategyResult(raw: unknown): PaymentAnalyticsStrategyResult | null {
  if (!raw || typeof raw !== 'object') return null
  const value = raw as Record<string, unknown>
  const totalCost = asFiniteNumber(value.total_cost)
  const paymentsMatrix = value.payments_matrix
  const balancesMatrix = value.balances_matrix
  const savingsVector = value.savings_vector
  const budgetTrace = value.budget_trace
  if (totalCost == null || !Array.isArray(paymentsMatrix) || !Array.isArray(balancesMatrix)) {
    return null
  }
  return {
    total_cost: totalCost,
    paymentsMatrix: paymentsMatrix as number[][],
    balancesMatrix: balancesMatrix as number[][],
    savingsVector: Array.isArray(savingsVector) ? (savingsVector as number[]) : undefined,
    budgetTrace: Array.isArray(budgetTrace) ? (budgetTrace as Array<Record<string, unknown>>) : undefined,
  }
}

function buildMonthlyIncome(
  budgetTrace: OptimizationAnalyticsResponse['budget_trace'],
): number[] | null {
  if (!Array.isArray(budgetTrace) || budgetTrace.length === 0) return null
  const values = budgetTrace
    .map((item) => asFiniteNumber(item?.income_in))
    .filter((value): value is number => value != null)
  return values.length > 0 ? values : null
}

function buildBudgetMetrics(
  budgetTrace: OptimizationAnalyticsResponse['budget_trace'],
): OptimizationBudgetMetrics {
  if (!Array.isArray(budgetTrace) || budgetTrace.length === 0) {
    return {
      totalAvailable: null,
      totalSpent: null,
      reserveEnd: null,
      spentShare: null,
    }
  }

  let totalAvailable = 0
  let totalSpent = 0
  let reserveEnd: number | null = null

  for (const row of budgetTrace) {
    totalAvailable += asFiniteNumber(row?.available_budget) ?? 0
    totalSpent += asFiniteNumber(row?.paid_total) ?? asFiniteNumber(row?.planned_payment) ?? 0
    reserveEnd =
      asFiniteNumber(row?.reserve_end) ??
      asFiniteNumber(row?.carry_out) ??
      reserveEnd
  }

  const spentShare = totalAvailable > 0 ? totalSpent / totalAvailable : null

  return {
    totalAvailable,
    totalSpent,
    reserveEnd,
    spentShare,
  }
}

export function buildOptimizationAnalyticsView(
  result: OptimizationAnalyticsResponse,
): OptimizationAnalyticsView {
  const topLevelBudgetTrace = Array.isArray(result.budget_trace) ? result.budget_trace : undefined
  const debts = Array.isArray(result.debts)
    ? result.debts.map((debt) => ({
        id: debt.id,
        name: debt.name,
        loan_type: debt.loan_type ?? undefined,
        principal: debt.principal ?? undefined,
        fixed_payment: debt.fixed_payment ?? undefined,
        default_rate_monthly: debt.default_rate_monthly ?? undefined,
      }))
    : []

  const baselineRaw =
    result.baseline_comparison && typeof result.baseline_comparison === 'object'
      ? (result.baseline_comparison as Record<string, unknown>)
      : null

  const baseline =
    baselineRaw &&
    asFiniteNumber(baselineRaw.milp_total_cost) != null &&
    asFiniteNumber(baselineRaw.avalanche_total_cost) != null &&
    asFiniteNumber(baselineRaw.snowball_total_cost) != null
      ? {
          milp_total_cost: asFiniteNumber(baselineRaw.milp_total_cost) ?? 0,
          avalanche_total_cost: asFiniteNumber(baselineRaw.avalanche_total_cost) ?? 0,
          snowball_total_cost: asFiniteNumber(baselineRaw.snowball_total_cost) ?? 0,
          savings_vs_avalanche_abs: asFiniteNumber(baselineRaw.savings_vs_avalanche_abs) ?? undefined,
          savings_vs_snowball_abs: asFiniteNumber(baselineRaw.savings_vs_snowball_abs) ?? undefined,
        }
      : null

  const strategyResults: Partial<Record<PaymentAnalyticsStrategyKey, PaymentAnalyticsStrategyResult>> = {}
  const rawStrategyResults =
    baselineRaw && typeof baselineRaw.strategy_results === 'object'
      ? (baselineRaw.strategy_results as Record<string, unknown>)
      : null

  for (const key of ['milp', 'avalanche', 'snowball'] as const) {
    const normalized = normalizeStrategyResult(rawStrategyResults?.[key])
    if (normalized) {
      strategyResults[key] = normalized
    }
  }

  if (strategyResults.milp && topLevelBudgetTrace && !strategyResults.milp.budgetTrace) {
    strategyResults.milp = {
      ...strategyResults.milp,
      budgetTrace: topLevelBudgetTrace,
    }
  }

  if (!strategyResults.milp && Array.isArray(result.payments_matrix) && Array.isArray(result.balances_matrix)) {
    strategyResults.milp = {
      total_cost: result.total_cost,
      paymentsMatrix: result.payments_matrix,
      balancesMatrix: result.balances_matrix,
      savingsVector: Array.isArray(result.savings_vector) ? result.savings_vector : undefined,
      budgetTrace: topLevelBudgetTrace,
    }
  }

  return {
    debts,
    strategyResults: Object.keys(strategyResults).length > 0 ? strategyResults : null,
    monthlyIncome: buildMonthlyIncome(result.budget_trace),
    baseline,
    budgetMetrics: buildBudgetMetrics(result.budget_trace),
    horizonMonths: result.horizon_months,
    ruModeActive: result.ru_mode,
  }
}
