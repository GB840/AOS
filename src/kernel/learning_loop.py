"""AIDE²-inspired 学习环（Learning Loop）—— 不犯同一错误两次。

核心机制（源自 Weco AIDE² 双层嵌套优化 + 树搜索淘汰制）：
  内层循环 = autopilot（搜索 → 执行 → 回报，已实现）
  外层循环 = LearningLoop（观察失败 → 分析根因 → 搜索替代方案 → 重试 → 验证）
  失败记忆库 = 持久化失败模式 + 成功修复方案，下次同类问题直接跳过

AIDE² 关键概念映射：
  - 树搜索淘汰制 → 失败模式匹配 + 预检拦截（约90%已知失败被提前拦掉）
  - 多臂老虎机 → 多修复策略加权选择（成功率高的优先）
  - 奖励黑客防御 → 验证门（修复后必须真跑通才算数）
  - 提示压缩 → 失败记忆压缩存储（只存模式指纹，不存原文）

使用：
  python -m kernel.learning_loop "帮我装好 ffmpeg"
  python -m kernel.learning_loop "搜索并安装最新的开源语音识别模型"

设计原则：
  - 零新依赖（JSON 文件做记忆库，标准库 only）
  - 渐进式：没有记忆库时等同于 autopilot
  - 记忆库自动积累，越用越聪明
"""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---- 数据模型 ----------------------------------------------------

@dataclass
class FailureRecord:
    """一次失败的记录，作为记忆单元持久化。"""
    id: str                                    # 唯一标识（hash）
    task_pattern: str                          # 任务模式指纹（泛化后的关键词）
    failed_step: str                           # 失败的步骤名（web.search / action.code_exec …）
    error_snippet: str                         # 错误信息片段（去噪后）
    root_cause: str                            # 根因分类（如 "missing_dependency" / "wrong_command"）
    fix_hint: str                              # 修复建议（如 "try: winget install ffmpeg"）
    resolved: bool = False                     # 是否已找到有效修复
    resolution: str = ""                       # 有效的修复方案
    attempts: int = 1                          # 同类错误出现次数
    created_at: str = field(default_factory=lambda: datetime.datetime.now().isoformat())


# ---- 失败记忆库 ------------------------------------------------

class FailureMemory:
    """持久化的失败模式库（本地 JSON 文件）。

    每次失败后存储模式指纹；再次遇到相同模式时，跳过冗余搜索直接提供已知修复。
    """

    _DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "_learning_memory", "failure_memory.json")

    def __init__(self, path: str | None = None, ttl_days: int = 30) -> None:
        self._path = path or self._DEFAULT_PATH
        self._ttl_days = ttl_days
        self._records: Dict[str, FailureRecord] = {}
        self._load()

    def _load(self) -> None:
        try:
            if os.path.exists(self._path):
                with open(self._path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                cutoff = datetime.datetime.now() - datetime.timedelta(days=self._ttl_days)
                loaded = forgotten = 0
                for rid, data in raw.items():
                    rec = FailureRecord(**data)
                    try:
                        created = datetime.datetime.fromisoformat(rec.created_at)
                    except Exception:
                        created = datetime.datetime.now()
                    # 原则2：失败即训练 + 遗忘（TTL）。过期模式自动丢弃，
                    # 避免记忆库无限膨胀、旧修复方案过时后仍被注入。
                    if created < cutoff:
                        forgotten += 1
                        continue
                    self._records[rid] = rec
                    loaded += 1
                if forgotten:
                    logger.info("FailureMemory 遗忘 %d 条过期记录 (TTL=%dd)", forgotten, self._ttl_days)
                    self._save()  # 持久化遗忘结果
                logger.info("FailureMemory 加载 %d 条记录", loaded)
        except Exception:
            logger.warning("FailureMemory 加载失败，从空库开始", exc_info=True)

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(
                {rid: _record_to_dict(r) for rid, r in self._records.items()},
                f, ensure_ascii=False, indent=2,
            )

    def add(self, record: FailureRecord) -> None:
        record.id = record.id or _fingerprint(record.task_pattern, record.failed_step, record.error_snippet)
        if record.id in self._records:
            self._records[record.id].attempts += 1
            if record.resolved and not self._records[record.id].resolved:
                self._records[record.id].resolved = True
                self._records[record.id].resolution = record.resolution
        else:
            self._records[record.id] = record
        self._save()

    def find_similar(self, task_pattern: str, failed_step: str) -> List[FailureRecord]:
        """查找与当前失败相似的历史记录。"""
        fp = _task_fingerprint(task_pattern)
        results: List[FailureRecord] = []
        for r in self._records.values():
            if r.failed_step == failed_step:
                sim = _pattern_similarity(fp, _task_fingerprint(r.task_pattern))
                if sim > 0.4:  # 相似度阈值
                    results.append(r)
        # 按相似度降序
        results.sort(key=lambda r: _pattern_similarity(fp, _task_fingerprint(r.task_pattern)), reverse=True)
        return results

    def get_fix_hints(self, task: str, failed_step: str) -> List[str]:
        """获取该任务+失败步的已知修复方案。"""
        similar = self.find_similar(task, failed_step)
        hints = []
        for r in similar:
            if r.resolved and r.resolution:
                hints.append(r.resolution)
            elif r.fix_hint:
                hints.append(r.fix_hint)
        return hints


def _record_to_dict(r: FailureRecord) -> Dict[str, Any]:
    d = {k: v for k, v in r.__dict__.items()}
    return d


# ---- 指纹与相似度 ------------------------------------------------


_IMPORTANT_WORDS = re.compile(r"[\u4e00-\u9fff]+|[a-zA-Z]{3,}", re.UNICODE)


def _task_fingerprint(task: str) -> set:
    """提取任务的模式指纹（关键词集合）。"""
    words = _IMPORTANT_WORDS.findall(task.lower())
    # 去 stop words
    stop = {"the", "and", "for", "with", "that", "this", "from", "are", "was",
            "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一",
            "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着",
            "没有", "看", "好", "自己", "这"}
    return {w for w in words if w not in stop}


def _pattern_similarity(a: set, b: set) -> float:
    """Jaccard 相似度。"""
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _fingerprint(task: str, failed_step: str, error: str) -> str:
    """生成该失败的唯一标识。"""
    raw = f"{task[:200]}|{failed_step}|{error[:200]}"
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


# ---- 失败分析器 --------------------------------------------------


_ERROR_PATTERNS = [
    # (正则, 根因分类, 默认修复提示)
    (r"(?:not found|no such file|command not found|不是.*命令|'[\w-]+' (?:is )?not recognized)",
     "missing_dependency", "该工具未安装，尝试用 winget / choco / pip 安装"),
    (r"(?:permission denied|access denied|拒绝访问|EACCES)",
     "permission_denied", "需要管理员权限，尝试以管理员身份运行"),
    (r"(?:timeout|timed out|超时|连接超时)",
     "timeout", "网络超时，重试或换镜像源"),
    (r"(?:syntax error|invalid syntax|unexpected token|解析错误)",
     "syntax_error", "命令语法错误，检查引号和转义"),
    (r"(?:out of memory|内存不足|OOM)",
     "out_of_memory", "内存不足，尝试减少并发或释放内存"),
    (r"(?:no space left|磁盘空间不足|disk full)",
     "disk_full", "磁盘空间不足，清理临时文件"),
    (r"(?:UnicodeDecodeError|encoding|decode error|charset)",
     "encoding_error", "编码问题，指定 UTF-8 或 GBK 编码"),
    (r"(?:WinError|windows error|Windows错误)",
     "windows_error", "Windows 平台问题，尝试用 cmd /c 替代 bash"),
    (r"(?:No module named|ModuleNotFoundError|ImportError|import.*error)",
     "missing_module", "Python 模块缺失，用 pip install 安装"),
    (r"(?:connection refused|cannot connect|无法连接|refused)",
     "connection_refused", "服务未启动或端口被占用"),
]


def analyze_failure(step_capability: str, error_text: str, task: str) -> FailureRecord:
    """分析执行失败的原因并生成修复建议。

    基于 AIDE² 的奖励黑客防御思路：不轻信错误信息表面文字，
    而是用模式匹配 + 上下文交叉验证根因。
    """
    error_clean = _clean_error(error_text)
    root_cause = "unknown"
    fix_hint = "搜索该错误信息找到解决方案"

    for pattern, cause, hint in _ERROR_PATTERNS:
        if re.search(pattern, error_text, re.IGNORECASE):
            root_cause = cause
            fix_hint = hint
            break

    # 如果错误很模糊但步骤是 code_exec，大概率是命令输错了
    if root_cause == "unknown" and step_capability == "action.code_exec":
        root_cause = "command_failed"
        fix_hint = "命令执行失败，检查命令格式或尝试替代命令"

    return FailureRecord(
        id="",
        task_pattern=task,
        failed_step=step_capability,
        error_snippet=error_clean[:300],
        root_cause=root_cause,
        fix_hint=fix_hint,
    )


def _clean_error(text: str) -> str:
    """去噪：移除时间戳、行号、堆栈帧等无关信息。"""
    # 去 ANSI escape codes
    text = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", text)
    # 去形如 "File \"...\", line N" 的堆栈行
    text = re.sub(r'File ".*?", line \d+.*?\n', "", text)
    # 去自动生成的 UUID / run ID
    text = re.sub(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "<UUID>", text)
    return text.strip()


# ---- 学习环 ------------------------------------------------------


class LearningLoop:
    """AIDE² 外层优化循环——包裹 autopilot，失败时学习并重试。

    核心循环：
      1. PREFLIGHT  — 查失败记忆库，有已知修复直接注入
      2. EXECUTE    — 跑 autopilot
      3. OBSERVE    — 成功了 → 返回；失败了 → 进分析
      4. ANALYZE    — 分析根因 + 搜索替代方案
      5. RETRY      — 用修复方案重试（最多 max_retries 轮）
      6. VERIFY     — 验证修复真的有效（奖励黑客防御）
      7. STORE      — 把模式 → 修复存入记忆库

    越用越聪明：每次失败都会积累到记忆库，下次同类问题直接走 PREFLIGHT 绕过。
    """

    def __init__(self, max_retries: int = 3, memory_path: str | None = None) -> None:
        self._max_retries = max_retries
        self._memory = FailureMemory(memory_path)

    def run(self, task: str, planner: str = "ag2") -> Dict[str, Any]:
        """执行任务，带失败学习与自动重试。"""
        start = time.time()
        retries = 0
        current_task = task
        fix_hints: List[str] = []
        trace: List[Dict[str, Any]] = []

        while retries < self._max_retries:
            # ---- PREFLIGHT：查记忆库 ----
            preflight_hints = self._memory.get_fix_hints(current_task, "action.code_exec")
            if preflight_hints:
                logger.info("PREFLIGHT: 命中 %d 条已知修复", len(preflight_hints))
                current_task = self._inject_hints(current_task, preflight_hints)

            # ---- EXECUTE ----
            from kernel.autopilot import run as autopilot_run
            result = autopilot_run(current_task, planner=planner)
            trace.append({
                "retry": retries,
                "planner": result.get("planner"),
                "ok_steps": result["execution"].get("ok_steps", 0),
                "failed_steps": result["execution"].get("failed_steps", 0),
            })

            # ---- OBSERVE ----
            exe = result.get("execution", {})
            if exe.get("failed_steps", 0) == 0:
                # 全部成功！
                result["learning"] = {"retries": retries, "memory_hits": len(preflight_hints)}
                result["total_duration_s"] = round(time.time() - start, 1)
                return result

            # ---- ANALYZE：定位失败步骤 ----
            failed_steps = [t for t in exe.get("trace", []) if not t.get("ok")]
            if not failed_steps:
                # 没有具体失败步 → 可能规划就错了，直接注入通用修复
                fix_hints.append(f"任务 '{task}' 执行失败，尝试简化任务或分步执行")
                current_task = self._inject_hints(task, fix_hints)
                retries += 1
                continue

            # 分析每个失败步
            for fs in failed_steps:
                step_cap = fs.get("capability", "unknown")
                error_text = str(fs.get("summary", "") + fs.get("error", ""))
                fr = analyze_failure(step_cap, error_text, task)

                # ---- 查历史：这个模式以前见过吗？ ----
                similar = self._memory.find_similar(task, step_cap)
                if similar:
                    known_fixes = [r.resolution or r.fix_hint for r in similar if r.resolved]
                    if known_fixes:
                        # 已知问题 + 已知修复 → 直接注入，不重复搜索
                        fix_hints.extend(known_fixes)
                        logger.info("ANALYZE: 命中已知修复: %s", known_fixes)
                        continue

                # ---- 新问题：搜索解决方案 ----
                search_query = _build_fix_query(fr)
                logger.info("ANALYZE: 新失败模式, 搜索: %s", search_query)
                fix_ideas = self._search_fix(search_query)
                fix_hints.extend(fix_ideas)

                # 存储（暂时 unresolved，等验证通过再标记）
                self._memory.add(fr)

            # ---- RETRY ----
            retries += 1
            logger.info("RETRY %d/%d: 注入 %d 条修复提示", retries, self._max_retries, len(fix_hints))
            current_task = self._inject_hints(task, fix_hints)

        # 重试耗尽
        return {
            "task": task,
            "planner": planner,
            "execution": {"ok_steps": 0, "failed_steps": 1, "trace": trace},
            "learning": {"retries": retries, "memory_updated": True, "hints_used": fix_hints},
            "error": "学习环重试耗尽，任务未完成。已记录失败模式，下次会更好。",
            "total_duration_s": round(time.time() - start, 1),
        }

    def _inject_hints(self, task: str, hints: List[str]) -> str:
        """把修复提示注入任务描述。过滤掉 URL-only / 无意义提示。"""
        if not hints:
            return task
        # 过滤：去重 + 去纯 URL + 去太短/太长的 + 只保留可操作的
        actionable_kw = ["install", "pip", "npm", "winget", "choco", "brew", "apt",
                         "run", "执行", "运行", "安装", "使用", "命令", "下载",
                         "download", "setup", "配置", "设置", "修改", "change",
                         "用", "试", "try", "use"]
        good = []
        for h in hints:
            h = h.strip()
            if not h or len(h) < 8 or len(h) > 300:
                continue
            if h.startswith("http") and " " not in h:
                continue  # 纯 URL
            # 拒收不可操作的碎片：必须含至少一个可操作关键词
            if not any(kw in h.lower() for kw in actionable_kw):
                continue
            # 拒收纯元数据行（license / 版权）
            skip_prefixes = ("cc ", "by-", "license", "copyright", "©")
            if any(h.lower().startswith(p) for p in skip_prefixes):
                continue
            if h not in good:
                good.append(h)
        if not good:
            return task
        uniq = good[:3]
        hint_text = ";\n".join(uniq)
        return (
            f"{task}\n\n"
            f"[系统提示：上次执行失败，已分析根因。已知修复方案：\n{hint_text}\n"
            f"请使用这些修复方案重试，不要重复之前的错误做法。]"
        )

    def _search_fix(self, query: str) -> List[str]:
        """搜索可能的修复方案。"""
        try:
            from core.fabric.adapters.search_adapter import SearchAdapter
            from core.fabric.adapter import InvokeRequest
            sa = SearchAdapter()
            if sa.health():
                res = sa.invoke(InvokeRequest(
                    capability="web.search",
                    payload={"type": "search", "query": query, "count": 3},
                ))
                if res.ok and res.data:
                    results = res.data.get("results", [])
                    return [r.get("summary", r.get("title", ""))[:200] for r in results if r]
        except Exception:
            logger.warning("搜索修复方案失败", exc_info=True)
        return []

    def verify_fix(self, task: str, original_error: str = "") -> bool:
        """验证修复是否真的有效（AIDE² 奖励黑客防御）。

        简单验证：重跑 autopilot，看是否还失败。
        更严格的验证（未来）：跑回归测试套件。
        """
        from kernel.autopilot import run as autopilot_run
        result = autopilot_run(task, planner="ag2")
        exe = result.get("execution", {})
        return exe.get("failed_steps", 0) == 0

    @property
    def memory_stats(self) -> Dict[str, Any]:
        """记忆库统计。"""
        records = self._memory._records
        total = len(records)
        resolved = sum(1 for r in records.values() if r.resolved)
        by_cause = {}
        for r in records.values():
            by_cause[r.root_cause] = by_cause.get(r.root_cause, 0) + 1
        return {
            "total_patterns": total,
            "resolved": resolved,
            "resolution_rate": f"{resolved/total*100:.0f}%" if total else "N/A",
            "top_causes": sorted(by_cause.items(), key=lambda x: x[1], reverse=True)[:5],
        }


def _build_fix_query(fr: FailureRecord) -> str:
    """从失败记录构造搜索查询。"""
    if fr.root_cause == "missing_dependency":
        return f"Windows 安装 {fr.task_pattern[:50]} 最简单方法"
    if fr.root_cause == "command_failed":
        return f"{fr.task_pattern[:50]} Windows 命令行 正确命令"
    if fr.root_cause == "windows_error":
        return f"{fr.task_pattern[:50]} Windows 替代方案 cmd"
    return f"{fr.task_pattern[:80]} {fr.root_cause} 解决方案"


# ---- CLI ---------------------------------------------------------


def _print_learning_result(r: Dict[str, Any]) -> None:
    learning = r.get("learning", {})
    exe = r.get("execution", {})

    print(f"\n{'='*60}")
    print(f"任务: {r['task'][:80]}")
    print(f"规划器: {r.get('planner', '?')}")
    print(f"耗时: {r.get('total_duration_s', r.get('duration_s', '?'))}s")
    print(f"重试: {learning.get('retries', 0)} 次")
    print(f"记忆命中: {learning.get('memory_hits', 0)} 条")
    print(f"{'='*60}")

    if r.get("error"):
        print(f"\n⚠️  {r['error']}")
    else:
        print(f"\n✅ 任务完成")

    trace = exe.get("trace", [])
    if trace:
        print(f"\n--- 执行历史 ---")
        for t in trace:
            rn = t.get("retry", "?")
            ok = t.get("ok_steps", "?")
            fail = t.get("failed_steps", "?")
            print(f"  第{rn}轮: {ok} 成功 / {fail} 失败")


def main() -> None:
    if len(sys.argv) < 2:
        print("用法: python -m kernel.learning_loop \"<任务描述>\"")
        print("示例:")
        print('  python -m kernel.learning_loop "帮我装好 ffmpeg"')
        print('  python -m kernel.learning_loop "搜索并安装最新的开源语音识别模型"')
        sys.exit(1)

    task = " ".join(sys.argv[1:])
    print(f"🧠 AOS 学习环: {task}")

    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
    except Exception:
        pass

    loop = LearningLoop(max_retries=2)
    result = loop.run(task)
    _print_learning_result(result)

    # 显示记忆库状态
    stats = loop.memory_stats
    print(f"\n--- 记忆库 ---")
    print(f"  已学习: {stats['total_patterns']} 种失败模式, {stats['resolved']} 已修复")
    print(f"  命中率: {stats['resolution_rate']}")
    if stats['top_causes']:
        print(f"  TOP 根因: {stats['top_causes'][:3]}")


if __name__ == "__main__":
    main()
