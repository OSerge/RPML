"""
Checkpoint manager for incremental experiment results.

Persists ComparisonResult to JSONL with atomic append and file locking
for resume-after-interrupt and parallel run safety.
"""

import dataclasses
import json
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .metrics import ComparisonResult

logger = logging.getLogger(__name__)

try:
    import fcntl
except ImportError:
    fcntl = None


def _result_from_dict(data: dict) -> "ComparisonResult":
    from .metrics import ComparisonResult

    def _float_or_none(v):
        if v is None:
            return None
        return float(v)

    return ComparisonResult(
        instance_name=data["instance_name"],
        n_loans=int(data["n_loans"]),
        optimal_cost=float(data["optimal_cost"]),
        optimal_solve_time=float(data["optimal_solve_time"]),
        optimal_gap=float(data["optimal_gap"]),
        optimal_status=str(data["optimal_status"]),
        avalanche_cost=float(data["avalanche_cost"]),
        avalanche_valid=bool(data.get("avalanche_valid", data.get("avalanche_feasible", False))),
        avalanche_feasible=bool(data["avalanche_feasible"]),
        avalanche_final_balance=float(data.get("avalanche_final_balance", 0.0)),
        avalanche_horizon_spend_advantage=_float_or_none(data.get("avalanche_horizon_spend_advantage", data.get("avalanche_savings"))),
        avalanche_savings=_float_or_none(data.get("avalanche_savings")),
        snowball_cost=float(data["snowball_cost"]),
        snowball_valid=bool(data.get("snowball_valid", data.get("snowball_feasible", False))),
        snowball_feasible=bool(data["snowball_feasible"]),
        snowball_final_balance=float(data.get("snowball_final_balance", 0.0)),
        snowball_horizon_spend_advantage=_float_or_none(data.get("snowball_horizon_spend_advantage", data.get("snowball_savings"))),
        snowball_savings=_float_or_none(data.get("snowball_savings")),
    )


class CheckpointManager:
    """
    Manages incremental persistence of experiment results to a JSONL file.

    Supports resume (skip already processed instances), atomic append with
    file locking for parallel workers, and corruption-tolerant load.
    """

    def __init__(self, checkpoint_path: Path | str, restart: bool = False) -> None:
        """
        Initialize checkpoint manager.

        Args:
            checkpoint_path: Path to the JSONL checkpoint file.
            restart: If True, clear existing checkpoint (start fresh).
        """
        self.checkpoint_path = Path(checkpoint_path)
        if restart and self.checkpoint_path.exists():
            self.checkpoint_path.unlink()
            logger.info("Checkpoint cleared (restart=True)")

    def load_existing_results(self) -> dict[str, "ComparisonResult"]:
        """
        Load all results from the checkpoint file.

        Invalid lines are skipped and logged. Returns a dict keyed by
        instance_name (last occurrence wins for duplicates).
        """
        out: dict[str, "ComparisonResult"] = {}
        if not self.checkpoint_path.exists():
            return out
        with open(self.checkpoint_path, "r", encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    r = _result_from_dict(data)
                    out[r.instance_name] = r
                except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
                    logger.warning(
                        "Checkpoint line %s invalid, skipping: %s", i, e
                    )
        return out

    def get_processed_instances(self) -> set[str]:
        """Return the set of instance names that already have results in the checkpoint."""
        return set(self.load_existing_results().keys())

    def save_result(self, result: "ComparisonResult") -> None:
        """
        Append one result to the checkpoint file.

        Uses exclusive file lock for process/thread safety, then flush and
        fsync so that a single line is durable before returning.
        """
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(dataclasses.asdict(result), ensure_ascii=False) + "\n"

        with open(self.checkpoint_path, "a", encoding="utf-8") as f:
            if fcntl is not None:
                try:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                except OSError:
                    pass
            try:
                f.write(payload)
                f.flush()
                if hasattr(os, "fsync"):
                    os.fsync(f.fileno())
            finally:
                if fcntl is not None:
                    try:
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                    except OSError:
                        pass

    def export_to_csv(self, output_path: Path | str) -> None:
        """
        Export all checkpoint results to a CSV file.

        Args:
            output_path: Path for the output CSV.
        """
        import pandas as pd

        results = list(self.load_existing_results().values())
        if not results:
            return
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        rows = [
            {
                "instance": r.instance_name,
                "n_loans": r.n_loans,
                "milp_cost": r.optimal_cost,
                "solve_time": r.optimal_solve_time,
                "gap": r.optimal_gap,
                "status": r.optimal_status,
                "avalanche_cost": r.avalanche_cost,
                "avalanche_valid": r.avalanche_valid,
                "avalanche_feasible": r.avalanche_feasible,
                "avalanche_final_balance": r.avalanche_final_balance,
                "avalanche_horizon_spend_advantage": r.avalanche_horizon_spend_advantage,
                "avalanche_savings": r.avalanche_savings,
                "snowball_cost": r.snowball_cost,
                "snowball_valid": r.snowball_valid,
                "snowball_feasible": r.snowball_feasible,
                "snowball_final_balance": r.snowball_final_balance,
                "snowball_horizon_spend_advantage": r.snowball_horizon_spend_advantage,
                "snowball_savings": r.snowball_savings,
            }
            for r in results
        ]
        df = pd.DataFrame(rows)
        df.to_csv(output_path, index=False)
