"""Tests for checkpoint module."""

import json
import tempfile
from pathlib import Path

import pytest

from rpml.checkpoint import CheckpointManager
from rpml.metrics import ComparisonResult


def _sample_result(name: str = "inst_4_1") -> ComparisonResult:
    return ComparisonResult(
        instance_name=name,
        n_loans=4,
        optimal_cost=1000.0,
        optimal_solve_time=1.5,
        optimal_gap=0.0,
        optimal_status="OPTIMAL",
        avalanche_cost=1500.0,
        avalanche_valid=True,
        avalanche_feasible=True,
        avalanche_final_balance=0.0,
        avalanche_horizon_spend_advantage=33.33,
        avalanche_savings=33.33,
        snowball_cost=1600.0,
        snowball_valid=True,
        snowball_feasible=True,
        snowball_final_balance=0.0,
        snowball_horizon_spend_advantage=37.5,
        snowball_savings=37.5,
    )


def test_save_and_load_roundtrip():
    """Save results and load them back; data is preserved."""
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "ck.jsonl"
        mgr = CheckpointManager(path)
        r1 = _sample_result("a")
        r2 = _sample_result("b")
        r2.optimal_cost = 2000.0
        mgr.save_result(r1)
        mgr.save_result(r2)
        loaded = mgr.load_existing_results()
        assert len(loaded) == 2
        assert loaded["a"].instance_name == "a"
        assert loaded["a"].optimal_cost == 1000.0
        assert loaded["b"].optimal_cost == 2000.0


def test_get_processed_instances():
    """get_processed_instances returns names of instances in checkpoint."""
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "ck.jsonl"
        mgr = CheckpointManager(path)
        assert mgr.get_processed_instances() == set()
        mgr.save_result(_sample_result("x"))
        mgr.save_result(_sample_result("y"))
        assert mgr.get_processed_instances() == {"x", "y"}


def test_restart_clears_checkpoint():
    """restart=True removes existing checkpoint file."""
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "ck.jsonl"
        mgr = CheckpointManager(path)
        mgr.save_result(_sample_result("z"))
        assert path.exists()
        mgr2 = CheckpointManager(path, restart=True)
        assert not path.exists()
        assert mgr2.get_processed_instances() == set()


def test_corruption_recovery():
    """Invalid lines in checkpoint are skipped; valid lines are loaded."""
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "ck.jsonl"
        path.write_text(
            '{"instance_name":"good","n_loans":4,"optimal_cost":1.0,"optimal_solve_time":0.1,"optimal_gap":0.0,'
            '"optimal_status":"OPTIMAL","avalanche_cost":2.0,"avalanche_valid":true,"avalanche_feasible":true,'
            '"avalanche_final_balance":0.0,"avalanche_horizon_spend_advantage":50.0,"avalanche_savings":50.0,'
            '"snowball_cost":2.2,"snowball_valid":true,"snowball_feasible":true,"snowball_final_balance":0.0,'
            '"snowball_horizon_spend_advantage":54.5,"snowball_savings":54.5}\n'
            "not valid json\n"
            '{"instance_name":"good2","n_loans":4,"optimal_cost":3.0,"optimal_solve_time":0.2,"optimal_gap":0.0,'
            '"optimal_status":"OPTIMAL","avalanche_cost":4.0,"avalanche_valid":true,"avalanche_feasible":true,'
            '"avalanche_final_balance":0.0,"avalanche_horizon_spend_advantage":25.0,"avalanche_savings":25.0,'
            '"snowball_cost":4.5,"snowball_valid":true,"snowball_feasible":true,"snowball_final_balance":0.0,'
            '"snowball_horizon_spend_advantage":33.3,"snowball_savings":33.3}\n',
            encoding="utf-8",
        )
        mgr = CheckpointManager(path)
        loaded = mgr.load_existing_results()
        assert set(loaded.keys()) == {"good", "good2"}
        assert loaded["good"].optimal_cost == 1.0
        assert loaded["good2"].optimal_cost == 3.0


def test_export_to_csv():
    """export_to_csv writes CSV with expected columns."""
    with tempfile.TemporaryDirectory() as d:
        ck_path = Path(d) / "ck.jsonl"
        csv_path = Path(d) / "out.csv"
        mgr = CheckpointManager(ck_path)
        mgr.save_result(_sample_result("csv_test"))
        mgr.export_to_csv(csv_path)
        assert csv_path.exists()
        content = csv_path.read_text(encoding="utf-8")
        assert "instance" in content
        assert "n_loans" in content
        assert "milp_cost" in content
        assert "csv_test" in content


def test_export_to_csv_creates_missing_parent_directory():
    """export_to_csv creates parent directories for the target CSV path."""
    with tempfile.TemporaryDirectory() as d:
        ck_path = Path(d) / "ck.jsonl"
        csv_path = Path(d) / "exports" / "out.csv"
        mgr = CheckpointManager(ck_path)
        mgr.save_result(_sample_result("csv_nested"))
        mgr.export_to_csv(csv_path)
        assert csv_path.exists()
        content = csv_path.read_text(encoding="utf-8")
        assert "csv_nested" in content


def test_export_to_csv_empty_checkpoint():
    """export_to_csv on empty checkpoint does not create file with data."""
    with tempfile.TemporaryDirectory() as d:
        csv_path = Path(d) / "out.csv"
        mgr = CheckpointManager(Path(d) / "nonexistent.jsonl")
        mgr.export_to_csv(csv_path)
        assert not csv_path.exists()
