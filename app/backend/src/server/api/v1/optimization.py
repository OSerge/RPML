import dataclasses
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from starlette.status import HTTP_422_UNPROCESSABLE_CONTENT
from pydantic import BaseModel, Field, model_validator
from rpml.income_monte_carlo import IncomeMCConfig
from sqlalchemy.orm import Session

from server.api.deps import get_current_user
from server.application.use_cases.run_optimization_async import (
    execute_create_async_optimization_task,
    execute_get_optimization_task_status,
)
from server.application.use_cases.run_optimization_sync import (
    DATASET_INPUT_MODE,
    MVP_ASSUMPTIONS,
    MVP_INPUT_MODE,
    SCENARIO_INPUT_MODE,
    OptimizationSolverFailed,
    execute_run_optimization_sync,
)
from server.infrastructure.rpml_adapter.instance_builder import OptimizationInstanceError
from server.domain.models.user import UserRead
from server.infrastructure.db.session import get_db
from server.services.dataset_instances import list_dataset_instances

router = APIRouter()

OptimizationInputMode = Literal["scenario_snapshot", "dataset_instance"]


class OptimizationMonteCarloConfig(BaseModel):
    n_scenarios: int = Field(default=16, ge=1, description="Количество сценариев Monte Carlo.")
    seed: int = Field(default=42, description="Базовый seed генератора случайных траекторий.")
    rho: float = Field(
        default=0.55,
        ge=-0.999,
        le=0.999,
        description="AR(1) коэффициент автокорреляции дохода.",
    )
    sigma: float = Field(default=0.15, ge=0, description="Волатильность логнормального шума.")
    shock_prob: float = Field(
        default=0.04,
        ge=0,
        le=1,
        description="Вероятность шокового снижения дохода в месяце.",
    )
    shock_severity_mean: float = Field(
        default=0.30,
        ge=0,
        description="Средняя глубина шока дохода.",
    )
    shock_severity_std: float = Field(
        default=0.10,
        ge=0,
        description="Стандартное отклонение глубины шока дохода.",
    )
    min_income_floor: float = Field(
        default=1.0,
        ge=0,
        description="Нижняя отсечка месячного дохода.",
    )

    def to_domain(self) -> IncomeMCConfig:
        return IncomeMCConfig(**self.model_dump())

    @classmethod
    def from_domain(cls, config: IncomeMCConfig) -> "OptimizationMonteCarloConfig":
        return cls(**dataclasses.asdict(config))


class OptimizationDebtSummary(BaseModel):
    id: int = Field(description="Идентификатор долга в рамках результата.")
    name: str = Field(description="Читаемое имя долга.")
    loan_type: str | None = Field(
        default=None,
        description="Нормализованный тип кредита, если доступен.",
    )
    principal: float | None = Field(
        default=None,
        description="Начальная сумма долга.",
    )
    fixed_payment: float | None = Field(
        default=None,
        description="Фиксированный или обязательный платеж по долгу.",
    )
    prepay_penalty: float | None = Field(
        default=None,
        description="Штраф за досрочное погашение по профилю долга.",
    )
    default_rate_monthly: float | None = Field(
        default=None,
        description="Штрафная/default ставка в месяц, если доступна.",
    )


class DatasetInstanceSummaryResponse(BaseModel):
    name: str = Field(description="Уникальный код dataset-инстанса.")
    loans_count: int = Field(description="Количество долгов в инстансе.")
    horizon_months: int = Field(description="Горизонт инстанса в месяцах.")
    n_cars: int = Field(description="Количество автокредитов.")
    n_houses: int = Field(description="Количество ипотек.")
    n_credit_cards: int = Field(description="Количество кредитных карт.")
    n_bank_loans: int = Field(description="Количество банковских займов.")


class DatasetInstanceCatalogResponse(BaseModel):
    total: int = Field(description="Сколько инстансов доступно в каталоге.")
    items: list[DatasetInstanceSummaryResponse] = Field(default_factory=list)


class OptimizationRunRequest(BaseModel):
    input_mode: OptimizationInputMode = Field(
        default=SCENARIO_INPUT_MODE,
        description="Источник входных данных: snapshot пользователя или dataset instance.",
    )
    instance_name: str | None = Field(
        default=None,
        description="Имя `.dat` инстанса. Обязательно для `dataset_instance`.",
    )
    horizon_months: int | None = Field(
        default=None,
        ge=1,
        le=360,
        description=(
            "Горизонт планирования в месяцах. "
            "Для `scenario_snapshot` обязателен; для `dataset_instance` должен совпадать с горизонтом инстанса, если передан."
        ),
    )
    ru_mode: bool = Field(
        default=True,
        description="Если true, применяются правила RU-режима по досрочному погашению.",
    )
    mc_income: bool = Field(
        default=False,
        description="Если true, дополнительно рассчитывается Monte Carlo summary по траекториям дохода.",
    )
    mc_config: OptimizationMonteCarloConfig | None = Field(
        default=None,
        description="Тонкие параметры Monte Carlo. Используются только при `mc_income=true`.",
    )

    @model_validator(mode="after")
    def validate_shape(self) -> "OptimizationRunRequest":
        if self.input_mode == DATASET_INPUT_MODE and not self.instance_name:
            raise ValueError("instance_name is required for dataset_instance mode")
        if self.input_mode == SCENARIO_INPUT_MODE and self.horizon_months is None:
            raise ValueError("horizon_months is required for scenario_snapshot mode")
        return self


class OptimizationRunResponse(BaseModel):
    status: str = Field(description="Статус решения MILP (например, OPTIMAL/FEASIBLE).")
    total_cost: float = Field(description="Стоимость базового детерминированного плана.")
    debts: list[OptimizationDebtSummary] = Field(
        default_factory=list,
        description="Сводка по долгам, соответствующая строкам матриц платежей и остатков.",
    )
    payments_matrix: list[list[float]] = Field(description="Матрица платежей [loan][month].")
    balances_matrix: list[list[float]] = Field(description="Матрица остатков [loan][month].")
    savings_vector: list[float] = Field(
        default_factory=list,
        description="Расчетный остаток доступного бюджета по месяцам для данного плана (непотраченные средства, перенесенные вперед).",
    )
    horizon_months: int = Field(description="Использованный горизонт планирования.")
    baseline_comparison: dict = Field(
        description="Сравнение MILP-плана с baseline-стратегиями (avalanche/snowball)."
    )
    input_mode: OptimizationInputMode = MVP_INPUT_MODE
    instance_name: str | None = Field(
        default=None,
        description="Имя dataset-инстанса, если расчет выполнен в `dataset_instance` режиме.",
    )
    assumptions: list[str] = Field(
        default_factory=lambda: list(MVP_ASSUMPTIONS),
        description="Список допущений, использованных при расчете.",
    )
    ru_mode: bool = Field(description="Фактически использованный RU-режим.")
    mc_income: bool = Field(description="Флаг Monte Carlo режима для этого расчета.")
    mc_summary: dict | None = Field(
        default=None,
        description=(
            "Агрегаты Monte Carlo по стоимости и времени решения "
            "(mean/median/p90, доля infeasible и т.д.)."
        ),
    )
    mc_config: OptimizationMonteCarloConfig | None = Field(
        default=None,
        description="Конфигурация Monte Carlo, использованная для расчета.",
    )
    budget_policy: str = Field(
        description="Политика применения месячного бюджета в модели.",
    )
    budget_trace: list[dict] = Field(
        default_factory=list,
        description=(
            "Помесячная трассировка бюджета: доход месяца, перенос, доступный бюджет, "
            "фактические платежи и остаток переноса."
        ),
    )


class CreateOptimizationTaskRequest(BaseModel):
    input_mode: OptimizationInputMode = Field(
        default=SCENARIO_INPUT_MODE,
        description="Источник входных данных для фоновой задачи.",
    )
    instance_name: str | None = Field(
        default=None,
        description="Имя `.dat` инстанса. Обязательно для `dataset_instance`.",
    )
    horizon_months: int | None = Field(
        default=None,
        ge=1,
        le=360,
        description=(
            "Горизонт планирования. Для dataset mode можно не передавать: будет использован горизонт инстанса."
        ),
    )
    ru_mode: bool = Field(
        default=True,
        description="Если true, применяются правила RU-режима.",
    )
    mc_income: bool = Field(
        default=False,
        description="Если true, в фоне будет рассчитан Monte Carlo summary.",
    )
    mc_config: OptimizationMonteCarloConfig | None = Field(
        default=None,
        description="Параметры Monte Carlo для фонового расчета.",
    )

    @model_validator(mode="after")
    def validate_shape(self) -> "CreateOptimizationTaskRequest":
        if self.input_mode == DATASET_INPUT_MODE and not self.instance_name:
            raise ValueError("instance_name is required for dataset_instance mode")
        if self.input_mode == SCENARIO_INPUT_MODE and self.horizon_months is None:
            raise ValueError("horizon_months is required for scenario_snapshot mode")
        return self


class CreateOptimizationTaskResponse(BaseModel):
    task_id: str = Field(description="Идентификатор асинхронной задачи.")
    status: Literal["pending"] = "pending"
    input_mode: OptimizationInputMode = Field(description="Режим входных данных задачи.")
    horizon_months: int = Field(description="Фактический горизонт задачи.")
    instance_name: str | None = Field(
        default=None,
        description="Имя dataset-инстанса, если задача создана в `dataset_instance` режиме.",
    )
    ru_mode: bool = Field(description="RU-режим, зафиксированный в задаче.")
    mc_income: bool = Field(description="MC-режим, зафиксированный в задаче.")


class OptimizationTaskStatusResponse(BaseModel):
    status: Literal["pending", "completed", "failed"]
    task_id: str = Field(description="Идентификатор асинхронной задачи.")
    plan_id: str | None = Field(
        default=None,
        description="Идентификатор готового плана (заполняется при completed).",
    )
    error: str | None = Field(
        default=None,
        description="Текст ошибки (заполняется при failed).",
    )
    input_mode: OptimizationInputMode = Field(description="Режим входных данных задачи.")
    horizon_months: int = Field(description="Горизонт задачи.")
    instance_name: str | None = Field(
        default=None,
        description="Имя dataset-инстанса, если задача считает dataset instance.",
    )
    ru_mode: bool = Field(description="RU-режим задачи.")
    mc_income: bool = Field(description="MC-режим задачи.")


@router.get(
    "/instances",
    response_model=DatasetInstanceCatalogResponse,
    summary="Каталог dataset-инстансов",
    description="Возвращает все доступные `.dat` инстансы из bundled Rios-Solis dataset.",
    responses={
        401: {"description": "Пользователь не аутентифицирован."},
    },
)
def get_dataset_instance_catalog(
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user),
) -> DatasetInstanceCatalogResponse:
    _ = db, current_user
    items = [
        DatasetInstanceSummaryResponse(
            name=item.name,
            loans_count=item.loans_count,
            horizon_months=item.horizon_months,
            n_cars=item.n_cars,
            n_houses=item.n_houses,
            n_credit_cards=item.n_credit_cards,
            n_bank_loans=item.n_bank_loans,
        )
        for item in list_dataset_instances()
    ]
    return DatasetInstanceCatalogResponse(total=len(items), items=items)


@router.get(
    "/mc-config/defaults",
    response_model=OptimizationMonteCarloConfig,
    summary="Дефолтные параметры Monte Carlo",
    description="Возвращает дефолтную конфигурацию модели стохастических траекторий дохода.",
    responses={
        401: {"description": "Пользователь не аутентифицирован."},
    },
)
def get_monte_carlo_defaults(
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user),
) -> OptimizationMonteCarloConfig:
    _ = db, current_user
    return OptimizationMonteCarloConfig.from_domain(IncomeMCConfig())


@router.post(
    "/run",
    response_model=OptimizationRunResponse,
    summary="Синхронный запуск оптимизации",
    description=(
        "Выполняет оптимизацию в рамках одного HTTP-запроса. "
        "Возвращает базовый план и, при `mc_income=true`, дополнительный Monte Carlo summary."
    ),
    responses={
        400: {"$ref": "#/components/responses/ErrorContent"},
        401: {"description": "Пользователь не аутентифицирован."},
        422: {"$ref": "#/components/responses/ErrorContent"},
    },
)
def run_optimization_sync(
    body: OptimizationRunRequest,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user),
) -> OptimizationRunResponse:
    mc_config = body.mc_config.to_domain() if body.mc_config is not None else None
    try:
        result = execute_run_optimization_sync(
            db,
            current_user.id,
            body.horizon_months,
            input_mode=body.input_mode,
            instance_name=body.instance_name,
            ru_mode=body.ru_mode,
            mc_income=body.mc_income,
            mc_config=mc_config,
        )
    except OptimizationInstanceError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from None
    except OptimizationSolverFailed as exc:
        hint = (
            " If status is INFEASIBLE, the horizon may be too short for this scenario "
            "(MILP requires zero balances at the last month; try horizon_months equal to the scenario profile)."
        )
        raise HTTPException(
            status_code=HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "message": "Optimization did not return a usable plan." + hint,
                "solver_status": exc.solver_status,
            },
        ) from None
    return OptimizationRunResponse(
        status=result.solver_status,
        total_cost=result.total_cost,
        debts=[OptimizationDebtSummary.model_validate(item) for item in result.debt_summaries],
        payments_matrix=result.payments_matrix,
        balances_matrix=result.balances_matrix,
        savings_vector=result.savings_vector,
        horizon_months=result.horizon_months,
        baseline_comparison=result.baseline_comparison,
        input_mode=result.input_mode,
        instance_name=result.instance_name,
        assumptions=result.assumptions,
        ru_mode=result.ru_mode,
        mc_income=result.mc_income,
        mc_summary=result.mc_summary,
        mc_config=(
            OptimizationMonteCarloConfig.from_domain(result.mc_config)
            if result.mc_config is not None
            else None
        ),
        budget_policy=result.budget_policy,
        budget_trace=result.budget_trace,
    )


@router.post(
    "/tasks",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=CreateOptimizationTaskResponse,
    summary="Создать асинхронную задачу оптимизации",
    description="Ставит расчет в очередь Celery и сразу возвращает task_id.",
    responses={
        401: {"description": "Пользователь не аутентифицирован."},
        422: {"$ref": "#/components/responses/ErrorContent"},
    },
)
def create_optimization_task(
    body: CreateOptimizationTaskRequest,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user),
) -> CreateOptimizationTaskResponse:
    out = execute_create_async_optimization_task(
        db,
        current_user.id,
        body.horizon_months,
        input_mode=body.input_mode,
        instance_name=body.instance_name,
        ru_mode=body.ru_mode,
        mc_income=body.mc_income,
        mc_config=body.mc_config.to_domain() if body.mc_config is not None else None,
    )
    return CreateOptimizationTaskResponse(
        task_id=out.task_id,
        status="pending",
        input_mode=out.input_mode,
        horizon_months=out.horizon_months,
        instance_name=out.instance_name,
        ru_mode=out.ru_mode,
        mc_income=out.mc_income,
    )


@router.get(
    "/tasks/{task_id}",
    response_model=OptimizationTaskStatusResponse,
    summary="Статус асинхронной задачи оптимизации",
    description=(
        "Возвращает текущий статус задачи. "
        "При completed в ответе присутствует `plan_id`, который можно запросить через `/optimization/plans/{plan_id}`."
    ),
    responses={
        401: {"description": "Пользователь не аутентифицирован."},
        404: {"$ref": "#/components/responses/ErrorContent"},
        422: {"$ref": "#/components/responses/ErrorContent"},
    },
)
def get_optimization_task_status(
    task_id: str,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user),
) -> OptimizationTaskStatusResponse:
    row = execute_get_optimization_task_status(db, current_user.id, task_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return OptimizationTaskStatusResponse(
        status=row.status,
        task_id=row.task_id,
        plan_id=row.plan_id,
        error=row.error,
        input_mode=row.input_mode,
        horizon_months=row.horizon_months,
        instance_name=row.instance_name,
        ru_mode=row.ru_mode,
        mc_income=row.mc_income,
    )
