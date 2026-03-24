"""Compatibility loader for the experiment CLI module."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def _load_experiments_module():
    script_path = Path(__file__).resolve().parents[3] / "scripts" / "run_experiments.py"
    spec = spec_from_file_location("_rpml_run_experiments_script", script_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load experiment script from {script_path}")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_impl = _load_experiments_module()
for _name, _value in vars(_impl).items():
    if not _name.startswith("_"):
        globals()[_name] = _value

__all__ = [name for name in vars(_impl) if not name.startswith("_")]
