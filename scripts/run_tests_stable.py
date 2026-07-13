#!/usr/bin/env python3
'''Stable full-suite pytest runner for the AOS stability system (L4 gate).

Why this exists
---------------
`pytest tests/` cannot complete reliably in this sandbox: a few native-
extension tests (zvec/rocksdb/cognee) crash the process, and under load other
imports (tokenizers/litellm) hang. pytest-timeout's thread mode cannot kill a
native thread, so one hang blocks the whole run and no summary is produced.

This runner runs every test_*.py as its OWN os-killed subprocess
(STABLE_TIMEOUT, default 200s). On timeout it kills the whole process TREE
(taskkill /F /T on Windows) incl. native threads. The run ALWAYS finishes and
emits real per-file red/green numbers to pytest_stable_report.json.

No per-test timeout is used: a legitimately slow test (e.g. test_kernel.py at
~94s) must not be false-failed. The only guard is the per-file OS timeout, which
kills genuine native hangs without masking real failures.

Usage:
    python scripts/run_tests_stable.py
    STABLE_TIMEOUT=90 python scripts/run_tests_stable.py
'''
from __future__ import annotations

import glob
import json
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.join(ROOT, "tests")
PER_FILE_TIMEOUT = int(os.environ.get("STABLE_TIMEOUT", "200"))

_SUM_RE = re.compile(r"(\d+)\s+(passed|failed|skipped|error|warning)")


def _parse_summary(out: str) -> dict:
    counts = {"passed": 0, "failed": 0, "skipped": 0, "error": 0, "timeout": 0}
    for m in _SUM_RE.finditer(out):
        n, kind = int(m.group(1)), m.group(2)
        if kind in counts:
            counts[kind] += n
    if "TIMEOUT" in out or "killed" in out:
        counts["timeout"] = 1
    return counts


def _run_file(rel: str) -> dict:
    cmd = [sys.executable, "-m", "pytest", rel, "-q", "--tb=line",
           "-p", "no:cacheprovider", "-p", "no:cov"]
    try:
        p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                           timeout=PER_FILE_TIMEOUT)
        rc = p.returncode
        out = (p.stdout or "") + (p.stderr or "")
        status = "OK" if rc == 0 else ("EMPTY" if rc == 5 else "FAIL")
    except subprocess.TimeoutExpired as e:
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(e.pid)],
                               capture_output=True)
            elif e.pid is not None:
                import os as _os
                _os.killpg(_os.getpgid(e.pid), 9)
        except Exception:
            pass
        rc = 124
        out = ((e.stdout or "") + (e.stderr or "") + "\n[TIMEOUT] killed\n")
        status = "TIMEOUT"
    # A hard crash (e.g. 0xC0000005 from zvec) returns a Windows fatal rc.
    if rc in (3221225477, 3221225786, 3221225626):
        status = "CRASH"
    counts = _parse_summary(out)
    summary = out.strip().splitlines()[-1] if out.strip() else ""
    return {
        "file": rel, "rc": rc, "status": status,
        "passed": counts["passed"], "failed": counts["failed"],
        "skipped": counts["skipped"], "error": counts["error"],
        "timeout": counts["timeout"], "summary": summary[:160],
    }


def main() -> int:
    files = sorted(glob.glob(os.path.join(TESTS, "test_*.py")))
    results = []
    totals = {"passed": 0, "failed": 0, "skipped": 0, "error": 0, "timeout": 0}
    t0 = time.time()
    for f in files:
        rel = os.path.relpath(f, ROOT)
        r = _run_file(rel)
        results.append(r)
        totals["passed"] += r["passed"]
        totals["failed"] += r["failed"]
        totals["skipped"] += r["skipped"]
        totals["error"] += r["error"]
        totals["timeout"] += r["timeout"]
        mark = {"OK": "OK ", "EMPTY": "XX ", "FAIL": "XX ",
                "TIMEOUT": "TT ", "CRASH": "CC "}.get(r["status"], "?? ")
        print("%s %-48s p=%d f=%d s=%d e=%d" % (
            mark, rel, r["passed"], r["failed"], r["skipped"], r["error"]),
            flush=True)
    report = {"totals": totals, "results": results,
              "elapsed_sec": round(time.time() - t0, 1)}
    with open(os.path.join(ROOT, "pytest_stable_report.json"), "w",
              encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
    print("# TOTALS:", json.dumps(totals, ensure_ascii=False))
    print("# ELAPSED: %.1fs" % report["elapsed_sec"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
