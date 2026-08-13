"""本地价值账本（母纲原则 6：价值回流·劳动有报）。

母纲依据（AGENTS.md §0.0 原则 6）：用户创造的价值流回用户口袋；劳动有报。
本模块是「价值回流」的最小真实实现，不是口号：

  - 用户在系统中的劳动产物（蒸馏出的经验 / 可靠引擎洞察 / 工作区产物）被记账，
    且 **永远归用户所有**（credited_to="user"），本地落盘、可导出、不上传。
  - 反虹吸闸门 scan_value_siphon()：本模块自身零网络，并轻量扫描仓库，
    检测是否有代码同时引用 value_ledger 和网络模块（非完备污点分析）。

诚实边界（不吹）：
  - 本模块只负责「记账 + 回流」，不做平台抽成、不做价值变现。
    变现属商业层（见 §0.0.4），且必须卖「省事」不卖「准入」。
  - 反虹吸是轻量字面扫描，不是完备污点分析；作用是防「明显」外泄，非证明绝对安全。
"""
from __future__ import annotations

import ast
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_LEDGER_PATH = "data/workspaces/value_ledger.jsonl"

# 理念8「限最大存储条数防磁盘打满」：value_ledger.jsonl 上限。
# 与 trace_store._MAX_TRACE_FILES=500 同源纪律。价值账本低频但永不删除（母纲
# 原则6：价值归用户）。上限 20000（账本比日志需更大窗口），达上限搬最旧到
# value_ledger.archived.jsonl 冷存（不物理删）；export 合并冷存+主文件导出，
# 确保用户价值完整回流。
_MAX_LEDGER = 20000
_TRIM_CHECK_EVERY = 50
_ARCHIVED_SUFFIX = ".archived.jsonl"

# 网络导入模块（用于反虹吸静态扫描）。只列真正的网络库；
# 用 AST 解析抽取真实 import 语句，字符串/注释里的同名词不会误判。
_NETWORK_MODULES = ("requests", "urllib", "httpx", "aiohttp", "socket", "grpc")


def _default_ledger_path() -> str:
    env = os.environ.get("AOS_VALUE_LEDGER_PATH")
    if env:
        return env
    try:
        root = Path(__file__).resolve().parents[2]  # src/kernel/value_ledger.py -> 回溯2层
    except Exception:
        root = Path(os.getcwd())
    return str(root / DEFAULT_LEDGER_PATH)


class ValueLedger:
    """用户价值账本：本地、归用户、可导出、零网络。"""

    def __init__(self, path: Optional[str] = None):
        self.path = path or _default_ledger_path()
        self._entries: List[Dict[str, Any]] = []
        self._load()
        # 理念8 轮转计数器
        self._since_last_trim = 0

    def record(self, kind: str, ref: str, note: Optional[str] = None) -> Dict[str, Any]:
        """记一笔用户价值。credited_to 恒为 "user"——价值永远归用户，不归平台。"""
        e = {
            "ts": time.time(),
            "ts_human": time.strftime("%Y-%m-%d %H:%M:%S"),
            "kind": kind,
            "ref": ref,
            "note": note or "",
            "credited_to": "user",  # 铁律：价值归用户，不归平台
        }
        self._entries.append(e)
        self._append(e)
        return e

    def all(self) -> List[Dict[str, Any]]:
        return list(self._entries)

    def total(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for e in self._entries:
            out[e["kind"]] = out.get(e["kind"], 0) + 1
        return out

    def export(self, dest: str) -> str:
        """回流：把账本导出到指定路径（与 sovereignty.export_all 同源通用格式）。

        导出的就是用户自己的劳动凭证，没有 AOS 也能直接读——这正是
        母纲「价值流回用户口袋」的代码承接。合并冷存归档，确保价值完整。
        """
        p = Path(dest)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8") as f:
            # 先写冷存归档（旧），再写主文件（新），保持时间序
            arch_path = self.path + _ARCHIVED_SUFFIX
            if os.path.exists(arch_path):
                try:
                    with open(arch_path, encoding="utf-8") as af:
                        for line in af:
                            if line.strip():
                                f.write(line if line.endswith("\n") else line + "\n")
                except Exception as e:
                    # P4-6 修复：冷存归档读取失败原静默 pass，改为告警
                    logger.warning("ValueLedger: 读取冷存归档失败（%s）: %s", arch_path, e)
            for e in self._entries:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        return str(p)

    # ---- 内部 ----
    def _load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        self._entries.append(json.loads(line))
                    except Exception as e:
                        # P4-6 修复：单行解析失败原静默 pass，改为 debug（高频，用 debug 不刷屏）
                        logger.debug("ValueLedger: 跳过损坏行: %s", e)
        except Exception as e:
            # P4-6 修复：整个文件加载失败原静默 pass，改为告警
            logger.warning("ValueLedger: 加载账本失败（%s）: %s", self.path, e)

    def _append(self, e: Dict[str, Any]) -> None:
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
            # 理念8：防磁盘打满的节流轮转（价值归用户，搬冷存不物理删）
            self._since_last_trim += 1
            if self._since_last_trim >= _TRIM_CHECK_EVERY:
                self._since_last_trim = 0
                self._enforce_rotation()
        except Exception as e:
            # P4-6 修复：价值记账失败原静默 pass，改为告警——价值归用户，
            # 记账失败必须让运维感知（磁盘满/权限错误等）
            logger.warning("ValueLedger: 价值记账失败（%s）: %s", self.path, e)

    def _enforce_rotation(self) -> None:
        """达 _MAX_LEDGER 上限时搬最旧到 value_ledger.archived.jsonl 冷存。

        价值账本永不物理删（母纲原则6：价值归用户）。export 合并冷存+主文件
        导出，确保价值完整回流。轮转失败不致命（best-effort）。
        """
        try:
            if not os.path.exists(self.path):
                return
            with open(self.path, "r", encoding="utf-8") as f:
                lines = [ln for ln in f if ln.strip()]
            if len(lines) < _MAX_LEDGER:
                return
            keep = lines[-_MAX_LEDGER:]
            archive = lines[:-_MAX_LEDGER]
            if not archive:
                return
            arch_path = self.path + _ARCHIVED_SUFFIX
            with open(arch_path, "a", encoding="utf-8") as f:
                f.writelines(archive)
            with open(self.path, "w", encoding="utf-8") as f:
                f.writelines(keep)
            # 同步内存视图：_entries 只保留主文件对应的条目（冷存已归档）
            self._entries = self._entries[-len(keep):] if len(self._entries) > len(keep) else self._entries
        except Exception:
            pass


def _ast_imports(path: Path) -> List[str]:
    """用 AST 抽取文件里真实的 import 模块名（忽略字符串/注释里的同名文本）。"""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return []
    mods: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                mods.append(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                mods.append(node.module)
            for a in node.names:
                mods.append(a.name)
    return mods


def _network_import_in(mods: List[str]) -> Optional[str]:
    for m in mods:
        for nm in _NETWORK_MODULES:
            if m == nm or m.startswith(nm + "."):
                return nm
    return None


def scan_value_siphon(root: Optional[str] = None) -> List[Dict[str, str]]:
    """反虹吸静态扫描：轻量导入扫描，检测是否有代码同时引用 value_ledger 和网络模块。

    返回命中列表（空 = 干净）。扫描两条铁律：
      1. 本模块自身不得含任何网络 import（账本代码不能自己对外打电话）。
      2. 任何 import 了 value_ledger 的模块不得同时含网络 import。

    实现：只用 AST 解析「真实 import 语句」（不扫字符串/注释），且只扫
    src/ 生产代码（tests/ 里的 socket 模拟等不计入）。这样既不误报守卫清单
    自身的文本，也不误报测试代码的合法 import。

    诚实声明：轻量导入扫描，非完备污点分析；防「明显」外泄，非证绝对安全。
    """
    if root:
        base = Path(root)
    else:
        base = Path(_default_ledger_path()).resolve().parents[2]
    src_dir = base / "src" if (base / "src").is_dir() else base
    hits: List[Dict[str, str]] = []
    for py in sorted(src_dir.rglob("*.py")):
        if ".git" in py.parts or "node_modules" in py.parts:
            continue
        mods = _ast_imports(py)
        net = _network_import_in(mods)
        if not net:
            continue
        is_self = py.name == "value_ledger.py"
        imports_vl = any("value_ledger" in m for m in mods)
        if is_self:
            hits.append({"file": str(py), "reason": "账本模块自身含网络导入"})
        elif imports_vl:
            hits.append({"file": str(py),
                         "reason": f"import value_ledger 且含网络导入 {net}"})
    return hits
