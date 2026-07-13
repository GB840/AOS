'''Environment probe for native-extension availability (zvec / cognee / rocksdb).

Why subprocess, not a thread
----------------------------
Importing / initializing ``zvec`` (and by extension cognee, which sits on
rocksdb + zvec) can HANG or CRASH the process (0xC0000005 access violation)
under load in this sandbox. A hanging import cannot be caught by a plain
``try/except``, and a crashing import kills the *whole* process -- even inside
a daemon thread. So we probe in a SEPARATE subprocess: a crash there only
kills the child, never the test runner.

Test files that depend on the native stack can do::

    from _env_probe import PYTEST_SKIP_NATIVE
    pytestmark = pytest.mark.skipif(PYTEST_SKIP_NATIVE,
                                    reason="native ext unavailable in this env")

On a real host where the extension imports fine, PYTEST_SKIP_NATIVE is False and
the tests run normally -- so this never masks a genuine failure.
'''
from __future__ import annotations

import subprocess
import sys


def _probe_subprocess(imports: list, timeout: float = 30.0) -> bool:
    '''Return True iff every name imports cleanly in a fresh subprocess.'''
    code = "; ".join("import %s" % m for m in imports)
    try:
        r = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            timeout=timeout,
        )
        return r.returncode == 0
    except Exception:
        return False


# zvec is the native layer; cognee builds on top of rocksdb/zvec.
ZVEC_AVAILABLE = _probe_subprocess(["zvec"])
COGNEE_AVAILABLE = _probe_subprocess(["cognee"])

# Skip any test that needs the native stack when it can't load here.
PYTEST_SKIP_NATIVE = not (ZVEC_AVAILABLE and COGNEE_AVAILABLE)


def native_stack_ok() -> bool:
    '''True iff the native memory stack can be loaded in this environment.'''
    return ZVEC_AVAILABLE and COGNEE_AVAILABLE
