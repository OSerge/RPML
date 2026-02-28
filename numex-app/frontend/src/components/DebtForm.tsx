import { useState, useEffect } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { createDebt } from '../services/api'
import {
  DebtType,
  DebtCreate,
  DEBT_TYPE_LABELS,
  DEBT_TYPE_DEFAULTS,
  PAYMENT_TYPE_LABELS,
  PREPAYMENT_LABELS,
  PaymentType,
  PrepaymentPolicy,
} from '../types/debt'

interface DebtFormProps {
  onClose: () => void
  onSuccess?: () => void
}

const DEBT_TYPES: DebtType[] = ['credit_card', 'mortgage', 'consumer_loan', 'car_loan', 'microloan']
const PAYMENT_TYPES: PaymentType[] = ['annuity', 'differentiated', 'minimum_percent']
const PREPAYMENT_POLICIES: PrepaymentPolicy[] = ['allowed', 'prohibited', 'with_penalty']

export function DebtForm({ onClose, onSuccess }: DebtFormProps) {
  const queryClient = useQueryClient()

  const [debtType, setDebtType] = useState<DebtType>('consumer_loan')
  const [name, setName] = useState('')
  const [principal, setPrincipal] = useState('')
  const [interestRate, setInterestRate] = useState('')
  const [startDate, setStartDate] = useState(new Date().toISOString().split('T')[0])

  const [paymentType, setPaymentType] = useState<PaymentType>('annuity')
  const [minPaymentPct, setMinPaymentPct] = useState('')
  const [fixedPayment, setFixedPayment] = useState('')
  const [termMonths, setTermMonths] = useState('')

  const [prepaymentPolicy, setPrepaymentPolicy] = useState<PrepaymentPolicy>('allowed')
  const [prepaymentPenaltyPct, setPrepaymentPenaltyPct] = useState('')

  const [creditLimit, setCreditLimit] = useState('')
  const [gracePeriodDays, setGracePeriodDays] = useState('')
  const [validationError, setValidationError] = useState('')

  useEffect(() => {
    const defaults = DEBT_TYPE_DEFAULTS[debtType]
    if (defaults.payment_type) setPaymentType(defaults.payment_type)
    if (defaults.prepayment_policy) setPrepaymentPolicy(defaults.prepayment_policy)
    if (defaults.min_payment_pct !== undefined) setMinPaymentPct(String(defaults.min_payment_pct))
    if (defaults.term_months !== undefined) setTermMonths(String(defaults.term_months))
    else setTermMonths('')
  }, [debtType])

  const mutation = useMutation({
    mutationFn: createDebt,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['debts'] })
      onSuccess?.()
      onClose()
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()

    const principalNum = parseFloat(principal)
    const interestNum = parseFloat(interestRate)
    if (!Number.isFinite(principalNum) || principalNum < 0) {
      setValidationError('Укажите корректную сумму долга')
      return
    }
    if (!Number.isFinite(interestNum) || interestNum < 0) {
      setValidationError('Укажите корректную ставку (% годовых)')
      return
    }
    setValidationError('')

    const term = parseInt(termMonths, 10)
    const termMonthsValue = Number.isFinite(term) && term > 0 ? term : null

    const data: DebtCreate = {
      name: name.trim(),
      debt_type: debtType,
      principal: principalNum,
      current_balance: principalNum,
      interest_rate_annual: interestNum,
      start_date: startDate,
      payment_type: paymentType,
      prepayment_policy: prepaymentPolicy,
      term_months: termMonthsValue,
    }

    const minPct = parseFloat(minPaymentPct)
    if (Number.isFinite(minPct) && minPct >= 0) data.min_payment_pct = minPct
    const fixed = parseFloat(fixedPayment)
    if (Number.isFinite(fixed) && fixed > 0) data.fixed_payment = fixed
    const penalty = parseFloat(prepaymentPenaltyPct)
    if (Number.isFinite(penalty) && penalty >= 0) data.prepayment_penalty_pct = penalty
    const limit = parseFloat(creditLimit)
    if (Number.isFinite(limit) && limit > 0) data.credit_limit = limit
    const days = parseInt(gracePeriodDays, 10)
    if (Number.isFinite(days) && days >= 0) data.grace_period_days = days

    mutation.mutate(data)
  }

  const showCreditCardFields = debtType === 'credit_card'
  const showTermField = debtType !== 'credit_card'
  const showMinPaymentPct = paymentType === 'minimum_percent'
  const showFixedPayment = paymentType !== 'minimum_percent'
  const showPenaltyPct = prepaymentPolicy === 'with_penalty'

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
      <div className="bg-white dark:bg-slate-800 rounded-2xl p-6 w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-6">
          Добавить долг
        </h2>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
              Тип долга
            </label>
            <select
              value={debtType}
              onChange={(e) => setDebtType(e.target.value as DebtType)}
              className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg text-slate-900 dark:text-white"
            >
              {DEBT_TYPES.map((type) => (
                <option key={type} value={type}>
                  {DEBT_TYPE_LABELS[type]}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
              Название
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Например: Ипотека Сбербанк"
              required
              className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg text-slate-900 dark:text-white"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                {showCreditCardFields ? 'Текущий долг' : 'Сумма кредита'}
              </label>
              <input
                type="number"
                value={principal}
                onChange={(e) => setPrincipal(e.target.value)}
                placeholder="500000"
                required
                min="0"
                step="0.01"
                className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg text-slate-900 dark:text-white"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                Ставка (% годовых)
              </label>
              <input
                type="number"
                value={interestRate}
                onChange={(e) => setInterestRate(e.target.value)}
                placeholder="15.5"
                required
                min="0"
                max="1000"
                step="0.01"
                className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg text-slate-900 dark:text-white"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                Дата начала
              </label>
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                required
                className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg text-slate-900 dark:text-white"
              />
            </div>
            {showTermField && (
              <div>
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                  Срок (месяцев)
                </label>
                <input
                  type="number"
                  value={termMonths}
                  onChange={(e) => setTermMonths(e.target.value)}
                  placeholder="36"
                  min="1"
                  max="600"
                  className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg text-slate-900 dark:text-white"
                />
              </div>
            )}
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
              Тип платежа
            </label>
            <select
              value={paymentType}
              onChange={(e) => setPaymentType(e.target.value as PaymentType)}
              className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg text-slate-900 dark:text-white"
            >
              {PAYMENT_TYPES.map((type) => (
                <option key={type} value={type}>
                  {PAYMENT_TYPE_LABELS[type]}
                </option>
              ))}
            </select>
          </div>

          {showMinPaymentPct && (
            <div>
              <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                Минимальный платёж (% от остатка)
              </label>
              <input
                type="number"
                value={minPaymentPct}
                onChange={(e) => setMinPaymentPct(e.target.value)}
                placeholder="5"
                min="0"
                max="100"
                step="0.1"
                className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg text-slate-900 dark:text-white"
              />
            </div>
          )}

          {showFixedPayment && (
            <div>
              <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                Фиксированный платёж (руб/мес, если известен)
              </label>
              <input
                type="number"
                value={fixedPayment}
                onChange={(e) => setFixedPayment(e.target.value)}
                placeholder="Рассчитается автоматически"
                min="0"
                step="0.01"
                className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg text-slate-900 dark:text-white"
              />
            </div>
          )}

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                Досрочное погашение
              </label>
              <select
                value={prepaymentPolicy}
                onChange={(e) => setPrepaymentPolicy(e.target.value as PrepaymentPolicy)}
                className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg text-slate-900 dark:text-white"
              >
                {PREPAYMENT_POLICIES.map((policy) => (
                  <option key={policy} value={policy}>
                    {PREPAYMENT_LABELS[policy]}
                  </option>
                ))}
              </select>
            </div>
            {showPenaltyPct && (
              <div>
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                  Штраф за досрочку (%)
                </label>
                <input
                  type="number"
                  value={prepaymentPenaltyPct}
                  onChange={(e) => setPrepaymentPenaltyPct(e.target.value)}
                  placeholder="1"
                  min="0"
                  max="100"
                  step="0.1"
                  className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg text-slate-900 dark:text-white"
                />
              </div>
            )}
          </div>

          {showCreditCardFields && (
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                  Кредитный лимит
                </label>
                <input
                  type="number"
                  value={creditLimit}
                  onChange={(e) => setCreditLimit(e.target.value)}
                  placeholder="300000"
                  min="0"
                  step="0.01"
                  className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg text-slate-900 dark:text-white"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                  Льготный период (дней)
                </label>
                <input
                  type="number"
                  value={gracePeriodDays}
                  onChange={(e) => setGracePeriodDays(e.target.value)}
                  placeholder="55"
                  min="0"
                  max="365"
                  className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg text-slate-900 dark:text-white"
                />
              </div>
            </div>
          )}

            {(validationError || mutation.isError) && (
              <div className="p-3 bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800 rounded-lg">
                <p className="text-sm text-red-900 dark:text-red-100">
                  {validationError || 'Ошибка при создании долга'}
                </p>
              </div>
            )}

          <div className="flex gap-3 pt-4">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 px-4 py-2 border border-slate-300 dark:border-slate-600 text-slate-700 dark:text-slate-300 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-700 transition-colors"
            >
              Отмена
            </button>
            <button
              type="submit"
              disabled={mutation.isPending}
              className="flex-1 px-4 py-2 bg-gradient-to-r from-indigo-500 to-purple-600 text-white rounded-lg hover:from-indigo-600 hover:to-purple-700 transition-all disabled:opacity-50"
            >
              {mutation.isPending ? 'Сохранение...' : 'Добавить'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
