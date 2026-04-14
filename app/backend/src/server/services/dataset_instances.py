from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import re

from rpml.data_loader import load_instance


@dataclass(frozen=True)
class DatasetInstanceSummary:
    name: str
    loans_count: int
    horizon_months: int
    n_cars: int
    n_houses: int
    n_credit_cards: int
    n_bank_loans: int


class DatasetInstanceNotFoundError(LookupError):
    """Requested bundled dataset instance was not found."""


_FILENAME_RE = re.compile(
    r"^(?P<prefix>Deudas)_(?P<loans>\d+)_(?P<cars>\d+)_(?P<houses>\d+)_(?P<cards>\d+)_(?P<banks>\d+)_(?P<horizon>\d+)_"
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[5]


def dataset_instances_dir() -> Path:
    return _repo_root() / "core" / "rpml" / "RiosSolisDataset" / "Instances" / "Instances"


def _summary_from_path(path: Path) -> DatasetInstanceSummary:
    match = _FILENAME_RE.match(path.stem)
    if match is not None:
        return DatasetInstanceSummary(
            name=path.stem,
            loans_count=int(match.group("loans")),
            horizon_months=int(match.group("horizon")),
            n_cars=int(match.group("cars")),
            n_houses=int(match.group("houses")),
            n_credit_cards=int(match.group("cards")),
            n_bank_loans=int(match.group("banks")),
        )

    instance = load_instance(path)
    return DatasetInstanceSummary(
        name=instance.name,
        loans_count=int(instance.n),
        horizon_months=int(instance.T),
        n_cars=int(instance.n_cars),
        n_houses=int(instance.n_houses),
        n_credit_cards=int(instance.n_credit_cards),
        n_bank_loans=int(instance.n_bank_loans),
    )


@lru_cache(maxsize=1)
def list_dataset_instances() -> tuple[DatasetInstanceSummary, ...]:
    root = dataset_instances_dir()
    items = tuple(
        sorted(
            (_summary_from_path(path) for path in root.glob("*.dat")),
            key=lambda item: (item.loans_count, item.horizon_months, item.name),
        )
    )
    return items


@lru_cache(maxsize=1024)
def get_dataset_instance_summary(instance_name: str) -> DatasetInstanceSummary:
    for item in list_dataset_instances():
        if item.name == instance_name:
            return item
    raise DatasetInstanceNotFoundError(
        f"Bundled dataset instance not found: {instance_name}"
    )


def load_dataset_instance_by_name(instance_name: str):
    summary = get_dataset_instance_summary(instance_name)
    path = dataset_instances_dir() / f"{summary.name}.dat"
    if not path.is_file():
        raise DatasetInstanceNotFoundError(
            f"Bundled dataset instance file not found: {instance_name}"
        )
    return load_instance(path)
