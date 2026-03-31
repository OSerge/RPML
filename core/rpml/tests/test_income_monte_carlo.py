import numpy as np
import pytest

from rpml.data_loader import RiosSolisInstance
from rpml.income_monte_carlo import (
    IncomeMCConfig,
    derive_instance_seed,
    replace_instance_income,
    simulate_income_paths,
)


def _build_instance() -> RiosSolisInstance:
    n = 1
    t = 6
    return RiosSolisInstance(
        name="mc_test",
        n=n,
        T=t,
        n_cars=1,
        n_houses=0,
        n_credit_cards=0,
        n_bank_loans=0,
        principals=np.array([1000.0]),
        interest_rates=np.full((n, t), 0.01),
        default_rates=np.full((n, t), 0.02),
        min_payment_pct=np.array([0.1]),
        prepay_penalty=np.array([0.0]),
        monthly_income=np.full(t, 100.0),
        release_time=np.array([0]),
        stipulated_amount=np.array([20.0]),
        fixed_payment=np.array([20.0]),
    )


def test_simulate_income_paths_is_deterministic_by_seed():
    base_income = np.array([100.0] * 12)
    cfg = IncomeMCConfig(n_scenarios=5, seed=123, sigma=0.1)

    first = simulate_income_paths(base_income, cfg)
    second = simulate_income_paths(base_income, cfg)

    assert np.allclose(first, second)


def test_simulate_income_paths_shape_and_floor():
    base_income = np.array([120.0, 100.0, 80.0, 60.0])
    cfg = IncomeMCConfig(n_scenarios=7, seed=42, sigma=0.2, min_income_floor=10.0)

    paths = simulate_income_paths(base_income, cfg)

    assert paths.shape == (7, 4)
    assert np.all(paths >= 10.0)


def test_simulate_income_paths_shock_reduces_income_with_zero_volatility():
    base_income = np.array([100.0] * 8)
    cfg = IncomeMCConfig(
        n_scenarios=2,
        seed=7,
        rho=0.0,
        sigma=0.0,
        shock_prob=1.0,
        shock_severity_mean=0.25,
        shock_severity_std=0.0,
        min_income_floor=1.0,
    )

    paths = simulate_income_paths(base_income, cfg)

    assert np.allclose(paths, 75.0)


def test_replace_instance_income_creates_copied_instance():
    instance = _build_instance()
    scenario_income = np.array([80.0, 90.0, 100.0, 110.0, 120.0, 130.0])

    replaced = replace_instance_income(instance, scenario_income, "0")

    assert replaced.name == "mc_test__mc_0"
    assert np.allclose(replaced.monthly_income, scenario_income)
    assert np.allclose(instance.monthly_income, np.full(instance.T, 100.0))


def test_replace_instance_income_validates_shape():
    instance = _build_instance()
    with pytest.raises(ValueError, match="shape mismatch"):
        replace_instance_income(instance, np.array([1.0, 2.0]), "bad")


def test_derive_instance_seed_is_stable_and_name_sensitive():
    first = derive_instance_seed(42, "instance_a")
    second = derive_instance_seed(42, "instance_a")
    third = derive_instance_seed(42, "instance_b")

    assert first == second
    assert first != third

