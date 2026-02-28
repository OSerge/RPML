export type DebtType = 'credit_card' | 'mortgage' | 'consumer_loan' | 'car_loan' | 'microloan'
export type PaymentType = 'annuity' | 'differentiated' | 'minimum_percent'
export type PrepaymentPolicy = 'allowed' | 'prohibited' | 'with_penalty'

export interface Debt {
  id: string
  name: string
  debt_type: DebtType

  principal: number
  current_balance: number
  interest_rate_annual: number

  payment_type: PaymentType
  min_payment_pct: number
  fixed_payment: number | null

  prepayment_policy: PrepaymentPolicy
  prepayment_penalty_pct: number | null

  late_fee_rate: number | null
  start_date: string
  term_months: number | null

  credit_limit: number | null
  grace_period_days: number | null
}

export interface DebtCreate {
  name: string
  debt_type: DebtType

  principal: number
  current_balance?: number
  interest_rate_annual: number

  payment_type?: PaymentType
  min_payment_pct?: number
  fixed_payment?: number

  prepayment_policy?: PrepaymentPolicy
  prepayment_penalty_pct?: number

  late_fee_rate?: number
  start_date: string
  term_months?: number | null

  credit_limit?: number
  grace_period_days?: number
}

export const DEBT_TYPE_LABELS: Record<DebtType, string> = {
  credit_card: 'Кредитная карта',
  mortgage: 'Ипотека',
  consumer_loan: 'Потребительский кредит',
  car_loan: 'Автокредит',
  microloan: 'Микрозайм',
}

export const PAYMENT_TYPE_LABELS: Record<PaymentType, string> = {
  annuity: 'Аннуитетный',
  differentiated: 'Дифференцированный',
  minimum_percent: '% от остатка',
}

export const PREPAYMENT_LABELS: Record<PrepaymentPolicy, string> = {
  allowed: 'Разрешено',
  prohibited: 'Запрещено',
  with_penalty: 'Со штрафом',
}

export const DEBT_TYPE_DEFAULTS: Record<DebtType, Partial<DebtCreate>> = {
  credit_card: {
    payment_type: 'minimum_percent',
    prepayment_policy: 'allowed',
    min_payment_pct: 5,
    term_months: undefined,
  },
  mortgage: {
    payment_type: 'annuity',
    prepayment_policy: 'with_penalty',
    min_payment_pct: 0,
    term_months: 240,
  },
  consumer_loan: {
    payment_type: 'annuity',
    prepayment_policy: 'allowed',
    min_payment_pct: 0,
    term_months: 36,
  },
  car_loan: {
    payment_type: 'annuity',
    prepayment_policy: 'with_penalty',
    min_payment_pct: 0,
    term_months: 60,
  },
  microloan: {
    payment_type: 'annuity',
    prepayment_policy: 'allowed',
    min_payment_pct: 0,
    term_months: 6,
  },
}

export interface DebtCardData {
  id: string
  name: string
  totalAmount: number
  remainingAmount: number
  monthlyPayment: number
  rate: number
  nextPaymentDate: string
  minPayment: number
  type: DebtType
}

export interface OptimizationPlan {
  id?: string
  total_cost: number
  savings_vs_minimum: number | null
  baseline_cost?: number
  payments_matrix: Record<string, number[]>
  balances_matrix?: Record<string, number[]>
  status?: string
  solve_time?: number
  horizon_months?: number
  created_at?: string
}

export interface OptimizationRequest {
  monthly_budget?: number
  budget_by_month?: number[]
  horizon_months?: number
}

export function mapDebtToCardData(debt: Debt): DebtCardData {
  let monthlyPayment: number
  if (debt.fixed_payment) {
    monthlyPayment = debt.fixed_payment
  } else if (debt.payment_type === 'minimum_percent') {
    monthlyPayment = Math.ceil(debt.current_balance * (debt.min_payment_pct / 100))
  } else {
    monthlyPayment = calculateAnnuityPayment(
      debt.current_balance,
      debt.interest_rate_annual,
      debt.term_months || 12
    )
  }

  const nextPaymentDate = new Date()
  nextPaymentDate.setDate(nextPaymentDate.getDate() + 30)

  return {
    id: debt.id,
    name: debt.name,
    totalAmount: debt.principal,
    remainingAmount: debt.current_balance,
    monthlyPayment,
    rate: debt.interest_rate_annual,
    nextPaymentDate: nextPaymentDate.toISOString().split('T')[0],
    minPayment: monthlyPayment,
    type: debt.debt_type,
  }
}

function calculateAnnuityPayment(principal: number, annualRate: number, termMonths: number): number {
  const monthlyRate = Math.pow(1 + annualRate / 100, 1 / 12) - 1
  if (monthlyRate === 0) {
    return Math.ceil(principal / termMonths)
  }
  return Math.ceil(
    principal * (monthlyRate * Math.pow(1 + monthlyRate, termMonths)) /
    (Math.pow(1 + monthlyRate, termMonths) - 1)
  )
}
