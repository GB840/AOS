#!/usr/bin/env python
"""
AOS v5.0 — AST 重复定义检测器 (CI 用)

检测「同一作用域内」被多次定义的函数 / 方法 / 类。Python 只会绑定
最后一个定义，前面的定义会被静默遮蔽 —— 这正是之前 brain.py 的 72 处
「重复方法」隐患的根因。

设计要点 (避免误报):
  - 作用域感知：模块 / 类 / 函数各自独立计数。
    cache_manager 里 3 个装饰器工厂各自内部的 `decorator`/`wrapper`
    处于不同函数作用域，不会被误报为重复。
  - 仅统计 `def`/`async def`/`class` 定义；普通赋值 (x=1; x=2) 忽略。
  - 自动排除 external/ (vendored 依赖)、node_modules、__pycache__ 与
    proto 生成的 *_pb2*.py。

退出码: 发现重复定义且 --fail-on-found 时返回 1 (CI 失败)；否则 0。
"""

import argparse
import ast
import os
import sys

# 默认排除的目录 (vendored / 生成物 / 缓存)
DEFAULT_EXCLUDE_DIRS = {
    "external", "node_modules", "__pycache__", ".git",
    ".venv", "venv", "env", "site-packages", "dist", "build",
}
# 排除的生成文件名模式 (proto 生成、Cython 等)
EXCLUDE_FILE_SUFFIXES = ("_pb2.py", "_pb2_grpc.py", "_pb2.pyi")


class Scope:
    __slots__ = ("kind", "label", "defs")

    def __init__(self, kind: str, label: str):
        self.kind = kind          # 'module' | 'class' | 'function'
        self.label = label        # 人类可读路径，如 "class UnifiedBrain"
        self.defs: dict[str, list[int]] = {}


class RedefVisitor(ast.NodeVisitor):
    def __init__(self, filename: str):
        self.filename = filename
        self.stack: list[Scope] = []
        self.issues: list[tuple[str, str, str, list[int]]] = []

    # ---- 作用域管理 ----
    def _enter(self, kind: str, label: str) -> None:
        self.stack.append(Scope(kind, label))

    def _exit(self) -> None:
        self.stack.pop()

    def _define(self, name: str, lineno: int) -> None:
        if not self.stack:
            return
        self.stack[-1].defs.setdefault(name, []).append(lineno)

    def _finalize(self) -> None:
        sc = self.stack[-1]
        for name, lines in sc.defs.items():
            if len(lines) > 1:
                self.issues.append((self.filename, sc.label, name, lines))

    # ---- 节点访问 ----
    def visit_Module(self, node: ast.Module) -> None:
        self._enter("module", "<module>")
        self.generic_visit(node)
        self._finalize()
        self._exit()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        if self.stack:
            self._define(node.name, node.lineno)
        self._enter("class", f"class {node.name}")
        self.generic_visit(node)
        self._finalize()
        self._exit()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if self.stack:
            self._define(node.name, node.lineno)
        self._enter("function", f"function {node.name}")
        self.generic_visit(node)
        self._finalize()
        self._exit()

    visit_AsyncFunctionDef = visit_FunctionDef


def _should_skip(path: str) -> bool:
    parts = set(os.path.normpath(path).split(os.sep))
    if parts & DEFAULT_EXCLUDE_DIRS:
        return True
    name = os.path.basename(path)
    if name.endswith(EXCLUDE_FILE_SUFFIXES):
        return True
    return False


def scan_path(root: str, issues: list) -> int:
    """扫描 root (文件或目录)，返回扫描的文件数。"""
    scanned = 0
    if os.path.isfile(root):
        files = [root]
    else:
        files = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in DEFAULT_EXCLUDE_DIRS]
            for fn in filenames:
                if fn.endswith(".py"):
                    files.append(os.path.join(dirpath, fn))

    for fpath in files:
        if _should_skip(fpath):
            continue
        try:
            with open(fpath, "r", encoding="utf-8") as fh:
                source = fh.read()
            tree = ast.parse(source, filename=fpath)
        except (SyntaxError, UnicodeDecodeError) as e:
            print(f"  [WARN] 跳过无法解析的文件 {fpath}: {e}", file=sys.stderr)
            continue
        scanned += 1
        visitor = RedefVisitor(fpath)
        visitor.visit(tree)
        issues.extend(visitor.issues)
    return scanned


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="检测同作用域内的重复 def/class 定义")
    parser.add_argument("paths", nargs="*", default=["src"],
                        help="要扫描的路径 (文件或目录)，默认 src")
    parser.add_argument("--fail-on-found", action="store_true", default=True,
                        help="发现重复时返回非零退出码 (CI 默认开启)")
    parser.add_argument("--no-fail", dest="fail_on_found", action="store_false",
                        help="仅报告，不设置失败退出码")
    args = parser.parse_args(argv)

    all_issues: list = []
    total = 0
    for p in args.paths:
        total += scan_path(p, all_issues)

    print(f"AST 重复定义检测: 扫描 {total} 个 Python 文件")

    if not all_issues:
        print("  ✅ 未发现同作用域内的重复定义。")
        return 0

    print(f"  ❌ 发现 {len(all_issues)} 处同作用域重复定义 (Python 只会保留最后一个):")
    for fpath, scope, name, lines in all_issues:
        locs = ", ".join(str(l) for l in lines)
        print(f"    - {fpath}:{locs}  [{scope}] 重复定义 `{name}`")
    return 1 if args.fail_on_found else 0


if __name__ == "__main__":
    raise SystemExit(main())
