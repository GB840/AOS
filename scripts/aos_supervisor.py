"""AOS unified supervisor -- one command to bring up the whole platform.

This is the SINGLE entry point for running AOS in production. It starts every
component in dependency order, gates each one on a health check, supervises
them (restarts any that die, with backoff), and shuts them all down cleanly on
Ctrl+C / SIGTERM.

Components
----------
  deerflow  -> the DeerFlow gateway (:2026). Uses ``scripts/run_deerflow.py``
               which loads the repo-root ``.env`` into os.environ (fixes the
               persistent 401) and self-heals ``agents_api.enabled``.
  aos       -> the AOS API + single-port gateway (:8000). Depends on DeerFlow
               so it boots in REAL routing mode.
  web       -> the Streamlit console (:8501, served under /web).
  openclaw  -> the OpenClaw gateway (:18789), a node package.

Usage
-----
  python scripts/aos_supervisor.py                # start all, supervise, stay up
  python scripts/aos_supervisor.py --check        # print health of every service
  python scripts/aos_supervisor.py --stop         # stop everything started here
  python scripts/aos_supervisor.py --only aos     # start a single service
  python scripts/aos_supervisor.py --skip web     # start all except web

Environment overrides
---------------------
  AOS_VENV        python exe of the AOS venv   (default: <workbuddy>/envs/aos/Scripts/python.exe)
  DEERFLOW_VENV   python exe of the DeerFlow backend venv
  NODE_BIN        node executable              (default: from PATH)
  OPENCLAW_TOKEN  token for the OpenClaw gateway (default: aos-fabric-2026local)
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

AOS_ROOT = Path(__file__).resolve().parents[1]
LOGS_DIR = AOS_ROOT / "logs"
PID_FILE = LOGS_DIR / "aos_pids.json"

# Insure localhost health checks never traverse an HTTP proxy (urllib honours
# proxy env vars; a misconfigured proxy makes 127.0.0.1 checks fail spuriously).
_no_proxy = os.environ.get("no_proxy", os.environ.get("NO_PROXY", ""))
if "127.0.0.1" not in _no_proxy:
    _no_proxy = (_no_proxy + ",127.0.0.1,localhost").strip(",")
os.environ["no_proxy"] = _no_proxy
os.environ["NO_PROXY"] = _no_proxy

# ---- executable resolution (with env overrides) ---------------------------
DEFAULT_AOS_VENV = Path(
    r"C:\Users\Administrator\.workbuddy\binaries\python\envs\aos\Scripts\python.exe"
)
DEFAULT_DEERFLOW_VENV = AOS_ROOT / "external" / "deer-flow" / "backend" / ".venv" / "Scripts" / "python.exe"
DEFAULT_OPENCLAW_TOKEN = "aos-fabric-2026local"

AOS_VENV = Path(os.environ.get("AOS_VENV", str(DEFAULT_AOS_VENV)))
DEERFLOW_VENV = Path(os.environ.get("DEERFLOW_VENV", str(DEFAULT_DEERFLOW_VENV)))
OPENCLAW_TOKEN = os.environ.get("OPENCLAW_TOKEN", DEFAULT_OPENCLAW_TOKEN)
# 网关用 --token 起的，AOS 的 OpenClawAdapter 必须拿到同一个 token 才能鉴权
# 通过 `openclaw agent` CLI 调网关。这里把 token 注入环境，使下游 openclaw
# 服务(继承)与 aos 服务(_aos_env 拷贝 os.environ)都能一致拿到，避免"网关活
# 着但 AOS 调不通"的隐性故障。
os.environ.setdefault("OPENCLAW_GATEWAY_TOKEN", OPENCLAW_TOKEN)
DEFAULT_SITE = Path(
    r"C:\Users\Administrator\.workbuddy\binaries\python\envs\default\Lib\site-packages"
)


def _resolve_node() -> str:
    if os.environ.get("NODE_BIN"):
        return os.environ["NODE_BIN"]
    # Prefer the same node the running OpenClaw uses.
    candidate = (
        r"C:\Users\Administrator\.workbuddy\binaries\node\versions\22.22.2\node.exe"
    )
    if Path(candidate).exists():
        return candidate
    # Fall back to whatever `node` is on PATH.
    return "node"


def _resolve_openclaw_mjs() -> str:
    # 1) env override
    if os.environ.get("OPENCLAW_MJS"):
        return os.environ["OPENCLAW_MJS"]
    # 2) global npm root
    try:
        out = subprocess.run(
            ["npm", "root", "-g"], capture_output=True, text=True, timeout=10
        )
        if out.returncode == 0:
            mjs = Path(out.stdout.strip()) / "openclaw" / "openclaw.mjs"
            if mjs.exists():
                return str(mjs)
    except Exception:
        pass
    # 3) known fallback path
    fb = Path(r"C:\Users\Administrator\AppData\Roaming\npm\node_modules\openclaw\openclaw.mjs")
    if fb.exists():
        return str(fb)
    raise RuntimeError("Cannot locate openclaw.mjs (set OPENCLAW_MJS env)")


NODE_BIN = _resolve_node()
OPENCLAW_MJS = _resolve_openclaw_mjs()

# ---- logging ---------------------------------------------------------------
LOGS_DIR.mkdir(exist_ok=True)
_super_log = LOGS_DIR / "supervisor.log"


def log(msg: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        with open(_super_log, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ---- service definitions ---------------------------------------------------
def _aos_env() -> dict:
    env = os.environ.copy()
    # The supervisor may inherit an unrelated PYTHONPATH from the launching
    # shell (e.g. a WorkBuddy CLI shim directory). Left on sys.path that shim
    # can shadow AOS modules and make AOS crash at import/init time -- which
    # manifested as AOS dying ~7s after start and the supervisor thrashing in a
    # restart loop. We deliberately REBUILD PYTHONPATH from scratch with only
    # AOS-owned paths plus the shared default-venv site-packages.
    canonical = [str(AOS_ROOT), str(AOS_ROOT / "src"), str(DEFAULT_SITE)]
    pp = [p for p in canonical]
    env["PYTHONPATH"] = os.pathsep.join(pp)
    # Borrow mem0/langfuse/browser-use from the shared default venv.
    env["AOS_EXTRA_SITE"] = str(DEFAULT_SITE)
    # Drop any WorkBuddy / shim related vars that could interfere with imports.
    for k in [k for k in list(env) if ("WORKBUDDY" in k.upper() or "SHIM" in k.upper())]:
        del env[k]
    return env


SERVICES = {
    "deerflow": {
        "cmd": [str(DEERFLOW_VENV), str(AOS_ROOT / "scripts" / "run_deerflow.py")],
        "cwd": str(AOS_ROOT),
        "env": None,
        "health": ("http", "http://127.0.0.1:2026/health"),
        "depends": [],
        "required": True,
    },
    "aos": {
        "cmd": [
            str(AOS_VENV), "-u", "-m", "uvicorn", "src.api.main:app",
            "--host", "127.0.0.1", "--port", "8000", "--log-level", "info",
        ],
        "cwd": str(AOS_ROOT),
        "env": _aos_env(),
        "health": ("http", "http://127.0.0.1:8000/health"),
        "depends": ["deerflow"],
        "required": True,
    },
    "web": {
        "cmd": [
            str(AOS_VENV), "-m", "streamlit", "run", "web/console.py",
            "--server.port", "8501", "--server.headless", "true",
            "--browser.gatherUsageStats", "false",
            "--server.address", "127.0.0.1", "--server.baseUrlPath", "/web",
        ],
        "cwd": str(AOS_ROOT),
        "env": _aos_env(),
        "health": ("tcp", "127.0.0.1", 8501),
        "depends": [],
        "required": True,
    },
    "openclaw": {
        "cmd": [
            NODE_BIN, OPENCLAW_MJS, "gateway", "run",
            "--bind", "loopback", "--port", "18789", "--token", OPENCLAW_TOKEN,
        ],
        "cwd": str(AOS_ROOT),
        "env": None,
        "health": ("tcp", "127.0.0.1", 18789),
        "depends": [],
        "required": True,
    },
}


# ---- health checks ---------------------------------------------------------
def _http_ok(url: str, timeout: float = 5.0, retries: int = 2) -> bool:
    import urllib.request

    last_err = None
    for _ in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                return r.status == 200
        except Exception as e:  # noqa: BLE001 - transient failures must not mark down
            last_err = e
            time.sleep(0.5)
    if last_err is not None:
        log(f"[health] {url} not ok: {type(last_err).__name__}: {str(last_err)[:80]}")
    return False


def _tcp_ok(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def check_health(svc: dict) -> bool:
    kind = svc["health"][0]
    if kind == "http":
        return _http_ok(svc["health"][1])
    return _tcp_ok(svc["health"][1], svc["health"][2])


# ---- process management ----------------------------------------------------
_procs: dict[str, subprocess.Popen] = {}
_start_time: dict[str, float] = {}
_unhealthy_since: dict[str, float] = {}
_restart_count: dict[str, list[float]] = {}
_fail_count: dict[str, int] = {}
_backoff: dict[str, float] = {}
_stop = False
# A heavy service (e.g. AOS runs its full brain init at import time and only
# binds its port after ~2 min) must not be killed just because /health is
# still unreachable during startup. Tolerate unhealthy for this long.
STARTUP_GRACE = 240.0

# A service that is ALIVE but momentarily unhealthy (e.g. AOS is busy serving a
# long chat request that occupies the single uvicorn worker, so /health times
# out) must NOT be killed -- it will recover on its own once the request
# finishes. Only kill+restart a merely-unhealthy (still-alive) service if it has
# been continuously unhealthy longer than this, which is far beyond any legit
# request. A DEAD process is always restarted immediately.
UNHEALTHY_KILL_THRESHOLD = 300.0

# ---- single-instance lock -------------------------------------------------
# Two supervisors controlling the same ports will each see the other's freshly
# started services as "unhealthy" and kill them -> an endless restart storm.
# Only one supervisor may own the stack at a time.
SUPERVISOR_LOCK = LOGS_DIR / "supervisor.lock"


def _pid_alive(pid: int) -> bool:
    try:
        import psutil

        return psutil.pid_exists(pid)
    except Exception:
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except Exception:
            return True


def _acquire_supervisor_lock() -> bool:
    """Guarantee a single supervisor owns the stack.

    Returns True if this process holds the lock, False if another live
    supervisor already does (caller should exit). Stale locks (dead pid) are
    overwritten. The lock is released on graceful shutdown and via atexit.
    """
    try:
        if SUPERVISOR_LOCK.exists():
            txt = SUPERVISOR_LOCK.read_text(encoding="utf-8").strip()
            try:
                old = int(txt)
            except Exception:
                old = None
            if old and old != os.getpid() and _pid_alive(old):
                log(
                    f"[lock] another AOS supervisor already running (pid={old}); "
                    f"refusing to start a second (would cause a restart storm)."
                )
                return False
        SUPERVISOR_LOCK.write_text(str(os.getpid()), encoding="utf-8")
        return True
    except Exception as e:  # never let lock failure block startup
        log(f"[lock] could not acquire lock ({e}); proceeding without it")
        return True


def _release_supervisor_lock() -> None:
    try:
        if SUPERVISOR_LOCK.exists():
            txt = SUPERVISOR_LOCK.read_text(encoding="utf-8").strip()
            if txt == str(os.getpid()):
                SUPERVISOR_LOCK.unlink()
    except Exception:
        pass


import atexit

atexit.register(_release_supervisor_lock)


def _open_log(name: str):
    return open(LOGS_DIR / f"{name}.log", "a", encoding="utf-8", buffering=1)


def start_service(name: str) -> subprocess.Popen:
    spec = SERVICES[name]
    log_file = _open_log(name)
    p = subprocess.Popen(
        spec["cmd"],
        cwd=spec["cwd"],
        env=spec["env"],
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
        close_fds=True,
    )
    _procs[name] = p
    _start_time[name] = time.time()
    _unhealthy_since.pop(name, None)
    _fail_count[name] = 0
    log(f"[start] {name} pid={p.pid}: {' '.join(spec['cmd'])}")
    return p


def stop_service(name: str) -> None:
    p = _procs.get(name)
    if p and p.poll() is None:
        log(f"[stop] {name} pid={p.pid}")
        p.terminate()
        try:
            p.wait(timeout=8)
        except subprocess.TimeoutExpired:
            p.kill()


def save_pids() -> None:
    data = {name: p.pid for name, p in _procs.items() if p.poll() is None}
    try:
        PID_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass


def load_pids() -> dict:
    try:
        return json.loads(PID_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def wait_healthy(name: str, timeout: float = 60.0) -> bool:
    spec = SERVICES[name]
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _procs.get(name) is None or _procs[name].poll() is not None:
            return False
        if check_health(spec):
            return True
        time.sleep(1.5)
    return False


def maybe_restart(name: str) -> None:
    """Supervise one service.

    Restarts the service when it is either:
      * dead (process exited), or
      * alive but unhealthy for 2 consecutive checks (covers the
        "process up but app hung" case, e.g. AOS listening yet /health
        times out).
    A single transient unhealthy check is tolerated before killing, to
    avoid restart storms on a brief blip.
    """
    spec = SERVICES[name]
    p = _procs.get(name)
    alive = p is not None and p.poll() is None
    healthy = check_health(spec) if alive else False

    if alive and healthy:
        _fail_count[name] = 0
        _unhealthy_since.pop(name, None)
        return

    if alive:
        age = time.time() - _start_time.get(name, time.time())
        if age < STARTUP_GRACE:
            # Within startup window: importing/initialising, not hung.
            return
        # Alive but unhealthy. This is often benign: a single-worker service
        # (e.g. AOS) can be momentarily unable to answer /health while it is
        # busy with a long request (chat / subagent run). Do NOT kill it -- let
        # it recover. Only terminate if it has been continuously unhealthy
        # longer than UNHEALTHY_KILL_THRESHOLD (a genuine hang/deadlock).
        now = time.time()
        if name not in _unhealthy_since:
            _unhealthy_since[name] = now
        unhealthy_for = now - _unhealthy_since[name]
        if unhealthy_for < UNHEALTHY_KILL_THRESHOLD:
            log(f"[supervise] {name} alive but unhealthy {unhealthy_for:.0f}s "
                f"(<{UNHEALTHY_KILL_THRESHOLD:.0f}s); waiting, will NOT kill")
            return
        log(f"[supervise] {name} alive but unhealthy >{UNHEALTHY_KILL_THRESHOLD:.0f}s; "
            f"terminating pid={p.pid}")
        p.terminate()
        try:
            p.wait(timeout=8)
        except subprocess.TimeoutExpired:
            p.kill()
    else:
        _fail_count[name] = 2  # dead -> restart immediately
        _unhealthy_since.pop(name, None)

    now = time.time()
    recent = [t for t in _restart_count.get(name, []) if now - t < 60]
    recent.append(now)
    _restart_count[name] = recent
    if len(recent) >= 5:
        _backoff[name] = min(_backoff.get(name, 1) * 2, 30)
    else:
        _backoff[name] = max(1.0, _backoff.get(name, 1) * 0.5)
    delay = _backoff[name]
    log(f"[supervise] restarting {name} (#{len(recent)}); backoff {delay:.1f}s")
    time.sleep(delay)
    start_service(name)
    if wait_healthy(name, 30):
        log(f"[supervise] {name} recovered")
        _fail_count[name] = 0
        _backoff[name] = 1.0


# ---- orchestration ---------------------------------------------------------
def run(only: list[str] | None, skip: list[str] | None, supervise: bool = True) -> None:
    global _stop
    enabled = [n for n in SERVICES if (only is None or n in only) and (skip is None or n not in skip)]

    # dependency-respecting start order
    ordered = []
    for n in SERVICES:
        if n in enabled and n not in ordered:
            for dep in SERVICES[n]["depends"]:
                if dep in enabled and dep not in ordered:
                    ordered.append(dep)
            ordered.append(n)

    START_TIMEOUT = {"deerflow": 300, "aos": 300, "web": 60, "openclaw": 90}
    log(f"Starting services: {ordered}")
    for name in ordered:
        spec = SERVICES[name]
        # Never start a service before its required dependencies are healthy.
        for dep in spec["depends"]:
            if not check_health(SERVICES[dep]):
                log(f"[wait] {name} blocked on dependency {dep}; waiting...")
                _deadline = time.time() + START_TIMEOUT.get(dep, 120)
                while time.time() < _deadline and not check_health(SERVICES[dep]):
                    time.sleep(3)
        # Idempotent: if the service is already healthy (e.g. the supervisor was
        # restarted while services are still up), attach to the running process
        # instead of spawning a duplicate that would fail to bind the port and
        # trigger a restart storm.
        if check_health(spec):
            port = _port_of(spec)
            pid = _pid_for_port(port) if port else None
            if pid:
                _procs[name] = _AttachedProc(pid)
                _start_time[name] = time.time()
                log(f"[start] {name} already healthy (pid={pid}); attached")
                save_pids()
                continue
        start_service(name)
        _to = START_TIMEOUT.get(name, 90)
        if not wait_healthy(name, _to):
            log(f"[WARN] {name} did not become healthy in {_to}s; continuing")
        else:
            log(f"[OK] {name} healthy")
        save_pids()

    if not supervise:
        log("Launched (no-supervise). Services run detached; exiting supervisor.")
        return

    log("All services launched. Supervising (Ctrl+C to stop)...")
    while not _stop:
        for name in ordered:
            maybe_restart(name)
        save_pids()
        time.sleep(3)


def do_check(only, skip) -> int:
    enabled = [n for n in SERVICES if (only is None or n in only) and (skip is None or n not in skip)]
    ok = True
    for name in enabled:
        live = _procs_maybe_live(name)
        healthy = check_health(SERVICES[name]) if live else False
        status = "HEALTHY" if healthy else ("RUNNING" if live else "DOWN")
        if not healthy:
            ok = False
        log(f"[check] {name:10s} {status}")
    return 0 if ok else 1


def _procs_maybe_live(name: str) -> bool:
    # Use the port from health spec to detect a live listener regardless of PID.
    spec = SERVICES[name]
    if spec["health"][0] == "tcp":
        return _tcp_ok(spec["health"][1], spec["health"][2])
    return _http_ok(spec["health"][1])


def do_stop() -> None:
    pids = load_pids()
    log(f"Stopping pids from {PID_FILE.name}: {pids}")
    for name, pid in pids.items():
        try:
            os.kill(pid, signal.SIGTERM)
        except Exception as e:
            log(f"[stop] failed to term {name} ({pid}): {e}")
    time.sleep(2)
    for name, pid in pids.items():
        try:
            os.kill(pid, signal.SIGKILL)
        except Exception:
            pass
    # also try ports as a safety net
    for spec in SERVICES.values():
        if spec["health"][0] == "tcp":
            _kill_by_port(spec["health"][2])
    # kill the supervisor itself if it is still alive (started elsewhere)
    try:
        if SUPERVISOR_LOCK.exists():
            txt = SUPERVISOR_LOCK.read_text(encoding="utf-8").strip()
            spid = int(txt)
            if _pid_alive(spid):
                log(f"[stop] terminating supervisor pid={spid}")
                os.kill(spid, signal.SIGTERM)
                time.sleep(1)
                if _pid_alive(spid):
                    os.kill(spid, signal.SIGKILL)
    except Exception:
        pass
    try:
        PID_FILE.unlink()
    except Exception:
        pass
    _release_supervisor_lock()
    log("Stop signal sent.")


def _kill_by_port(port: int) -> None:
    try:
        out = subprocess.run(
            ["netstat", "-ano"], capture_output=True
        ).stdout.decode("gbk", "ignore")
        for line in out.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                pid = line.split()[-1].strip()
                if pid.isdigit():
                    os.kill(int(pid), signal.SIGKILL)
    except Exception:
        pass


def _pid_for_port(port: int) -> int | None:
    """Find the PID owning a LISTENING socket on ``port`` (best effort)."""
    try:
        out = subprocess.run(
            ["netstat", "-ano"], capture_output=True
        ).stdout.decode("gbk", "ignore")
        for line in out.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                pid = line.split()[-1].strip()
                if pid.isdigit():
                    return int(pid)
    except Exception:
        pass
    return None


def _port_of(spec: dict) -> int | None:
    h = spec["health"]
    if h[0] == "tcp":
        return h[2]
    # http: parse port out of the URL
    try:
        return int(h[1].split(":")[-1].split("/")[0])
    except Exception:
        return None


class _AttachedProc:
    """A minimal Popen shim wrapping an already-running external PID so the
    supervisor can attach to services it did not spawn (idempotent restart)."""

    def __init__(self, pid: int):
        self.pid = pid

    def poll(self):
        return None if _pid_alive(self.pid) else 0

    def terminate(self):
        try:
            os.kill(self.pid, signal.SIGTERM)
        except Exception:
            pass

    def kill(self):
        try:
            os.kill(self.pid, signal.SIGKILL)
        except Exception:
            pass

    def wait(self, timeout: float = 8):
        import time as _t

        _deadline = _t.time() + timeout
        while _t.time() < _deadline:
            if not _pid_alive(self.pid):
                return 0
            _t.sleep(0.5)
        return None


def _handle_signal(signum, frame):
    global _stop
    _stop = True
    log(f"Received signal {signum}; shutting down...")
    for name in list(_procs.keys()):
        stop_service(name)
    try:
        PID_FILE.unlink()
    except Exception:
        pass
    _release_supervisor_lock()
    log("Shutdown complete.")
    sys.exit(0)


def main() -> None:
    ap = argparse.ArgumentParser(description="AOS unified supervisor")
    ap.add_argument("--check", action="store_true", help="Print health of services and exit")
    ap.add_argument("--stop", action="store_true", help="Stop services started by this supervisor")
    ap.add_argument("--only", nargs="*", help="Start only these services")
    ap.add_argument("--skip", nargs="*", help="Start all except these services")
    ap.add_argument("--no-supervise", action="store_true", help="Start once, do not supervise")
    args = ap.parse_args()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    if args.stop:
        do_stop()
        return
    if args.check:
        sys.exit(do_check(args.only, args.skip))
    if not _acquire_supervisor_lock():
        sys.exit(1)
    run(args.only, args.skip, supervise=not args.no_supervise)


if __name__ == "__main__":
    main()
