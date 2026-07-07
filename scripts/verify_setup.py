"""
AOS v5.0 Startup Verification Script
=====================================
Verifies the system can start properly before launching.

Usage:
    python scripts/verify_setup.py
    python scripts/verify_setup.py --skip-docker
"""

import sys
import os
import time
import socket
import subprocess
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))


def check_port(port: int, host: str = "localhost") -> bool:
    """Check if a port is in use."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2)
    try:
        result = sock.connect_ex((host, port))
        return result == 0
    except Exception:
        return False
    finally:
        sock.close()


def check_path(path: str, description: str) -> bool:
    """Check if a path exists."""
    exists = os.path.exists(path)
    status = "✅" if exists else "❌"
    print(f"  {status} {description}: {path}")
    return exists


def check_module(module_name: str) -> bool:
    """Check if a Python module can be imported."""
    try:
        __import__(module_name)
        print(f"  ✅ {module_name} imported successfully")
        return True
    except ImportError as e:
        print(f"  ❌ {module_name} import failed: {e}")
        return False
    except Exception as e:
        print(f"  ⚠️  {module_name} warning: {e}")
        return True  # Warning is acceptable


def run_command(cmd: list, description: str) -> tuple[bool, str]:
    """Run a shell command and return success + output."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(PROJECT_ROOT),
        )
        success = result.returncode == 0
        status = "✅" if success else "❌"
        print(f"  {status} {description}")
        if not success and result.stderr:
            print(f"     Error: {result.stderr[:200]}")
        return success, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        print(f"  ⚠️  {description} (timeout)")
        return False, ""
    except FileNotFoundError:
        print(f"  ⏭️  {description} (not found)")
        return False, ""
    except Exception as e:
        print(f"  ❌ {description} failed: {e}")
        return False, ""


def main():
    print("=" * 60)
    print("  AOS v5.0 Startup Verification")
    print("=" * 60)
    print()

    all_ok = True

    # ---- Check directory structure ----
    print("📁 Directory structure:")
    dirs_ok = True
    dirs_ok &= check_path(str(PROJECT_ROOT / "src"), "src/ directory")
    dirs_ok &= check_path(str(PROJECT_ROOT / "src" / "api"), "src/api/ directory")
    dirs_ok &= check_path(str(PROJECT_ROOT / "src" / "web"), "src/web/ directory")
    dirs_ok &= check_path(str(PROJECT_ROOT / "src" / "core"), "src/core/ directory")
    dirs_ok &= check_path(str(PROJECT_ROOT / "src" / "deerflow"), "src/deerflow/ directory")
    dirs_ok &= check_path(str(PROJECT_ROOT / "src" / "hermes"), "src/hermes/ directory")
    dirs_ok &= check_path(str(PROJECT_ROOT / "src" / "memory"), "src/memory/ directory")
    dirs_ok &= check_path(str(PROJECT_ROOT / "src" / "skills"), "src/skills/ directory")
    dirs_ok &= check_path(str(PROJECT_ROOT / "tests"), "tests/ directory")
    dirs_ok &= check_path(str(PROJECT_ROOT / "configs"), "configs/ directory")
    all_ok &= dirs_ok
    print()

    # ---- Check critical files ----
    print("📄 Critical files:")
    files_ok = True
    files_ok &= check_path(str(PROJECT_ROOT / "pyproject.toml"), "pyproject.toml")
    files_ok &= check_path(str(PROJECT_ROOT / ".env.example"), ".env.example")
    files_ok &= check_path(str(PROJECT_ROOT / "requirements.txt"), "requirements.txt")
    files_ok &= check_path(str(PROJECT_ROOT / "config.yaml"), "config.yaml")
    files_ok &= check_path(str(PROJECT_ROOT / "src" / "api" / "main.py"), "src/api/main.py")
    files_ok &= check_path(str(PROJECT_ROOT / "src" / "core" / "brain.py"), "src/core/brain.py")
    files_ok &= check_path(str(PROJECT_ROOT / "launch.py"), "launch.py")
    all_ok &= files_ok
    print()

    # ---- Check Python environment ----
    print("🐍 Python environment:")
    print(f"  Python: {sys.version.split()[0]}")
    if sys.version_info < (3, 10):
        print("  ❌ Python 3.10+ required")
        all_ok = False
    else:
        print("  ✅ Python version OK")
    print()

    # ---- Check core modules ----
    print("📦 Core modules:")
    core_modules = [
        "fastapi",
        "uvicorn",
        "pydantic",
        "pydantic_settings",
        "streamlit",
        "requests",
        "chromadb",
        "pyyaml",
    ]
    modules_ok = all(check_module(m) for m in core_modules)
    all_ok &= modules_ok
    print()

    # ---- Check data directories ----
    print("💾 Data directories:")
    data_ok = True
    for subdir in ["data/sqlite", "data/chroma", "outputs", "logs"]:
        full_path = PROJECT_ROOT / subdir
        if not full_path.exists():
            try:
                full_path.mkdir(parents=True, exist_ok=True)
                print(f"  ✅ Created: {subdir}")
            except Exception as e:
                print(f"  ❌ Cannot create {subdir}: {e}")
                data_ok = False
        else:
            print(f"  ✅ {subdir} exists")
    all_ok &= data_ok
    print()

    # ---- Check port availability ----
    print("🔌 Port availability:")
    ports_ok = True
    for port, name in [(8000, "API server"), (8501, "Web UI"), (5432, "PostgreSQL")]:
        if check_port(port):
            print(f"  ⚠️  Port {port} ({name}) already in use")
            ports_ok = False
        else:
            print(f"  ✅ Port {port} ({name}) available")
    # Not a blocker, just a warning
    print()

    # ---- Check environment file ----
    print("🔐 Environment:")
    env_ok = True
    env_path = PROJECT_ROOT / ".env"
    env_example = PROJECT_ROOT / ".env.example"
    if env_path.exists():
        print("  ✅ .env exists")
        # Check for placeholder keys
        with open(env_path) as f:
            content = f.read()
        has_real_key = "ZHIPU_API_KEY=" in content and not any(
            line.strip().startswith("ZHIPU_API_KEY=$") or
            line.strip() == "ZHIPU_API_KEY="
            for line in content.split("\n")
            if line.strip().startswith("ZHIPU_API_KEY")
        )
        if has_real_key:
            print("  ✅ API key configured")
        else:
            print("  ⚠️  No API key configured (AOS will use fallback mode)")
    elif env_example.exists():
        print("  ⚠️  .env missing, copying from .env.example...")
        import shutil
        try:
            shutil.copy(env_example, env_path)
            print("  ✅ Created .env from template")
        except Exception as e:
            print(f"  ❌ Failed to create .env: {e}")
            env_ok = False
    else:
        print("  ⚠️  No .env or .env.example found")
    all_ok &= env_ok
    print()

    # ---- Quick import test ----
    print("🧠 AOS module import test:")
    try:
        from src.utils.config import config
        print(f"  ✅ Config loaded: {config.APP_NAME} v{config.APP_VERSION}")
    except Exception as e:
        print(f"  ⚠️  Config load warning: {e}")
        print("     (AOS will use defaults)")

    try:
        from src.router import LLMRouter, TaskType
        print("  ✅ Router module imported")
    except Exception as e:
        print(f"  ⚠️  Router import warning: {e}")

    try:
        from src.memory.memory import MemoryManager
        print("  ✅ Memory module imported")
    except Exception as e:
        print(f"  ⚠️  Memory import warning: {e}")
    print()

    # ---- Summary ----
    print("=" * 60)
    if all_ok:
        print("  ✅ ALL CHECKS PASSED")
        print()
        print("  You can now start AOS:")
        print("    python launch.py              # API + Web UI")
        print("    make run                      # Docker (if available)")
        print()
    else:
        print("  ❌ SOME CHECKS FAILED")
        print()
        print("  Please fix the issues above before starting AOS.")
        print("  Run 'python scripts/check_dependencies.py' for details.")
        print()
    print("=" * 60)

    return 0 if all_ok else 1


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Verify AOS setup")
    parser.add_argument("--skip-docker", action="store_true", help="Skip Docker checks")
    args = parser.parse_args()

    sys.exit(main())
