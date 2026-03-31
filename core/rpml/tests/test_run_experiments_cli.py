import sys
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from rpml.cli import (
    main,
    parse_args,
    process_monte_carlo_instance,
    resolve_solver_strategy,
    run_monte_carlo_experiments,
    run_monte_carlo_experiments_parallel,
)
from rpml.checkpoint import CheckpointManager
from rpml.income_monte_carlo import IncomeMCConfig
from rpml.metrics import ComparisonResult, MonteCarloAggregateResult
from rpml.milp_model import DEFAULT_SOLVER, FALLBACK_SOLVER


def test_resolve_solver_strategy_defaults_to_highs_with_fallback():
    solver_name, enable_fallback = resolve_solver_strategy(use_scip=False)

    assert solver_name == DEFAULT_SOLVER
    assert enable_fallback is True


def test_resolve_solver_strategy_uses_scip_without_fallback():
    solver_name, enable_fallback = resolve_solver_strategy(use_scip=True)

    assert solver_name == FALLBACK_SOLVER
    assert enable_fallback is False


def test_parse_args_accepts_scip_flag(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["run-experiments", "--scip"])

    args = parse_args()

    assert args.scip is True


def test_parse_args_accepts_timeline_export_flags(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run-experiments",
            "--export-timelines",
            "--timelines-dir",
            "tmp/custom_timelines",
        ],
    )

    args = parse_args()

    assert args.export_timelines is True
    assert str(args.timelines_dir).endswith("tmp/custom_timelines")


def test_parse_args_accepts_monte_carlo_flags(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run-experiments",
            "--mc-income",
            "--mc-scenarios",
            "24",
            "--mc-seed",
            "123",
            "--mc-rho",
            "0.7",
            "--mc-sigma",
            "0.2",
            "--mc-shock-prob",
            "0.05",
            "--mc-shock-severity",
            "0.4",
            "--mc-output",
            "tmp/mc.csv",
        ],
    )

    args = parse_args()

    assert args.mc_income is True
    assert args.mc_scenarios == 24
    assert args.mc_seed == 123
    assert args.mc_rho == 0.7
    assert args.mc_sigma == 0.2
    assert args.mc_shock_prob == 0.05
    assert args.mc_shock_severity == 0.4
    assert str(args.mc_output).endswith("tmp/mc.csv")


def test_run_monte_carlo_experiments_returns_scenario_comparisons(monkeypatch):
    instance = SimpleNamespace(name="inst_a", n=4, monthly_income=np.array([100.0, 100.0]))

    monkeypatch.setattr("rpml.cli.load_all_instances", lambda _: [instance])
    monkeypatch.setattr("rpml.cli.get_instances_by_size", lambda _: {4: [instance]})
    monkeypatch.setattr("rpml.cli.derive_instance_seed", lambda base_seed, instance_name: 11)
    monkeypatch.setattr(
        "rpml.cli.simulate_income_paths",
        lambda base_income, cfg: np.array([[100.0, 100.0], [90.0, 110.0]], dtype=float),
    )
    monkeypatch.setattr(
        "rpml.cli.replace_instance_income",
        lambda src, income, suffix: SimpleNamespace(
            name=f"{src.name}__mc_{suffix}",
            n=src.n,
            monthly_income=np.array(income, dtype=float),
        ),
    )
    monkeypatch.setattr(
        "rpml.cli.solve_rpml",
        lambda scenario_instance, **kwargs: SimpleNamespace(
            status="OPTIMAL", objective_value=900.0, solve_time=0.2, gap=0.0
        ),
    )
    monkeypatch.setattr("rpml.cli.debt_avalanche", lambda scenario_instance: SimpleNamespace(total_cost=1000.0))
    monkeypatch.setattr("rpml.cli.debt_snowball", lambda scenario_instance: SimpleNamespace(total_cost=1100.0))
    monkeypatch.setattr("rpml.cli.validate_baseline_solution", lambda solution, instance: (True, [], 0.0))
    monkeypatch.setattr(
        "rpml.cli.compare_solutions",
        lambda **kwargs: ComparisonResult(
            instance_name=kwargs["instance_name"],
            n_loans=kwargs["n_loans"],
            optimal_cost=900.0,
            optimal_solve_time=0.2,
            optimal_gap=0.0,
            optimal_status="OPTIMAL",
            avalanche_cost=1000.0,
            avalanche_valid=True,
            avalanche_feasible=True,
            avalanche_final_balance=0.0,
            avalanche_horizon_spend_advantage=10.0,
            avalanche_savings=10.0,
            snowball_cost=1100.0,
            snowball_valid=True,
            snowball_feasible=True,
            snowball_final_balance=0.0,
            snowball_horizon_spend_advantage=18.0,
            snowball_savings=18.0,
        ),
    )
    monkeypatch.setattr(
        "rpml.cli.aggregate_monte_carlo_results_from_comparisons",
        lambda **kwargs: MonteCarloAggregateResult(
            instance_name=kwargs["instance_name"],
            n_loans=kwargs["n_loans"],
            n_scenarios=2,
            feasible_scenarios=2,
            infeasible_scenarios=0,
            infeasible_rate=0.0,
            mean_cost=900.0,
            median_cost=900.0,
            p90_cost=900.0,
            mean_solve_time=0.2,
            p90_solve_time=0.2,
            p95_required_budget_overrun_proxy=0.0,
        ),
    )

    aggregates, scenario_rows, scenario_comparisons = run_monte_carlo_experiments(
        dataset_path=Path("/tmp/unused"),
        mc_config=IncomeMCConfig(n_scenarios=2, seed=1),
        max_instances_per_group=1,
        verbose=False,
        allowed_n_loans=(4,),
    )

    assert len(aggregates) == 1
    assert len(scenario_rows) == 2
    assert len(scenario_comparisons) == 2
    assert {r.instance_name for r in scenario_comparisons} == {"inst_a__mc_0", "inst_a__mc_1"}


def test_main_mc_income_prints_baseline_summary(monkeypatch, capsys, tmp_path):
    dataset_path = tmp_path / "RiosSolisDataset" / "Instances" / "Instances"
    dataset_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("rpml.cli.PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(
        "rpml.cli.parse_args",
        lambda: Namespace(
            checkpoint=None,
            timeout_log=None,
            timelines_dir=None,
            scip=False,
            summary=False,
            max_instances=None,
            n_loans=[4],
            time_limit=1,
            watchdog_grace_seconds=1,
            parallel=False,
            workers=None,
            export_timelines=False,
            mc_income=True,
            mc_scenarios=2,
            mc_seed=42,
            mc_rho=0.55,
            mc_sigma=0.15,
            mc_shock_prob=0.04,
            mc_shock_severity=0.30,
            mc_output=None,
            include_known_timeouts=False,
            restart=False,
        ),
    )
    monkeypatch.setattr(
        "rpml.cli.run_monte_carlo_experiments",
        lambda **kwargs: (
            [
                MonteCarloAggregateResult(
                    instance_name="inst_a",
                    n_loans=4,
                    n_scenarios=2,
                    feasible_scenarios=2,
                    infeasible_scenarios=0,
                    infeasible_rate=0.0,
                    mean_cost=950.0,
                    median_cost=950.0,
                    p90_cost=960.0,
                    mean_solve_time=0.2,
                    p90_solve_time=0.3,
                    p95_required_budget_overrun_proxy=0.0,
                )
            ],
            [{"instance_name": "inst_a", "scenario_name": "inst_a__mc_0", "scenario_index": 0}],
            [
                ComparisonResult(
                    instance_name="inst_a__mc_0",
                    n_loans=4,
                    optimal_cost=950.0,
                    optimal_solve_time=0.2,
                    optimal_gap=0.0,
                    optimal_status="OPTIMAL",
                    avalanche_cost=1000.0,
                    avalanche_valid=True,
                    avalanche_feasible=True,
                    avalanche_final_balance=0.0,
                    avalanche_horizon_spend_advantage=5.0,
                    avalanche_savings=5.0,
                    snowball_cost=1100.0,
                    snowball_valid=True,
                    snowball_feasible=True,
                    snowball_final_balance=0.0,
                    snowball_horizon_spend_advantage=13.64,
                    snowball_savings=13.64,
                )
            ],
        ),
    )
    monkeypatch.setattr(
        "rpml.cli._write_mc_outputs",
        lambda **kwargs: (
            tmp_path / "tmp" / "mc_income_results.csv",
            tmp_path / "tmp" / "mc_income_results_scenarios.csv",
            tmp_path / "tmp" / "mc_income_results_meta.json",
        ),
    )

    main()
    out = capsys.readouterr().out

    assert "MONTE CARLO INCOME SUMMARY" in out
    assert "MONTE CARLO BASELINE COMPARISON SUMMARY" in out
    assert "Debt Avalanche: valid 1, repaid_by_T 1, not_repaid_by_T 0" in out
    assert "Debt Snowball: valid 1, repaid_by_T 1, not_repaid_by_T 0" in out


def test_main_mc_income_parallel_uses_parallel_runner(monkeypatch, capsys, tmp_path):
    dataset_path = tmp_path / "RiosSolisDataset" / "Instances" / "Instances"
    dataset_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("rpml.cli.PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(
        "rpml.cli.parse_args",
        lambda: Namespace(
            checkpoint=None,
            timeout_log=None,
            timelines_dir=None,
            scip=False,
            summary=False,
            max_instances=None,
            n_loans=[4],
            time_limit=1,
            watchdog_grace_seconds=1,
            parallel=True,
            workers=2,
            export_timelines=False,
            mc_income=True,
            mc_scenarios=2,
            mc_seed=42,
            mc_rho=0.55,
            mc_sigma=0.15,
            mc_shock_prob=0.04,
            mc_shock_severity=0.30,
            mc_output=None,
            include_known_timeouts=False,
            restart=False,
        ),
    )

    def _sequential_should_not_be_called(**kwargs):
        raise AssertionError("Sequential MC runner must not be called when parallel=True")

    monkeypatch.setattr("rpml.cli.run_monte_carlo_experiments", _sequential_should_not_be_called)

    called = {"parallel": False}

    def _parallel_runner(**kwargs):
        called["parallel"] = True
        return (
            [
                MonteCarloAggregateResult(
                    instance_name="inst_a",
                    n_loans=4,
                    n_scenarios=2,
                    feasible_scenarios=2,
                    infeasible_scenarios=0,
                    infeasible_rate=0.0,
                    mean_cost=950.0,
                    median_cost=950.0,
                    p90_cost=960.0,
                    mean_solve_time=0.2,
                    p90_solve_time=0.3,
                    p95_required_budget_overrun_proxy=0.0,
                )
            ],
            [{"instance_name": "inst_a", "scenario_name": "inst_a__mc_0", "scenario_index": 0}],
            [
                ComparisonResult(
                    instance_name="inst_a__mc_0",
                    n_loans=4,
                    optimal_cost=950.0,
                    optimal_solve_time=0.2,
                    optimal_gap=0.0,
                    optimal_status="OPTIMAL",
                    avalanche_cost=1000.0,
                    avalanche_valid=True,
                    avalanche_feasible=True,
                    avalanche_final_balance=0.0,
                    avalanche_horizon_spend_advantage=5.0,
                    avalanche_savings=5.0,
                    snowball_cost=1100.0,
                    snowball_valid=True,
                    snowball_feasible=True,
                    snowball_final_balance=0.0,
                    snowball_horizon_spend_advantage=13.64,
                    snowball_savings=13.64,
                )
            ],
        )

    monkeypatch.setattr("rpml.cli.run_monte_carlo_experiments_parallel", _parallel_runner)
    monkeypatch.setattr(
        "rpml.cli._write_mc_outputs",
        lambda **kwargs: (
            tmp_path / "tmp" / "mc_income_results.csv",
            tmp_path / "tmp" / "mc_income_results_scenarios.csv",
            tmp_path / "tmp" / "mc_income_results_meta.json",
        ),
    )

    main()
    out = capsys.readouterr().out

    assert called["parallel"] is True
    assert "MONTE CARLO INCOME SUMMARY" in out


def test_main_mc_income_uses_separate_default_directory(monkeypatch, tmp_path):
    dataset_path = tmp_path / "RiosSolisDataset" / "Instances" / "Instances"
    dataset_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("rpml.cli.PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(
        "rpml.cli.parse_args",
        lambda: Namespace(
            checkpoint=None,
            timeout_log=None,
            timelines_dir=None,
            scip=False,
            summary=False,
            max_instances=None,
            n_loans=[4],
            time_limit=1,
            watchdog_grace_seconds=1,
            parallel=False,
            workers=None,
            export_timelines=False,
            mc_income=True,
            mc_scenarios=2,
            mc_seed=42,
            mc_rho=0.55,
            mc_sigma=0.15,
            mc_shock_prob=0.04,
            mc_shock_severity=0.30,
            mc_output=None,
            include_known_timeouts=False,
            restart=False,
        ),
    )

    captured = {"checkpoint_path": None, "output_path": None}

    def _runner(**kwargs):
        captured["checkpoint_path"] = kwargs.get("checkpoint_path")
        return ([], [], [])

    def _writer(**kwargs):
        captured["output_path"] = kwargs.get("output_path")
        output_path = kwargs["output_path"]
        return (
            output_path,
            output_path.with_name(f"{output_path.stem}_scenarios{output_path.suffix}"),
            output_path.with_name(f"{output_path.stem}_meta.json"),
        )

    monkeypatch.setattr("rpml.cli.run_monte_carlo_experiments", _runner)
    monkeypatch.setattr("rpml.cli._write_mc_outputs", _writer)

    main()

    assert captured["checkpoint_path"] == tmp_path / "tmp" / "monte_carlo" / "experiment_results_checkpoint.jsonl"
    assert captured["output_path"] == tmp_path / "tmp" / "monte_carlo" / "mc_income_results.csv"


def test_process_monte_carlo_instance_returns_instance_payload(monkeypatch):
    instance = SimpleNamespace(name="inst_a", n=4, monthly_income=np.array([100.0, 100.0]))
    monkeypatch.setattr("rpml.cli.derive_instance_seed", lambda base_seed, instance_name: 11)
    monkeypatch.setattr(
        "rpml.cli.simulate_income_paths",
        lambda base_income, cfg: np.array([[100.0, 100.0], [90.0, 110.0]], dtype=float),
    )
    monkeypatch.setattr(
        "rpml.cli.replace_instance_income",
        lambda src, income, suffix: SimpleNamespace(
            name=f"{src.name}__mc_{suffix}",
            n=src.n,
            monthly_income=np.array(income, dtype=float),
        ),
    )
    monkeypatch.setattr(
        "rpml.cli.solve_rpml",
        lambda scenario_instance, **kwargs: SimpleNamespace(
            status="OPTIMAL", objective_value=900.0, solve_time=0.2, gap=0.0
        ),
    )
    monkeypatch.setattr("rpml.cli.debt_avalanche", lambda scenario_instance: SimpleNamespace(total_cost=1000.0))
    monkeypatch.setattr("rpml.cli.debt_snowball", lambda scenario_instance: SimpleNamespace(total_cost=1100.0))
    monkeypatch.setattr("rpml.cli.validate_baseline_solution", lambda solution, instance: (True, [], 0.0))
    monkeypatch.setattr(
        "rpml.cli.compare_solutions",
        lambda **kwargs: ComparisonResult(
            instance_name=kwargs["instance_name"],
            n_loans=kwargs["n_loans"],
            optimal_cost=900.0,
            optimal_solve_time=0.2,
            optimal_gap=0.0,
            optimal_status="OPTIMAL",
            avalanche_cost=1000.0,
            avalanche_valid=True,
            avalanche_feasible=True,
            avalanche_final_balance=0.0,
            avalanche_horizon_spend_advantage=10.0,
            avalanche_savings=10.0,
            snowball_cost=1100.0,
            snowball_valid=True,
            snowball_feasible=True,
            snowball_final_balance=0.0,
            snowball_horizon_spend_advantage=18.0,
            snowball_savings=18.0,
        ),
    )
    monkeypatch.setattr(
        "rpml.cli.aggregate_monte_carlo_results_from_comparisons",
        lambda **kwargs: MonteCarloAggregateResult(
            instance_name=kwargs["instance_name"],
            n_loans=kwargs["n_loans"],
            n_scenarios=2,
            feasible_scenarios=2,
            infeasible_scenarios=0,
            infeasible_rate=0.0,
            mean_cost=900.0,
            median_cost=900.0,
            p90_cost=900.0,
            mean_solve_time=0.2,
            p90_solve_time=0.2,
            p95_required_budget_overrun_proxy=0.0,
        ),
    )

    result = process_monte_carlo_instance(
        (
            instance,
            IncomeMCConfig(n_scenarios=2, seed=1),
            1,
            DEFAULT_SOLVER,
            None,
            {},
        )
    )

    assert result[0] == "ok"
    assert result[1].instance_name == "inst_a"
    assert len(result[2]) == 2
    assert len(result[3]) == 2


def test_run_monte_carlo_experiments_parallel_merges_results_deterministically(monkeypatch):
    inst_b = SimpleNamespace(name="inst_b", n=4, monthly_income=np.array([100.0, 100.0]))
    inst_a = SimpleNamespace(name="inst_a", n=4, monthly_income=np.array([100.0, 100.0]))
    monkeypatch.setattr("rpml.cli.load_all_instances", lambda _: [inst_b, inst_a])
    monkeypatch.setattr("rpml.cli.get_instances_by_size", lambda _: {4: [inst_b, inst_a]})

    def _fake_worker(args_tuple):
        inst = args_tuple[0]
        rows = [
            {"instance_name": inst.name, "scenario_name": f"{inst.name}__mc_1", "scenario_index": 1},
            {"instance_name": inst.name, "scenario_name": f"{inst.name}__mc_0", "scenario_index": 0},
        ]
        comps = [
            ComparisonResult(
                instance_name=f"{inst.name}__mc_1",
                n_loans=4,
                optimal_cost=1.0,
                optimal_solve_time=1.0,
                optimal_gap=0.0,
                optimal_status="OPTIMAL",
                avalanche_cost=1.0,
                avalanche_valid=True,
                avalanche_feasible=True,
                avalanche_final_balance=0.0,
                avalanche_horizon_spend_advantage=0.0,
                avalanche_savings=0.0,
                snowball_cost=1.0,
                snowball_valid=True,
                snowball_feasible=True,
                snowball_final_balance=0.0,
                snowball_horizon_spend_advantage=0.0,
                snowball_savings=0.0,
            ),
            ComparisonResult(
                instance_name=f"{inst.name}__mc_0",
                n_loans=4,
                optimal_cost=1.0,
                optimal_solve_time=1.0,
                optimal_gap=0.0,
                optimal_status="OPTIMAL",
                avalanche_cost=1.0,
                avalanche_valid=True,
                avalanche_feasible=True,
                avalanche_final_balance=0.0,
                avalanche_horizon_spend_advantage=0.0,
                avalanche_savings=0.0,
                snowball_cost=1.0,
                snowball_valid=True,
                snowball_feasible=True,
                snowball_final_balance=0.0,
                snowball_horizon_spend_advantage=0.0,
                snowball_savings=0.0,
            ),
        ]
        aggregate = MonteCarloAggregateResult(
            instance_name=inst.name,
            n_loans=4,
            n_scenarios=2,
            feasible_scenarios=2,
            infeasible_scenarios=0,
            infeasible_rate=0.0,
            mean_cost=1.0,
            median_cost=1.0,
            p90_cost=1.0,
            mean_solve_time=1.0,
            p90_solve_time=1.0,
            p95_required_budget_overrun_proxy=0.0,
        )
        return ("ok", aggregate, rows, comps)

    monkeypatch.setattr("rpml.cli.process_monte_carlo_instance", _fake_worker)

    class _FakeFuture:
        def __init__(self, value):
            self._value = value

        def result(self):
            return self._value

    class _FakeExecutor:
        def __init__(self, max_workers=None):
            self.max_workers = max_workers

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def submit(self, fn, args):
            return _FakeFuture(fn(args))

    monkeypatch.setattr("rpml.cli.futures.ProcessPoolExecutor", _FakeExecutor)
    monkeypatch.setattr("rpml.cli.futures.as_completed", lambda iterable: list(reversed(list(iterable))))

    aggregates, scenario_rows, scenario_comparisons = run_monte_carlo_experiments_parallel(
        dataset_path=Path("/tmp/unused"),
        mc_config=IncomeMCConfig(n_scenarios=2, seed=1),
        max_instances_per_group=None,
        verbose=False,
        allowed_n_loans=(4,),
        n_workers=2,
    )

    assert [item.instance_name for item in aggregates] == ["inst_a", "inst_b"]
    assert [(row["instance_name"], row["scenario_index"]) for row in scenario_rows] == [
        ("inst_a", 0),
        ("inst_a", 1),
        ("inst_b", 0),
        ("inst_b", 1),
    ]
    assert [item.instance_name for item in scenario_comparisons] == [
        "inst_a__mc_0",
        "inst_a__mc_1",
        "inst_b__mc_0",
        "inst_b__mc_1",
    ]


def test_run_monte_carlo_experiments_parallel_keyboard_interrupt_kills_workers(monkeypatch):
    inst_a = SimpleNamespace(name="inst_a", n=4, monthly_income=np.array([100.0, 100.0]))
    monkeypatch.setattr("rpml.cli.load_all_instances", lambda _: [inst_a])
    monkeypatch.setattr("rpml.cli.get_instances_by_size", lambda _: {4: [inst_a]})

    killed = {"flag": False}
    shutdown_called = {"flag": False}

    class _FakeProc:
        def kill(self):
            killed["flag"] = True

    class _FakeFuture:
        pass

    class _FakeExecutor:
        def __init__(self, max_workers=None):
            self._processes = {1: _FakeProc()}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def submit(self, fn, args):
            return _FakeFuture()

        def shutdown(self, wait=False, cancel_futures=True):
            shutdown_called["flag"] = True

    monkeypatch.setattr("rpml.cli.futures.ProcessPoolExecutor", _FakeExecutor)

    def _raise_interrupt(_futures):
        raise KeyboardInterrupt()

    monkeypatch.setattr("rpml.cli.futures.as_completed", _raise_interrupt)

    with pytest.raises(KeyboardInterrupt):
        run_monte_carlo_experiments_parallel(
            dataset_path=Path("/tmp/unused"),
            mc_config=IncomeMCConfig(n_scenarios=2, seed=1),
            max_instances_per_group=None,
            verbose=False,
            allowed_n_loans=(4,),
            n_workers=2,
        )

    assert killed["flag"] is True
    assert shutdown_called["flag"] is True


def _mc_comparison(name: str, n_loans: int = 4, status: str = "OPTIMAL") -> ComparisonResult:
    return ComparisonResult(
        instance_name=name,
        n_loans=n_loans,
        optimal_cost=950.0,
        optimal_solve_time=0.2,
        optimal_gap=0.0,
        optimal_status=status,
        avalanche_cost=1000.0,
        avalanche_valid=True,
        avalanche_feasible=True,
        avalanche_final_balance=0.0,
        avalanche_horizon_spend_advantage=5.0,
        avalanche_savings=5.0,
        snowball_cost=1100.0,
        snowball_valid=True,
        snowball_feasible=True,
        snowball_final_balance=0.0,
        snowball_horizon_spend_advantage=13.64,
        snowball_savings=13.64,
    )


def test_run_monte_carlo_experiments_skips_only_fully_completed_instances(monkeypatch, tmp_path):
    instance = SimpleNamespace(name="inst_a", n=4, monthly_income=np.array([100.0, 100.0]))
    monkeypatch.setattr("rpml.cli.load_all_instances", lambda _: [instance])
    monkeypatch.setattr("rpml.cli.get_instances_by_size", lambda _: {4: [instance]})
    monkeypatch.setattr(
        "rpml.cli._run_monte_carlo_for_instance",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("instance should be skipped")),
    )

    checkpoint_path = tmp_path / "mc_checkpoint.jsonl"
    mgr = CheckpointManager(checkpoint_path)
    mgr.save_result(_mc_comparison("inst_a__mc_0"))
    mgr.save_result(_mc_comparison("inst_a__mc_1"))

    aggregates, scenario_rows, scenario_comparisons = run_monte_carlo_experiments(
        dataset_path=Path("/tmp/unused"),
        mc_config=IncomeMCConfig(n_scenarios=2, seed=1),
        max_instances_per_group=1,
        verbose=False,
        allowed_n_loans=(4,),
        checkpoint_path=checkpoint_path,
    )

    assert len(aggregates) == 1
    assert aggregates[0].instance_name == "inst_a"
    assert len(scenario_rows) == 2
    assert [r.instance_name for r in scenario_comparisons] == ["inst_a__mc_0", "inst_a__mc_1"]


def test_run_monte_carlo_experiments_resumes_incomplete_instance_by_missing_scenarios(monkeypatch, tmp_path):
    instance = SimpleNamespace(name="inst_a", n=4, monthly_income=np.array([100.0, 100.0]))
    monkeypatch.setattr("rpml.cli.load_all_instances", lambda _: [instance])
    monkeypatch.setattr("rpml.cli.get_instances_by_size", lambda _: {4: [instance]})

    checkpoint_path = tmp_path / "mc_checkpoint.jsonl"
    mgr = CheckpointManager(checkpoint_path)
    mgr.save_result(_mc_comparison("inst_a__mc_0"))

    captured_existing = {"count": 0}

    def _fake_run_instance(**kwargs):
        captured_existing["count"] = len(kwargs["existing_scenario_results"])
        ck = CheckpointManager(Path(kwargs["checkpoint_path"]))
        c0 = kwargs["existing_scenario_results"][0]
        c1 = _mc_comparison("inst_a__mc_1")
        ck.save_result(c1)
        aggregate = MonteCarloAggregateResult(
            instance_name="inst_a",
            n_loans=4,
            n_scenarios=2,
            feasible_scenarios=2,
            infeasible_scenarios=0,
            infeasible_rate=0.0,
            mean_cost=950.0,
            median_cost=950.0,
            p90_cost=950.0,
            mean_solve_time=0.2,
            p90_solve_time=0.2,
            p95_required_budget_overrun_proxy=0.0,
        )
        rows = [
            {"instance_name": "inst_a", "scenario_name": "inst_a__mc_0", "scenario_index": 0},
            {"instance_name": "inst_a", "scenario_name": "inst_a__mc_1", "scenario_index": 1},
        ]
        return aggregate, rows, [c0, c1]

    monkeypatch.setattr("rpml.cli._run_monte_carlo_for_instance", _fake_run_instance)

    aggregates, scenario_rows, scenario_comparisons = run_monte_carlo_experiments(
        dataset_path=Path("/tmp/unused"),
        mc_config=IncomeMCConfig(n_scenarios=2, seed=1),
        max_instances_per_group=1,
        verbose=False,
        allowed_n_loans=(4,),
        checkpoint_path=checkpoint_path,
    )

    assert captured_existing["count"] == 1
    assert len(aggregates) == 1
    assert len(scenario_rows) == 2
    assert [r.instance_name for r in scenario_comparisons] == ["inst_a__mc_0", "inst_a__mc_1"]


def test_run_monte_carlo_parallel_skips_fully_completed_instances(monkeypatch, tmp_path):
    instance = SimpleNamespace(name="inst_a", n=4, monthly_income=np.array([100.0, 100.0]))
    monkeypatch.setattr("rpml.cli.load_all_instances", lambda _: [instance])
    monkeypatch.setattr("rpml.cli.get_instances_by_size", lambda _: {4: [instance]})

    checkpoint_path = tmp_path / "mc_checkpoint.jsonl"
    mgr = CheckpointManager(checkpoint_path)
    mgr.save_result(_mc_comparison("inst_a__mc_0"))
    mgr.save_result(_mc_comparison("inst_a__mc_1"))

    submit_calls = {"count": 0}

    class _FakeExecutor:
        def __init__(self, max_workers=None):
            self.max_workers = max_workers

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def submit(self, fn, args):
            submit_calls["count"] += 1
            return None

    monkeypatch.setattr("rpml.cli.futures.ProcessPoolExecutor", _FakeExecutor)
    monkeypatch.setattr("rpml.cli.futures.as_completed", lambda submitted: [])

    aggregates, scenario_rows, scenario_comparisons = run_monte_carlo_experiments_parallel(
        dataset_path=Path("/tmp/unused"),
        mc_config=IncomeMCConfig(n_scenarios=2, seed=1),
        max_instances_per_group=1,
        verbose=False,
        allowed_n_loans=(4,),
        n_workers=1,
        checkpoint_path=checkpoint_path,
    )

    assert submit_calls["count"] == 0
    assert len(aggregates) == 1
    assert len(scenario_rows) == 2
    assert [r.instance_name for r in scenario_comparisons] == ["inst_a__mc_0", "inst_a__mc_1"]


def test_run_monte_carlo_parallel_resumes_only_missing_scenarios(monkeypatch, tmp_path):
    instance = SimpleNamespace(name="inst_a", n=4, monthly_income=np.array([100.0, 100.0]))
    monkeypatch.setattr("rpml.cli.load_all_instances", lambda _: [instance])
    monkeypatch.setattr("rpml.cli.get_instances_by_size", lambda _: {4: [instance]})

    checkpoint_path = tmp_path / "mc_checkpoint.jsonl"
    mgr = CheckpointManager(checkpoint_path)
    mgr.save_result(_mc_comparison("inst_a__mc_0"))

    submit_payload = {"existing_count": None}

    class _FakeFuture:
        def __init__(self, value):
            self._value = value

        def result(self):
            return self._value

    class _FakeExecutor:
        def __init__(self, max_workers=None):
            self.max_workers = max_workers

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def submit(self, fn, args):
            submit_payload["existing_count"] = len(args[5])
            ck = CheckpointManager(Path(args[4]))
            ck.save_result(_mc_comparison("inst_a__mc_1"))
            return _FakeFuture(
                (
                    "ok",
                    MonteCarloAggregateResult(
                        instance_name="inst_a",
                        n_loans=4,
                        n_scenarios=2,
                        feasible_scenarios=2,
                        infeasible_scenarios=0,
                        infeasible_rate=0.0,
                        mean_cost=950.0,
                        median_cost=950.0,
                        p90_cost=950.0,
                        mean_solve_time=0.2,
                        p90_solve_time=0.2,
                        p95_required_budget_overrun_proxy=0.0,
                    ),
                    [],
                    [],
                )
            )

    monkeypatch.setattr("rpml.cli.futures.ProcessPoolExecutor", _FakeExecutor)
    monkeypatch.setattr("rpml.cli.futures.as_completed", lambda iterable: list(iterable))

    aggregates, scenario_rows, scenario_comparisons = run_monte_carlo_experiments_parallel(
        dataset_path=Path("/tmp/unused"),
        mc_config=IncomeMCConfig(n_scenarios=2, seed=1),
        max_instances_per_group=1,
        verbose=False,
        allowed_n_loans=(4,),
        n_workers=1,
        checkpoint_path=checkpoint_path,
    )

    assert submit_payload["existing_count"] == 1
    assert len(aggregates) == 1
    assert len(scenario_rows) == 2
    assert [r.instance_name for r in scenario_comparisons] == ["inst_a__mc_0", "inst_a__mc_1"]
