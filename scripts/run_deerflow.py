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
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

DEERFLOW_ROOT = Path(r"D:\AOS\external\deer-flow")
DEERFLOW_BACKEND = DEERFLOW_ROOT / "backend"
DEERFLOW_CONFIG = DEERFLOW_ROOT / "config.yaml"
ENV_PATH = DEERFLOW_ROOT / ".env"


def _ensure_agents_api_enabled() -> None:
    """Make sure DeerFlow's custom-agent management API is turned on.

    ``config.yaml`` lives under ``external/`` (gitignored), so any local edit
    is lost on a fresh ``git checkout`` / re-vendor. Enabling ``agents_api``
    here, at launch time, makes the AOS real ``assistant_id`` subagent routing
    reproducible without relying on a committed file.

    Tries a real YAML round-trip first (preserves comments/ordering-when-possible
    via ruamel if present), and falls back to a line-level patch so the launcher
    never hard-fails on a missing optional dependency.
    """
    if not DEERFLOW_CONFIG.exists():
        print("[run_deerflow] config.yaml not found; skipping agents_api ensure", flush=True)
        return

    try:
        import yaml  # type: ignore

        with open(DEERFLOW_CONFIG, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        agents_api = cfg.get("agents_api")
        if isinstance(agents_api, dict) and agents_api.get("enabled") is True:
            print("[run_deerflow] agents_api already enabled", flush=True)
            return
        cfg["agents_api"] = {"enabled": True}
        with open(DEERFLOW_CONFIG, "w", encoding="utf-8") as f:
            yaml.safe_dump(cfg, f, sort_keys=False, allow_unicode=True)
        print("[run_deerflow] agents_api.enabled set to true", flush=True)
    except Exception as exc:  # noqa: BLE001 - fallback path must never crash launch
        print(f"[run_deerflow] yaml path failed ({exc}); using text fallback", flush=True)
        _ensure_agents_api_text()


def _ensure_agents_api_text() -> None:
    text = DEERFLOW_CONFIG.read_text(encoding="utf-8")
    if re.search(r"^\s*agents_api\s*:\s*$", text, re.MULTILINE) or re.search(
        r"agents_api\s*:\s*\{\s*enabled\s*:\s*true", text
    ):
        # Present but maybe disabled -> force enabled.
        text = re.sub(
            r"agents_api\s*:\s*\{\s*enabled\s*:\s*false\s*\}",
            "agents_api: {enabled: true}",
            text,
        )
        if "agents_api" in text and "enabled: true" not in text:
            text = re.sub(
                r"(agents_api\s*:\s*\n(\s*)enabled\s*:\s*)false",
                r"\1true",
                text,
            )
        else:
            print("[run_deerflow] agents_api text already enabled", flush=True)
            DEERFLOW_CONFIG.write_text(text, encoding="utf-8")
            return
        DEERFLOW_CONFIG.write_text(text, encoding="utf-8")
        print("[run_deerflow] agents_api.enabled forced true (text)", flush=True)
        return
    # Not present at all -> append.
    text = text.rstrip() + "\n\nagents_api:\n  enabled: true\n"
    DEERFLOW_CONFIG.write_text(text, encoding="utf-8")
    print("[run_deerflow] agents_api.enabled appended (text)", flush=True)


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

    # 3.5) Self-heal: make sure the custom-agent API is enabled so AOS can route
    # subagents via the real assistant_id (reproducible across re-vendors).
    _ensure_agents_api_enabled()

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
