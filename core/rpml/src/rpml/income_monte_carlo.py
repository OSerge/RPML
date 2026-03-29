from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256

import numpy as np

from .data_loader import RiosSolisInstance


@dataclass(frozen=True)
class IncomeMCConfig:
    n_scenarios: int = 16
    seed: int = 42
    rho: float = 0.55
    sigma: float = 0.15
    shock_prob: float = 0.04
    shock_severity_mean: float = 0.30
    shock_severity_std: float = 0.10
    min_income_floor: float = 1.0

    def validate(self) -> None:
        if self.n_scenarios < 1:
            raise ValueError("n_scenarios must be >= 1")
        if not (-0.999 <= self.rho <= 0.999):
            raise ValueError("rho must be in [-0.999, 0.999]")
        if self.sigma < 0:
            raise ValueError("sigma must be >= 0")
        if not (0.0 <= self.shock_prob <= 1.0):
            raise ValueError("shock_prob must be in [0, 1]")
        if self.shock_severity_mean < 0:
            raise ValueError("shock_severity_mean must be >= 0")
        if self.shock_severity_std < 0:
            raise ValueError("shock_severity_std must be >= 0")
        if self.min_income_floor < 0:
            raise ValueError("min_income_floor must be >= 0")


def derive_instance_seed(base_seed: int, instance_name: str) -> int:
    digest = sha256(f"{base_seed}:{instance_name}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=False)


def simulate_income_paths(base_income: np.ndarray, config: IncomeMCConfig) -> np.ndarray:
    config.validate()
    base_income = np.asarray(base_income, dtype=float)
    if base_income.ndim != 1:
        raise ValueError("base_income must be a 1D array")
    if base_income.size == 0:
        raise ValueError("base_income must not be empty")

    safe_base = np.maximum(base_income, config.min_income_floor)
    n_scenarios = config.n_scenarios
    horizon = safe_base.shape[0]

    rng = np.random.default_rng(config.seed)
    ar_noise = np.zeros((n_scenarios, horizon), dtype=float)
    z = rng.standard_normal((n_scenarios, horizon))

    innovation_scale = float(np.sqrt(max(0.0, 1.0 - config.rho**2)))
    ar_noise[:, 0] = z[:, 0]
    for t in range(1, horizon):
        ar_noise[:, t] = config.rho * ar_noise[:, t - 1] + innovation_scale * z[:, t]

    growth_component = np.exp(config.sigma * ar_noise)

    shock_events = rng.random((n_scenarios, horizon)) < config.shock_prob
    shock_severity = rng.normal(
        loc=config.shock_severity_mean,
        scale=config.shock_severity_std,
        size=(n_scenarios, horizon),
    )
    shock_severity = np.clip(shock_severity, 0.0, 0.95)
    shock_multiplier = np.where(shock_events, 1.0 - shock_severity, 1.0)

    incomes = safe_base[None, :] * growth_component * shock_multiplier
    return np.maximum(incomes, config.min_income_floor)


def replace_instance_income(
    instance: RiosSolisInstance,
    monthly_income: np.ndarray,
    scenario_suffix: str,
) -> RiosSolisInstance:
    monthly_income = np.asarray(monthly_income, dtype=float)
    if monthly_income.shape != (instance.T,):
        raise ValueError(
            f"monthly_income shape mismatch: expected {(instance.T,)}, got {monthly_income.shape}"
        )
    return replace(
        instance,
        name=f"{instance.name}__mc_{scenario_suffix}",
        monthly_income=monthly_income.copy(),
    )

