from __future__ import annotations

import runpy
from pathlib import Path


def main() -> None:
    current = Path(__file__).resolve()
    tools_script = current.parents[2] / "tools" / "gradio_api_tester.py"
    module_globals = runpy.run_path(str(tools_script))
    build_app = module_globals.get("build_app")
    if build_app is None:
        raise RuntimeError("build_app not found in tools/gradio_api_tester.py")
    ui = build_app()
    ui.launch(server_name="127.0.0.1", server_port=7860)
