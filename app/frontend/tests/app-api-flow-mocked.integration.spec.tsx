/// <reference lib="dom" />
/**
 * Интеграция UI + api-client против мока global.fetch (не браузерный e2e).
 * Сценарий: login → долг → sync optimize; затем async task + опрос + plan через клиент API.
 */
import { afterEach, beforeEach, describe, expect, test } from 'bun:test'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { AppRoutes } from '../src/App'
import {
  createOptimizationTask,
  getOptimizationPlan,
  getOptimizationTaskStatus,
} from '../src/lib/api-client'
import { clearStoredToken, setStoredToken } from '../src/lib/auth-storage'

type DebtRow = { id: number; user_id: number; name: string; loan_type?: string }
const mockDatasetInstance = {
  name: 'Deudas_4_0_0_2_2_120_fijo_fijo_0',
  loans_count: 4,
  horizon_months: 120,
  n_cars: 0,
  n_houses: 0,
  n_credit_cards: 2,
  n_bank_loans: 2,
}

const mockOptimizationDebts = [
  {
    id: 1,
    name: 'Кредитная карта 1',
    loan_type: 'credit_card',
    principal: 1200,
    fixed_payment: 150,
    prepay_penalty: 0,
    default_rate_monthly: 0.02,
  },
  {
    id: 2,
    name: 'Банковский кредит 1',
    loan_type: 'bank_loan',
    principal: 1800,
    fixed_payment: 220,
    prepay_penalty: 0,
    default_rate_monthly: 0.025,
  },
]

const mockBudgetTrace = [
  {
    month: 1,
    income_in: 0,
    available_budget: 0,
    planned_payment: 120,
    paid_total: 120,
    reserve_end: 0,
    carry_out: 0,
  },
  {
    month: 2,
    income_in: 900,
    available_budget: 900,
    planned_payment: 260,
    paid_total: 260,
    reserve_end: 640,
    carry_out: 640,
  },
]

const mockBaselineComparison = {
  milp_total_cost: 100,
  avalanche_total_cost: 110,
  snowball_total_cost: 115,
  savings_vs_avalanche_abs: 10,
  savings_vs_avalanche_pct: 9.1,
  savings_vs_snowball_abs: 15,
  savings_vs_snowball_pct: 13.0,
  strategy_results: {
    milp: {
      total_cost: 100,
      payments_matrix: [
        [120, 80],
        [0, 180],
      ],
      balances_matrix: [
        [1080, 1000],
        [1800, 1620],
      ],
      savings_vector: [0, 640],
    },
    avalanche: {
      total_cost: 110,
      payments_matrix: [
        [100, 100],
        [20, 160],
      ],
      balances_matrix: [
        [1100, 1000],
        [1780, 1620],
      ],
      savings_vector: [0, 640],
    },
    snowball: {
      total_cost: 115,
      payments_matrix: [
        [80, 120],
        [40, 140],
      ],
      balances_matrix: [
        [1120, 1000],
        [1760, 1620],
      ],
      savings_vector: [0, 640],
    },
  },
}

function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === 'string') {
    return input.startsWith('http') ? input : new URL(input, 'http://localhost').href
  }
  if (input instanceof URL) {
    return input.href
  }
  return input.url
}

function pathnameOf(u: string): string {
  return new URL(u).pathname
}

function installFetchMock(): () => void {
  const debts: DebtRow[] = []
  let taskStatusPolls = 0
  const original = globalThis.fetch

  const mockFetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = requestUrl(input)
    const path = pathnameOf(url)
    const method = (init?.method ?? 'GET').toUpperCase()
    const json = (body: unknown, status: number) =>
      new Response(JSON.stringify(body), {
        status,
        headers: { 'Content-Type': 'application/json' },
      })

    if (path === '/api/v1/auth/login' && method === 'POST') {
      return json({ access_token: 'mock-jwt', token_type: 'bearer' }, 200)
    }
    if (path === '/api/v1/debts/loan-types' && method === 'GET') {
      return json({ supported_values: ['car_loan', 'house_loan', 'credit_card', 'bank_loan'] }, 200)
    }
    if (path === '/api/v1/debts' && method === 'GET') {
      return json(debts, 200)
    }
    if (path === '/api/v1/debts' && method === 'POST') {
      const raw = JSON.parse((init?.body as string) ?? '{}') as { name?: string; loan_type?: string }
      const row: DebtRow = {
        id: 42,
        user_id: 7,
        name: String(raw.name ?? ''),
        loan_type: raw.loan_type ?? 'bank_loan',
      }
      debts.push(row)
      return json(row, 201)
    }
    if (path === '/api/v1/optimization/run' && method === 'POST') {
      const body = JSON.parse((init?.body as string) ?? '{}') as Record<string, unknown>
      expect(body.input_mode).toBe('dataset_instance')
      expect(body.instance_name).toBe(mockDatasetInstance.name)
      return json(
        {
          status: 'OPTIMAL',
          total_cost: 100,
          debts: mockOptimizationDebts,
          payments_matrix: [
            [120, 80],
            [0, 180],
          ],
          balances_matrix: [
            [1080, 1000],
            [1800, 1620],
          ],
          savings_vector: [0, 640],
          horizon_months: mockDatasetInstance.horizon_months,
          baseline_comparison: mockBaselineComparison,
          input_mode: 'dataset_instance',
          instance_name: mockDatasetInstance.name,
          assumptions: ['dataset instance'],
          ru_mode: true,
          mc_income: false,
          mc_summary: null,
          mc_config: null,
          budget_policy: 'starts_next_month_with_carryover',
          budget_trace: mockBudgetTrace,
        },
        200,
      )
    }
    if (path === '/api/v1/optimization/instances' && method === 'GET') {
      return json({ total: 1, items: [mockDatasetInstance] }, 200)
    }
    if (path === '/api/v1/optimization/mc-config/defaults' && method === 'GET') {
      return json(
        {
          n_scenarios: 16,
          seed: 42,
          rho: 0.55,
          sigma: 0.15,
          shock_prob: 0.04,
          shock_severity_mean: 0.3,
          shock_severity_std: 0.1,
          min_income_floor: 1,
        },
        200,
      )
    }
    if (path === '/api/v1/optimization/tasks' && method === 'POST') {
      const body = JSON.parse((init?.body as string) ?? '{}') as Record<string, unknown>
      expect(body.input_mode).toBe('dataset_instance')
      expect(body.instance_name).toBe(mockDatasetInstance.name)
      return json(
        {
          task_id: 'task-mock-1',
          status: 'pending',
          input_mode: 'dataset_instance',
          horizon_months: mockDatasetInstance.horizon_months,
          instance_name: mockDatasetInstance.name,
          ru_mode: true,
          mc_income: false,
        },
        202,
      )
    }
    const taskGet = /^\/api\/v1\/optimization\/tasks\/([^/]+)$/.exec(path)
    if (taskGet && method === 'GET') {
      const taskId = taskGet[1]
      taskStatusPolls += 1
      if (taskStatusPolls === 1) {
        return json(
          {
            task_id: taskId,
            status: 'pending',
            plan_id: null,
            error: null,
            input_mode: 'dataset_instance',
            horizon_months: mockDatasetInstance.horizon_months,
            instance_name: mockDatasetInstance.name,
            ru_mode: true,
            mc_income: false,
          },
          200,
        )
      }
      return json(
        {
          task_id: taskId,
          status: 'completed',
          plan_id: 'plan-mock-1',
          error: null,
          input_mode: 'dataset_instance',
          horizon_months: mockDatasetInstance.horizon_months,
          instance_name: mockDatasetInstance.name,
          ru_mode: true,
          mc_income: false,
        },
        200,
      )
    }
    const planGet = /^\/api\/v1\/optimization\/plans\/([^/]+)$/.exec(path)
    if (planGet && method === 'GET') {
      return json(
        {
          status: 'OPTIMAL',
          total_cost: 200,
          debts: mockOptimizationDebts,
          payments_matrix: [
            [140, 90],
            [20, 220],
          ],
          balances_matrix: [
            [1060, 970],
            [1780, 1560],
          ],
          savings_vector: [0, 530],
          horizon_months: mockDatasetInstance.horizon_months,
          baseline_comparison: {
            ...mockBaselineComparison,
            milp_total_cost: 200,
            savings_vs_avalanche_abs: -90,
            savings_vs_avalanche_pct: -81.8,
            savings_vs_snowball_abs: -85,
            savings_vs_snowball_pct: -73.9,
          },
          input_mode: 'dataset_instance',
          instance_name: mockDatasetInstance.name,
          assumptions: [],
          ru_mode: true,
          mc_income: false,
          mc_summary: null,
          mc_config: null,
          budget_policy: 'starts_next_month_with_carryover',
          budget_trace: [
            {
              month: 1,
              income_in: 0,
              available_budget: 0,
              planned_payment: 160,
              paid_total: 160,
              reserve_end: 0,
              carry_out: 0,
            },
            {
              month: 2,
              income_in: 900,
              available_budget: 900,
              planned_payment: 310,
              paid_total: 310,
              reserve_end: 530,
              carry_out: 530,
            },
          ],
        },
        200,
      )
    }

    return new Response(`unexpected fetch: ${method} ${path}`, { status: 500 })
  }

  globalThis.fetch = mockFetch as unknown as typeof fetch

  return () => {
    globalThis.fetch = original
  }
}

describe('app-api-flow (mocked fetch)', () => {
  let restoreFetch: () => void

  beforeEach(() => {
    localStorage.clear()
    clearStoredToken()
    restoreFetch = installFetchMock()
  })

  afterEach(() => {
    restoreFetch()
  })

  test('login, create debt, dataset sync optimize, async poll + plan (client)', async () => {
    render(
      <MemoryRouter initialEntries={['/debts']}>
        <AppRoutes />
      </MemoryRouter>,
    )

    const email = document.querySelector('input[type="email"]') as HTMLInputElement
    const password = document.querySelector('input[type="password"]') as HTMLInputElement
    fireEvent.change(email, { target: { value: 'u@example.dev' } })
    fireEvent.change(password, { target: { value: 'secret' } })
    fireEvent.click(screen.getByRole('button', { name: /войти/i }))

    await waitFor(() => {
      screen.getByRole('heading', { name: /^долги$/i })
    })

    fireEvent.change(screen.getByPlaceholderText('Название'), {
      target: { value: 'smoke-loan' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^добавить$/i }))

    await waitFor(() => {
      expect(screen.getByText('smoke-loan')).toBeTruthy()
    })

    fireEvent.click(screen.getByRole('link', { name: /оптимизация/i }))

    await waitFor(() => {
      screen.getByRole('heading', { name: /оптимизационный расчет/i })
    })

    expect(screen.getByText(mockDatasetInstance.name)).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: /синхронный расчет/i }))

    await waitFor(() => {
      expect(screen.getByText('OPTIMAL')).toBeTruthy()
    })

    fireEvent.click(screen.getByRole('button', { name: /запустить в фоне/i }))

    await waitFor(
      () => {
        expect(screen.getByText(/стоимость плана/i)).toBeTruthy()
      },
      { timeout: 5000 },
    )

    fireEvent.click(screen.getByRole('tab', { name: /аналитика/i }))

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /график погашения долгов/i })).toBeTruthy()
      expect(screen.getByRole('heading', { name: /распределение платежей/i })).toBeTruthy()
      expect(screen.getByRole('button', { name: /синхронный расчет/i })).toBeTruthy()
      expect(screen.getByRole('button', { name: /фоновый план/i })).toBeTruthy()
    })

    const task = await createOptimizationTask({
      input_mode: 'dataset_instance',
      instance_name: mockDatasetInstance.name,
      horizon_months: mockDatasetInstance.horizon_months,
      ru_mode: true,
      mc_income: false,
    })
    expect(task.task_id).toBe('task-mock-1')

    let planId: string | null = null
    for (let i = 0; i < 10; i += 1) {
      const st = await getOptimizationTaskStatus(task.task_id)
      if (st.status === 'completed') {
        planId = st.plan_id ?? null
        break
      }
      await new Promise((r) => setTimeout(r, 0))
    }
    expect(planId).toBe('plan-mock-1')

    const plan = await getOptimizationPlan(planId!)
    expect(plan.total_cost).toBe(200)
    expect(plan.payments_matrix).toEqual([
      [140, 90],
      [20, 220],
    ])
    expect(plan.input_mode).toBe('dataset_instance')
    expect(plan.instance_name).toBe(mockDatasetInstance.name)
  }, 15000)

  test('stale token on protected workspace redirects back to login after backend 401', async () => {
    setStoredToken('expired-token')

    const original = globalThis.fetch
    globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = requestUrl(input)
      const path = pathnameOf(url)
      const method = (init?.method ?? 'GET').toUpperCase()

      if (path === '/api/v1/debts/loan-types' && method === 'GET') {
        return new Response(
          JSON.stringify({ supported_values: ['car_loan', 'house_loan', 'credit_card', 'bank_loan'] }),
          {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          },
        )
      }

      if (
        (path === '/api/v1/optimization/instances' || path === '/api/v1/optimization/mc-config/defaults') &&
        method === 'GET'
      ) {
        return new Response(JSON.stringify({ detail: 'Not authenticated' }), {
          status: 401,
          headers: { 'Content-Type': 'application/json' },
        })
      }

      return new Response(`unexpected fetch: ${method} ${path}`, { status: 500 })
    }) as typeof fetch

    render(
      <MemoryRouter initialEntries={['/optimization']}>
        <AppRoutes />
      </MemoryRouter>,
    )

    await waitFor(() => {
      screen.getByRole('heading', { name: /вход/i })
    })

    expect(screen.queryByRole('heading', { name: /оптимизационный расчет/i })).toBeNull()
    expect(localStorage.getItem('rpml_access_token')).toBeNull()

    globalThis.fetch = original
  })

  test('legacy dashboard route forwards to unified optimization workspace', async () => {
    setStoredToken('mock-jwt')

    const original = globalThis.fetch

    globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = requestUrl(input)
      const path = pathnameOf(url)
      const method = (init?.method ?? 'GET').toUpperCase()
      const json = (body: unknown, status: number) =>
        new Response(JSON.stringify(body), {
          status,
          headers: { 'Content-Type': 'application/json' },
        })

      if (path === '/api/v1/debts/loan-types' && method === 'GET') {
        return json({ supported_values: ['car_loan', 'house_loan', 'credit_card', 'bank_loan'] }, 200)
      }

      if (path === '/api/v1/optimization/instances' && method === 'GET') {
        return json({ total: 1, items: [mockDatasetInstance] }, 200)
      }

      if (path === '/api/v1/optimization/mc-config/defaults' && method === 'GET') {
        return json(
          {
            n_scenarios: 16,
            seed: 42,
            rho: 0.55,
            sigma: 0.15,
            shock_prob: 0.04,
            shock_severity_mean: 0.3,
            shock_severity_std: 0.1,
            min_income_floor: 1,
          },
          200,
        )
      }

      return new Response(`unexpected fetch: ${method} ${path}`, { status: 500 })
    }) as typeof fetch

    render(
      <MemoryRouter initialEntries={['/dashboard']}>
        <AppRoutes />
      </MemoryRouter>,
    )

    await waitFor(() => {
      screen.getByRole('heading', { name: /оптимизационный расчет/i })
    })

    expect(screen.getByText(mockDatasetInstance.name)).toBeTruthy()

    globalThis.fetch = original
  })
})
