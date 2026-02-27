import { getSupabase } from '../lib/supabase'

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

export async function getDebts() {
  const res = await fetch(`${API_BASE}/debts`, { headers: await getAuthHeaders() })
  if (!res.ok) throw new Error('Failed to fetch debts')
  return res.json()
}

export async function createDebt(data: Record<string, unknown>) {
  const res = await fetch(`${API_BASE}/debts`, {
    method: 'POST',
    headers: await getAuthHeaders(),
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error('Failed to create debt')
  return res.json()
}

export async function runOptimization() {
  const res = await fetch(`${API_BASE}/optimize`, {
    method: 'POST',
    headers: await getAuthHeaders(),
  })
  if (!res.ok) throw new Error('Optimization failed')
  return res.json()
}

export async function getBudgetSummary() {
  const res = await fetch(`${API_BASE}/budget/summary`, { headers: await getAuthHeaders() })
  if (!res.ok) throw new Error('Failed to fetch budget')
  return res.json()
}

export async function getGoals() {
  const res = await fetch(`${API_BASE}/goals`, { headers: await getAuthHeaders() })
  if (!res.ok) throw new Error('Failed to fetch goals')
  return res.json()
}

export async function explainQuestion(question: string, planContext?: string): Promise<string> {
  const res = await fetch(`${API_BASE}/explain`, {
    method: 'POST',
    headers: await getAuthHeaders(),
    body: JSON.stringify({ question, plan_context: planContext }),
  })
  if (!res.ok) throw new Error('Explain failed')
  return res.text()
}

export async function getMe() {
  const res = await fetch(`${API_BASE}/auth/me`, { headers: await getAuthHeaders() })
  if (!res.ok) throw new Error('Not authenticated')
  return res.json()
}
