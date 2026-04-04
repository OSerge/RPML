"""
Run experiments on Rios-Solis dataset.

Compares optimal MILP solutions with baseline strategies.
"""

import argparse
import concurrent.futures as futures
import csv
import dataclasses
import hashlib
import json
import os
import re
import signal
import sys
from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List

import numpy as np
from tqdm import tqdm

from rpml.data_loader import load_all_instances, get_instances_by_size, with_ru_prepayment_rules
from rpml.milp_model import (
    DEFAULT_SOLVER,
    FALLBACK_SOLVER,
    evaluate_fixed_plan_shortfalls,
    solve_rpml,
    solve_stochastic_rpml,
)
from rpml.baseline import debt_avalanche, debt_snowball
from rpml.metrics import (
    ComparisonResult,
    MonteCarloAggregateResult,
    StochasticRiskComparisonResult,
    aggregate_monte_carlo_results_from_comparisons,
    compute_cash_shortfall_rate,
    compute_cvar,
    compare_solutions,
    print_stochastic_risk_summary,
    print_summary,
    validate_baseline_solution,
)
from rpml.checkpoint import CheckpointManager
from rpml.income_monte_carlo import (
    IncomeMCConfig,
    derive_instance_seed,
    replace_instance_income,
    simulate_income_paths,
)
from rpml.timeline_export import export_timeline_json


PROJECT_ROOT = Path(__file__).resolve().parents[2]


TIMEOUT_CSV_COLUMNS = [
    "instance_name",
    "n_loans",
    "time_limit_seconds",
    "watchdog_timeout_seconds",
    "reason",
    "recorded_at_utc",
]

MC_INSTANCE_CSV_COLUMNS = [
    "instance_name",
    "n_loans",
    "n_scenarios",
    "feasible_scenarios",
    "infeasible_scenarios",
    "infeasible_rate",
    "mean_cost",
    "median_cost",
    "p90_cost",
    "mean_solve_time",
    "p90_solve_time",
    "p95_required_budget_overrun_proxy",
]

MC_SCENARIO_CSV_COLUMNS = [
    "instance_name",
    "scenario_name",
    "scenario_index",
    "status",
    "objective_cost",
    "solve_time",
    "gap",
]

H2_INSTANCE_CSV_COLUMNS = [
    "instance_name",
    "n_loans",
    "n_scenarios",
    "risk_alpha",
    "risk_lambda",
    "shortfall_epsilon",
    "shortfall_rate_beta",
    "deterministic_status",
    "deterministic_cost",
    "deterministic_solve_time",
    "deterministic_gap",
    "deterministic_mean_shortfall",
    "deterministic_median_shortfall",
    "deterministic_p90_shortfall",
    "deterministic_max_shortfall",
    "deterministic_cvar_shortfall",
    "deterministic_cash_shortfall_rate",
    "stochastic_status",
    "stochastic_total_payment_cost",
    "stochastic_objective_value",
    "stochastic_solve_time",
    "stochastic_gap",
    "stochastic_mean_shortfall",
    "stochastic_median_shortfall",
    "stochastic_p90_shortfall",
    "stochastic_max_shortfall",
    "stochastic_cvar_shortfall",
    "stochastic_cash_shortfall_rate",
    "delta_total_payment_cost",
    "delta_cvar_shortfall",
    "delta_cash_shortfall_rate",
]

H2_SCENARIO_CSV_COLUMNS = [
    "instance_name",
    "scenario_index",
    "deterministic_shortfall",
    "stochastic_shortfall",
]


RUN_CONFIG_FILENAME = "run_config.json"
RUN_STATE_FILENAME = "run_state.json"
LAST_SHUTDOWN_SIGNAL: int | None = None


def _shutdown_signal_handler(signum, _frame) -> None:
    global LAST_SHUTDOWN_SIGNAL
    LAST_SHUTDOWN_SIGNAL = signum
    raise KeyboardInterrupt


def _install_shutdown_signal_handlers() -> dict[int, Any]:
    previous_handlers: dict[int, Any] = {}
    handled_signals = [signal.SIGINT]
    if hasattr(signal, "SIGTERM"):
        handled_signals.append(signal.SIGTERM)
    for sig in handled_signals:
        previous_handlers[sig] = signal.getsignal(sig)
        signal.signal(sig, _shutdown_signal_handler)
    return previous_handlers


def _restore_shutdown_signal_handlers(previous_handlers: dict[int, Any]) -> None:
    for sig, handler in previous_handlers.items():
        signal.signal(sig, handler)


@contextmanager
def _suppress_native_solver_output(enabled: bool = True):
    if not enabled:
        yield
        return
    try:
        saved_stdout_fd = os.dup(1)
        saved_stderr_fd = os.dup(2)
        devnull_fd = os.open(os.devnull, os.O_WRONLY)
    except OSError:
        yield
        return
    try:
        os.dup2(devnull_fd, 1)
        os.dup2(devnull_fd, 2)
        yield
    finally:
        try:
            os.dup2(saved_stdout_fd, 1)
            os.dup2(saved_stderr_fd, 2)
        finally:
            os.close(saved_stdout_fd)
            os.close(saved_stderr_fd)
            os.close(devnull_fd)


def _json_ready(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _json_ready(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(v) for v in value]
    return value


def _slugify_token(value: str) -> str:
    token = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-")
    return token or "na"


def _build_run_param_slug(args: argparse.Namespace) -> str:
    loan_counts = "-".join(str(x) for x in sorted(set(args.n_loans)))
    stochastic_cvar = bool(getattr(args, "stochastic_cvar", False))
    parts = [
        "ru" if args.ru else "base",
        "h2cvar" if stochastic_cvar else ("mc" if args.mc_income else "std"),
        f"n{loan_counts}",
        f"tl{args.time_limit}",
    ]
    if args.max_instances is not None:
        parts.append(f"m{args.max_instances}")
    if args.mc_income:
        parts.extend(
            [
                f"sc{args.mc_scenarios}",
                f"seed{args.mc_seed}",
            ]
        )
    if stochastic_cvar:
        alpha = int(round(float(getattr(args, "risk_alpha", 0.95)) * 100))
        lam = str(getattr(args, "risk_lambda", 1.0)).replace(".", "p")
        parts.extend([f"a{alpha}", f"l{lam}"])
        beta = getattr(args, "shortfall_rate_beta", None)
        if beta is not None:
            parts.append(f"b{str(beta).replace('.', 'p')}")
    return "_".join(_slugify_token(part) for part in parts)


def _build_run_signature(args: argparse.Namespace, initial_solver_name: str) -> dict[str, Any]:
    stochastic_cvar = bool(getattr(args, "stochastic_cvar", False))
    signature = {
        "ru": bool(args.ru),
        "mc_income": bool(args.mc_income),
        "stochastic_cvar": stochastic_cvar,
        "n_loans": list(args.n_loans),
        "max_instances": args.max_instances,
        "time_limit": args.time_limit,
        "watchdog_grace_seconds": args.watchdog_grace_seconds,
        "scip": bool(args.scip),
        "initial_solver": initial_solver_name,
        "include_known_timeouts": bool(args.include_known_timeouts),
        "parallel": bool(args.parallel),
        "workers": args.workers,
    }
    if args.mc_income:
        signature.update(
            {
                "mc_scenarios": args.mc_scenarios,
                "mc_seed": args.mc_seed,
                "mc_rho": args.mc_rho,
                "mc_sigma": args.mc_sigma,
                "mc_shock_prob": args.mc_shock_prob,
                "mc_shock_severity": args.mc_shock_severity,
            }
        )
    if stochastic_cvar:
        signature.update(
            {
                "risk_alpha": float(getattr(args, "risk_alpha", 0.95)),
                "risk_lambda": float(getattr(args, "risk_lambda", 1.0)),
                "shortfall_epsilon": float(getattr(args, "shortfall_epsilon", 1e-6)),
                "shortfall_rate_beta": getattr(args, "shortfall_rate_beta", None),
            }
        )
    return signature


def _load_json_file(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None
    if isinstance(data, dict):
        return data
    return None


def _write_json_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(_json_ready(payload), f, ensure_ascii=False, indent=2)


def _write_run_state(run_dir: Path, status: str) -> None:
    now_iso = datetime.now(timezone.utc).isoformat()
    state_path = run_dir / RUN_STATE_FILENAME
    existing = _load_json_file(state_path) or {}
    payload = {
        "run_id": run_dir.name,
        "status": status,
        "started_at_utc": existing.get("started_at_utc", now_iso),
        "updated_at_utc": now_iso,
    }
    _write_json_file(state_path, payload)


def _find_resume_last_run_dir(runs_root: Path) -> Path | None:
    if not runs_root.exists():
        return None

    def sort_key(run_dir: Path) -> float:
        state = _load_json_file(run_dir / RUN_STATE_FILENAME)
        if state and isinstance(state.get("updated_at_utc"), str):
            try:
                return datetime.fromisoformat(state["updated_at_utc"]).timestamp()
            except ValueError:
                pass
        return run_dir.stat().st_mtime

    candidates = []
    for child in runs_root.iterdir():
        if not child.is_dir():
            continue
        state = _load_json_file(child / RUN_STATE_FILENAME)
        status = (state or {}).get("status")
        if status in {"running", "interrupted"}:
            candidates.append(child)
            continue
        checkpoint_dir = child / "checkpoint"
        if status != "completed" and checkpoint_dir.exists():
            candidates.append(child)
    if not candidates:
        return None
    candidates.sort(key=sort_key, reverse=True)
    return candidates[0]


def _create_run_id(args: argparse.Namespace, signature: dict[str, Any]) -> str:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    params_slug = _build_run_param_slug(args)
    digest = hashlib.sha1(
        json.dumps(signature, sort_keys=True, ensure_ascii=True).encode("utf-8")
    ).hexdigest()[:8]
    return f"{timestamp}_{params_slug}_{digest}"


def _resolve_summary_checkpoint_for_run(
    run_dir: Path,
    prefer_mc: bool,
) -> tuple[Path, bool, bool]:
    std_checkpoint = run_dir / "checkpoint" / "experiment_results_checkpoint.jsonl"
    mc_checkpoint = run_dir / "checkpoint" / "monte_carlo_experiment_results_checkpoint.jsonl"
    h2_checkpoint = run_dir / "checkpoint" / "stochastic_cvar_experiment_results_checkpoint.jsonl"
    if h2_checkpoint.exists() and not prefer_mc:
        return h2_checkpoint, False, True
    if prefer_mc:
        return mc_checkpoint, True, False
    if std_checkpoint.exists() and not mc_checkpoint.exists():
        return std_checkpoint, False, False
    if mc_checkpoint.exists() and not std_checkpoint.exists():
        return mc_checkpoint, True, False
    if std_checkpoint.exists() and mc_checkpoint.exists():
        return std_checkpoint, False, False
    return std_checkpoint, False, False


def resolve_solver_strategy(use_scip: bool) -> tuple[str, bool]:
    """Return initial solver and whether HiGHS->SCIP fallback is enabled."""
    if use_scip:
        return FALLBACK_SOLVER, False
    return DEFAULT_SOLVER, True


def _serialize_mc_config(config: IncomeMCConfig) -> dict:
    return dataclasses.asdict(config)


def _write_mc_outputs(
    output_path: Path,
    aggregates: list[MonteCarloAggregateResult],
    scenario_rows: list[dict],
    config: IncomeMCConfig,
    run_id: str | None = None,
) -> tuple[Path, Path, Path]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    scenario_path = output_path.with_name(f"{output_path.stem}_scenarios{output_path.suffix}")
    metadata_path = output_path.with_name(f"{output_path.stem}_meta.json")

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=MC_INSTANCE_CSV_COLUMNS)
        writer.writeheader()
        for item in aggregates:
            writer.writerow(dataclasses.asdict(item))

    with open(scenario_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=MC_SCENARIO_CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(scenario_rows)

    metadata = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "income_mc_config": _serialize_mc_config(config),
        "aggregates_file": str(output_path),
        "scenarios_file": str(scenario_path),
        "instance_count": len(aggregates),
        "scenario_count": len(scenario_rows),
    }
    if run_id is not None:
        metadata["run_id"] = run_id
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    return output_path, scenario_path, metadata_path


def _load_h2_checkpoint_results(
    checkpoint_path: Path | None,
) -> dict[str, StochasticRiskComparisonResult]:
    if checkpoint_path is None or not checkpoint_path.exists():
        return {}

    out: dict[str, StochasticRiskComparisonResult] = {}
    with open(checkpoint_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
                payload.setdefault("shortfall_rate_beta", None)
                result = StochasticRiskComparisonResult(**payload)
            except Exception:
                continue
            out[result.instance_name] = result
    return out


def _save_h2_checkpoint_result(
    checkpoint_path: Path | None,
    result: StochasticRiskComparisonResult,
) -> None:
    if checkpoint_path is None:
        return
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    with open(checkpoint_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(dataclasses.asdict(result), ensure_ascii=False) + "\n")


def _write_h2_outputs(
    output_path: Path,
    results: list[StochasticRiskComparisonResult],
    config: IncomeMCConfig,
    risk_alpha: float,
    risk_lambda: float,
    shortfall_epsilon: float,
    shortfall_rate_beta: float | None,
    run_id: str | None = None,
) -> tuple[Path, Path, Path]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    scenario_path = output_path.with_name(f"{output_path.stem}_scenarios{output_path.suffix}")
    metadata_path = output_path.with_name(f"{output_path.stem}_meta.json")

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=H2_INSTANCE_CSV_COLUMNS)
        writer.writeheader()
        for item in results:
            row = dataclasses.asdict(item)
            row.pop("deterministic_scenario_shortfalls", None)
            row.pop("stochastic_scenario_shortfalls", None)
            writer.writerow(row)

    with open(scenario_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=H2_SCENARIO_CSV_COLUMNS)
        writer.writeheader()
        for item in results:
            for idx, (det_sf, stoch_sf) in enumerate(
                zip(item.deterministic_scenario_shortfalls, item.stochastic_scenario_shortfalls)
            ):
                writer.writerow(
                    {
                        "instance_name": item.instance_name,
                        "scenario_index": idx,
                        "deterministic_shortfall": det_sf,
                        "stochastic_shortfall": stoch_sf,
                    }
                )

    metadata = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "income_mc_config": _serialize_mc_config(config),
        "risk_alpha": risk_alpha,
        "risk_lambda": risk_lambda,
        "shortfall_epsilon": shortfall_epsilon,
        "shortfall_rate_beta": shortfall_rate_beta,
        "aggregates_file": str(output_path),
        "scenarios_file": str(scenario_path),
        "instance_count": len(results),
        "scenario_count": int(sum(len(r.stochastic_scenario_shortfalls) for r in results)),
    }
    if run_id is not None:
        metadata["run_id"] = run_id
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    return output_path, scenario_path, metadata_path


def _shortfall_stats(
    scenario_shortfalls: np.ndarray,
    alpha: float,
    epsilon: float,
    monthly_shortfalls: np.ndarray | None = None,
) -> dict[str, float]:
    if scenario_shortfalls.size == 0:
        raise ValueError("scenario_shortfalls must not be empty")
    if not np.all(np.isfinite(scenario_shortfalls)):
        return {
            "mean": float("inf"),
            "median": float("inf"),
            "p90": float("inf"),
            "max": float("inf"),
            "cvar": float("inf"),
            "cash_shortfall_rate": 1.0,
        }
    return {
        "mean": float(np.mean(scenario_shortfalls)),
        "median": float(np.median(scenario_shortfalls)),
        "p90": float(np.percentile(scenario_shortfalls, 90)),
        "max": float(np.max(scenario_shortfalls)),
        "cvar": compute_cvar(scenario_shortfalls, alpha=alpha),
        "cash_shortfall_rate": compute_cash_shortfall_rate(
            monthly_shortfalls if monthly_shortfalls is not None else scenario_shortfalls,
            epsilon=epsilon,
        ),
    }


def _build_stochastic_cvar_result(
    *,
    instance,
    mc_config: IncomeMCConfig,
    risk_alpha: float,
    risk_lambda: float,
    shortfall_epsilon: float,
    shortfall_rate_beta: float | None,
    time_limit_seconds: int,
    solver_name: str,
    ru_mode: bool,
) -> StochasticRiskComparisonResult:
    instance_seed = derive_instance_seed(mc_config.seed, instance.name)
    instance_mc_config = dataclasses.replace(mc_config, seed=instance_seed)
    scenario_incomes = simulate_income_paths(instance.monthly_income, instance_mc_config)

    deterministic = solve_rpml(
        instance,
        time_limit_seconds=time_limit_seconds,
        solver_name=solver_name,
        ru_mode=ru_mode,
    )
    deterministic_ok = deterministic.status in ("OPTIMAL", "FEASIBLE")
    if deterministic_ok:
        deterministic_monthly_shortfalls, deterministic_scenario_shortfalls = (
            evaluate_fixed_plan_shortfalls(
                deterministic.payments,
                scenario_incomes,
            )
        )
    else:
        deterministic_monthly_shortfalls = np.full(
            scenario_incomes.shape, float("inf"), dtype=float
        )
        deterministic_scenario_shortfalls = np.full(
            scenario_incomes.shape[0], float("inf"), dtype=float
        )

    stochastic = solve_stochastic_rpml(
        instance=instance,
        scenario_incomes=scenario_incomes,
        risk_alpha=risk_alpha,
        risk_lambda=risk_lambda,
        shortfall_epsilon=shortfall_epsilon,
        shortfall_rate_beta=shortfall_rate_beta,
        time_limit_seconds=time_limit_seconds,
        solver_name=solver_name,
        ru_mode=ru_mode,
    )
    stochastic_scenario_shortfalls = np.asarray(
        stochastic.scenario_total_shortfalls, dtype=float
    )
    stochastic_monthly_shortfalls = np.asarray(
        stochastic.scenario_shortfalls, dtype=float
    )

    det_stats = _shortfall_stats(
        deterministic_scenario_shortfalls,
        alpha=risk_alpha,
        epsilon=shortfall_epsilon,
        monthly_shortfalls=deterministic_monthly_shortfalls,
    )
    stoch_stats = _shortfall_stats(
        stochastic_scenario_shortfalls,
        alpha=risk_alpha,
        epsilon=shortfall_epsilon,
        monthly_shortfalls=stochastic_monthly_shortfalls,
    )
    stoch_stats["cash_shortfall_rate"] = float(stochastic.cash_shortfall_rate)

    det_cost = float(deterministic.objective_value)
    stoch_cost = float(stochastic.total_payment_cost)
    delta_cost = (
        stoch_cost - det_cost
        if np.isfinite(det_cost) and np.isfinite(stoch_cost)
        else float("inf")
    )

    return StochasticRiskComparisonResult(
        instance_name=instance.name,
        n_loans=instance.n,
        n_scenarios=int(scenario_incomes.shape[0]),
        risk_alpha=risk_alpha,
        risk_lambda=risk_lambda,
        shortfall_epsilon=shortfall_epsilon,
        shortfall_rate_beta=shortfall_rate_beta,
        deterministic_status=deterministic.status,
        deterministic_cost=det_cost,
        deterministic_solve_time=float(deterministic.solve_time),
        deterministic_gap=float(deterministic.gap),
        deterministic_mean_shortfall=det_stats["mean"],
        deterministic_median_shortfall=det_stats["median"],
        deterministic_p90_shortfall=det_stats["p90"],
        deterministic_max_shortfall=det_stats["max"],
        deterministic_cvar_shortfall=det_stats["cvar"],
        deterministic_cash_shortfall_rate=det_stats["cash_shortfall_rate"],
        stochastic_status=stochastic.status,
        stochastic_total_payment_cost=stoch_cost,
        stochastic_objective_value=float(stochastic.objective_value),
        stochastic_solve_time=float(stochastic.solve_time),
        stochastic_gap=float(stochastic.gap),
        stochastic_mean_shortfall=stoch_stats["mean"],
        stochastic_median_shortfall=stoch_stats["median"],
        stochastic_p90_shortfall=stoch_stats["p90"],
        stochastic_max_shortfall=stoch_stats["max"],
        stochastic_cvar_shortfall=stoch_stats["cvar"],
        stochastic_cash_shortfall_rate=stoch_stats["cash_shortfall_rate"],
        delta_total_payment_cost=delta_cost,
        delta_cvar_shortfall=float(
            stoch_stats["cvar"] - det_stats["cvar"]
            if np.isfinite(stoch_stats["cvar"]) and np.isfinite(det_stats["cvar"])
            else float("inf")
        ),
        delta_cash_shortfall_rate=float(
            stoch_stats["cash_shortfall_rate"] - det_stats["cash_shortfall_rate"]
        ),
        deterministic_scenario_shortfalls=deterministic_scenario_shortfalls.astype(float).tolist(),
        stochastic_scenario_shortfalls=stochastic_scenario_shortfalls.astype(float).tolist(),
    )


def run_stochastic_cvar_experiments(
    dataset_path: Path,
    mc_config: IncomeMCConfig,
    risk_alpha: float,
    risk_lambda: float,
    shortfall_epsilon: float,
    shortfall_rate_beta: float | None = None,
    max_instances_per_group: int | None = None,
    time_limit_seconds: int = 300,
    verbose: bool = True,
    allowed_n_loans: tuple[int, ...] = (4, 8),
    solver_name: str = DEFAULT_SOLVER,
    checkpoint_path: Path | None = None,
    restart: bool = False,
    ru_mode: bool = False,
) -> list[StochasticRiskComparisonResult]:
    if restart and checkpoint_path is not None and checkpoint_path.exists():
        checkpoint_path.unlink()

    existing = _load_h2_checkpoint_results(checkpoint_path)
    processed = set(existing.keys())

    if verbose:
        print("Loading instances...")

    instances = load_all_instances(dataset_path)
    grouped = get_instances_by_size(instances)

    selected_instances = []
    for n_loans in allowed_n_loans:
        group_instances = grouped.get(n_loans, [])
        if max_instances_per_group:
            group_instances = group_instances[:max_instances_per_group]
        selected_instances.extend(group_instances)

    if verbose:
        print(f"Loaded {len(instances)} instances")
        print(f"Selected for H2: {len(selected_instances)} instances")
        if processed:
            print(f"Resuming H2: {len(processed)} instance(s) already in checkpoint")

    results: list[StochasticRiskComparisonResult] = list(existing.values())
    iterator = tqdm(selected_instances, file=sys.stdout) if verbose else selected_instances

    for instance in iterator:
        if instance.name in processed:
            if verbose:
                tqdm.write(f"Skipping {instance.name} (already processed in H2 checkpoint)", file=sys.stdout)
            continue

        try:
            result = _build_stochastic_cvar_result(
                instance=instance,
                mc_config=mc_config,
                risk_alpha=risk_alpha,
                risk_lambda=risk_lambda,
                shortfall_epsilon=shortfall_epsilon,
                shortfall_rate_beta=shortfall_rate_beta,
                time_limit_seconds=time_limit_seconds,
                solver_name=solver_name,
                ru_mode=ru_mode,
            )
            results.append(result)
            _save_h2_checkpoint_result(checkpoint_path, result)
            processed.add(instance.name)
        except Exception as exc:
            if verbose:
                print(f"\nError processing {instance.name} in stochastic CVaR mode: {exc}")
            continue

    results.sort(key=lambda item: item.instance_name)
    return results


def process_stochastic_cvar_instance(args_tuple):
    (
        instance,
        mc_config,
        risk_alpha,
        risk_lambda,
        shortfall_epsilon,
        shortfall_rate_beta,
        time_limit_seconds,
        solver_name,
        ru_mode,
    ) = args_tuple
    try:
        result = _build_stochastic_cvar_result(
            instance=instance,
            mc_config=mc_config,
            risk_alpha=risk_alpha,
            risk_lambda=risk_lambda,
            shortfall_epsilon=shortfall_epsilon,
            shortfall_rate_beta=shortfall_rate_beta,
            time_limit_seconds=time_limit_seconds,
            solver_name=solver_name,
            ru_mode=ru_mode,
        )
        return ("ok", result)
    except Exception as e:
        return ("error", instance.name, str(e))


def run_stochastic_cvar_experiments_parallel(
    dataset_path: Path,
    mc_config: IncomeMCConfig,
    risk_alpha: float,
    risk_lambda: float,
    shortfall_epsilon: float,
    shortfall_rate_beta: float | None = None,
    max_instances_per_group: int | None = None,
    time_limit_seconds: int = 300,
    verbose: bool = True,
    allowed_n_loans: tuple[int, ...] = (4, 8),
    solver_name: str = DEFAULT_SOLVER,
    n_workers: int | None = None,
    checkpoint_path: Path | None = None,
    restart: bool = False,
    ru_mode: bool = False,
) -> list[StochasticRiskComparisonResult]:
    from multiprocessing import cpu_count

    if restart and checkpoint_path is not None and checkpoint_path.exists():
        checkpoint_path.unlink()

    existing = _load_h2_checkpoint_results(checkpoint_path)
    processed = set(existing.keys())

    if verbose:
        print("Loading instances...")

    instances = load_all_instances(dataset_path)
    grouped = get_instances_by_size(instances)

    selected_instances = []
    for n_loans in allowed_n_loans:
        group_instances = grouped.get(n_loans, [])
        if max_instances_per_group:
            group_instances = group_instances[:max_instances_per_group]
        selected_instances.extend(group_instances)

    instances_to_process = [
        instance for instance in selected_instances if instance.name not in processed
    ]

    if verbose:
        print(f"Loaded {len(instances)} instances")
        print(f"Selected for H2: {len(selected_instances)} instances")
        if processed:
            print(f"Resuming H2: {len(processed)} instance(s) already in checkpoint")
        print(
            f"\nProcessing {len(instances_to_process)} instances in parallel with stochastic CVaR..."
        )

    worker_count = n_workers or cpu_count()
    if verbose:
        print(f"Using {worker_count} workers")

    args_list = [
        (
            instance,
            mc_config,
            risk_alpha,
            risk_lambda,
            shortfall_epsilon,
            shortfall_rate_beta,
            time_limit_seconds,
            solver_name,
            ru_mode,
        )
        for instance in instances_to_process
    ]

    results: list[StochasticRiskComparisonResult] = list(existing.values())
    executor = None
    submitted = []

    def _kill_executor_workers(current_executor) -> None:
        processes = getattr(current_executor, "_processes", {}) or {}
        for proc in processes.values():
            try:
                proc.kill()
            except Exception:
                pass
        try:
            current_executor.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass

    pbar_ctx = tqdm(total=len(args_list), file=sys.stdout) if verbose else nullcontext()
    try:
        with pbar_ctx as pbar:
            executor = futures.ProcessPoolExecutor(max_workers=worker_count)
            submitted = [
                executor.submit(process_stochastic_cvar_instance, args)
                for args in args_list
            ]
            for future in futures.as_completed(submitted):
                result = future.result()
                if result and result[0] == "ok":
                    h2_result = result[1]
                    results.append(h2_result)
                    _save_h2_checkpoint_result(checkpoint_path, h2_result)
                elif result and result[0] == "error" and verbose:
                    print(f"Error processing {result[1]} in stochastic CVaR mode: {result[2]}")
                if pbar is not None:
                    pbar.update(1)
    except KeyboardInterrupt:
        if verbose:
            print("\nInterrupted by user. Shutting down stochastic CVaR workers...")
        for future in submitted:
            if hasattr(future, "cancel"):
                future.cancel()
        if executor is not None:
            _kill_executor_workers(executor)
        raise
    finally:
        if executor is not None:
            try:
                executor.shutdown(wait=False, cancel_futures=True)
            except Exception:
                pass

    if checkpoint_path is not None:
        results = list(_load_h2_checkpoint_results(checkpoint_path).values())
    results.sort(key=lambda item: item.instance_name)
    return results


def load_timeout_instances(timeout_log_path: Path | None) -> set[str]:
    """Load timed-out instance names from timeout CSV log."""
    if timeout_log_path is None or not timeout_log_path.exists():
        return set()
    out: set[str] = set()
    try:
        with open(timeout_log_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = (row.get("instance_name") or "").strip()
                if name:
                    out.add(name)
    except Exception:
        # Best-effort log loading; experiment should still run.
        return set()
    return out


def append_timeout_records(timeout_log_path: Path | None, records: list[dict]) -> None:
    """Append unique timeout records to CSV log."""
    if timeout_log_path is None or not records:
        return
    timeout_log_path.parent.mkdir(parents=True, exist_ok=True)
    existing = load_timeout_instances(timeout_log_path)
    is_new_file = not timeout_log_path.exists()
    with open(timeout_log_path, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=TIMEOUT_CSV_COLUMNS)
        if is_new_file:
            writer.writeheader()
        for rec in records:
            name = rec.get("instance_name")
            if not name or name in existing:
                continue
            writer.writerow(rec)
            existing.add(name)


def remove_timeout_instances(timeout_log_path: Path | None, instance_names: set[str]) -> None:
    """Remove successfully solved instances from timeout CSV log."""
    if timeout_log_path is None or not timeout_log_path.exists() or not instance_names:
        return
    try:
        with open(timeout_log_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            rows = [row for row in reader if (row.get("instance_name") or "").strip() not in instance_names]
        with open(timeout_log_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=TIMEOUT_CSV_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
    except Exception:
        # Best-effort cleanup only.
        return


def run_experiments(
    dataset_path: Path,
    max_instances_per_group: int | None = None,
    time_limit_seconds: int = 300,
    verbose: bool = True,
    allowed_n_loans: tuple[int, ...] = (4, 8),
    checkpoint_path: Path | None = None,
    timeout_log_path: Path | None = None,
    skip_known_timeouts: bool = True,
    restart: bool = False,
    solver_name: str = DEFAULT_SOLVER,
    export_timelines: bool = False,
    timelines_dir: Path | None = None,
    ru_mode: bool = False,
) -> List[ComparisonResult]:
    """
    Run experiments on all instances.

    Results are saved incrementally to the checkpoint file. Already processed
    instances are skipped on resume.
    """
    if verbose:
        print("Loading instances...")

    instances = load_all_instances(dataset_path)
    grouped = get_instances_by_size(instances)

    if verbose:
        print(f"Loaded {len(instances)} instances")
        for n, group in grouped.items():
            print(f"  {n} loans: {len(group)} instances")

    checkpoint = (
        CheckpointManager(checkpoint_path, restart=restart)
        if checkpoint_path
        else None
    )
    processed = checkpoint.get_processed_instances() if checkpoint else set()
    
    if verbose and checkpoint_path:
        if processed:
            print(f"Resuming: {len(processed)} instances already in checkpoint")
        else:
            print("Starting fresh (no checkpoint found or checkpoint is empty)")

    known_timeouts = load_timeout_instances(timeout_log_path) if skip_known_timeouts else set()
    if verbose and timeout_log_path:
        if known_timeouts:
            print(f"Skipping {len(known_timeouts)} known timeout instance(s) from: {timeout_log_path}")
        else:
            print(f"No known timeout instances in: {timeout_log_path}")

    results = []

    for n_loans in allowed_n_loans:
        group_instances = grouped.get(n_loans, [])

        if not group_instances:
            continue

        if max_instances_per_group:
            group_instances = group_instances[:max_instances_per_group]

        if verbose:
            print(f"\nProcessing {n_loans}-loan instances ({len(group_instances)} instances)...")

        iterator = tqdm(group_instances, file=sys.stdout) if verbose else group_instances

        for instance in iterator:
            if instance.name in processed:
                if verbose:
                    tqdm.write(f"Skipping {instance.name} (already processed)", file=sys.stdout)
                continue
            if instance.name in known_timeouts:
                if verbose:
                    tqdm.write(f"Skipping {instance.name} (known timeout)", file=sys.stdout)
                continue

            try:
                baseline_instance = with_ru_prepayment_rules(instance) if ru_mode else instance
                optimal_solution = solve_rpml(
                    instance,
                    time_limit_seconds=time_limit_seconds,
                    solver_name=solver_name,
                    ru_mode=ru_mode,
                )

                avalanche_solution = debt_avalanche(baseline_instance)
                snowball_solution = debt_snowball(baseline_instance)
                avalanche_valid, avalanche_errors, avalanche_final_balance = validate_baseline_solution(
                    avalanche_solution, baseline_instance
                )
                snowball_valid, snowball_errors, snowball_final_balance = validate_baseline_solution(
                    snowball_solution, baseline_instance
                )
                avalanche_feasible = avalanche_valid and avalanche_final_balance < 1.0
                snowball_feasible = snowball_valid and snowball_final_balance < 1.0

                if optimal_solution.status not in ["OPTIMAL", "FEASIBLE"]:
                    if verbose:
                        tqdm.write(f"Warning: {instance.name} MILP status: {optimal_solution.status}", file=sys.stdout)
                if verbose and not avalanche_valid:
                    tqdm.write(
                        f"  {instance.name}: Debt Avalanche invalid ({'; '.join(avalanche_errors[:2])})",
                        file=sys.stdout,
                    )
                if verbose and not avalanche_feasible:
                    tqdm.write(
                        f"  {instance.name}: Debt Avalanche not repaid by T (max balance: {avalanche_final_balance:,.0f})",
                        file=sys.stdout,
                    )
                if verbose and not snowball_valid:
                    tqdm.write(
                        f"  {instance.name}: Debt Snowball invalid ({'; '.join(snowball_errors[:2])})",
                        file=sys.stdout,
                    )
                if verbose and not snowball_feasible:
                    tqdm.write(
                        f"  {instance.name}: Debt Snowball not repaid by T (max balance: {snowball_final_balance:,.0f})",
                        file=sys.stdout,
                    )

                comparison = compare_solutions(
                    optimal=optimal_solution,
                    avalanche=avalanche_solution,
                    snowball=snowball_solution,
                    instance_name=instance.name,
                    n_loans=n_loans,
                    avalanche_valid=avalanche_valid,
                    avalanche_repaid_by_T=avalanche_feasible,
                    avalanche_final_balance=avalanche_final_balance,
                    snowball_valid=snowball_valid,
                    snowball_repaid_by_T=snowball_feasible,
                    snowball_final_balance=snowball_final_balance,
                )

                if export_timelines and timelines_dir is not None:
                    export_timeline_json(
                        output_dir=timelines_dir,
                        instance=baseline_instance,
                        comparison=comparison,
                        optimal_solution=optimal_solution,
                        avalanche_solution=avalanche_solution,
                        snowball_solution=snowball_solution,
                    )

                results.append(comparison)
                if checkpoint:
                    checkpoint.save_result(comparison)
                remove_timeout_instances(timeout_log_path, {instance.name})
                processed.add(instance.name)

            except Exception as e:
                if verbose:
                    print(f"\nError processing {instance.name}: {e}")
                continue

    if checkpoint:
        results = list(checkpoint.load_existing_results().values())
    return results


def run_monte_carlo_experiments(
    dataset_path: Path,
    mc_config: IncomeMCConfig,
    max_instances_per_group: int | None = None,
    time_limit_seconds: int = 300,
    verbose: bool = True,
    allowed_n_loans: tuple[int, ...] = (4, 8),
    solver_name: str = DEFAULT_SOLVER,
    checkpoint_path: Path | None = None,
    restart: bool = False,
    ru_mode: bool = False,
) -> tuple[list[MonteCarloAggregateResult], list[dict], list[ComparisonResult]]:
    if verbose:
        print("Loading instances...")

    instances = load_all_instances(dataset_path)
    grouped = get_instances_by_size(instances)

    if verbose:
        print(f"Loaded {len(instances)} instances")
        print(f"  Selected loan counts: {list(allowed_n_loans)}")
        for n_loans in allowed_n_loans:
            group_instances = grouped.get(n_loans, [])
            if max_instances_per_group:
                group_instances = group_instances[:max_instances_per_group]
            print(f"  {n_loans} loans (selected): {len(group_instances)} instances")

    checkpoint = (
        CheckpointManager(checkpoint_path, restart=restart)
        if checkpoint_path is not None
        else None
    )
    checkpoint_results = checkpoint.load_existing_results() if checkpoint is not None else {}
    all_instances = []
    for n_loans in allowed_n_loans:
        group_instances = grouped.get(n_loans, [])
        if max_instances_per_group:
            group_instances = group_instances[:max_instances_per_group]
        all_instances.extend(group_instances)
    selected_base_instances = {inst.name for inst in all_instances}
    existing_by_instance: dict[str, dict[int, ComparisonResult]] = {
        inst_name: _get_monte_carlo_scenario_results(
            base_instance_name=inst_name,
            expected_scenarios=mc_config.n_scenarios,
            comparison_by_name=checkpoint_results,
        )
        for inst_name in selected_base_instances
    }
    completed_instances = {
        inst_name
        for inst_name in selected_base_instances
        if len(existing_by_instance.get(inst_name, {})) == mc_config.n_scenarios
    }
    if verbose and checkpoint_path is not None:
        if completed_instances:
            print(
                f"Resuming Monte Carlo: {len(completed_instances)} base instance(s) fully completed in checkpoint"
            )
        else:
            print("Monte Carlo checkpoint has no fully completed base instances")

    aggregates: list[MonteCarloAggregateResult] = []
    scenario_rows: list[dict] = []
    scenario_comparisons: list[ComparisonResult] = []

    for n_loans in allowed_n_loans:
        group_instances = grouped.get(n_loans, [])

        if not group_instances:
            continue

        if max_instances_per_group:
            group_instances = group_instances[:max_instances_per_group]

        if verbose:
            print(f"\nProcessing {n_loans}-loan instances ({len(group_instances)} instances) with Monte Carlo...")

        iterator = tqdm(group_instances, file=sys.stdout) if verbose else group_instances

        for instance in iterator:
            if instance.name in completed_instances:
                if verbose:
                    tqdm.write(
                        f"Skipping {instance.name} (Monte Carlo fully completed in checkpoint)",
                        file=sys.stdout,
                    )
                continue
            try:
                existing_results = existing_by_instance.get(instance.name, {})
                if verbose and existing_results:
                    tqdm.write(
                        _format_monte_carlo_resume_line(
                            base_instance_name=instance.name,
                            done_scenarios=len(existing_results),
                            total_scenarios=mc_config.n_scenarios,
                        ),
                        file=sys.stdout,
                    )
                aggregate, instance_rows, instance_comparisons = _run_monte_carlo_for_instance(
                    instance=instance,
                    mc_config=mc_config,
                    time_limit_seconds=time_limit_seconds,
                    solver_name=solver_name,
                    checkpoint_path=checkpoint_path,
                    existing_scenario_results=existing_results,
                    ru_mode=ru_mode,
                )
                aggregates.append(aggregate)
                scenario_rows.extend(instance_rows)
                scenario_comparisons.extend(instance_comparisons)
            except Exception as e:
                if verbose:
                    print(f"\nError processing {instance.name}: {e}")
                continue

    if checkpoint is not None:
        checkpoint_results = checkpoint.load_existing_results()
        return _build_monte_carlo_outputs_from_checkpoint(
            comparison_by_name=checkpoint_results,
            expected_scenarios=mc_config.n_scenarios,
            selected_base_instances=selected_base_instances,
        )
    _sort_monte_carlo_outputs(aggregates, scenario_rows, scenario_comparisons)
    return aggregates, scenario_rows, scenario_comparisons


def _run_monte_carlo_for_instance(
    *,
    instance,
    mc_config: IncomeMCConfig,
    time_limit_seconds: int,
    solver_name: str,
    checkpoint_path: Path | str | None = None,
    existing_scenario_results: dict[int, ComparisonResult] | None = None,
    ru_mode: bool = False,
    suppress_solver_output: bool = False,
) -> tuple[MonteCarloAggregateResult, list[dict], list[ComparisonResult]]:
    instance_seed = derive_instance_seed(mc_config.seed, instance.name)
    instance_mc_config = dataclasses.replace(mc_config, seed=instance_seed)
    incomes = simulate_income_paths(instance.monthly_income, instance_mc_config)

    existing_scenario_results = existing_scenario_results or {}
    scenario_rows: list[dict] = []
    scenario_comparisons: list[ComparisonResult] = []
    checkpoint = CheckpointManager(Path(checkpoint_path)) if checkpoint_path is not None else None
    for idx, scenario_income in enumerate(incomes):
        existing = existing_scenario_results.get(idx)
        if existing is not None:
            scenario_comparisons.append(existing)
            scenario_rows.append(
                {
                    "instance_name": instance.name,
                    "scenario_name": existing.instance_name,
                    "scenario_index": idx,
                    "status": existing.optimal_status,
                    "objective_cost": existing.optimal_cost,
                    "solve_time": existing.optimal_solve_time,
                    "gap": existing.optimal_gap,
                }
            )
            continue
        scenario_instance = replace_instance_income(instance, scenario_income, str(idx))
        baseline_instance = with_ru_prepayment_rules(scenario_instance) if ru_mode else scenario_instance
        with _suppress_native_solver_output(enabled=suppress_solver_output):
            solution = solve_rpml(
                scenario_instance,
                time_limit_seconds=time_limit_seconds,
                solver_name=solver_name,
                ru_mode=ru_mode,
            )
        scenario_rows.append(
            {
                "instance_name": instance.name,
                "scenario_name": scenario_instance.name,
                "scenario_index": idx,
                "status": solution.status,
                "objective_cost": solution.objective_value,
                "solve_time": solution.solve_time,
                "gap": solution.gap,
            }
        )
        avalanche_solution = debt_avalanche(baseline_instance)
        snowball_solution = debt_snowball(baseline_instance)
        avalanche_valid, _, avalanche_final_balance = validate_baseline_solution(
            avalanche_solution, baseline_instance
        )
        snowball_valid, _, snowball_final_balance = validate_baseline_solution(
            snowball_solution, baseline_instance
        )
        avalanche_feasible = avalanche_valid and avalanche_final_balance < 1.0
        snowball_feasible = snowball_valid and snowball_final_balance < 1.0
        comparison = compare_solutions(
                optimal=solution,
                avalanche=avalanche_solution,
                snowball=snowball_solution,
                instance_name=scenario_instance.name,
                n_loans=instance.n,
                avalanche_valid=avalanche_valid,
                avalanche_repaid_by_T=avalanche_feasible,
                avalanche_final_balance=avalanche_final_balance,
                snowball_valid=snowball_valid,
                snowball_repaid_by_T=snowball_feasible,
                snowball_final_balance=snowball_final_balance,
            )
        scenario_comparisons.append(comparison)
        if checkpoint is not None:
            checkpoint.save_result(comparison)

    aggregate = aggregate_monte_carlo_results_from_comparisons(
        instance_name=instance.name,
        n_loans=instance.n,
        scenario_results=scenario_comparisons,
    )
    return aggregate, scenario_rows, scenario_comparisons


def process_monte_carlo_instance(args_tuple):
    """
    Process one base instance in Monte Carlo mode (for multiprocessing).
    """
    if len(args_tuple) == 6:
        (
            instance,
            mc_config,
            time_limit_seconds,
            solver_name,
            checkpoint_path,
            existing_scenario_results,
        ) = args_tuple
        ru_mode = False
    else:
        (
            instance,
            mc_config,
            time_limit_seconds,
            solver_name,
            checkpoint_path,
            existing_scenario_results,
            ru_mode,
        ) = args_tuple
    try:
        aggregate, scenario_rows, scenario_comparisons = _run_monte_carlo_for_instance(
            instance=instance,
            mc_config=mc_config,
            time_limit_seconds=time_limit_seconds,
            solver_name=solver_name,
            checkpoint_path=checkpoint_path,
            existing_scenario_results=existing_scenario_results,
            ru_mode=ru_mode,
            suppress_solver_output=True,
        )
        return ("ok", aggregate, scenario_rows, scenario_comparisons)
    except Exception as e:
        return ("error", instance.name, str(e))


def _scenario_name_sort_key(name: str) -> tuple[str, int, str]:
    if "__mc_" in name:
        base, suffix = name.rsplit("__mc_", 1)
        if suffix.isdigit():
            return (base, int(suffix), name)
    return (name, 10**9, name)


def _sort_monte_carlo_outputs(
    aggregates: list[MonteCarloAggregateResult],
    scenario_rows: list[dict],
    scenario_comparisons: list[ComparisonResult],
) -> None:
    aggregates.sort(key=lambda item: item.instance_name)
    scenario_rows.sort(
        key=lambda row: (
            row.get("instance_name", ""),
            int(row.get("scenario_index", 0)),
            row.get("scenario_name", ""),
        )
    )
    scenario_comparisons.sort(key=lambda item: _scenario_name_sort_key(item.instance_name))


def _split_monte_carlo_scenario_name(name: str) -> tuple[str, int] | None:
    if "__mc_" not in name:
        return None
    base, suffix = name.rsplit("__mc_", 1)
    if not suffix.isdigit():
        return None
    return base, int(suffix)


def _is_monte_carlo_instance_complete(
    base_instance_name: str,
    expected_scenarios: int,
    comparison_by_name: dict[str, ComparisonResult],
) -> bool:
    return len(
        _get_monte_carlo_scenario_results(
            base_instance_name=base_instance_name,
            expected_scenarios=expected_scenarios,
            comparison_by_name=comparison_by_name,
        )
    ) == expected_scenarios


def _get_monte_carlo_scenario_results(
    *,
    base_instance_name: str,
    expected_scenarios: int,
    comparison_by_name: dict[str, ComparisonResult],
) -> dict[int, ComparisonResult]:
    out: dict[int, ComparisonResult] = {}
    for idx in range(expected_scenarios):
        scenario_name = f"{base_instance_name}__mc_{idx}"
        result = comparison_by_name.get(scenario_name)
        if result is not None:
            out[idx] = result
    return out


def _build_monte_carlo_outputs_from_checkpoint(
    comparison_by_name: dict[str, ComparisonResult],
    expected_scenarios: int,
    selected_base_instances: set[str],
) -> tuple[list[MonteCarloAggregateResult], list[dict], list[ComparisonResult]]:
    grouped: dict[str, list[ComparisonResult]] = {}
    for result in comparison_by_name.values():
        parsed = _split_monte_carlo_scenario_name(result.instance_name)
        if parsed is None:
            continue
        base_name, _ = parsed
        if base_name not in selected_base_instances:
            continue
        grouped.setdefault(base_name, []).append(result)

    aggregates: list[MonteCarloAggregateResult] = []
    scenario_rows: list[dict] = []
    scenario_comparisons: list[ComparisonResult] = []

    for base_name, results in grouped.items():
        by_idx: dict[int, ComparisonResult] = {}
        for result in results:
            parsed = _split_monte_carlo_scenario_name(result.instance_name)
            if parsed is None:
                continue
            _, idx = parsed
            by_idx[idx] = result
        if len(by_idx) < expected_scenarios:
            continue
        ordered = [by_idx[idx] for idx in range(expected_scenarios) if idx in by_idx]
        if len(ordered) != expected_scenarios:
            continue

        aggregates.append(
            aggregate_monte_carlo_results_from_comparisons(
                instance_name=base_name,
                n_loans=ordered[0].n_loans,
                scenario_results=ordered,
            )
        )
        scenario_comparisons.extend(ordered)
        for idx, result in enumerate(ordered):
            scenario_rows.append(
                {
                    "instance_name": base_name,
                    "scenario_name": result.instance_name,
                    "scenario_index": idx,
                    "status": result.optimal_status,
                    "objective_cost": result.optimal_cost,
                    "solve_time": result.optimal_solve_time,
                    "gap": result.optimal_gap,
                }
            )

    _sort_monte_carlo_outputs(aggregates, scenario_rows, scenario_comparisons)
    return aggregates, scenario_rows, scenario_comparisons


def _format_monte_carlo_resume_line(
    base_instance_name: str,
    done_scenarios: int,
    total_scenarios: int,
) -> str:
    remaining = max(total_scenarios - done_scenarios, 0)
    return (
        f"{base_instance_name}: resumed {done_scenarios}/{total_scenarios}, "
        f"remaining {remaining}"
    )


def run_monte_carlo_experiments_parallel(
    dataset_path: Path,
    mc_config: IncomeMCConfig,
    max_instances_per_group: int | None = None,
    time_limit_seconds: int = 300,
    verbose: bool = True,
    allowed_n_loans: tuple[int, ...] = (4, 8),
    solver_name: str = DEFAULT_SOLVER,
    n_workers: int | None = None,
    checkpoint_path: Path | None = None,
    restart: bool = False,
    ru_mode: bool = False,
) -> tuple[list[MonteCarloAggregateResult], list[dict], list[ComparisonResult]]:
    from multiprocessing import cpu_count

    if verbose:
        print("Loading instances...")

    instances = load_all_instances(dataset_path)
    grouped = get_instances_by_size(instances)

    if verbose:
        print(f"Loaded {len(instances)} instances")
        print(f"  Selected loan counts: {list(allowed_n_loans)}")
        for n_loans in allowed_n_loans:
            group_instances = grouped.get(n_loans, [])
            if max_instances_per_group:
                group_instances = group_instances[:max_instances_per_group]
            print(f"  {n_loans} loans (selected): {len(group_instances)} instances")

    all_instances = []
    for n_loans in allowed_n_loans:
        group_instances = grouped.get(n_loans, [])
        if not group_instances:
            continue
        if max_instances_per_group:
            group_instances = group_instances[:max_instances_per_group]
        all_instances.extend(group_instances)

    checkpoint = (
        CheckpointManager(checkpoint_path, restart=restart)
        if checkpoint_path is not None
        else None
    )
    checkpoint_results = checkpoint.load_existing_results() if checkpoint is not None else {}
    selected_base_instances = {inst.name for inst in all_instances}
    existing_by_instance: dict[str, dict[int, ComparisonResult]] = {
        inst_name: _get_monte_carlo_scenario_results(
            base_instance_name=inst_name,
            expected_scenarios=mc_config.n_scenarios,
            comparison_by_name=checkpoint_results,
        )
        for inst_name in selected_base_instances
    }
    completed_instances = {
        inst_name
        for inst_name in selected_base_instances
        if len(existing_by_instance.get(inst_name, {})) == mc_config.n_scenarios
    }
    instances_to_process = [
        inst for inst in all_instances if inst.name not in completed_instances
    ]

    if verbose:
        print(
            f"\nProcessing {len(instances_to_process)} instances in parallel with Monte Carlo..."
        )
        if completed_instances:
            print(
                f"  (Skipped {len(completed_instances)} base instance(s) fully completed in checkpoint)"
            )

    args_list = []
    for instance in instances_to_process:
        existing_results = existing_by_instance.get(instance.name, {})
        if verbose and existing_results:
            print(
                _format_monte_carlo_resume_line(
                    base_instance_name=instance.name,
                    done_scenarios=len(existing_results),
                    total_scenarios=mc_config.n_scenarios,
                )
            )
        args_list.append(
            (
                instance,
                mc_config,
                time_limit_seconds,
                solver_name,
                str(checkpoint_path) if checkpoint_path is not None else None,
                existing_results,
                ru_mode,
            )
        )

    worker_count = n_workers or cpu_count()
    if verbose:
        print(f"Using {worker_count} workers")

    aggregates: list[MonteCarloAggregateResult] = []
    scenario_rows: list[dict] = []
    scenario_comparisons: list[ComparisonResult] = []
    executor = None

    def _kill_executor_workers(current_executor) -> None:
        processes = getattr(current_executor, "_processes", {}) or {}
        for proc in processes.values():
            try:
                proc.kill()
            except Exception:
                pass
        try:
            current_executor.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass

    pbar_ctx = tqdm(total=len(args_list), file=sys.stdout) if verbose else nullcontext()
    submitted = []
    try:
        with pbar_ctx as pbar:
            executor = futures.ProcessPoolExecutor(max_workers=worker_count)
            submitted = [executor.submit(process_monte_carlo_instance, args) for args in args_list]
            for future in futures.as_completed(submitted):
                result = future.result()
                if result and result[0] == "ok":
                    aggregates.append(result[1])
                    scenario_rows.extend(result[2])
                    scenario_comparisons.extend(result[3])
                elif result and result[0] == "error" and verbose:
                    print(f"Error processing {result[1]}: {result[2]}")
                if pbar is not None:
                    pbar.update(1)
    except KeyboardInterrupt:
        if verbose:
            print("\nInterrupted by user. Shutting down Monte Carlo workers...")
        for future in submitted:
            if hasattr(future, "cancel"):
                future.cancel()
        if executor is not None:
            _kill_executor_workers(executor)
        raise
    finally:
        if executor is not None:
            try:
                executor.shutdown(wait=False, cancel_futures=True)
            except Exception:
                pass

    if checkpoint is not None:
        checkpoint_results = checkpoint.load_existing_results()
        return _build_monte_carlo_outputs_from_checkpoint(
            comparison_by_name=checkpoint_results,
            expected_scenarios=mc_config.n_scenarios,
            selected_base_instances=selected_base_instances,
        )
    _sort_monte_carlo_outputs(aggregates, scenario_rows, scenario_comparisons)
    return aggregates, scenario_rows, scenario_comparisons


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Run RPML experiments on Rios-Solis dataset",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    
    parser.add_argument(
        "-m", "--max-instances",
        type=int,
        default=None,
        metavar="N",
        help="Maximum instances per loan group (None = all)",
    )
    
    parser.add_argument(
        "-n", "--n-loans",
        type=int,
        nargs="+",
        default=[4, 8],
        metavar="N",
        help="Loan counts to process (e.g., -n 4 8 12)",
    )
    
    parser.add_argument(
        "-t", "--time-limit",
        type=int,
        default=300,
        metavar="SEC",
        help="Time limit for MILP solver in seconds",
    )
    parser.add_argument(
        "--watchdog-grace-seconds",
        type=int,
        default=15,
        metavar="SEC",
        help="Extra seconds above --time-limit before watchdog kills a stuck worker",
    )
    
    parser.add_argument(
        "-p", "--parallel",
        action="store_true",
        help="Enable multiprocessing for parallel instance solving",
    )
    
    parser.add_argument(
        "-w", "--workers",
        type=int,
        default=None,
        metavar="N",
        help="Number of parallel workers (default: CPU count)",
    )
    
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=None,
        metavar="PATH",
        help="Path to checkpoint file (default: tmp/experiment_results_checkpoint.jsonl)",
    )
    
    parser.add_argument(
        "--restart",
        action="store_true",
        help="Ignore existing checkpoint and start fresh",
    )
    
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Show summary of existing checkpoint results and exit (don't run experiments)",
    )
    parser.add_argument(
        "--timeout-log",
        type=Path,
        default=None,
        metavar="PATH",
        help="Path to timeout CSV log (default: tmp/timeout_instances.csv)",
    )
    parser.add_argument(
        "--include-known-timeouts",
        action="store_true",
        help="Process instances listed in timeout log instead of skipping them",
    )
    parser.add_argument(
        "--scip",
        action="store_true",
        help="Use SCIP directly for all instances and disable HiGHS->SCIP fallback",
    )
    parser.add_argument(
        "--ru",
        action="store_true",
        help="Apply RU repayment rules: no prepayment penalties and no prepayment prohibition",
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="Store all artifacts in isolated run directory under tmp/runs/<run_id>",
    )
    parser.add_argument(
        "--run-id",
        type=str,
        default=None,
        metavar="ID",
        help="Use existing run id (resume) or create run directory with this id",
    )
    parser.add_argument(
        "--resume-last",
        action="store_true",
        help="Resume the latest unfinished run from runs directory",
    )
    parser.add_argument(
        "--runs-dir",
        type=Path,
        default=None,
        metavar="PATH",
        help="Root directory containing run folders (default: tmp/runs)",
    )
    parser.add_argument(
        "--force-params-mismatch",
        action="store_true",
        help="Allow run resume even if current parameters differ from saved run config",
    )
    parser.add_argument(
        "--export-timelines",
        action="store_true",
        help="Export per-instance monthly trajectories to JSON files",
    )
    parser.add_argument(
        "--timelines-dir",
        type=Path,
        default=None,
        metavar="PATH",
        help="Directory for timeline JSON files (default: tmp/timelines)",
    )
    parser.add_argument(
        "--mc-income",
        action="store_true",
        help="Enable Monte Carlo simulation mode for monthly income scenarios",
    )
    parser.add_argument(
        "--mc-scenarios",
        type=int,
        default=16,
        metavar="N",
        help="Number of Monte Carlo scenarios per instance",
    )
    parser.add_argument(
        "--mc-seed",
        type=int,
        default=42,
        metavar="N",
        help="Base seed for Monte Carlo scenario generation",
    )
    parser.add_argument(
        "--mc-rho",
        type=float,
        default=0.55,
        metavar="RHO",
        help="AR(1) correlation for Monte Carlo income shocks",
    )
    parser.add_argument(
        "--mc-sigma",
        type=float,
        default=0.15,
        metavar="SIGMA",
        help="Log-scale volatility for Monte Carlo income shocks",
    )
    parser.add_argument(
        "--mc-shock-prob",
        type=float,
        default=0.04,
        metavar="P",
        help="Per-month probability of negative income shock",
    )
    parser.add_argument(
        "--mc-shock-severity",
        type=float,
        default=0.30,
        metavar="S",
        help="Mean severity of negative income shock in [0, 1]",
    )
    parser.add_argument(
        "--mc-output",
        type=Path,
        default=None,
        metavar="PATH",
        help="CSV path for Monte Carlo aggregated results (default: tmp/mc_income_results.csv)",
    )
    parser.add_argument(
        "--stochastic-cvar",
        action="store_true",
        help="Enable stochastic RPML mode with CVaR objective on scenario shortfalls",
    )
    parser.add_argument(
        "--risk-alpha",
        type=float,
        default=0.95,
        metavar="A",
        help="CVaR confidence level alpha in (0, 1)",
    )
    parser.add_argument(
        "--risk-lambda",
        type=float,
        default=1.0,
        metavar="L",
        help="Weight of CVaR term in objective",
    )
    parser.add_argument(
        "--shortfall-epsilon",
        type=float,
        default=1e-6,
        metavar="EPS",
        help="Threshold for counting scenario cash shortfall event",
    )
    parser.add_argument(
        "--shortfall-rate-beta",
        type=float,
        default=None,
        metavar="B",
        help="Upper bound on Cash Shortfall Rate in [0, 1]",
    )
    parser.add_argument(
        "--h2-output",
        type=Path,
        default=None,
        metavar="PATH",
        help="CSV path for stochastic CVaR aggregated results",
    )
    
    args = parser.parse_args()
    if args.run_id and args.resume_last:
        parser.error("--run-id and --resume-last cannot be used together")
    run_mode_requested = bool(
        args.run or args.run_id is not None or args.resume_last or args.runs_dir is not None
    )
    if args.force_params_mismatch and not run_mode_requested:
        parser.error("--force-params-mismatch requires run mode (--run/--run-id/--resume-last)")
    if args.stochastic_cvar and args.risk_lambda < 0:
        parser.error("--risk-lambda must be >= 0")
    if args.stochastic_cvar and not (0.0 < args.risk_alpha < 1.0):
        parser.error("--risk-alpha must be in (0, 1)")
    if args.stochastic_cvar and args.shortfall_epsilon < 0:
        parser.error("--shortfall-epsilon must be >= 0")
    if (
        args.stochastic_cvar
        and args.shortfall_rate_beta is not None
        and not (0.0 <= args.shortfall_rate_beta <= 1.0)
    ):
        parser.error("--shortfall-rate-beta must be in [0, 1]")
    return args


def process_instance(args_tuple):
    """Process a single instance (for multiprocessing)."""
    (
        instance,
        time_limit_seconds,
        verbose,
        checkpoint_path,
        processed_set,
        solver_name,
        export_timelines,
        timelines_dir_str,
        ru_mode,
    ) = args_tuple

    if processed_set is not None and instance.name in processed_set:
        return ("skip_processed", instance.name)

    try:
        baseline_instance = with_ru_prepayment_rules(instance) if ru_mode else instance
        with _suppress_native_solver_output(enabled=True):
            optimal_solution = solve_rpml(
                instance,
                time_limit_seconds=time_limit_seconds,
                solver_name=solver_name,
                ru_mode=ru_mode,
            )

        avalanche_solution = debt_avalanche(baseline_instance)
        snowball_solution = debt_snowball(baseline_instance)
        avalanche_valid, _, avalanche_final_balance = validate_baseline_solution(
            avalanche_solution, baseline_instance
        )
        snowball_valid, _, snowball_final_balance = validate_baseline_solution(
            snowball_solution, baseline_instance
        )
        avalanche_feasible = avalanche_valid and avalanche_final_balance < 1.0
        snowball_feasible = snowball_valid and snowball_final_balance < 1.0

        comparison = compare_solutions(
            optimal=optimal_solution,
            avalanche=avalanche_solution,
            snowball=snowball_solution,
            instance_name=instance.name,
            n_loans=instance.n,
            avalanche_valid=avalanche_valid,
            avalanche_repaid_by_T=avalanche_feasible,
            avalanche_final_balance=avalanche_final_balance,
            snowball_valid=snowball_valid,
            snowball_repaid_by_T=snowball_feasible,
            snowball_final_balance=snowball_final_balance,
        )

        if export_timelines and timelines_dir_str is not None:
            export_timeline_json(
                output_dir=Path(timelines_dir_str),
                instance=baseline_instance,
                comparison=comparison,
                optimal_solution=optimal_solution,
                avalanche_solution=avalanche_solution,
                snowball_solution=snowball_solution,
            )

        if checkpoint_path is not None:
            checkpoint = CheckpointManager(Path(str(checkpoint_path)))
            checkpoint.save_result(comparison)
        status = optimal_solution.status
        result_kind = "ok" if status in ("OPTIMAL", "FEASIBLE") else "ok_infeasible"
        return (result_kind, comparison, solver_name)

    except Exception as e:
        return ("error", instance.name, str(e), solver_name)


def run_experiments_parallel(
    dataset_path: Path,
    max_instances_per_group: int | None = None,
    time_limit_seconds: int = 300,
    watchdog_grace_seconds: int = 15,
    verbose: bool = True,
    allowed_n_loans: tuple[int, ...] = (4, 8),
    n_workers: int | None = None,
    checkpoint_path: Path | None = None,
    timeout_log_path: Path | None = None,
    skip_known_timeouts: bool = True,
    restart: bool = False,
    initial_solver_name: str = DEFAULT_SOLVER,
    enable_solver_fallback: bool = True,
    export_timelines: bool = False,
    timelines_dir: Path | None = None,
    ru_mode: bool = False,
) -> List[ComparisonResult]:
    """
    Run experiments on all instances using multiprocessing.

    Results are saved incrementally to the checkpoint file. Already processed
    instances are skipped on resume.
    """
    from multiprocessing import cpu_count

    if verbose:
        print("Loading instances...")

    instances = load_all_instances(dataset_path)
    grouped = get_instances_by_size(instances)

    if verbose:
        print(f"Loaded {len(instances)} instances")
        for n, group in grouped.items():
            print(f"  {n} loans: {len(group)} instances")

    all_instances = []
    for n_loans in allowed_n_loans:
        group_instances = grouped.get(n_loans, [])

        if not group_instances:
            continue

        if max_instances_per_group:
            group_instances = group_instances[:max_instances_per_group]

        all_instances.extend(group_instances)

    checkpoint = (
        CheckpointManager(checkpoint_path, restart=restart)
        if checkpoint_path
        else None
    )
    processed = checkpoint.get_processed_instances() if checkpoint else set()
    
    if verbose and checkpoint_path:
        if processed:
            print(f"Resuming: {len(processed)} instances already in checkpoint")
        else:
            print("Starting fresh (no checkpoint found or checkpoint is empty)")

    known_timeouts = load_timeout_instances(timeout_log_path) if skip_known_timeouts else set()
    to_process = [
        inst
        for inst in all_instances
        if inst.name not in processed and inst.name not in known_timeouts
    ]
    if verbose:
        print(f"\nProcessing {len(to_process)} instances in parallel...")
        if processed:
            print(f"  (Skipped {len(all_instances) - len(to_process)} already processed)")
        if known_timeouts:
            print(f"  (Skipped {len(known_timeouts)} known timeout instance(s))")

    ck_path_str = str(checkpoint_path) if checkpoint_path else None
    timelines_dir_str = str(timelines_dir) if timelines_dir else None
    args_list = [
        (
            inst,
            time_limit_seconds,
            False,
            ck_path_str,
            processed,
            initial_solver_name,
            export_timelines,
            timelines_dir_str,
            ru_mode,
        )
        for inst in to_process
    ]

    n_workers = n_workers or cpu_count()
    if verbose:
        print(f"Using {n_workers} workers")

    # External hard timeout per worker task. Keep it close to the MILP limit so
    # a hung solver does not stall the pool much longer than requested.
    per_instance_timeout = time_limit_seconds + watchdog_grace_seconds

    from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
    import time
    from collections import deque

    def _kill_executor_workers(executor: ProcessPoolExecutor) -> None:
        # Hard-stop worker processes when a solver run hangs (ignores internal limits).
        processes = getattr(executor, "_processes", {}) or {}
        for proc in processes.values():
            try:
                proc.kill()
            except Exception:
                pass
        executor.shutdown(wait=False, cancel_futures=True)

    raw_results = []
    pending_args = deque(args_list)
    completed_instances = set(processed)
    pbar_ctx = tqdm(total=len(args_list), file=sys.stdout) if verbose else nullcontext()

    try:
        with pbar_ctx as pbar:
            while pending_args:
                executor = ProcessPoolExecutor(max_workers=n_workers)
                inflight: dict = {}
                try:
                    while pending_args and len(inflight) < n_workers:
                        args = pending_args.popleft()
                        future = executor.submit(process_instance, args)
                        inflight[future] = (args, time.time())

                    while inflight:
                        done, _ = wait(inflight.keys(), timeout=1.0, return_when=FIRST_COMPLETED)

                        # Consume completed futures first
                        for future in done:
                            (args, _) = inflight.pop(future)
                            inst = args[0]
                            try:
                                result = future.result()
                                raw_results.append(result)
                                if result and result[0] in ("ok", "ok_infeasible"):
                                    remove_timeout_instances(timeout_log_path, {inst.name})
                                    completed_instances.add(inst.name)
                            except Exception as e:
                                raw_results.append(("error", inst.name, str(e)))
                            finally:
                                if pbar is not None:
                                    pbar.update(1)

                        # Backfill workers
                        while pending_args and len(inflight) < n_workers:
                            args = pending_args.popleft()
                            future = executor.submit(process_instance, args)
                            inflight[future] = (args, time.time())

                        # Watchdog: if any task runs too long, kill the whole pool and continue.
                        now = time.time()
                        timed_out = [
                            (future, args)
                            for future, (args, started_at) in inflight.items()
                            if (now - started_at) > per_instance_timeout
                        ]
                        if timed_out:
                            timeout_names = [args[0].name for _, args in timed_out]
                            timeout_records = []
                            for _, args in timed_out:
                                inst = args[0]
                                solver_name = args[5]
                                if enable_solver_fallback and solver_name == DEFAULT_SOLVER:
                                    retry_args = (
                                        inst,
                                        time_limit_seconds,
                                        False,
                                        ck_path_str,
                                        processed,
                                        FALLBACK_SOLVER,
                                        export_timelines,
                                        timelines_dir_str,
                                        ru_mode,
                                    )
                                    pending_args.appendleft(retry_args)
                                    if verbose:
                                        print(f"\nRetrying {inst.name} with {FALLBACK_SOLVER} after {DEFAULT_SOLVER} timeout")
                                else:
                                    raw_results.append(
                                        ("error", inst.name, f"Watchdog timeout > {per_instance_timeout:.0f}s after {solver_name}")
                                    )
                                    completed_instances.add(inst.name)
                                    timeout_records.append(
                                        {
                                            "instance_name": inst.name,
                                            "n_loans": inst.n,
                                            "time_limit_seconds": time_limit_seconds,
                                            "watchdog_timeout_seconds": int(per_instance_timeout),
                                            "reason": f"watchdog_timeout_after_{solver_name.lower()}",
                                            "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
                                        }
                                    )
                                    if pbar is not None:
                                        pbar.update(1)
                            append_timeout_records(timeout_log_path, timeout_records)

                            # Requeue non-timeout in-flight tasks (they were killed with the pool).
                            for future, (args, _) in inflight.items():
                                if args[0].name not in timeout_names:
                                    pending_args.appendleft(args)
                            inflight.clear()

                            if verbose:
                                print(
                                    f"\nWatchdog: killed worker pool due to timeout on {len(timeout_names)} instance(s): "
                                    + ", ".join(timeout_names[:3])
                                    + ("..." if len(timeout_names) > 3 else "")
                                )
                            _kill_executor_workers(executor)
                            break
                except KeyboardInterrupt:
                    print("\nInterrupted by user. Shutting down workers...")
                    _kill_executor_workers(executor)
                    raise
                finally:
                    try:
                        executor.shutdown(wait=False, cancel_futures=True)
                    except Exception:
                        pass

                # Filter out already completed args after a watchdog restart.
                if pending_args:
                    pending_args = deque([a for a in pending_args if a[0].name not in completed_instances])
    except KeyboardInterrupt:
        if verbose:
            print("\nInterrupted by user. Workers terminated.")
        raise

    for r in raw_results:
        if r is None:
            continue
        if r[0] == "skip_processed":
            pass
        elif r[0] == "skip_status" and verbose:
            print(f"  Skipped {r[1]}: status {r[2]}")
        elif r[0] == "error" and verbose:
            print(f"  Error {r[1]}: {r[2]}")

    if checkpoint:
        return list(checkpoint.load_existing_results().values())
    results = []
    for r in raw_results:
        if r is not None and r[0] in ("ok", "ok_infeasible"):
            results.append(r[1])
    return results


def main():
    """Main entry point."""
    global LAST_SHUTDOWN_SIGNAL
    LAST_SHUTDOWN_SIGNAL = None
    previous_signal_handlers = _install_shutdown_signal_handlers()
    run_dir: Path | None = None
    try:
        args = parse_args()

        default_args = {
            "max_instances": None,
            "n_loans": [4, 8],
            "time_limit": 300,
            "watchdog_grace_seconds": 15,
            "parallel": False,
            "workers": None,
            "checkpoint": None,
            "restart": False,
            "summary": False,
            "timeout_log": None,
            "include_known_timeouts": False,
            "scip": False,
            "ru": False,
            "run": False,
            "run_id": None,
            "resume_last": False,
            "runs_dir": None,
            "force_params_mismatch": False,
            "export_timelines": False,
            "timelines_dir": None,
            "mc_income": False,
            "mc_scenarios": 16,
            "mc_seed": 42,
            "mc_rho": 0.55,
            "mc_sigma": 0.15,
            "mc_shock_prob": 0.04,
            "mc_shock_severity": 0.30,
            "stochastic_cvar": False,
            "risk_alpha": 0.95,
            "risk_lambda": 1.0,
            "shortfall_epsilon": 1e-6,
            "shortfall_rate_beta": None,
            "h2_output": None,
            "mc_output": None,
        }
        for key, value in default_args.items():
            if not hasattr(args, key):
                setattr(args, key, value)

        dataset_path = PROJECT_ROOT / "RiosSolisDataset" / "Instances" / "Instances"
        if not dataset_path.exists():
            print(f"Error: Dataset path not found: {dataset_path}")
            return 1

        initial_solver_name, enable_solver_fallback = resolve_solver_strategy(args.scip)
        base_tmp_dir = PROJECT_ROOT / "tmp"
        stochastic_cvar_mode = bool(getattr(args, "stochastic_cvar", False))
        run_mode_requested = bool(
            args.run or args.run_id is not None or args.resume_last or args.runs_dir is not None
        )
        run_id: str | None = None
        runs_root = args.runs_dir or (base_tmp_dir / "runs")
        effective_mc_mode = bool(args.mc_income)
        effective_h2_mode = stochastic_cvar_mode

        if run_mode_requested:
            runs_root.mkdir(parents=True, exist_ok=True)
            if args.summary and args.run_id is None and not args.resume_last and args.checkpoint is None:
                print("Error: --summary with run mode requires --run-id or --resume-last (or explicit --checkpoint).")
                return 1
            if args.resume_last:
                resume_dir = _find_resume_last_run_dir(runs_root)
                if resume_dir is None:
                    print(f"Error: no unfinished runs found in {runs_root}")
                    return 1
                run_dir = resume_dir
                run_id = run_dir.name
            elif args.run_id is not None:
                run_id = _slugify_token(args.run_id)
                run_dir = runs_root / run_id
            else:
                run_signature = _build_run_signature(args, initial_solver_name)
                run_id = _create_run_id(args, run_signature)
                run_dir = runs_root / run_id

            if run_dir is None:
                print("Error: failed to resolve run directory")
                return 1
            if args.summary and args.run_id is not None and not run_dir.exists():
                print(f"Error: run '{run_id}' not found in {runs_root}")
                return 1
            run_dir.mkdir(parents=True, exist_ok=True)
            if not args.summary:
                run_signature = _build_run_signature(args, initial_solver_name)
                run_config_path = run_dir / RUN_CONFIG_FILENAME
                existing_config = _load_json_file(run_config_path)
                existing_signature = (existing_config or {}).get("signature")
                if (
                    existing_signature is not None
                    and existing_signature != run_signature
                    and not args.force_params_mismatch
                ):
                    print(f"Error: run '{run_id}' has different parameters in {run_config_path}")
                    print("Use --force-params-mismatch to continue or start a new run.")
                    return 1

                config_payload = {
                    "run_id": run_id,
                    "created_at_utc": (existing_config or {}).get(
                        "created_at_utc",
                        datetime.now(timezone.utc).isoformat(),
                    ),
                    "updated_at_utc": datetime.now(timezone.utc).isoformat(),
                    "signature": run_signature,
                    "cli_args": vars(args),
                }
                _write_json_file(run_config_path, config_payload)

            tmp_dir = run_dir
            mc_tmp_dir = run_dir / "monte_carlo"
            h2_tmp_dir = run_dir / "stochastic_cvar"
            if args.summary and args.checkpoint is None:
                (
                    default_checkpoint_path,
                    effective_mc_mode,
                    effective_h2_mode,
                ) = _resolve_summary_checkpoint_for_run(
                    run_dir,
                    args.mc_income,
                )
            else:
                if effective_h2_mode:
                    default_checkpoint_path = (
                        run_dir / "checkpoint" / "stochastic_cvar_experiment_results_checkpoint.jsonl"
                    )
                else:
                    default_checkpoint_path = (
                        run_dir / "checkpoint" / "monte_carlo_experiment_results_checkpoint.jsonl"
                        if effective_mc_mode
                        else run_dir / "checkpoint" / "experiment_results_checkpoint.jsonl"
                    )
            default_timeout_log_path = (
                run_dir / "logs" / "monte_carlo_timeout_instances.csv"
                if effective_mc_mode
                else run_dir / "logs" / "timeout_instances.csv"
            )
            if effective_h2_mode:
                default_results_csv_path = (
                    run_dir / "exports" / "stochastic_cvar_experiment_results.csv"
                )
            else:
                default_results_csv_path = (
                    run_dir / "exports" / "monte_carlo_experiment_results.csv"
                    if effective_mc_mode
                    else run_dir / "exports" / "experiment_results.csv"
                )
            default_timelines_dir = run_dir / "timelines"
        else:
            tmp_dir = base_tmp_dir / "ru" if args.ru else base_tmp_dir
            mc_tmp_dir = tmp_dir / "monte_carlo"
            h2_tmp_dir = tmp_dir / "stochastic_cvar"
            if effective_h2_mode:
                default_checkpoint_path = h2_tmp_dir / "experiment_results_checkpoint.jsonl"
            else:
                default_checkpoint_path = (
                    mc_tmp_dir / "experiment_results_checkpoint.jsonl"
                    if effective_mc_mode
                    else tmp_dir / "experiment_results_checkpoint.jsonl"
                )
            default_timeout_log_path = (
                mc_tmp_dir / "timeout_instances.csv"
                if effective_mc_mode
                else tmp_dir / "timeout_instances.csv"
            )
            if effective_h2_mode:
                default_results_csv_path = h2_tmp_dir / "experiment_results.csv"
            else:
                default_results_csv_path = (
                    mc_tmp_dir / "experiment_results.csv"
                    if effective_mc_mode
                    else tmp_dir / "experiment_results.csv"
                )
            default_timelines_dir = tmp_dir / "timelines"

        checkpoint_path = args.checkpoint or default_checkpoint_path
        timeout_log_path = args.timeout_log or default_timeout_log_path
        timelines_dir = args.timelines_dir or default_timelines_dir

        if args.summary:
            print("=" * 60)
            print("RPML EXPERIMENT RESULTS SUMMARY")
            print("=" * 60)
            if run_mode_requested:
                print(f"Run ID: {run_id}")
                print(f"Run dir: {run_dir}")
            print(f"\nLoading results from: {checkpoint_path}\n")
            if not checkpoint_path.exists():
                print("No checkpoint file found for the selected run/path.")
                return 0

            if effective_h2_mode:
                h2_results = list(_load_h2_checkpoint_results(checkpoint_path).values())
                if not h2_results:
                    print("No stochastic CVaR results found in checkpoint.")
                    return 0
                print_stochastic_risk_summary(h2_results)
                mc_config = IncomeMCConfig(
                    n_scenarios=args.mc_scenarios,
                    seed=args.mc_seed,
                    rho=args.mc_rho,
                    sigma=args.mc_sigma,
                    shock_prob=args.mc_shock_prob,
                    shock_severity_mean=args.mc_shock_severity,
                    shock_severity_std=max(args.mc_shock_severity * 0.25, 0.01),
                    min_income_floor=1.0,
                )
                csv_path = args.h2_output or default_results_csv_path
                instance_csv, scenario_csv, metadata_json = _write_h2_outputs(
                    output_path=csv_path,
                    results=h2_results,
                    config=mc_config,
                    risk_alpha=args.risk_alpha,
                    risk_lambda=args.risk_lambda,
                    shortfall_epsilon=args.shortfall_epsilon,
                    shortfall_rate_beta=args.shortfall_rate_beta,
                    run_id=run_id,
                )
                print(f"\nResults exported to: {instance_csv}")
                print(f"Scenario export: {scenario_csv}")
                print(f"Metadata export: {metadata_json}")
                return 0

            checkpoint = CheckpointManager(checkpoint_path)
            results = list(checkpoint.load_existing_results().values())
            if not results:
                print("No results found in checkpoint.")
                return 0
            print_summary(results)

            csv_path = default_results_csv_path
            checkpoint.export_to_csv(csv_path)
            if results:
                print(f"\nResults exported to: {csv_path}")
            return 0

        print("=" * 60)
        print("RPML EXPERIMENTS")
        print("=" * 60)
        print("\nRunning experiments on Rios-Solis dataset...")
        print("Comparing optimal MILP with Debt Avalanche and Debt Snowball baselines.")
        print(f"\nParameters:")
        print(f"  Max instances per group: {args.max_instances or 'all'}")
        print(f"  Loan counts: {args.n_loans}")
        print(f"  Time limit: {args.time_limit}s")
        print(f"  Watchdog timeout: {args.time_limit + args.watchdog_grace_seconds}s")
        print(f"  Initial solver: {initial_solver_name}")
        print(f"  HiGHS->SCIP fallback: {'enabled' if enable_solver_fallback else 'disabled'}")
        print(f"  RU mode: {'enabled' if args.ru else 'disabled'}")
        print(f"  Run mode: {'enabled' if run_mode_requested else 'disabled'}")
        if run_mode_requested:
            print(f"  Runs root: {runs_root}")
            print(f"  Run ID: {run_id}")
            print(f"  Run dir: {run_dir}")
        print(f"  Multiprocessing: {'enabled' if args.parallel else 'disabled'}")
        if args.parallel:
            print(f"  Workers: {args.workers or 'auto (CPU count)'}")
        print(f"  Checkpoint: {checkpoint_path}")
        print(f"  Timeout log: {timeout_log_path}")
        print(f"  Export timelines: {'yes' if args.export_timelines else 'no'}")
        if args.export_timelines:
            print(f"  Timelines dir: {timelines_dir}")
        print(f"  Stochastic CVaR mode: {'yes' if stochastic_cvar_mode else 'no'}")
        print(f"  Monte Carlo income mode: {'yes' if args.mc_income else 'no'}")
        if args.mc_income or stochastic_cvar_mode:
            print(f"  MC scenarios: {args.mc_scenarios}")
            print(f"  MC seed: {args.mc_seed}")
            print(f"  MC rho: {args.mc_rho}")
            print(f"  MC sigma: {args.mc_sigma}")
            print(f"  MC shock prob: {args.mc_shock_prob}")
            print(f"  MC shock severity: {args.mc_shock_severity}")
        if stochastic_cvar_mode:
            print(f"  CVaR alpha: {args.risk_alpha}")
            print(f"  Risk lambda: {args.risk_lambda}")
            print(f"  Shortfall epsilon: {args.shortfall_epsilon}")
            print(
                "  Shortfall rate beta: "
                + ("none" if args.shortfall_rate_beta is None else str(args.shortfall_rate_beta))
            )
        print(f"  Skip known timeouts: {'no' if args.include_known_timeouts else 'yes'}")
        if args.restart:
            print("  Restart: yes (ignoring existing checkpoint)")
        print()

        try:
            if run_dir is not None:
                _write_run_state(run_dir, "running")

            if stochastic_cvar_mode:
                h2_output_path = args.h2_output or (h2_tmp_dir / "stochastic_cvar_results.csv")
                mc_config = IncomeMCConfig(
                    n_scenarios=args.mc_scenarios,
                    seed=args.mc_seed,
                    rho=args.mc_rho,
                    sigma=args.mc_sigma,
                    shock_prob=args.mc_shock_prob,
                    shock_severity_mean=args.mc_shock_severity,
                    shock_severity_std=max(args.mc_shock_severity * 0.25, 0.01),
                    min_income_floor=1.0,
                )
                mc_config.validate()

                if args.parallel:
                    h2_results = run_stochastic_cvar_experiments_parallel(
                        dataset_path=dataset_path,
                        mc_config=mc_config,
                        risk_alpha=args.risk_alpha,
                        risk_lambda=args.risk_lambda,
                        shortfall_epsilon=args.shortfall_epsilon,
                        shortfall_rate_beta=args.shortfall_rate_beta,
                        max_instances_per_group=args.max_instances,
                        time_limit_seconds=args.time_limit,
                        verbose=True,
                        allowed_n_loans=tuple(args.n_loans),
                        solver_name=initial_solver_name,
                        n_workers=args.workers,
                        checkpoint_path=checkpoint_path,
                        restart=args.restart,
                        ru_mode=args.ru,
                    )
                else:
                    h2_results = run_stochastic_cvar_experiments(
                        dataset_path=dataset_path,
                        mc_config=mc_config,
                        risk_alpha=args.risk_alpha,
                        risk_lambda=args.risk_lambda,
                        shortfall_epsilon=args.shortfall_epsilon,
                        shortfall_rate_beta=args.shortfall_rate_beta,
                        max_instances_per_group=args.max_instances,
                        time_limit_seconds=args.time_limit,
                        verbose=True,
                        allowed_n_loans=tuple(args.n_loans),
                        solver_name=initial_solver_name,
                        checkpoint_path=checkpoint_path,
                        restart=args.restart,
                        ru_mode=args.ru,
                    )
                instance_csv, scenario_csv, metadata_json = _write_h2_outputs(
                    output_path=h2_output_path,
                    results=h2_results,
                    config=mc_config,
                    risk_alpha=args.risk_alpha,
                    risk_lambda=args.risk_lambda,
                    shortfall_epsilon=args.shortfall_epsilon,
                    shortfall_rate_beta=args.shortfall_rate_beta,
                    run_id=run_id,
                )
                print("\n" + "=" * 60)
                print("STOCHASTIC CVAR SUMMARY")
                print("=" * 60)
                print_stochastic_risk_summary(h2_results)
                print(f"H2 aggregate CSV: {instance_csv}")
                print(f"H2 scenario CSV: {scenario_csv}")
                print(f"H2 metadata JSON: {metadata_json}")
                if run_dir is not None:
                    _write_run_state(run_dir, "completed")
                return 0

            if args.mc_income:
                mc_output_path = args.mc_output or (mc_tmp_dir / "mc_income_results.csv")
                mc_config = IncomeMCConfig(
                    n_scenarios=args.mc_scenarios,
                    seed=args.mc_seed,
                    rho=args.mc_rho,
                    sigma=args.mc_sigma,
                    shock_prob=args.mc_shock_prob,
                    shock_severity_mean=args.mc_shock_severity,
                    shock_severity_std=max(args.mc_shock_severity * 0.25, 0.01),
                    min_income_floor=1.0,
                )
                mc_config.validate()

                if args.parallel:
                    aggregates, scenario_rows, scenario_comparisons = run_monte_carlo_experiments_parallel(
                        dataset_path=dataset_path,
                        mc_config=mc_config,
                        max_instances_per_group=args.max_instances,
                        time_limit_seconds=args.time_limit,
                        verbose=True,
                        allowed_n_loans=tuple(args.n_loans),
                        solver_name=initial_solver_name,
                        n_workers=args.workers,
                        checkpoint_path=checkpoint_path,
                        restart=args.restart,
                        ru_mode=args.ru,
                    )
                else:
                    aggregates, scenario_rows, scenario_comparisons = run_monte_carlo_experiments(
                        dataset_path=dataset_path,
                        mc_config=mc_config,
                        max_instances_per_group=args.max_instances,
                        time_limit_seconds=args.time_limit,
                        verbose=True,
                        allowed_n_loans=tuple(args.n_loans),
                        solver_name=initial_solver_name,
                        checkpoint_path=checkpoint_path,
                        restart=args.restart,
                        ru_mode=args.ru,
                    )
                instance_csv, scenario_csv, metadata_json = _write_mc_outputs(
                    output_path=mc_output_path,
                    aggregates=aggregates,
                    scenario_rows=scenario_rows,
                    config=mc_config,
                    run_id=run_id,
                )

                print("\n" + "=" * 60)
                print("MONTE CARLO INCOME SUMMARY")
                print("=" * 60)
                print(f"Instances processed: {len(aggregates)}")
                if aggregates:
                    avg_infeasible = float(np.mean([r.infeasible_rate for r in aggregates]))
                    avg_cost = float(np.mean([r.mean_cost for r in aggregates if np.isfinite(r.mean_cost)]))
                    print(f"Average infeasible rate: {avg_infeasible:.3f}")
                    if np.isfinite(avg_cost):
                        print(f"Average mean cost: {avg_cost:,.2f}")
                print(f"MC aggregate CSV: {instance_csv}")
                print(f"MC scenario CSV: {scenario_csv}")
                print(f"MC metadata JSON: {metadata_json}")
                if scenario_comparisons:
                    print("\n" + "=" * 60)
                    print("MONTE CARLO BASELINE COMPARISON SUMMARY")
                    print_summary(scenario_comparisons)
                if run_dir is not None:
                    _write_run_state(run_dir, "completed")
                return 0

            if args.parallel:
                results = run_experiments_parallel(
                    dataset_path=dataset_path,
                    max_instances_per_group=args.max_instances,
                    time_limit_seconds=args.time_limit,
                    watchdog_grace_seconds=args.watchdog_grace_seconds,
                    verbose=True,
                    allowed_n_loans=tuple(args.n_loans),
                    n_workers=args.workers,
                    checkpoint_path=checkpoint_path,
                    timeout_log_path=timeout_log_path,
                    skip_known_timeouts=not args.include_known_timeouts,
                    restart=args.restart,
                    initial_solver_name=initial_solver_name,
                    enable_solver_fallback=enable_solver_fallback,
                    export_timelines=args.export_timelines,
                    timelines_dir=timelines_dir,
                    ru_mode=args.ru,
                )
            else:
                results = run_experiments(
                    dataset_path=dataset_path,
                    max_instances_per_group=args.max_instances,
                    time_limit_seconds=args.time_limit,
                    verbose=True,
                    allowed_n_loans=tuple(args.n_loans),
                    checkpoint_path=checkpoint_path,
                    timeout_log_path=timeout_log_path,
                    skip_known_timeouts=not args.include_known_timeouts,
                    restart=args.restart,
                    solver_name=initial_solver_name,
                    export_timelines=args.export_timelines,
                    timelines_dir=timelines_dir,
                    ru_mode=args.ru,
                )

            print("\n" + "=" * 60)
            print_summary(results)

            checkpoint = CheckpointManager(checkpoint_path)
            csv_path = default_results_csv_path
            checkpoint.export_to_csv(csv_path)
            if checkpoint.load_existing_results():
                print(f"\nResults exported to: {csv_path}")
            if timeout_log_path.exists():
                print(f"Timeout instances logged to: {timeout_log_path}")
            if run_dir is not None:
                _write_run_state(run_dir, "completed")
            return 0
        except KeyboardInterrupt:
            if run_dir is not None:
                _write_run_state(run_dir, "interrupted")
            if LAST_SHUTDOWN_SIGNAL == getattr(signal, "SIGTERM", None):
                print("\nReceived SIGTERM. Exiting...")
                return 143
            print("\nInterrupted by user. Exiting...")
            return 130
    finally:
        _restore_shutdown_signal_handlers(previous_signal_handlers)


if __name__ == "__main__":
    sys.exit(main())
