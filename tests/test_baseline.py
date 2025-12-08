"""Tests for baseline algorithms."""

import pytest
import numpy as np
from pathlib import Path

from rpml.data_loader import load_instance
from rpml.baseline import debt_avalanche, debt_snowball, debt_average


@pytest.fixture
def sample_instance():
    """Load a sample instance for testing."""
    dataset_path = Path(__file__).parent.parent / "RiosSolisDataset" / "Instances" / "Instances"
    
    test_file = None
    for f in dataset_path.glob("Deudas_4_*.dat"):
        test_file = f
        break
    
    if test_file is None:
        pytest.skip("No test instance found")
    
    return load_instance(test_file)


def test_debt_avalanche(sample_instance):
    """Test debt avalanche strategy."""
    solution = debt_avalanche(sample_instance)
    
    assert solution.payments.shape == (sample_instance.n, sample_instance.T)
    assert solution.balances.shape == (sample_instance.n, sample_instance.T)
    assert solution.savings.shape == (sample_instance.T,)
    assert solution.total_cost > 0
    assert solution.strategy_name == "Debt Avalanche"
    
    # Check final balances are approximately zero
    for j in range(sample_instance.n):
        final_balance = solution.balances[j, -1]
        assert abs(final_balance) < 1.0, f"Loan {j} final balance {final_balance} not zero"


def test_debt_snowball(sample_instance):
    """Test debt snowball strategy."""
    solution = debt_snowball(sample_instance)
    
    assert solution.payments.shape == (sample_instance.n, sample_instance.T)
    assert solution.balances.shape == (sample_instance.n, sample_instance.T)
    assert solution.savings.shape == (sample_instance.T,)
    assert solution.total_cost > 0
    assert solution.strategy_name == "Debt Snowball"
    
    # Check final balances
    for j in range(sample_instance.n):
        final_balance = solution.balances[j, -1]
        assert abs(final_balance) < 1.0


def test_debt_average(sample_instance):
    """Test debt average strategy."""
    solution = debt_average(sample_instance)
    
    assert solution.payments.shape == (sample_instance.n, sample_instance.T)
    assert solution.balances.shape == (sample_instance.n, sample_instance.T)
    assert solution.savings.shape == (sample_instance.T,)
    assert solution.total_cost > 0
    assert solution.strategy_name == "Debt Average"
    
    # Check final balances
    for j in range(sample_instance.n):
        final_balance = solution.balances[j, -1]
        assert abs(final_balance) < 1.0
