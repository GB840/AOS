"""
AOS v5.0 System Dependency Checker
===================================
Verifies that all required and optional dependencies are properly installed
and that external frameworks (Hermes, DeerFlow) are accessible.

Usage:
    python scripts/check_dependencies.py
    python scripts/check_dependencies.py --verbose
    python scripts/check_dependencies.py --fix
"""

import sys
import os
from pathlib import Path
from typing import NamedTuple
from dataclasses import dataclass
from enum import Enum

# Add project to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))


class Status(Enum):
    OK = "✅"
    WARN = "⚠️"
    FAIL = "❌"
    SKIP = "⏭️"


@dataclass
class Check:
    name: str
    status: Status
    message: str
    fix_hint: str = ""


class DependencyChecker:
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.checks: list[Check] = []
        self.project_root = PROJECT_ROOT

    def run(self) -> bool:
        """Run all checks. Returns True if all critical checks pass."""
        print("=" * 60)
        print("  AOS v5.0 Dependency Checker")
        print("=" * 60)
        print()

        self.check_python_version()
        self.check_core_packages()
        self.check_optional_packages()
        self.check_external_frameworks()
        self.check_data_directories()
        self.check_env_file()
        self.check_config()

        self.print_results()
        return self.all_passed

    @property
    def all_passed(self) -> bool:
        """True if no FAIL checks."""
        return not any(c.status == Status.FAIL for c in self.checks)

    def add(self, name: str, status: Status, message: str, fix_hint: str = ""):
        self.checks.append(Check(name, status, message, fix_hint))
        if self.verbose or status in (Status.FAIL, Status.WARN):
            print(f"  {status.value} {name}: {message}")
            if fix_hint:
                print(f"     💡 {fix_hint}")

    # ---- Python ----

    def check_python_version(self):
        v = sys.version_info
        version_str = f"{v.major}.{v.minor}.{v.micro}"
        if v >= (3, 10):
            self.add("Python", Status.OK, f"{version_str} (OK)")
        else:
            self.add("Python", Status.FAIL, f"{version_str} (need 3.10+)")

    # ---- Core packages ----

    def check_core_packages(self):
        core_packages = [
            ("fastapi", "FastAPI web framework"),
            ("uvicorn", "ASGI server"),
            ("pydantic", "Data validation"),
            ("pydantic_settings", "Settings management"),
            ("langchain_core", "LangChain core"),
            ("langgraph", "Multi-agent orchestration"),
            ("requests", "HTTP client"),
            ("httpx", "Async HTTP client"),
            ("chromadb", "Vector database"),
            ("streamlit", "Web UI"),
            ("yaml", "YAML parsing"),
        ]

        print("  Core packages:")
        all_ok = True
        for pkg, desc in core_packages:
            try:
                __import__(pkg)
                self.add(f"  {pkg}", Status.OK, "installed", "")
            except ImportError:
                self.add(f"  {pkg}", Status.FAIL, "NOT installed", f"pip install {pkg}")
                all_ok = False

        if all_ok:
            print(f"  {Status.OK.value} All core packages installed")

    # ---- Optional packages ----

    def check_optional_packages(self):
        print()
        print("  Optional packages:")

        optional_packages = [
            ("pytest", "Testing framework", "pip install pytest"),
            ("ruff", "Linter & formatter", "pip install ruff"),
            ("mypy", "Type checker", "pip install mypy"),
            ("pyaudio", "Audio recording (voice)", "pip install pyaudio"),
            ("librosa", "Audio processing", "pip install librosa"),
            ("opencv_python", "Computer vision", "pip install opencv-python"),
            ("Pillow", "Image processing", "pip install Pillow"),
            ("cognee", "Knowledge graphs", "pip install cognee"),
            ("duckduckgo_search", "Web search", "pip install duckduckgo-search"),
            ("jina", "Web content extraction", "pip install jina"),
            ("websocket_client", "WebSocket support", "pip install websocket-client"),
        ]

        for pkg, desc, fix in optional_packages:
            try:
                __import__(pkg)
                self.add(f"  {pkg}", Status.OK, f"{desc} ✓", "")
            except ImportError:
                self.add(f"  {pkg}", Status.WARN, f"{desc} (optional)", fix)

    # ---- External frameworks ----

    def check_external_frameworks(self):
        print()
        print("  External frameworks:")

        # Try to load from config
        try:
            from src.utils.config import config
            hermes_path = config.HERMES_SOURCE_PATH
            deerflow_path = config.DEERFLOW_SOURCE_PATH
        except Exception:
            hermes_path = str(self.project_root / "external" / "hermes-agent")
            deerflow_path = str(self.project_root / "external" / "deer-flow" / "backend")

        # Hermes Agent
        hermes_ok = False
        if hermes_path and os.path.exists(hermes_path):
            try:
                if os.path.exists(os.path.join(hermes_path, "run_agent.py")):
                    self.add("  Hermes Agent", Status.OK, f"Found at {hermes_path}")
                    hermes_ok = True
                else:
                    self.add("  Hermes Agent", Status.WARN, "Directory exists but run_agent.py not found",
                            "Ensure you cloned from NousResearch/hermes-agent")
            except Exception as e:
                self.add("  Hermes Agent", Status.WARN, f"Path error: {e}")
        else:
            self.add("  Hermes Agent", Status.SKIP, "Not found (will use AOS built-in fallback)",
                    f"Clone with: git clone https://github.com/NousResearch/hermes-agent {hermes_path}")

        # DeerFlow
        if deerflow_path and os.path.exists(deerflow_path):
            try:
                if os.path.exists(os.path.join(deerflow_path, "deerflow", "client.py")):
                    self.add("  DeerFlow 2.0", Status.OK, f"Found at {deerflow_path}")
                else:
                    self.add("  DeerFlow 2.0", Status.WARN, "Directory exists but deerflow/client.py not found",
                            "Ensure you cloned from ByteDance/deer-flow")
            except Exception as e:
                self.add("  DeerFlow 2.0", Status.WARN, f"Path error: {e}")
        else:
            self.add("  DeerFlow 2.0", Status.SKIP, "Not found (will use AOS built-in fallback)",
                    f"Clone with: git clone https://github.com/ByteDance/deer-flow external/deer-flow")

        # Sub-agents
        try:
            from src.deerflow.path_detect import detect_openclaw_path, detect_uitars_path
            from src.utils.config import config
            
            subagent_configs = [
                ("OpenClaw", detect_openclaw_path(), config.OPENCLAW_CWD),
                ("UI-TARS", detect_uitars_path(), config.UITARS_CWD),
                ("Lobster", config.LOBSTER_PATH, config.LOBSTER_PATH),
            ]
        except Exception:
            subagent_configs = [
                ("OpenClaw", str(self.project_root / "external" / "jiuwenclaw"), ""),
                ("UI-TARS", str(self.project_root / "external" / "UI-TARS-desktop"), ""),
                ("Lobster", str(self.project_root / "external" / "lobster"), ""),
            ]

        print()
        print("  Sub-agent sources:")
        for name, detected_path, config_path in subagent_configs:
            actual_path = detected_path or config_path
            if actual_path and os.path.exists(actual_path):
                self.add(f"  {name}", Status.OK, f"Found at {actual_path}")
            else:
                fallback_path = str(self.project_root / "external" / name.lower().replace("-", "_"))
                self.add(f"  {name}", Status.SKIP, f"Not found (configured: {config_path or 'not set'})",
                        f"Clone to {fallback_path} or set {name.upper()}_PATH in .env")

    # ---- Data directories ----

    def check_data_directories(self):
        print()
        print("  Data directories:")

        required_dirs = [
            "data/sqlite",
            "data/chroma",
            "outputs",
            "logs",
        ]

        all_ok = True
        for d in required_dirs:
            full_path = self.project_root / d
            if full_path.exists():
                self.add(f"  {d}", Status.OK, "exists")
            else:
                full_path.mkdir(parents=True, exist_ok=True)
                self.add(f"  {d}", Status.OK, "created")
                all_ok = False

        if all_ok:
            print(f"  {Status.OK.value} All data directories present")

    # ---- Environment file ----

    def check_env_file(self):
        print()
        env_path = self.project_root / ".env"
        env_example = self.project_root / ".env.example"

        if env_path.exists():
            self.add(".env", Status.OK, "exists")
        else:
            if env_example.exists():
                self.add(".env", Status.WARN, "Missing (will use .env.example)",
                        "cp .env.example .env")
            else:
                self.add(".env", Status.FAIL, "Missing and no .env.example found")

        # Check for API keys
        if env_path.exists():
            with open(env_path) as f:
                content = f.read()

            has_any_key = any(k in content for k in [
                "ZHIPU_API_KEY", "SILICONFLOW_API_KEY", "BAIDU_API_KEY",
                "UNIFIED_API_KEY", "OLLAMA"
            ])

            if "ZHIPU_API_KEY=" in content and "ZHIPU_API_KEY=$" not in content and "ZHIPU_API_KEY=$" not in content:
                self.add("  API Keys", Status.OK, "At least one API key configured")
            elif has_any_key:
                self.add("  API Keys", Status.WARN, "Some keys configured but may be empty",
                        "Check .env and fill in your API keys")
            else:
                self.add("  API Keys", Status.FAIL, "No API keys configured",
                        "Add API keys to .env (see .env.example)")

    # ---- Config file ----

    def check_config(self):
        print()
        config_path = self.project_root / "config.yaml"
        if config_path.exists():
            self.add("config.yaml", Status.OK, "exists")
        else:
            self.add("config.yaml", Status.WARN, "Not found (optional, defaults used)")

    # ---- Print summary ----

    def print_results(self):
        print()
        print("=" * 60)

        fail_count = sum(1 for c in self.checks if c.status == Status.FAIL)
        warn_count = sum(1 for c in self.checks if c.status == Status.WARN)
        skip_count = sum(1 for c in self.checks if c.status == Status.SKIP)
        ok_count = sum(1 for c in self.checks if c.status == Status.OK)

        print(f"  Summary: {ok_count} OK  {warn_count} WARN  {fail_count} FAIL  {skip_count} SKIP")
        print("=" * 60)

        if fail_count > 0:
            print()
            print("  ❌ CRITICAL: Some required dependencies are missing!")
            print("  Please fix the FAIL items before running AOS.")
            print()
            return False
        elif warn_count > 0:
            print()
            print("  ⚠️  WARNING: Some optional dependencies are missing.")
            print("  AOS will work but some features may be disabled.")
            print()
            return True
        else:
            print()
            print("  ✅ All dependencies ready! Run `python launch.py` to start AOS.")
            print()
            return True


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Check AOS dependencies")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show all checks")
    parser.add_argument("--fix", action="store_true", help="Attempt to fix issues")
    args = parser.parse_args()

    checker = DependencyChecker(verbose=args.verbose)
    success = checker.run()

    if args.fix:
        print()
        print("Auto-fix not implemented. Please follow the fix hints above.")

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
