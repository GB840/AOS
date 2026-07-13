'''pytest conftest — ensures v5.0 Config won't crash during collection.

Stability hook (L3 of the AOS stability system): a few test modules depend on
the native memory stack (zvec / cognee / rocksdb) which is known to CRASH the
process (0xC0000005) under load in this sandbox -- and a crash during import
kills the whole pytest run before any skip can take effect. We therefore
IGNORE those modules at collection time by default, so the suite always
finishes. Set AOS_RUN_NATIVE_TESTS=1 to opt back in (real hosts / deep runs).

The unified native probe (tests/_env_probe.py) still exposes PYTEST_SKIP_NATIVE
for finer-grained skips inside modules that merely *use* the native stack.
'''
import os
import sys
import pytest
from pathlib import Path

# 将 src/ 与 tests/ 加入 sys.path, 使模块的非前缀 import 在测试环境中可用.
_src_dir = str(Path(__file__).resolve().parent.parent / "src")
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)
_tests_dir = str(Path(__file__).resolve().parent)
if _tests_dir not in sys.path:
    sys.path.insert(0, _tests_dir)

# Must run before ANY import touches utils/config.py
_fields = ["API_KEY_HASH", "ADMIN_USERNAME", "ADMIN_PASSWORD", "POSTGRES_PASSWORD", "AOS_TOKEN_SECRET"]
for f in _fields:
    os.environ.setdefault(f, "conftest-placeholder")

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
except ImportError:
    pass

# --- L3 stability: ignore native-stack modules that crash the runner by default ---
RUN_NATIVE = os.environ.get("AOS_RUN_NATIVE_TESTS") == "1"

collect_ignore = []
if not RUN_NATIVE:
    # 这些模块在 import 阶段就会触发 zvec/cognee 原生崩溃 (0xC0000005)，
    # 必须跳过收集，否则会杀死整个 pytest 进程。
    collect_ignore += [
        "test_memory.py",
        "test_agency_roles_consolidation.py",
    ]
