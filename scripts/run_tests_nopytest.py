# -*- coding: utf-8 -*-
"""无 pytest 环境下内联复跑指定测试模块（仅支持无 fixture 的纯函数用例）。"""
import importlib
import sys
import traceback
import types
from contextlib import contextmanager

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, r"D:\AOS")
sys.path.insert(0, r"D:\AOS\src")   # 测试用 `from kernel.xxx import` 形式

# ---- 最小 pytest stub：无 pytest 环境下让纯函数用例可跑（raises/approx/mark/fixture/skip）----
if "pytest" not in sys.modules:
    try:
        import pytest  # noqa: F401
    except ModuleNotFoundError:
        _pt = types.ModuleType("pytest")

        class _ExcInfo:
            """模拟 pytest 的 ExceptionInfo，支持 e.value / e.type / str(e)。"""

            def __init__(self):
                self.value = None
                self.type = None

            def __str__(self):
                return str(self.value)

        @contextmanager
        def _raises(exc, match=None, **kw):
            info = _ExcInfo()
            try:
                yield info
            except exc as err:
                info.value, info.type = err, type(err)
                if match:
                    import re
                    assert re.search(match, str(err)), f"{err!r} 不匹配 {match!r}"
                return
            raise AssertionError(f"DID NOT RAISE {exc}")

        class _Approx:
            def __init__(self, v, rel=1e-6, abs=1e-9):
                self.v, self.rel, self.abs = v, rel, abs

            def __eq__(self, other):
                return abs(other - self.v) <= max(self.abs, self.rel * abs(self.v))

        class _MarkStub:
            def __getattr__(self, _name):
                def deco(*a, **kw):
                    if a and callable(a[0]):
                        return a[0]
                    return lambda fn: fn
                return deco

        def _fixture(*a, **kw):
            if a and callable(a[0]):
                return a[0]
            return lambda fn: fn

        def _skip(reason=""):
            raise RuntimeError(f"skipped: {reason}")

        _pt.raises = _raises
        _pt.approx = _Approx
        _pt.mark = _MarkStub()
        _pt.fixture = _fixture
        _pt.skip = _skip
        _pt.importorskip = lambda name, **kw: importlib.import_module(name)
        sys.modules["pytest"] = _pt

MODULES = [
    "tests.test_soul_memory_lineage",
    "tests.test_spirit_layer",
    "tests.test_lifeform_selfbuild",
]

total_pass = total_fail = 0
for name in MODULES:
    try:
        mod = importlib.import_module(name)
    except Exception as exc:  # noqa: BLE001
        print(f"[SKIP] {name} 导入失败：{exc}")
        continue
    funcs = [(k, v) for k, v in vars(mod).items()
             if k.startswith("test_") and callable(v) and getattr(v, "__module__", "") == mod.__name__]
    p = f = 0
    for fname, fn in funcs:
        try:
            if fn.__code__.co_argcount:      # 需要 fixture，跳过
                print(f"  SKIP {fname} (需 fixture)")
                continue
            fn()
            p += 1
        except Exception as exc:  # noqa: BLE001
            f += 1
            print(f"  FAIL {fname}: {exc}")
            traceback.print_exc()
    total_pass += p
    total_fail += f
    print(f"[{name}] {p} passed / {f} failed （共 {len(funcs)} 个用例）")

print(f"\n===== 汇总：{total_pass} passed / {total_fail} failed =====")
sys.exit(1 if total_fail else 0)
