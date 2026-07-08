"""Launch the DeerFlow gateway with its ``.env`` correctly loaded.

Why this launcher exists
-------------------------
DeerFlow's auth middleware (``app.gateway.auth_disabled`` and
``app.gateway.internal_auth``) reads ``DEER_FLOW_AUTH_DISABLED`` and
``DEER_FLOW_INTERNAL_AUTH_TOKEN`` directly from ``os.environ``.

DeerFlow's config module (``deerflow.config.app_config``) calls
``load_dotenv()`` at *import time*, but ``python-dotenv`` resolves the
``.env`` file relative to the **current working directory**. The standard
launch is ``uvicorn app.gateway.app:app`` run from ``backend/``, while this
vendored copy keeps its ``.env`` at the repo root. So ``load_dotenv()``
looks in ``backend/.env`` (which does not exist), the auth flags never reach
``os.environ``, and every ``/api/*`` call returns ``401 not_authenticated``
even though ``config.yaml`` still loads via the legacy path search.

This launcher fixes it deterministically:
  1. Explicitly loads the repo-root ``.env`` into ``os.environ`` (override=True),
     so the auth flags are present no matter what CWD uvicorn inherits.
  2. chdir's to the repo root so DeerFlow's own import-time ``load_dotenv()``
     also resolves correctly.
  3. Puts ``backend/`` on ``sys.path`` so ``app.gateway.app:app`` imports.

Run with the DeerFlow backend venv python, e.g.::

    external/deer-flow/backend/.venv/Scripts/python.exe scripts/run_deerflow.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

DEERFLOW_ROOT = Path(r"D:\AOS\external\deer-flow")
DEERFLOW_BACKEND = DEERFLOW_ROOT / "backend"
ENV_PATH = DEERFLOW_ROOT / ".env"


def main() -> None:
    # 1) Pull the repo-root .env into os.environ (override so our intent wins
    #    over any value uvicorn's parent shell may have set).
    if ENV_PATH.exists():
        load_dotenv(ENV_PATH, override=True)
    else:
        # Fall back to CWD-based resolution if the repo layout changed.
        load_dotenv(override=True)

    # 2) Make DeerFlow's own import-time load_dotenv() resolve the same file.
    os.chdir(DEERFLOW_ROOT)

    # 3) Ensure the gateway app module is importable.
    backend_str = str(DEERFLOW_BACKEND)
    if backend_str not in sys.path:
        sys.path.insert(0, backend_str)

    import uvicorn

    host = os.environ.get("DEERFLOW_HOST", "127.0.0.1")
    try:
        port = int(os.environ.get("PORT", "2026"))
    except ValueError:
        port = 2026

    uvicorn.run(
        "app.gateway.app:app",
        host=host,
        port=port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
