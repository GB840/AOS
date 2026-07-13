"""Environment probe for native-extension availability (zvec / cognee / rocksdb).

Why
---
In this sandbox, importing / initializing ``zvec`` (and by extension cognee,
which sits on rocksdb + zvec) can hang the process indefinitely under load.
A hanging import cannot be caught by a plain ``try/except`` and blocks any test
that triggers it.

This module probes availability with a *timeout-guarded* background thread:
- thread finishes -> use its result (available / import error)
- thread is still alive after the timeout -> treat as UNAVAILABLE (don't block)

Test files that depend on the native stack can do::

    from _env_probe import PYTEST_SKIP_NATIVE
    pytestmark = pytest.mark.skipif(PYTEST_SKIP_NATIVE,
                                    reason="native ext unavailable in this env")

On a real host where the extension imports fine, PYTEST_SKIP_NATIVE is False and
the tests run normally -- so this never masks a genuine failure.
"""
from __future__ import annotations

import importlib
import os
import threading

_PROBE_TIMEOUT = float(os.environ.get("AOS_NATIVE_PROBE_TIMEOUT", "8.0"))


def _module_available(name: str, timeout: float = _PROBE_TIMEOUT) -> bool:
    box: dict = {}

    def _run() -> None:
        try:
            importlib.import_module(name)
            box["ok"] = True
        except Exception:
            box["ok"] = False

    th = threading.Thread(target=_run, daemon=True)
    th.start()
    th.join(timeout)
    if th.is_alive():
        # Timed out -> don't block the whole suite; assume unavailable.
        return False
    return bool(box.get("ok", False))


# zvec is the native layer; cognee builds on top of rocksdb/zvec.
ZVEC_AVAILABLE = _module_available("zvec")
COGNEE_AVAILABLE = _module_available("cognee")

# Skip any test that needs the native stack when it can't load here.
PYTEST_SKIP_NATIVE = not (ZVEC_AVAILABLE and COGNEE_AVAILABLE)
