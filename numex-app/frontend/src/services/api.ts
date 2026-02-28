import { getSupabase } from '../lib/supabase'
import type { Debt, DebtCreate, OptimizationPlan, OptimizationRequest } from '../types/debt'

const API_BASE = '/api/v1'

async function getAccessToken(): Promise<string | null> {
  const client = getSupabase()
  if (!client) return null
  const { data } = await client.auth.getSession()
  return data.session?.access_token ?? null
}

async function getAuthHeaders(): Promise<HeadersInit> {
  const token = await getAccessToken()
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  }
}

export async function getDebts(): Promise<Debt[]> {
  const res = await fetch(`${API_BASE}/debts`, { headers: await getAuthHeaders() })
  if (!res.ok) throw new Error('Failed to fetch debts')
  return res.json()
}

export async function getDebt(id: string): Promise<Debt> {
  const res = await fetch(`${API_BASE}/debts/${id}`, { headers: await getAuthHeaders() })
  if (!res.ok) throw new Error('Failed to fetch debt')
  return res.json()
}

export async function createDebt(data: DebtCreate): Promise<Debt> {
  const res = await fetch(`${API_BASE}/debts`, {
    method: 'POST',
    headers: await getAuthHeaders(),
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error('Failed to create debt')
  return res.json()
}

export async function updateDebt(id: string, data: Partial<Debt>): Promise<Debt> {
  const res = await fetch(`${API_BASE}/debts/${id}`, {
    method: 'PATCH',
    headers: await getAuthHeaders(),
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error('Failed to update debt')
  return res.json()
}

export async function deleteDebt(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/debts/${id}`, {
    method: 'DELETE',
    headers: await getAuthHeaders(),
  })
  if (!res.ok) throw new Error('Failed to delete debt')
}

export async function runOptimization(params?: OptimizationRequest): Promise<OptimizationPlan> {
  const res = await fetch(`${API_BASE}/optimize`, {
    method: 'POST',
    headers: await getAuthHeaders(),
    body: params ? JSON.stringify(params) : undefined,
  })
  if (!res.ok) throw new Error('Optimization failed')
  return res.json()
}

export async function getOptimizationPlan(id: string): Promise<OptimizationPlan> {
  const res = await fetch(`${API_BASE}/optimize/${id}`, { headers: await getAuthHeaders() })
  if (!res.ok) throw new Error('Failed to fetch plan')
  return res.json()
}

export interface BudgetSummary {
  total_income: number
  total_expense: number
  balance: number
}

export async function getBudgetSummary(): Promise<BudgetSummary> {
  const res = await fetch(`${API_BASE}/budget/summary`, { headers: await getAuthHeaders() })
  if (!res.ok) throw new Error('Failed to fetch budget')
  return res.json()
}

export interface Goal {
  id: string
  name: string
  target_amount: number
  target_date: string
}

export async function getGoals(): Promise<Goal[]> {
  const res = await fetch(`${API_BASE}/goals`, { headers: await getAuthHeaders() })
  if (!res.ok) throw new Error('Failed to fetch goals')
  return res.json()
}

export async function explainQuestion(
  question: string,
  planContext?: string,
  includeUserData: boolean = true
): Promise<string> {
  const res = await fetch(`${API_BASE}/explain`, {
    method: 'POST',
    headers: await getAuthHeaders(),
    body: JSON.stringify({
      question,
      plan_context: planContext,
      include_user_data: includeUserData,
    }),
  })
  if (!res.ok) throw new Error('Explain failed')
  return res.text()
}

export interface UserMe {
  id: string
  email: string
}

export async function getMe(): Promise<UserMe> {
  const res = await fetch(`${API_BASE}/auth/me`, { headers: await getAuthHeaders() })
  if (!res.ok) throw new Error('Not authenticated')
  return res.json()
}
