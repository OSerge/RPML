import { type FormEvent, useCallback, useEffect, useState } from 'react'
import {
  createDebt,
  type DebtCreate,
  listDebts,
  listLoanTypes,
  type DebtRead,
  type LoanType
} from '@/lib/api-client'
import { clearStoredToken } from '@/lib/auth-storage'
import { buildDebtDisplayNames } from '@/lib/debt-display'
import { useNavigate } from 'react-router-dom'
import { LOAN_TYPE_LABELS, parseLoanTypes } from '@/lib/loan-types'
import { cn } from '@/lib/utils'

const PREPAY_PROHIBITED_VALUE = 1_000_000_000_000
const CREDIT_CARD_FIXED_PAYMENT_SENTINEL = 100_000_000_000_000

function buildDebtCreatePayload(name: string, loanType: LoanType, principal: number): DebtCreate {
  const normalizedPrincipal = Math.max(0, Number.isFinite(principal) ? principal : 0)
  const common = {
    name: name.trim(),
    loan_type: loanType,
    principal: normalizedPrincipal,
    prepay_penalty: PREPAY_PROHIBITED_VALUE,
    interest_rate_monthly: 0.02,
    default_rate_monthly: 0.03,
    release_time: 0,
  } satisfies Partial<DebtCreate>

  if (loanType === 'credit_card') {
    return {
      ...common,
      fixed_payment: CREDIT_CARD_FIXED_PAYMENT_SENTINEL,
      min_payment_pct: 0.1,
      stipulated_amount: 0,
    } as DebtCreate
  }

  const monthlyBase = Math.max(1000, normalizedPrincipal * 0.05)
  return {
    ...common,
    fixed_payment: monthlyBase,
    min_payment_pct: 0.05,
    stipulated_amount: monthlyBase,
  } as DebtCreate
}

export function DebtsPage() {
  const navigate = useNavigate()
  const [items, setItems] = useState<DebtRead[]>([])
  const [name, setName] = useState('')
  const [loanTypeOptions, setLoanTypeOptions] = useState<LoanType[]>([])
  const [loanType, setLoanType] = useState<LoanType>('bank_loan')
  const [principal, setPrincipal] = useState(100000)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const displayNames = buildDebtDisplayNames(items)

  const refresh = useCallback(async () => {
    setError(null)
    const rows = await listDebts()
    setItems(rows)
  }, [])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        setLoading(true)
        const [debts, typesDir] = await Promise.all([listDebts(), listLoanTypes()])
        if (cancelled) return
        setItems(debts)
        const opts = parseLoanTypes(typesDir)
        setLoanTypeOptions(opts)
        if (opts.includes('bank_loan')) {
          setLoanType('bank_loan')
        } else {
          setLoanType(opts[0] ?? 'bank_loan')
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : 'Не удалось загрузить данные')
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  async function onCreate(e: FormEvent) {
    e.preventDefault()
    setError(null)
    try {
      await createDebt(buildDebtCreatePayload(name, loanType, principal))
      setName('')
      setPrincipal(100000)
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка создания')
    }
  }

  function logout() {
    clearStoredToken()
    navigate('/login', { replace: true })
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-xl font-medium">Долги</h2>
        <button
          type="button"
          onClick={logout}
          className="rounded-md border border-border px-3 py-1.5 text-sm"
        >
          Выйти
        </button>
      </div>
      {loading ? <p className="text-sm text-muted-foreground">Загрузка…</p> : null}
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
      <ul className="divide-y divide-border rounded-md border border-border">
        {items.length === 0 && !loading ? (
          <li className="px-3 py-4 text-sm text-muted-foreground">Пока нет долгов</li>
        ) : null}
        {items.map((d) => (
          <li key={d.id} className="px-3 py-2 text-sm">
            <span className="font-medium">{displayNames[d.id] ?? d.name}</span>
            <span className="ml-2 text-muted-foreground">#{d.id}</span>
            {d.loan_type ? (
              <span className="ml-2 text-muted-foreground">
                · {LOAN_TYPE_LABELS[d.loan_type] ?? d.loan_type}
              </span>
            ) : null}
          </li>
        ))}
      </ul>
      <form onSubmit={onCreate} className="flex flex-wrap items-end gap-2">
        <label className="flex min-w-[200px] flex-1 flex-col gap-1">
          <span className="text-sm text-muted-foreground">Новый долг</span>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Название"
            required
            className="rounded-md border border-input bg-background px-3 py-2 text-sm"
          />
        </label>
        <label className="flex min-w-[170px] flex-col gap-1">
          <span className="text-sm text-muted-foreground">Остаток долга (principal)</span>
          <input
            type="number"
            min={0}
            value={principal}
            onChange={(e) => setPrincipal(Number(e.target.value))}
            required
            className="rounded-md border border-input bg-background px-3 py-2 text-sm"
          />
        </label>
        <label className="flex min-w-[180px] flex-col gap-1">
          <span className="text-sm text-muted-foreground">Тип кредита</span>
          <select
            value={loanType}
            onChange={(e) => setLoanType(e.target.value as LoanType)}
            className="rounded-md border border-input bg-background px-3 py-2 text-sm"
          >
            {loanTypeOptions.map((lt) => (
              <option key={lt} value={lt}>
                {LOAN_TYPE_LABELS[lt] ?? lt}
              </option>
            ))}
          </select>
        </label>
        <button
          type="submit"
          className={cn(
            'rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground',
          )}
        >
          Добавить
        </button>
      </form>
    </div>
  )
}
