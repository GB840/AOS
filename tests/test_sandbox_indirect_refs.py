"""沙箱间接引用拦截回归测试。

验证 `_check_dangerous_patterns` 覆盖 9 类进程派生载荷（含原漏的 5 类间接引用：
模块别名 / from-import 别名 / __import__ 直接调用 / importlib·builtins 动态加载 /
变量别名转手 / sys.modules 动态获取），且合法代码不被误杀。

诚实边界声明：本层是 **defense-in-depth 护栏，非安全边界**。纯 Python 内的
删文件 / 偷密钥 / 打网络 / 吃内存载荷本层不防护，不可信代码必须进容器 / VM。
"""
import pytest

from execution.sandbox import _check_dangerous_patterns as chk

# 9 个进程派生载荷（原 4 拦 + 新补 5 族间接引用），全部应被拦
PROCESS_SPAWN_PAYLOADS = [
    'import os; os.system("calc")',
    'import os as o; o.system("calc")',
    'from os import system; system("calc")',
    'getattr(__import__("o"+"s"), "sys"+"tem")("calc")',
    'import importlib; importlib.import_module("os").system("calc")',
    'eval(compile(__import__("base64").b64decode(b"xxx")))',
    'import builtins; builtins.__import__("os").system("calc")',
    'import os\nf = os.system\nf("calc")',
    'import sys; sys.modules["os"].system("calc")',
]

# 合法代码，不应被拦（验证不误杀）
SAFE_CODE = [
    'import os.path\nprint(os.path.join("a","b"))',
    'import sys\nprint(sys.argv)',
    'import subprocess\nprint(subprocess)',
    'import importlib\nprint(importlib.util.find_spec("os"))',
    'print(sum([1,2,3]))',
    'import json\njson.dumps({"a":1})',
    'import os\nprint(os.getcwd())',
]


@pytest.mark.parametrize("code", PROCESS_SPAWN_PAYLOADS)
def test_process_spawn_payloads_blocked(code):
    """进程派生载荷必须被拦截（含 5 类间接引用绕过方式）。"""
    assert chk(code) is not None, f"进程派生载荷应被拦截: {code!r}"


@pytest.mark.parametrize("code", SAFE_CODE)
def test_safe_python_code_passes(code):
    """合法 Python 代码不应被误杀。"""
    assert chk(code) is None, f"合法代码不应被拦: {code!r}"
