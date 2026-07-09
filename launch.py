"""
AOS launcher -- thin delegator to the unified supervisor.

The real orchestration (dependency-ordered start, health gating, process
supervision, graceful shutdown) lives in ``scripts/aos_supervisor.py``. This
file keeps the old ``python launch.py`` entry point working by forwarding to it.

Usage:
    python launch.py                 # start the full stack (deerflow+aos+web+openclaw)
    python launch.py --api-only      # start only the AOS API
    python launch.py --ui-only       # start only the web console
    python launch.py --check         # print health of every service
"""

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
SUPERVISOR = PROJECT_ROOT / "scripts" / "aos_supervisor.py"


def main() -> None:
    args = sys.argv[1:]
    # Map legacy flags to supervisor flags.
    if "--api-only" in args:
        args = [a for a in args if a != "--api-only"] + ["--only", "aos"]
    elif "--ui-only" in args:
        args = [a for a in args if a != "--ui-only"] + ["--only", "web"]

    cmd = [sys.executable, str(SUPERVISOR)] + args
    print(f"[launch] delegating to supervisor: {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    sys.exit(proc.returncode)


if __name__ == "__main__":
    main()
