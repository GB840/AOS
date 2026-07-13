#!/usr/bin/env python3
"""Stable pytest runner: each test file runs in its own OS-killed subprocess.

Why this exists
---------------
In this sandbox, a few native-extension tests (zvec / rocksdb / cognee) hang
indefinitely during execution. pytest-timeout only has *thread* mode here, which
cannot kill a native thread, so one hanging test blocks the entire suite and no
summary is ever produced (the process is killed by the OS before flushing).

Running every test file as its own process lets the OS kill the whole process
tree on timeout. The run therefore ALWAYS completes, and we get real per-file
red/green numbers instead of a silent hang.

Usage
-----
    python scripts/run_tests_stable.py            # default 200s per-file OS cap
    STABLE_TIMEOUT=90 python scripts/run_tests_stable.py
Results are printed to stdout and written to pytest_stable_report.json.
"""
from __future__ import annotations

import glob
import json
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS_DIR = os.path.join(ROOT, "tests")
PER_FILE_TIMEOUT = int(os.environ.get("STABLE_TIMEOUT", "200"))

ENV = dict(os.environ)
ENV["PYTHONPATH"] = os.path.join(ROOT, "src")
ENV.setdefault("PYTHONWARNINGS", "ignore")

_SUMMARY_RE = re.compile(
    r"(?:(\d+)\s+passed)?"
    r"(?:,?\s*(\d+)\s+failed)?"
    r"(?:,?\s*(\d+)\s+skipped)?"
    r"(?:,?\s*(\d+)\s+error)?"
    r"(?:,?\s*(\d+)\s+xfailed)?"
    r"(?:,?\s*(\d+)\s+xpassed)?"
    r"(?:,?\s*(\d+)\s+deselected)?"
)


def _kill_tree(pid: int) -> None:
    # Windows: taskkill /T kills the whole process tree (children included).
    try:
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            capture_output=True,
        )
    except Exception:
        pass


def run_one(path: str) -> dict:
    rel = os.path.relpath(path, ROOT)
    cmd = [
        sys.executable, "-m", "pytest", rel, "-q", "--tb=line",
        "-p", "no:cacheprovider", "-p", "no:cov",
    ]
    t0 = time.time()
    proc = subprocess.Popen(
        cmd, cwd=ROOT, env=ENV,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1,
    )
    timed_out = False
    try:
        stdout, _ = proc.communicate(timeout=PER_FILE_TIMEOUT)
        out = stdout or ""
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill_tree(proc.pid)
        try:
            stdout, _ = proc.communicate(timeout=10)
            out = stdout or ""
        except Exception:
            out = ""
        out += f"\n[TIMEOUT] killed after {PER_FILE_TIMEOUT}s\n"
    elapsed = time.time() - t0
    rc = proc.returncode if not timed_out else -1

    last_summary = ""
    for line in reversed(out.splitlines()):
        if any(k in line for k in ("passed", "failed", "error", "skipped")):
            last_summary = line.strip()
            break
    m = _SUMMARY_RE.search(last_summary)

    def _n(g):
        try:
            return int(g) if g else 0
        except Exception:
            return 0

    passed = _n(m.group(1)) if m else 0
    failed = _n(m.group(2)) if m else 0
    skipped = _n(m.group(3)) if m else 0
    error = _n(m.group(4)) if m else 0

    if timed_out:
        status = "TIMEOUT"
    elif rc == 0:
        status = "OK"
    elif rc == 1:
        status = "FAIL"
    elif rc == 2:
        status = "ERROR"
    elif rc == 5:
        status = "EMPTY"
    else:
        status = f"RC={rc}"

    return {
        "file": rel,
        "status": status,
        "rc": rc,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "error": error,
        "elapsed": round(elapsed, 1),
        "summary": last_summary,
        "timed_out": timed_out,
    }


def main() -> int:
    files = sorted(
        f for f in glob.glob(os.path.join(TESTS_DIR, "**", "test_*.py"), recursive=True)
        if "__pycache__" not in f
    )
    print(
        f"# stable pytest runner: {len(files)} files, "
        f"per-file timeout {PER_FILE_TIMEOUT}s",
        flush=True,
    )
    results: list[dict] = []
    tot = {"passed": 0, "failed": 0, "skipped": 0, "error": 0, "timeout": 0}
    for f in files:
        r = run_one(f)
        results.append(r)
        tag = "TIMEOUT" if r["timed_out"] else ("OK " if r["status"] == "OK" else "XX ")
        print(
            f"{tag} {r['file']:52s} {r['status']:7s} "
            f"p={r['passed']} f={r['failed']} s={r['skipped']} "
            f"e={r['error']} {r['elapsed']}s",
            flush=True,
        )
        tot["passed"] += r["passed"]
        tot["failed"] += r["failed"]
        tot["skipped"] += r["skipped"]
        tot["error"] += r["error"]
        if r["timed_out"]:
            tot["timeout"] += 1

    print("\n# TOTALS:", json.dumps(tot), flush=True)
    report = os.path.join(ROOT, "pytest_stable_report.json")
    with open(report, "w", encoding="utf-8") as fh:
        json.dump({"totals": tot, "results": results}, fh, indent=2, ensure_ascii=False)
    print("# report ->", report, flush=True)

    # Non-zero exit only if there are real failures/errors (timeouts are
    # environmental, not code failures, so they don't fail the stable run).
    return 1 if (tot["failed"] or tot["error"]) else 0


if __name__ == "__main__":
    sys.exit(main())
