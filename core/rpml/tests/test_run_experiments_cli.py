import sys

from rpml.cli import parse_args, resolve_solver_strategy
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
