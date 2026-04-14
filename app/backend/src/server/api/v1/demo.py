import json
import math
from pathlib import Path
import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from server.api.deps import get_current_user
from server.domain.models.user import UserRead
from server.infrastructure.db.session import get_db
from server.services.demo_seed import (
    DemoSeedScenarioNotFoundError,
    DemoSeedValidationError,
    list_bundled_demo_instances,
    seed_demo_scenario,
)

router = APIRouter()


class DemoRunTopSavingsItem(BaseModel):
    instance_name: str = Field(description="Имя инстанса из checkpoint.")
    savings_pct: float = Field(
        description="Экономия MILP vs выбранная baseline-стратегия в процентах."
    )
    savings_abs: float = Field(
        description="Абсолютная экономия MILP vs выбранная baseline-стратегия."
    )
    optimal_cost: float = Field(description="Стоимость MILP.")
    baseline_cost: float = Field(description="Стоимость baseline-стратегии.")
    optimal_status: str | None = Field(
        default=None,
        description="Статус MILP решения для инстанса.",
    )


class DemoRunTopSavingsResponse(BaseModel):
    run_id: str
    metric: Literal["avalanche", "snowball"]
    checkpoint_path: str
    total_instances: int
    items: list[DemoRunTopSavingsItem]


class DemoSeedRequest(BaseModel):
    scenario_code: str | None = Field(
        default=None,
        description=(
            "Код bundled demo-сценария из `/api/v1/demo/instances`. "
            "Если не указан, используется стандартный demo-инстанс."
        ),
    )


class DemoSeedResponse(BaseModel):
    ok: bool
    scenario_code: str
    debts_count: int


class DemoInstanceSummary(BaseModel):
    code: str = Field(description="Код сценария, который сохраняется в `scenario_profiles.code`.")
    source_file: str = Field(description="Имя bundled JSON-файла в `core/rpml/result_samples`.")
    horizon_months: int = Field(description="Горизонт сценария в месяцах.")
    loans_count: int = Field(description="Количество долгов в bundled сценарии.")
    has_dat_file: bool = Field(description="Есть ли рядом исходный `.dat` с реальными ставками.")
    available_baselines: list[str] = Field(
        default_factory=list,
        description="Baseline-стратегии, присутствующие в bundled summary.",
    )


RUN_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[6]


def _validate_run_id(run_id: str) -> str:
    if not RUN_ID_RE.fullmatch(run_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid run_id format.",
        )
    return run_id


def _checkpoint_root() -> Path:
    return (_repo_root() / "core" / "rpml" / "tmp" / "runs").resolve()


def _checkpoint_path_for_run(run_id: str) -> tuple[Path, str]:
    safe_run_id = _validate_run_id(run_id)
    checkpoint_root = _checkpoint_root()
    checkpoint_path = (
        checkpoint_root / safe_run_id / "checkpoint" / "experiment_results_checkpoint.jsonl"
    ).resolve()
    try:
        relative_path = checkpoint_path.relative_to(_repo_root().resolve())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid run_id path.",
        ) from exc
    return checkpoint_path, str(relative_path)


def _to_float(value: object) -> float | None:
    if not isinstance(value, (int, float)):
        return None
    out = float(value)
    if not math.isfinite(out):
        return None
    return out


def _build_top_savings_for_run(
    *,
    run_id: str,
    metric: Literal["avalanche", "snowball"],
    limit: int,
) -> DemoRunTopSavingsResponse:
    checkpoint_path, checkpoint_relpath = _checkpoint_path_for_run(run_id)
    if not checkpoint_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run checkpoint not found: {checkpoint_relpath}",
        )

    savings_key = f"{metric}_savings"
    baseline_cost_key = f"{metric}_cost"
    items: list[DemoRunTopSavingsItem] = []
    with checkpoint_path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                continue
            instance_name = row.get("instance_name")
            if not isinstance(instance_name, str):
                continue
            optimal_cost = _to_float(row.get("optimal_cost"))
            baseline_cost = _to_float(row.get(baseline_cost_key))
            if optimal_cost is None or baseline_cost is None:
                continue
            savings_pct = _to_float(row.get(savings_key))
            if savings_pct is None:
                if baseline_cost == 0:
                    savings_pct = 0.0
                else:
                    savings_pct = (baseline_cost - optimal_cost) / baseline_cost * 100.0
            savings_abs = baseline_cost - optimal_cost
            items.append(
                DemoRunTopSavingsItem(
                    instance_name=instance_name,
                    savings_pct=savings_pct,
                    savings_abs=savings_abs,
                    optimal_cost=optimal_cost,
                    baseline_cost=baseline_cost,
                    optimal_status=(
                        row.get("optimal_status")
                        if isinstance(row.get("optimal_status"), str)
                        else None
                    ),
                )
            )

    items.sort(key=lambda item: item.savings_pct, reverse=True)
    top_items = items[:limit]
    return DemoRunTopSavingsResponse(
        run_id=run_id,
        metric=metric,
        checkpoint_path=checkpoint_relpath,
        total_instances=len(items),
        items=top_items,
    )


@router.post(
    "/seed",
    response_model=DemoSeedResponse,
    summary="Заполнить демо-данные",
    description=(
        "Идемпотентно создает/обновляет демо-сценарий и связанные данные для текущего пользователя, "
        "чтобы можно было сразу запускать оптимизацию."
    ),
    responses={
        401: {"description": "Пользователь не аутентифицирован."},
        422: {"description": "Ошибка валидации демо-данных."},
    },
)
def post_demo_seed(
    body: DemoSeedRequest | None = None,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user),
) -> DemoSeedResponse:
    try:
        payload = seed_demo_scenario(
            db,
            current_user.id,
            scenario_code=body.scenario_code if body is not None else None,
        )
    except DemoSeedValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(e),
        ) from e
    except DemoSeedScenarioNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e
    db.commit()
    return DemoSeedResponse.model_validate(payload)


@router.get(
    "/instances",
    response_model=list[DemoInstanceSummary],
    summary="Список доступных demo-инстансов",
    description=(
        "Возвращает каталог bundled demo-сценариев из `core/rpml/result_samples`, "
        "которые можно загрузить через `/api/v1/demo/seed`."
    ),
    responses={
        401: {"description": "Пользователь не аутентифицирован."},
    },
)
def get_demo_instances(
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user),
) -> list[DemoInstanceSummary]:
    _ = db, current_user
    return [DemoInstanceSummary.model_validate(item) for item in list_bundled_demo_instances()]


@router.get(
    "/runs/{run_id}/top-savings",
    response_model=DemoRunTopSavingsResponse,
    summary="Топ инстансов по экономии MILP",
    description=(
        "Читает checkpoint эксперимента run и возвращает top-N инстансов по "
        "процентной экономии MILP относительно Avalanche или Snowball."
    ),
    responses={
        401: {"description": "Пользователь не аутентифицирован."},
        404: {"description": "Run/checkpoint не найден."},
    },
)
def get_demo_run_top_savings(
    run_id: str,
    metric: Literal["avalanche", "snowball"] = Query(
        default="avalanche",
        description="Базовая стратегия для сравнения.",
    ),
    limit: int = Query(
        default=10,
        ge=1,
        le=100,
        description="Количество строк в топе.",
    ),
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user),
) -> DemoRunTopSavingsResponse:
    _ = db, current_user
    return _build_top_savings_for_run(run_id=run_id, metric=metric, limit=limit)
