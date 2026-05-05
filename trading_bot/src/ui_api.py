"""Uvicorn entrypoint for the UI API.

This wrapper avoids the `src.api` package/module name collision by loading
`src/api.py` (standalone module) from file and re-exporting its FastAPI app.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_api_path = Path(__file__).with_name("api.py")
_spec = importlib.util.spec_from_file_location("ui_api_impl", _api_path)
if _spec is None or _spec.loader is None:
    raise RuntimeError(f"Failed to load API module from {_api_path}")

_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

app = _module.app
