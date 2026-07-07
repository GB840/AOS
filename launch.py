"""
AOS v5.0 Unified Launcher -- starts API + UI together.

Usage:
    python launch.py              # Start both API and UI
    python launch.py --api-only   # Start only API server
    python launch.py --ui-only    # Start only Streamlit UI
    python launch.py --port 8080  # Custom API port
"""

import sys
import os
import subprocess
import time
import argparse
from pathlib import Path

# 获取项目根目录（支持不同运行方式）
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

def main():
    parser = argparse.ArgumentParser(description="AOS v5.0 Launcher")
    parser.add_argument("--api-only", action="store_true", help="Start only API server")
    parser.add_argument("--ui-only", action="store_true", help="Start only Streamlit UI")
    parser.add_argument("--port", type=int, default=8000, help="API port (default: 8000)")
    parser.add_argument("--ui-port", type=int, default=8501, help="UI port (default: 8501)")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind (default: 0.0.0.0)")
    args = parser.parse_args()

    print("=" * 50)
    print("  AOS v5.0 - Agent Operating System")
    print("  Hermes v0.15.2 + DeerFlow 2.0 DEEP")
    print("=" * 50)

    # 设置工作目录和Python路径（使用相对路径）
    os.chdir(PROJECT_ROOT)
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    if str(PROJECT_ROOT / "src") not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT / "src"))

    # 关键修复：子进程(uvicorn/streamlit)是独立 Python，不会继承本进程的 sys.path 插入。
    # 必须把项目根与 src/ 注入 PYTHONPATH，否则子进程里 `from utils.config` / `import src.api.main` 会失败。
    _env = os.environ.copy()
    _pp = _env.get("PYTHONPATH", "")
    _pp_parts = _pp.split(os.pathsep) if _pp else []
    for _p in (str(PROJECT_ROOT), str(PROJECT_ROOT / "src")):
        if _p not in _pp_parts:
            _pp_parts.insert(0, _p)
    _env["PYTHONPATH"] = os.pathsep.join(_pp_parts)

    print(f"  Project root: {PROJECT_ROOT}")
    print(f"  Working directory: {os.getcwd()}")

    try:
        from src.core import get_brain
        brain = get_brain()
        print(f"\n  Brain initialized: {brain.identity.aid}")
        health = brain.health_check()
        print(f"  Health: {health['status']}")
    except Exception as e:
        print(f"\n  WARNING: Brain init failed: {e}")
        print("  Continuing anyway...")

    processes = []

    try:
        if not args.ui_only:
            print(f"\n  Starting API server on {args.host}:{args.port}...")
            api_proc = subprocess.Popen([
                sys.executable, "-m", "uvicorn",
                "src.api.main:app",
                "--host", args.host,
                "--port", str(args.port),
                "--reload",
            ], cwd=str(PROJECT_ROOT), env=_env)
            processes.append(("API", api_proc))
            print(f"  API: http://localhost:{args.port}")
            print(f"  Docs: http://localhost:{args.port}/docs")

        if not args.api_only:
            time.sleep(2)
            print(f"\n  Starting Streamlit UI on port {args.ui_port}...")
            ui_proc = subprocess.Popen([
                sys.executable, "-m", "streamlit", "run",
                "src/web/app.py",
                "--server.port", str(args.ui_port),
                "--server.headless", "true",
            ], cwd=str(PROJECT_ROOT), env=_env)
            processes.append(("UI", ui_proc))
            print(f"  UI: http://localhost:{args.ui_port}")

        print("\n" + "=" * 50)
        print("  AOS is running! Press Ctrl+C to stop.")
        print("=" * 50)

        # Wait for any process to exit
        while all(p.poll() is None for _, p in processes):
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n  Shutting down...")
    finally:
        for name, proc in processes:
            if proc.poll() is None:
                print(f"  Stopping {name}...")
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        print("  AOS stopped.")

if __name__ == "__main__":
    main()
