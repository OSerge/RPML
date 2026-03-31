"""Tests for data loader module."""

import pytest
from pathlib import Path

from rpml.data_loader import load_instance, RiosSolisInstance


def test_load_instance():
    """Test loading a single instance file."""
    dataset_path = Path(__file__).resolve().parents[3] / "RiosSolisDataset" / "Instances" / "Instances"
    
    # Find a 4-loan instance
    test_file = None
    for f in dataset_path.glob("Deudas_4_*.dat"):
        test_file = f
        break
    
    if test_file is None:
        pytest.skip("No test instance found")
    
    instance = load_instance(test_file)
    
    assert isinstance(instance, RiosSolisInstance)
    assert instance.n == 4
    assert instance.T == 120
    assert instance.principals.shape == (4,)
    assert instance.interest_rates.shape == (4, 120)
    assert instance.default_rates.shape == (4, 120)
    assert instance.monthly_income.shape == (120,)
    assert instance.release_time.shape == (4,)
    assert instance.total_debt > 0


def test_instance_properties():
    """Test instance property calculations."""
    dataset_path = Path(__file__).resolve().parents[3] / "RiosSolisDataset" / "Instances" / "Instances"
    
    test_file = None
    for f in dataset_path.glob("Deudas_4_*.dat"):
        test_file = f
        break
    
    if test_file is None:
        pytest.skip("No test instance found")
    
    instance = load_instance(test_file)
    
    # Test properties
    assert instance.total_debt == pytest.approx(sum(instance.principals))
    assert instance.avg_interest_rate > 0
    
    # Test prepayment check
    for j in range(instance.n):
        allowed = instance.is_prepayment_allowed(j)
        assert isinstance(allowed, bool)
