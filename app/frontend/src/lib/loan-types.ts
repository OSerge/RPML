import type { LoanType, LoanTypeDirectory } from './api-client'

export const DEFAULT_LOAN_TYPES: LoanType[] = [
  'car_loan',
  'house_loan',
  'credit_card',
  'bank_loan',
]

export const LOAN_TYPE_LABELS: Record<LoanType, string> = {
  car_loan: 'Автокредит',
  house_loan: 'Ипотека',
  credit_card: 'Кредитная карта',
  bank_loan: 'Потребительский кредит',
}

export function parseLoanTypes(dir: LoanTypeDirectory | null | undefined): LoanType[] {
  const raw = dir?.supported_values
  if (raw && raw.length > 0) {
    return raw as LoanType[]
  }
  return DEFAULT_LOAN_TYPES
}
