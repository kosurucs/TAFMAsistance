"""Uvicorn entrypoint for the UI API.

This wrapper avoids the `src.api` package/module name collision by loading
`src/api.py` (standalone module) from file and re-exporting its FastAPI app.
After loading the base app it mounts the router-based sub-apps that live in
`src/api/routers/` so that /llm, /research, and /api/backtest endpoints are
available from the single server process.
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

# ── Mount routers that are NOT in the legacy api.py ──────────────────────────
# (bot, market, portfolio, trade routers are already covered inline in api.py)
try:
    from src.api.routers import backtest, llm, research, algo  # noqa: E402
    app.include_router(backtest.router, tags=["Backtest"])
    app.include_router(llm.router, tags=["LLM"])
    app.include_router(research.router, tags=["Research"])
    app.include_router(algo.router, tags=["Algo"])
except Exception as _e:  # pragma: no cover
    import warnings
    warnings.warn(f"ui_api: failed to mount extended routers: {_e}")
