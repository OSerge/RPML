import { startTransition, useDeferredValue, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { CircleHelp } from 'lucide-react'

import { PaymentAnalyticsPanel } from '@/components/PaymentAnalytics'
import {
  createOptimizationTask,
  getOptimizationInstanceCatalog,
  getOptimizationMonteCarloDefaults,
  getOptimizationPlan,
  getOptimizationTaskStatus,
  runOptimizationSync,
  type CreateOptimizationTaskResponse,
  type DatasetInstanceSummaryResponse,
  type OptimizationMonteCarloConfig,
  type OptimizationPlanResponse,
  type OptimizationRunRequest,
  type OptimizationRunResponse,
  type OptimizationTaskStatusResponse,
} from '@/lib/api-client'
import { buildOptimizationAnalyticsView } from '@/lib/optimization-analytics'
import { cn } from '@/lib/utils'

type WorkspaceTab = 'run' | 'analytics' | 'mc'
type LoanCountFilter = 'all' | 4 | 8 | 12
type ResultSource = 'sync' | 'background'

const LOAN_FILTERS: LoanCountFilter[] = ['all', 4, 8, 12]
const POLL_INTERVAL_MS = 2000

function formatCurrency(value: number | null | undefined) {
  return new Intl.NumberFormat('ru-RU', {
    style: 'currency',
    currency: 'RUB',
    maximumFractionDigits: 0,
  }).format(value ?? 0)
}

function formatNumber(value: number | null | undefined, digits = 2) {
  if (value == null || Number.isNaN(value)) return '—'
  return new Intl.NumberFormat('ru-RU', {
    maximumFractionDigits: digits,
  }).format(value)
}

function formatPercent(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return '—'
  return `${(value * 100).toFixed(1)}%`
}

function formatInstancesCountLabel(count: number) {
  const mod10 = count % 10
  const mod100 = count % 100
  if (mod10 === 1 && mod100 !== 11) return `${count} инстанс доступен для расчета`
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return `${count} инстанса доступны для расчета`
  return `${count} инстансов доступны для расчета`
}

function formatAssumption(value: string) {
  switch (value) {
    case 'Loan terms and monthly budget are loaded from the bundled Rios-Solis dataset instance.':
      return 'Параметры займов и месячный бюджет загружены из выбранного инстанса Rios-Solis.'
    case 'Loan terms and monthly budget are taken from persisted debts and scenario profile.':
      return 'Параметры займов и месячный бюджет взяты из сохраненных долгов и профиля сценария.'
    default:
      return value
  }
}

function formatBudgetPolicy(value: string | null | undefined) {
  switch (value) {
    case 'starts_next_month_with_carryover':
      return 'бюджет начинается со следующего месяца, остаток переносится дальше'
    default:
      return value ?? '—'
  }
}

function formatResultSourceLabel(value: ResultSource | null) {
  switch (value) {
    case 'background':
      return 'фоновый расчет'
    case 'sync':
      return 'синхронный расчет'
    default:
      return '—'
  }
}

function readNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function parseWorkspaceTab(value: string | null): WorkspaceTab {
  return value === 'analytics' || value === 'mc' ? value : 'run'
}

function parseResultSource(value: string | null): ResultSource | null {
  return value === 'sync' || value === 'background' ? value : null
}

function buildOptimizationRequest(
  instance: DatasetInstanceSummaryResponse,
  ruMode: boolean,
  mcIncome: boolean,
  mcConfig: OptimizationMonteCarloConfig | null,
): OptimizationRunRequest {
  return {
    input_mode: 'dataset_instance',
    instance_name: instance.name,
    horizon_months: instance.horizon_months,
    ru_mode: ruMode,
    mc_income: mcIncome,
    mc_config: mcIncome ? mcConfig : null,
  }
}

export function OptimizationPage() {
  const [searchParams, setSearchParams] = useSearchParams()

  const [instances, setInstances] = useState<DatasetInstanceSummaryResponse[]>([])
  const [search, setSearch] = useState('')
  const [loanFilter, setLoanFilter] = useState<LoanCountFilter>('all')
  const deferredSearch = useDeferredValue(search.trim().toLowerCase())

  const [catalogLoading, setCatalogLoading] = useState(true)
  const [catalogError, setCatalogError] = useState<string | null>(null)

  const [ruMode, setRuMode] = useState(true)
  const [mcIncome, setMcIncome] = useState(false)
  const [mcConfig, setMcConfig] = useState<OptimizationMonteCarloConfig | null>(null)

  const [runLoading, setRunLoading] = useState(false)
  const [taskCreating, setTaskCreating] = useState(false)
  const [pageError, setPageError] = useState<string | null>(null)
  const [syncResult, setSyncResult] = useState<OptimizationRunResponse | null>(null)
  const [taskStatus, setTaskStatus] = useState<OptimizationTaskStatusResponse | CreateOptimizationTaskResponse | null>(null)
  const [taskPlan, setTaskPlan] = useState<OptimizationPlanResponse | null>(null)

  const activeTab = parseWorkspaceTab(searchParams.get('tab'))
  const requestedInstanceName = searchParams.get('instance')
  const requestedResultSource = parseResultSource(searchParams.get('result'))

  function patchSearchParams(
    patch: Partial<Record<'tab' | 'instance' | 'result', string | null>>,
    replace = false,
  ) {
    const next = new URLSearchParams(searchParams)
    for (const [key, value] of Object.entries(patch)) {
      if (value) {
        next.set(key, value)
      } else {
        next.delete(key)
      }
    }
    setSearchParams(next, { replace })
  }

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        setCatalogLoading(true)
        setCatalogError(null)
        const [catalog, defaults] = await Promise.all([
          getOptimizationInstanceCatalog(),
          getOptimizationMonteCarloDefaults(),
        ])
        if (cancelled) return
        setInstances(catalog.items ?? [])
        setMcConfig(defaults)
      } catch (error) {
        if (!cancelled) {
          setCatalogError(error instanceof Error ? error.message : 'Не удалось загрузить каталог инстансов')
        }
      } finally {
        if (!cancelled) {
          setCatalogLoading(false)
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const filteredInstances = useMemo(() => {
    return instances.filter((item) => {
      if (loanFilter !== 'all' && item.loans_count !== loanFilter) return false
      if (!deferredSearch) return true
      return item.name.toLowerCase().includes(deferredSearch)
    })
  }, [deferredSearch, instances, loanFilter])

  const selectedInstance = useMemo(() => {
    const direct = instances.find((item) => item.name === requestedInstanceName)
    if (direct) return direct
    return instances[0] ?? null
  }, [instances, requestedInstanceName])

  useEffect(() => {
    if (catalogLoading || instances.length === 0) return
    const hasRequestedInstance = requestedInstanceName
      ? instances.some((item) => item.name === requestedInstanceName)
      : false
    if (!hasRequestedInstance) {
      patchSearchParams(
        {
          tab: activeTab,
          instance: instances[0]?.name ?? null,
          result: requestedResultSource,
        },
        true,
      )
    }
  }, [activeTab, catalogLoading, instances, requestedInstanceName, requestedResultSource])

  useEffect(() => {
    if (!taskStatus || taskStatus.status !== 'pending') return
    let cancelled = false
    const timer = window.setTimeout(async () => {
      try {
        const nextStatus = await getOptimizationTaskStatus(taskStatus.task_id)
        if (cancelled) return
        setTaskStatus(nextStatus)
      } catch (error) {
        if (!cancelled) {
          setPageError(error instanceof Error ? error.message : 'Не удалось обновить статус фоновой задачи')
        }
      }
    }, POLL_INTERVAL_MS)

    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [taskStatus])

  const completedPlanId =
    taskStatus && taskStatus.status === 'completed' && 'plan_id' in taskStatus ? taskStatus.plan_id ?? null : null

  useEffect(() => {
    if (!completedPlanId) return
    let cancelled = false
    ;(async () => {
      try {
        const plan = await getOptimizationPlan(completedPlanId)
        if (!cancelled) {
          setTaskPlan(plan)
        }
      } catch (error) {
        if (!cancelled) {
          setPageError(error instanceof Error ? error.message : 'Не удалось загрузить готовый план')
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [completedPlanId])

  const activeResultSource: ResultSource | null = useMemo(() => {
    if (requestedResultSource === 'background' && taskPlan) return 'background'
    if (requestedResultSource === 'sync' && syncResult) return 'sync'
    if (taskPlan) return 'background'
    if (syncResult) return 'sync'
    return null
  }, [requestedResultSource, syncResult, taskPlan])

  useEffect(() => {
    const current = parseResultSource(searchParams.get('result'))
    if (current === activeResultSource) return
    patchSearchParams({ result: activeResultSource }, true)
  }, [activeResultSource, searchParams])

  const activeResult = activeResultSource === 'background' ? taskPlan : syncResult
  const analyticsView = useMemo(
    () => (activeResult ? buildOptimizationAnalyticsView(activeResult) : null),
    [activeResult],
  )

  const activeBaseline =
    activeResult?.baseline_comparison && typeof activeResult.baseline_comparison === 'object'
      ? (activeResult.baseline_comparison as Record<string, unknown>)
      : null

  const mcSummary = (syncResult?.mc_summary as Record<string, number | null> | null | undefined) ?? null
  const planMcSummary = (taskPlan?.mc_summary as Record<string, number | null> | null | undefined) ?? null
  const activeMcSummary =
    activeResultSource === 'background'
      ? planMcSummary
      : activeResultSource === 'sync'
        ? mcSummary
        : null

  const taskError = taskStatus && 'error' in taskStatus ? taskStatus.error : null

  async function onRunSync() {
    if (!selectedInstance) return
    try {
      setRunLoading(true)
      setPageError(null)
      const payload = buildOptimizationRequest(selectedInstance, ruMode, mcIncome, mcConfig)
      const result = await runOptimizationSync(payload)
      setSyncResult(result)
      patchSearchParams({ result: 'sync' })
    } catch (error) {
      setSyncResult(null)
      setPageError(error instanceof Error ? error.message : 'Ошибка синхронного расчета')
    } finally {
      setRunLoading(false)
    }
  }

  async function onRunBackground() {
    if (!selectedInstance) return
    try {
      setTaskCreating(true)
      setPageError(null)
      setTaskPlan(null)
      const task = await createOptimizationTask(
        buildOptimizationRequest(selectedInstance, ruMode, mcIncome, mcConfig),
      )
      setTaskStatus(task)
      patchSearchParams({ result: 'background' })
    } catch (error) {
      setTaskStatus(null)
      setTaskPlan(null)
      setPageError(error instanceof Error ? error.message : 'Не удалось поставить расчет в очередь')
    } finally {
      setTaskCreating(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-3xl space-y-2">
          <div>
            <h2 className="text-2xl font-semibold tracking-tight">Оптимизационный расчет</h2>
          </div>
        </div>
      </div>

      {pageError ? (
        <p className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {pageError}
        </p>
      ) : null}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,390px)_minmax(0,1fr)]">
        <aside className="rounded-2xl border border-border bg-card">
            <div className="border-b border-border px-4 py-4">
              <p className="text-sm font-medium">Каталог инстансов</p>
              <p className="mt-1 text-xs text-muted-foreground">
                {catalogLoading ? 'Загружаю каталог…' : formatInstancesCountLabel(instances.length)}
              </p>
            </div>

          <div className="space-y-4 px-4 py-4">
            <label className="block space-y-1">
              <span className="text-xs text-muted-foreground">Поиск по имени</span>
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Например, Deudas_4_..."
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              />
            </label>

            <div className="flex flex-wrap gap-2">
              {LOAN_FILTERS.map((value) => (
                <button
                  key={String(value)}
                  type="button"
                  onClick={() => setLoanFilter(value)}
                  className={cn(
                    'rounded-full border px-3 py-1 text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2',
                    loanFilter === value
                      ? 'border-primary bg-primary text-primary-foreground'
                      : 'border-border text-muted-foreground hover:text-foreground',
                  )}
                >
                  {value === 'all' ? 'Все' : `${value} займа`}
                </button>
              ))}
            </div>

            {catalogError ? (
              <p className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                {catalogError}
              </p>
            ) : null}

            <div className="max-h-[720px] overflow-auto pr-1 [content-visibility:auto]">
              <div className="space-y-2">
                {filteredInstances.map((item) => (
                  <button
                    key={item.name}
                    type="button"
                    onClick={() => {
                      startTransition(() => {
                        patchSearchParams({ instance: item.name })
                        setPageError(null)
                      })
                    }}
                    className={cn(
                      'w-full rounded-xl border px-3 py-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2',
                      selectedInstance?.name === item.name
                        ? 'border-primary bg-primary/5'
                        : 'border-border hover:border-primary/40 hover:bg-muted/30',
                    )}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium">{item.name}</p>
                        <p className="mt-1 text-xs text-muted-foreground">
                          {item.loans_count} долгов • {item.horizon_months} мес.
                        </p>
                      </div>
                      <span className="rounded-full bg-muted px-2 py-1 text-[11px] text-muted-foreground">
                        {item.n_credit_cards} карт / {item.n_bank_loans} банковских
                      </span>
                    </div>
                  </button>
                ))}
                {!catalogLoading && filteredInstances.length === 0 ? (
                  <p className="rounded-xl border border-dashed border-border px-3 py-6 text-center text-sm text-muted-foreground">
                    По текущему фильтру ничего не найдено.
                  </p>
                ) : null}
              </div>
            </div>
          </div>
        </aside>

        <div className="space-y-6">
          <section className="rounded-2xl border border-border bg-card">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-4">
              <div>
                <p className="text-sm font-medium">Рабочая область</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {selectedInstance
                    ? `${selectedInstance.name} · ${selectedInstance.loans_count} долгов · ${selectedInstance.horizon_months} мес.`
                    : 'Выбери инстанс из каталога слева'}
                </p>
              </div>

              <div
                role="tablist"
                aria-label="Разделы рабочей области"
                className="flex flex-wrap gap-2"
              >
                <TabButton
                  active={activeTab === 'run'}
                  tabId="optimization-tab-run"
                  panelId="optimization-panel-run"
                  onClick={() => patchSearchParams({ tab: 'run' })}
                >
                  Запуск
                </TabButton>
                <TabButton
                  active={activeTab === 'analytics'}
                  tabId="optimization-tab-analytics"
                  panelId="optimization-panel-analytics"
                  onClick={() => patchSearchParams({ tab: 'analytics' })}
                >
                  Аналитика
                </TabButton>
                <TabButton
                  active={activeTab === 'mc'}
                  tabId="optimization-tab-mc"
                  panelId="optimization-panel-mc"
                  onClick={() => patchSearchParams({ tab: 'mc' })}
                >
                  Монте-Карло
                </TabButton>
              </div>
            </div>

            {activeTab === 'run' ? (
              <div
                id="optimization-panel-run"
                role="tabpanel"
                aria-labelledby="optimization-tab-run"
                className="space-y-6 px-4 py-4"
              >
                <div className="grid gap-3 md:grid-cols-3">
                  <StatCard
                    label="Источник данных"
                    value={selectedInstance ? 'Встроенный набор' : '—'}
                    hint="Расчет выполняется на сервере по выбранному `.dat`."
                  />
                  <StatCard
                    label="Горизонт"
                    value={selectedInstance ? `${selectedInstance.horizon_months} мес.` : '—'}
                    hint="Фиксируется выбранным `.dat`."
                  />
                  <StatCard
                    label="Состав долгов"
                    value={
                      selectedInstance
                        ? `${selectedInstance.n_cars}/${selectedInstance.n_houses}/${selectedInstance.n_credit_cards}/${selectedInstance.n_bank_loans}`
                        : '—'
                    }
                    hint="авто / жилье / карты / банковские"
                  />
                </div>

                <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(280px,360px)]">
                  <div className="space-y-4">
                    <div className="grid gap-3 sm:grid-cols-2">
                      <ToggleField
                        label="RU-режим"
                        description="Применять правила досрочного погашения для российского сценария."
                        hint="В этом режиме досрочное погашение разрешается моделью даже для займов, где в исходном профиле оно было заблокировано."
                        checked={ruMode}
                        onChange={setRuMode}
                      />
                      <ToggleField
                        label="Режим Монте-Карло"
                        description="Считать стохастическую сводку по доходу поверх базового плана."
                        checked={mcIncome}
                        onChange={setMcIncome}
                      />
                    </div>

                    <div className="rounded-xl border border-border/70 bg-muted/20 p-4">
                      <p className="text-sm font-medium">Параметры расчета</p>
                      <ul className="mt-3 space-y-2 text-sm text-muted-foreground">
                        <li>Инстанс: {selectedInstance?.name ?? '—'}</li>
                        <li>Горизонт: {selectedInstance?.horizon_months ?? '—'} мес.</li>
                        <li>RU-режим: {ruMode ? 'включен' : 'выключен'}</li>
                        <li>Монте-Карло: {mcIncome ? 'включен' : 'выключен'}</li>
                      </ul>
                    </div>
                  </div>

                  <div className="rounded-xl border border-border/70 bg-background p-4">
                    <p className="text-sm font-medium">Режим запуска</p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      Синхронный расчет подходит для быстрой проверки. Фоновый расчет ставит задачу в очередь
                      и сохраняет план для повторного открытия.
                    </p>
                    <div className="mt-4 space-y-3">
                      <button
                        type="button"
                        onClick={onRunSync}
                        disabled={!selectedInstance || runLoading}
                        className={cn(
                          'w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2',
                          (!selectedInstance || runLoading) && 'opacity-60',
                        )}
                      >
                        {runLoading ? 'Считаю…' : 'Синхронный расчет'}
                      </button>
                      <button
                        type="button"
                        onClick={onRunBackground}
                        disabled={!selectedInstance || taskCreating}
                        className={cn(
                          'w-full rounded-md border border-border px-4 py-2 text-sm font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2',
                          (!selectedInstance || taskCreating) && 'opacity-60',
                        )}
                      >
                        {taskCreating ? 'Ставлю в очередь…' : 'Запустить в фоне'}
                      </button>
                    </div>
                    <div className="mt-4 rounded-xl border border-dashed border-border bg-muted/20 p-3">
                      <p className="text-sm font-medium">После расчета</p>
                      <p className="mt-1 text-xs text-muted-foreground">
                        Помесячный план, структура затрат и сравнение стратегий доступны во вкладке
                        «Аналитика».
                      </p>
                      <button
                        type="button"
                        onClick={() => patchSearchParams({ tab: 'analytics' })}
                        className="mt-3 rounded-md border border-border px-3 py-2 text-sm"
                      >
                        Открыть аналитику
                      </button>
                    </div>
                  </div>
                </div>

                <div className="grid gap-4 xl:grid-cols-2">
                  <section className="rounded-2xl border border-border/70 bg-background p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-medium">Последний синхронный расчет</p>
                        <p className="mt-1 text-xs text-muted-foreground">
                          Быстрая проверка качества плана без очереди.
                        </p>
                      </div>
                      {syncResult ? (
                        <button
                          type="button"
                          onClick={() => patchSearchParams({ tab: 'analytics', result: 'sync' })}
                          className="rounded-md border border-border px-3 py-2 text-xs"
                        >
                          Смотреть графики
                        </button>
                      ) : null}
                    </div>

                    {!syncResult ? (
                      <p className="mt-4 text-sm text-muted-foreground">
                        После синхронного расчета здесь появится краткая сводка по стоимости и сравнению со стратегиями.
                      </p>
                    ) : (
                      <div className="mt-4 grid gap-3 sm:grid-cols-2">
                        <StatCard label="Статус" value={syncResult.status} />
                        <StatCard label="Общая стоимость" value={formatCurrency(syncResult.total_cost)} />
                        <StatCard
                          label="Сравнение с Avalanche"
                          value={formatCurrency(readNumber(activeResultSource === 'sync' ? activeBaseline?.savings_vs_avalanche_abs : syncResult.baseline_comparison?.savings_vs_avalanche_abs))}
                          hint={formatPercent(
                            (readNumber(syncResult.baseline_comparison?.savings_vs_avalanche_pct) ?? 0) / 100,
                          )}
                        />
                        <StatCard
                          label="Сравнение со Snowball"
                          value={formatCurrency(readNumber(syncResult.baseline_comparison?.savings_vs_snowball_abs))}
                          hint={formatPercent(
                            (readNumber(syncResult.baseline_comparison?.savings_vs_snowball_pct) ?? 0) / 100,
                          )}
                        />
                      </div>
                    )}
                  </section>

                  <section className="rounded-2xl border border-border/70 bg-background p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-medium">Фоновая задача</p>
                        <p className="mt-1 text-xs text-muted-foreground">
                          Очередь, сохраненный результат и повторное открытие расчета.
                        </p>
                      </div>
                      {taskPlan ? (
                        <button
                          type="button"
                          onClick={() => patchSearchParams({ tab: 'analytics', result: 'background' })}
                          className="rounded-md border border-border px-3 py-2 text-xs"
                        >
                          Смотреть графики
                        </button>
                      ) : null}
                    </div>

                    {!taskStatus ? (
                      <p className="mt-4 text-sm text-muted-foreground">
                        После фонового запуска здесь будут текущий статус, идентификатор задачи и сохраненный план.
                      </p>
                    ) : (
                      <div className="mt-4 space-y-4">
                        <div className="grid gap-3 sm:grid-cols-2">
                          <StatCard label="Статус задачи" value={taskStatus.status} />
                          <StatCard label="ID задачи" value={taskStatus.task_id} mono />
                          <StatCard label="Режим входных данных" value={taskStatus.input_mode} />
                          <StatCard label="Горизонт" value={`${taskStatus.horizon_months} мес.`} />
                        </div>

                        {taskStatus.instance_name ? (
                          <p className="text-xs text-muted-foreground">Инстанс: {taskStatus.instance_name}</p>
                        ) : null}

                        {taskError ? (
                          <p className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                            {taskError}
                          </p>
                        ) : null}

                        {taskPlan ? (
                          <div className="grid gap-3 sm:grid-cols-2">
                            <StatCard label="Статус плана" value={taskPlan.status} />
                            <StatCard label="Стоимость плана" value={formatCurrency(taskPlan.total_cost)} />
                          </div>
                        ) : null}
                      </div>
                    )}
                  </section>
                </div>
              </div>
            ) : null}

            {activeTab === 'analytics' ? (
              <div
                id="optimization-panel-analytics"
                role="tabpanel"
                aria-labelledby="optimization-tab-analytics"
                className="space-y-6 px-4 py-4"
              >
                {!activeResult || !analyticsView ? (
                  <div className="rounded-2xl border border-dashed border-border bg-muted/10 p-8 text-center">
                    <p className="text-base font-medium">Аналитика появится после первого расчета</p>
                    <p className="mt-2 text-sm text-muted-foreground">
                      Сначала запусти синхронный или фоновый расчет на вкладке «Запуск», затем здесь откроются
                      графики по месяцам, сравнение стратегий и разбор бюджета.
                    </p>
                    <button
                      type="button"
                      onClick={() => patchSearchParams({ tab: 'run' })}
                      className="mt-4 rounded-md border border-border px-3 py-2 text-sm"
                    >
                      Перейти к запуску
                    </button>
                  </div>
                ) : (
                  <>
                    <div className="flex flex-wrap items-start justify-between gap-4">
                      <div>
                        <p className="text-sm font-medium">Разбор результата</p>
                        <p className="mt-1 text-xs text-muted-foreground">
                          {activeResult.instance_name
                            ? `${activeResult.instance_name} · ${activeResult.horizon_months} мес.`
                            : `${activeResult.horizon_months} мес.`}
                        </p>
                      </div>

                      {syncResult && taskPlan ? (
                        <div className="flex flex-wrap gap-2">
                          <ResultSourceButton
                            active={activeResultSource === 'sync'}
                            onClick={() => patchSearchParams({ result: 'sync' })}
                          >
                            Синхронный расчет
                          </ResultSourceButton>
                          <ResultSourceButton
                            active={activeResultSource === 'background'}
                            onClick={() => patchSearchParams({ result: 'background' })}
                          >
                            Фоновый план
                          </ResultSourceButton>
                        </div>
                      ) : null}
                    </div>

                    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                      <StatCard label="Статус" value={activeResult.status} />
                      <StatCard label="Общая стоимость" value={formatCurrency(activeResult.total_cost)} />
                      <StatCard
                        label="Потрачено из бюджета"
                        value={formatCurrency(analyticsView.budgetMetrics.totalSpent)}
                        hint={
                          analyticsView.budgetMetrics.spentShare != null
                            ? `${formatPercent(analyticsView.budgetMetrics.spentShare)} доступного бюджета использовано`
                            : 'Доля использования бюджета появится после полной трассировки бюджета'
                        }
                      />
                      <StatCard
                        label="Резерв на конец"
                        value={formatCurrency(analyticsView.budgetMetrics.reserveEnd)}
                        hint={
                          analyticsView.budgetMetrics.totalAvailable != null
                            ? `Всего бюджета на горизонте: ${formatCurrency(analyticsView.budgetMetrics.totalAvailable)}`
                            : 'Показатель недоступен без полной трассировки бюджета'
                        }
                      />
                      <StatCard
                        label="Сравнение с Avalanche"
                        value={formatCurrency(readNumber(activeBaseline?.savings_vs_avalanche_abs))}
                        hint={formatPercent((readNumber(activeBaseline?.savings_vs_avalanche_pct) ?? 0) / 100)}
                      />
                      <StatCard
                        label="Сравнение со Snowball"
                        value={formatCurrency(readNumber(activeBaseline?.savings_vs_snowball_abs))}
                        hint={formatPercent((readNumber(activeBaseline?.savings_vs_snowball_pct) ?? 0) / 100)}
                      />
                    </div>

                    <div className="rounded-2xl border border-border/70 bg-muted/20 p-4">
                      <p className="text-sm font-medium">Исходные условия</p>
                      <ul className="mt-2 space-y-1 text-xs text-muted-foreground">
                        {(activeResult.assumptions ?? []).map((item) => (
                          <li key={item}>{formatAssumption(item)}</li>
                        ))}
                        {activeResult.budget_policy ? (
                          <li>Политика бюджета: {formatBudgetPolicy(activeResult.budget_policy)}</li>
                        ) : null}
                        <li>Источник результата: {formatResultSourceLabel(activeResultSource)}</li>
                      </ul>
                    </div>

                    {activeResult.mc_income ? <MonteCarloSummary summary={activeMcSummary} /> : null}

                    <PaymentAnalyticsPanel
                      debts={analyticsView.debts}
                      strategyResults={analyticsView.strategyResults}
                      monthlyIncome={analyticsView.monthlyIncome}
                      horizonMonths={analyticsView.horizonMonths}
                      baseline={analyticsView.baseline}
                    />
                  </>
                )}
              </div>
            ) : null}

            {activeTab === 'mc' ? (
              <div
                id="optimization-panel-mc"
                role="tabpanel"
                aria-labelledby="optimization-tab-mc"
                className="space-y-4 px-4 py-4"
              >
                <div className="rounded-xl border border-border/70 bg-muted/20 p-4">
                  <p className="text-sm font-medium">Тонкая настройка Monte Carlo</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Эти настройки влияют только на стохастическую сводку по доходу и применяются, когда
                    режим Монте-Карло включен на вкладке «Запуск».
                  </p>
                </div>

                {mcConfig ? (
                  <div className="grid gap-3 md:grid-cols-2">
                    <NumberField
                      label="Количество сценариев (n_scenarios)"
                      value={mcConfig.n_scenarios}
                      min={1}
                      step={1}
                      onChange={(value) => setMcConfig((prev) => (prev ? { ...prev, n_scenarios: value } : prev))}
                    />
                    <NumberField
                      label="Начальное зерно (seed)"
                      value={mcConfig.seed}
                      step={1}
                      onChange={(value) => setMcConfig((prev) => (prev ? { ...prev, seed: value } : prev))}
                    />
                    <NumberField
                      label="Автокорреляция (rho)"
                      value={mcConfig.rho}
                      step={0.01}
                      min={-0.999}
                      max={0.999}
                      onChange={(value) => setMcConfig((prev) => (prev ? { ...prev, rho: value } : prev))}
                    />
                    <NumberField
                      label="Волатильность (sigma)"
                      value={mcConfig.sigma}
                      step={0.01}
                      min={0}
                      onChange={(value) => setMcConfig((prev) => (prev ? { ...prev, sigma: value } : prev))}
                    />
                    <NumberField
                      label="Вероятность шока (shock_prob)"
                      value={mcConfig.shock_prob}
                      step={0.01}
                      min={0}
                      max={1}
                      onChange={(value) => setMcConfig((prev) => (prev ? { ...prev, shock_prob: value } : prev))}
                    />
                    <NumberField
                      label="Средняя сила шока (shock_severity_mean)"
                      value={mcConfig.shock_severity_mean}
                      step={0.01}
                      min={0}
                      onChange={(value) =>
                        setMcConfig((prev) => (prev ? { ...prev, shock_severity_mean: value } : prev))
                      }
                    />
                    <NumberField
                      label="Разброс силы шока (shock_severity_std)"
                      value={mcConfig.shock_severity_std}
                      step={0.01}
                      min={0}
                      onChange={(value) =>
                        setMcConfig((prev) => (prev ? { ...prev, shock_severity_std: value } : prev))
                      }
                    />
                    <NumberField
                      label="Нижняя граница дохода (min_income_floor)"
                      value={mcConfig.min_income_floor}
                      step={1}
                      min={0}
                      onChange={(value) => setMcConfig((prev) => (prev ? { ...prev, min_income_floor: value } : prev))}
                    />
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground">Загружаю конфигурацию Монте-Карло по умолчанию…</p>
                )}

                {activeMcSummary ? <MonteCarloSummary summary={activeMcSummary} /> : null}
              </div>
            ) : null}
          </section>
        </div>
      </div>
    </div>
  )
}

function TabButton({
  active,
  children,
  onClick,
  tabId,
  panelId,
}: {
  active: boolean
  children: string
  onClick: () => void
  tabId: string
  panelId: string
}) {
  return (
    <button
      id={tabId}
      type="button"
      role="tab"
      aria-selected={active}
      aria-controls={panelId}
      onClick={onClick}
      className={cn(
        'rounded-full px-3 py-1.5 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2',
        active ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground hover:text-foreground',
      )}
    >
      {children}
    </button>
  )
}

function ResultSourceButton({
  active,
  children,
  onClick,
}: {
  active: boolean
  children: string
  onClick: () => void
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        'rounded-full border px-3 py-1.5 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2',
        active
          ? 'border-primary bg-primary text-primary-foreground'
          : 'border-border bg-background text-muted-foreground hover:text-foreground',
      )}
    >
      {children}
    </button>
  )
}

function ToggleField({
  label,
  description,
  hint,
  checked,
  onChange,
}: {
  label: string
  description: string
  hint?: string
  checked: boolean
  onChange: (checked: boolean) => void
}) {
  return (
    <label className="flex items-start gap-3 rounded-xl border border-border/70 bg-background p-4">
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="mt-1 rounded border-input"
      />
      <span className="space-y-1">
        <span className="flex items-center gap-2 text-sm font-medium">
          <span>{label}</span>
          {hint ? (
            <span
              className="inline-flex h-5 w-5 items-center justify-center rounded-full border border-border text-muted-foreground"
              title={hint}
              aria-label={hint}
            >
              <CircleHelp className="h-3.5 w-3.5" />
            </span>
          ) : null}
        </span>
        <span className="block text-xs text-muted-foreground">{description}</span>
      </span>
    </label>
  )
}

function NumberField({
  label,
  value,
  onChange,
  min,
  max,
  step,
}: {
  label: string
  value: number
  onChange: (value: number) => void
  min?: number
  max?: number
  step?: number
}) {
  return (
    <label className="block space-y-1">
      <span className="text-xs text-muted-foreground">{label}</span>
      <input
        type="number"
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={(event) => onChange(Number(event.target.value))}
        className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
      />
    </label>
  )
}

function StatCard({
  label,
  value,
  hint,
  mono = false,
}: {
  label: string
  value: string
  hint?: string
  mono?: boolean
}) {
  return (
    <div className="rounded-xl border border-border/70 bg-background p-3">
      <p className="text-xs uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className={cn('mt-1 text-sm font-semibold', mono && 'break-all font-mono text-xs')}>{value}</p>
      {hint ? <p className="mt-1 text-xs text-muted-foreground">{hint}</p> : null}
    </div>
  )
}

function MonteCarloSummary({
  summary,
}: {
  summary: Record<string, number | null> | null
}) {
  if (!summary) return null
  return (
    <div className="rounded-xl border border-border/70 bg-background p-4">
      <p className="text-sm font-medium">Сводка Монте-Карло</p>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <StatCard label="Сценарии" value={formatNumber(summary.n_scenarios, 0)} />
        <StatCard label="Допустимые" value={formatNumber(summary.feasible_scenarios, 0)} />
        <StatCard label="Доля недопустимых" value={formatPercent(summary.infeasible_rate)} />
        <StatCard label="Средняя стоимость" value={formatCurrency(summary.mean_total_cost)} />
        <StatCard label="Медианная стоимость" value={formatCurrency(summary.median_total_cost)} />
        <StatCard label="P90 стоимости" value={formatCurrency(summary.p90_total_cost)} />
      </div>
    </div>
  )
}
