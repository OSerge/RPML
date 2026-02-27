export interface Debt {
  id: string
  name: string
  principal: number
  current_balance: number
  interest_rate_annual: number
  min_payment_pct: number
  late_fee_rate: number
  start_date: string
  term_months: number
  created_at?: string
  updated_at?: string
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
  type: 'mortgage' | 'car' | 'credit_card' | 'consumer'
}

export interface OptimizationPlan {
  id?: string
  total_cost: number
  savings_vs_minimum: number
  payments_matrix: Record<string, unknown>
  explanations?: Record<string, string>
  created_at?: string
}

export function mapDebtToCardData(debt: Debt): DebtCardData {
  const monthlyPayment = Math.ceil(debt.current_balance * (debt.min_payment_pct / 100))
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
    type: inferDebtType(debt.name),
  }
}

function inferDebtType(name: string): 'mortgage' | 'car' | 'credit_card' | 'consumer' {
  const nameLower = name.toLowerCase()
  if (nameLower.includes('ипотек') || nameLower.includes('mortgage')) return 'mortgage'
  if (nameLower.includes('авто') || nameLower.includes('car')) return 'car'
  if (nameLower.includes('карт') || nameLower.includes('card')) return 'credit_card'
  return 'consumer'
}
