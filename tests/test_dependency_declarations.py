"""依赖声明对账守门测试。

背景（审查报告 #21 / #22，均核实为真，且实测比报告说的更严重）：
- requirements.txt 手抄了 9 个包，pyproject.toml 里有 19 个 —— 照前者装环境
  会缺 openai/litellm/httpx/psutil 等 10 个依赖。
- 更严重：``bcrypt`` / ``PyJWT`` / ``pydantic-settings`` / ``starlette`` /
  ``aiosqlite`` 这 5 个被代码模块顶层直接 import 的包，**两个文件里都没声明**，
  按 pyproject 装出来的环境连 API 服务都起不来（本轮实测踩中）。

一次性补齐会再次漂移，所以用这个测试从结构上守住：
1. src/ 下所有模块级第三方 import 必须能在 pyproject.toml 中找到声明；
2. requirements.txt 不得再手抄包清单（只允许注释 + "-e ." 转发）。

诚实分级：② 级（静态对账 + 单测实证）。
"""
from __future__ import annotations

import ast
import pathlib
import sys

import pytest

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"

# import 名 → 发行包名（两者不一致的情况）
_DIST_ALIAS = {
    "yaml": "pyyaml",
    "jwt": "pyjwt",
    "dotenv": "python-dotenv",
    "pil": "pillow",
    "multipart": "python-multipart",
    "sklearn": "scikit-learn",
    "cv2": "opencv-python",
    "google": "protobuf",       # google.protobuf 由 protobuf 发行包提供
    "grpc": "grpcio",
    "pydantic_settings": "pydantic-settings",
    "websocket": "websocket-client",
    "langchain_core": "langchain-core",
}

# 明确豁免：由本仓生成/托管，不是可安装的第三方包
_EXEMPT = {
    "src",           # 仓内绝对导入
}


def _local_module_names() -> set[str]:
    """src/ 下所有包名与模块名（含生成的 *_pb2.py），这些不是第三方依赖。"""
    names = set()
    for p in _SRC.rglob("*.py"):
        names.add(p.stem)
    for p in _SRC.rglob("*"):
        if p.is_dir():
            names.add(p.name)
    return names


def _collect_top_level_imports() -> dict[str, set[str]]:
    """收集 src/ 中所有 *模块级*（col_offset == 0）的第三方 import。

    函数体内的懒加载 import 不算 —— AOS 内核零依赖约定就是靠懒加载做到的，
    把它们算进硬依赖会逼着内核声明本不需要的包。
    """
    std = set(sys.stdlib_module_names)
    local = _local_module_names() | _EXEMPT
    found: dict[str, set[str]] = {}
    for f in _SRC.rglob("*.py"):
        try:
            tree = ast.parse(f.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            if getattr(node, "col_offset", 1) != 0:
                continue
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            else:
                names = [node.module] if (node.module and node.level == 0) else []
            for n in names:
                top = (n or "").split(".")[0]
                if top and top not in std and top not in local and not top.startswith("_"):
                    found.setdefault(top, set()).add(str(f.relative_to(_ROOT)))
    return found


def _declared_text() -> str:
    return (_ROOT / "pyproject.toml").read_text(encoding="utf-8").lower()


def test_pyproject_declares_every_top_level_third_party_import():
    declared = _declared_text()
    found = _collect_top_level_imports()
    assert found, "扫描不到任何第三方 import，说明扫描逻辑坏了"

    missing = {}
    for pkg, files in found.items():
        dist = _DIST_ALIAS.get(pkg.lower(), pkg.lower())
        if dist not in declared:
            missing[pkg] = sorted(files)[:3]

    assert not missing, (
        "以下包被 src/ 模块级 import 但未在 pyproject.toml 声明，"
        "按 pyproject 装出的环境会直接崩：\n"
        + "\n".join(f"  {p}  ← {', '.join(fs)}" for p, fs in sorted(missing.items()))
    )


@pytest.mark.parametrize("critical", [
    "bcrypt", "pyjwt", "pydantic-settings", "starlette", "aiosqlite",
])
def test_previously_missing_critical_deps_are_declared(critical):
    """这 5 个是本轮实测踩中的硬缺失，单独钉死防回退。"""
    assert critical in _declared_text(), f"{critical} 又从 pyproject 里消失了"


def test_requirements_txt_does_not_duplicate_the_package_list():
    """requirements.txt 只允许注释 + '-e .' 转发，不得再手抄包清单。"""
    req = _ROOT / "requirements.txt"
    if not req.exists():
        pytest.skip("requirements.txt 已删除，单一真相源目标同样达成")

    pinned = []
    for line in req.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s in ("-e .", "-e ./"):
            continue
        pinned.append(s)

    assert not pinned, (
        "requirements.txt 又出现了手抄的依赖行，会与 pyproject.toml 漂移：\n  "
        + "\n  ".join(pinned)
    )
