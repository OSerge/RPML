import type { components } from '@/contracts/generated/types'

type LoanType = components['schemas']['LoanType']

type DebtLike = {
  id: number
  name?: string | null
  loan_type?: LoanType | null
}

const TYPE_LABEL: Record<LoanType, string> = {
  car_loan: 'Автокредит',
  house_loan: 'Ипотека',
  credit_card: 'Кредитка',
  bank_loan: 'Банк-кредит',
}

const GENERATED_DEBT_NAME_RE = /_loan_\d+$/i

function isGeneratedDebtName(name: string): boolean {
  return GENERATED_DEBT_NAME_RE.test(name.trim())
}

export function buildDebtDisplayNames(debts: DebtLike[]): Record<number, string> {
  const names: Record<number, string> = {}
  const typeCounters: Partial<Record<LoanType, number>> = {}

  for (const debt of debts) {
    const rawName = debt.name?.trim() ?? ''
    const loanType = debt.loan_type ?? null
    const typeLabel = loanType ? TYPE_LABEL[loanType] : null

    if (rawName && (!isGeneratedDebtName(rawName) || !typeLabel)) {
      names[debt.id] = rawName
      continue
    }

    if (typeLabel && loanType) {
      const idx = (typeCounters[loanType] ?? 0) + 1
      typeCounters[loanType] = idx
      names[debt.id] = `${typeLabel} ${idx}`
      continue
    }

    names[debt.id] = rawName || `Долг ${debt.id}`
  }

  return names
}
