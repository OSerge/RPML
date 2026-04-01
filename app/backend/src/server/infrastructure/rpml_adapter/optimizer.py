"""Thin adapter around core RPML solver."""

from __future__ import annotations

from rpml.data_loader import RiosSolisInstance
from rpml.milp_model import RPMLSolution, solve_rpml


class RpmlAdapter:
    """Maps domain inputs to `RiosSolisInstance`, runs `solve_rpml`, returns `RPMLSolution`."""

    def run(
        self,
        instance: RiosSolisInstance,
        *,
        time_limit_seconds: int | None = 60,
        ru_mode: bool = True,
    ) -> RPMLSolution:
        return solve_rpml(
            instance,
            time_limit_seconds=time_limit_seconds,
            ru_mode=ru_mode,
        )
