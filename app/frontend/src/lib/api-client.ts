import { clearStoredToken, getStoredToken } from './auth-storage'
import type { components } from '../contracts/generated/types'

const base = () => (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')

/** OpenAPI `ErrorResponse` (HTTPException и др.). */
export type ErrorResponse = components['schemas']['ErrorResponse']

type HttpValidationErrorBody = components['schemas']['HTTPValidationError']

export type ApiErrorJsonBody = ErrorResponse | HttpValidationErrorBody

/** Тело ошибки: JSON с `detail` или сырой текст (не JSON / HTML). */
export type ApiErrorBody = ApiErrorJsonBody | string | null

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly body: ApiErrorBody,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

export type LoginRequest = components['schemas']['UserLogin']
export type LoginResponse = components['schemas']['TokenResponse']

export type DebtRead = components['schemas']['DebtRead']
export type DebtCreate = components['schemas']['DebtCreate']
export type DebtUpdate = components['schemas']['DebtUpdate']
export type LoanType = components['schemas']['LoanType']
export type LoanTypeDirectory = components['schemas']['LoanTypeDirectory']

export type DashboardResponse = components['schemas']['DashboardResponse']

export type ScenarioProfileResponse = components['schemas']['ScenarioProfileResponse']
export type ScenarioProfileUpdateRequest = components['schemas']['ScenarioProfileUpdateRequest']
export type AvailableBudgetEstimateRequest = components['schemas']['AvailableBudgetEstimateRequest']
export type AvailableBudgetEstimateResponse = components['schemas']['AvailableBudgetEstimateResponse']

export type OptimizationRunRequest = components['schemas']['OptimizationRunRequest']
export type OptimizationRunResponse = components['schemas']['OptimizationRunResponse']
export type OptimizationInputMode = components['schemas']['OptimizationRunRequest']['input_mode']
export type OptimizationMonteCarloConfig = components['schemas']['OptimizationMonteCarloConfig']
export type DatasetInstanceCatalogResponse = components['schemas']['DatasetInstanceCatalogResponse']
export type DatasetInstanceSummaryResponse = components['schemas']['DatasetInstanceSummaryResponse']

export type CreateOptimizationTaskRequest = components['schemas']['CreateOptimizationTaskRequest']
export type CreateOptimizationTaskResponse = components['schemas']['CreateOptimizationTaskResponse']
export type OptimizationTaskStatusResponse = components['schemas']['OptimizationTaskStatusResponse']
export type OptimizationPlanResponse = components['schemas']['OptimizationPlanResponse']

export type DemoRunTopSavingsMetric = 'avalanche' | 'snowball'

export type DemoRunTopSavingsItem = {
  instance_name: string
  savings_pct: number
  savings_abs: number
  optimal_cost: number
  baseline_cost: number
  optimal_status?: string | null
}

export type DemoRunTopSavingsResponse = {
  run_id: string
  metric: DemoRunTopSavingsMetric
  checkpoint_path: string
  total_instances: number
  items: DemoRunTopSavingsItem[]
}

function parseJsonSafe(text: string): unknown {
  try {
    return JSON.parse(text) as unknown
  } catch {
    return text
  }
}

function toApiErrorBody(raw: unknown): ApiErrorBody {
  if (raw === null) return null
  if (typeof raw === 'string') return raw
  if (typeof raw === 'object' && raw !== null && 'detail' in raw) {
    return raw as ApiErrorJsonBody
  }
  return String(raw)
}

function parseErrorDetail(body: ApiErrorBody, fallback: string): string {
  if (body === null) return fallback
  if (typeof body === 'string') return body
  const d = body.detail
  if (d === undefined) return fallback
  if (typeof d === 'string') return d
  if (Array.isArray(d)) {
    return d
      .map((item) =>
        typeof item === 'object' && item !== null && 'msg' in item
          ? String((item as { msg: unknown }).msg)
          : JSON.stringify(item),
      )
      .join(', ')
  }
  if (typeof d === 'object' && d !== null) {
    const o = d as Record<string, unknown>
    if (typeof o.message === 'string') {
      const extra = o.solver_status != null ? ` (${String(o.solver_status)})` : ''
      return `${o.message}${extra}`
    }
    return JSON.stringify(d)
  }
  return fallback
}

export async function apiFetch<T>(
  path: string,
  init: RequestInit & { auth?: boolean } = {},
): Promise<T> {
  const { auth = true, headers: hdrs, ...rest } = init
  const headers = new Headers(hdrs)
  if (!headers.has('Content-Type') && rest.body !== undefined) {
    headers.set('Content-Type', 'application/json')
  }
  if (auth) {
    const t = getStoredToken()
    if (t) {
      headers.set('Authorization', `Bearer ${t}`)
    }
  }
  const res = await fetch(`${base()}${path}`, { ...rest, headers })
  const text = await res.text()
  const raw = text ? parseJsonSafe(text) : null
  if (res.status === 401 && auth) {
    clearStoredToken()
  }
  if (!res.ok) {
    const errBody = toApiErrorBody(raw)
    const msg = parseErrorDetail(errBody, res.statusText)
    throw new ApiError(msg, res.status, errBody)
  }
  return raw as T
}

export async function login(body: LoginRequest): Promise<LoginResponse> {
  return apiFetch<LoginResponse>('/api/v1/auth/login', {
    method: 'POST',
    body: JSON.stringify(body),
    auth: false,
  })
}

export async function listDebts(): Promise<DebtRead[]> {
  return apiFetch<DebtRead[]>('/api/v1/debts', { method: 'GET' })
}

export async function listLoanTypes(): Promise<LoanTypeDirectory> {
  return apiFetch<LoanTypeDirectory>('/api/v1/debts/loan-types', { method: 'GET' })
}

export async function getDebt(id: number): Promise<DebtRead> {
  return apiFetch<DebtRead>(`/api/v1/debts/${id}`, { method: 'GET' })
}

export async function deleteDebt(id: number): Promise<void> {
  await apiFetch<unknown>(`/api/v1/debts/${id}`, { method: 'DELETE' })
}

export async function createDebt(body: DebtCreate): Promise<DebtRead> {
  return apiFetch<DebtRead>('/api/v1/debts', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export async function patchDebt(id: number, body: DebtUpdate): Promise<DebtRead> {
  return apiFetch<DebtRead>(`/api/v1/debts/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

export async function getDashboard(): Promise<DashboardResponse> {
  return apiFetch<DashboardResponse>('/api/v1/dashboard', { method: 'GET' })
}

export async function getScenarioProfile(): Promise<ScenarioProfileResponse> {
  return apiFetch<ScenarioProfileResponse>('/api/v1/scenario/profile', { method: 'GET' })
}

export async function putScenarioProfile(
  body: ScenarioProfileUpdateRequest,
): Promise<ScenarioProfileResponse> {
  return apiFetch<ScenarioProfileResponse>('/api/v1/scenario/profile', {
    method: 'PUT',
    body: JSON.stringify(body),
  })
}

export async function estimateAvailableBudget(
  body: AvailableBudgetEstimateRequest,
): Promise<AvailableBudgetEstimateResponse> {
  return apiFetch<AvailableBudgetEstimateResponse>(
    '/api/v1/scenario/profile/estimate-available-budget',
    {
      method: 'POST',
      body: JSON.stringify(body),
    },
  )
}

export async function seedDemoScenario(): Promise<{ ok: boolean; scenario_code: string; debts_count: number }> {
  return apiFetch<{ ok: boolean; scenario_code: string; debts_count: number }>('/api/v1/demo/seed', {
    method: 'POST',
  })
}

export async function getDemoRunTopSavings(params: {
  runId: string
  metric?: DemoRunTopSavingsMetric
  limit?: number
}): Promise<DemoRunTopSavingsResponse> {
  const metric = params.metric ?? 'avalanche'
  const limit = params.limit ?? 10
  const query = new URLSearchParams({
    metric,
    limit: String(limit),
  })
  return apiFetch<DemoRunTopSavingsResponse>(
    `/api/v1/demo/runs/${encodeURIComponent(params.runId)}/top-savings?${query.toString()}`,
    { method: 'GET' },
  )
}

export async function runOptimizationSync(
  body: OptimizationRunRequest,
): Promise<OptimizationRunResponse> {
  return apiFetch<OptimizationRunResponse>('/api/v1/optimization/run', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export async function getOptimizationInstanceCatalog(): Promise<DatasetInstanceCatalogResponse> {
  return apiFetch<DatasetInstanceCatalogResponse>('/api/v1/optimization/instances', {
    method: 'GET',
  })
}

export async function getOptimizationMonteCarloDefaults(): Promise<OptimizationMonteCarloConfig> {
  return apiFetch<OptimizationMonteCarloConfig>('/api/v1/optimization/mc-config/defaults', {
    method: 'GET',
  })
}

export async function createOptimizationTask(
  body: CreateOptimizationTaskRequest,
): Promise<CreateOptimizationTaskResponse> {
  return apiFetch<CreateOptimizationTaskResponse>('/api/v1/optimization/tasks', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export async function getOptimizationTaskStatus(
  taskId: string,
): Promise<OptimizationTaskStatusResponse> {
  return apiFetch<OptimizationTaskStatusResponse>(
    `/api/v1/optimization/tasks/${encodeURIComponent(taskId)}`,
    { method: 'GET' },
  )
}

export async function getOptimizationPlan(
  planId: string,
): Promise<OptimizationPlanResponse> {
  return apiFetch<OptimizationPlanResponse>(
    `/api/v1/optimization/plans/${encodeURIComponent(planId)}`,
    { method: 'GET' },
  )
}
