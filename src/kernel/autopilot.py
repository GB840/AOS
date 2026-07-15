"""AOS 自主闭环（Autopilot）：一句话任务 → 自己搜 → 自己装 → 回来汇报。

把 ag2 规划 + plan_bridge 解析 + OrchestrationChiplet 编排 + 真实适配器
（搜索 / 代码执行 / LLM 推理 / 记忆）串成一条自给自足的管道。

使用方式：
  python -m kernel.autopilot "在本地装好 ffmpeg 并验证"
  python -m kernel.autopilot "搜索最新的开源语音识别模型并评估是否适合 Windows"

设计原则：
  - 零依赖 FabricHub 全量构造（不拖 deerflow / 127 个适配器注册的慢启动）
  - 所有适配器按需惰性初始化
  - ag2 不可用时透明降级 heuristic planner
  - 执行结果清晰可读（不堆 raw JSON）
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---- 适配器惰性单例 ------------------------------------------------

_search: Any = None
_code_exec: Any = None
_ag2: Any = None


def _get_search():
    global _search
    if _search is None:
        from core.fabric.adapters.search_adapter import SearchAdapter
        _search = SearchAdapter()
    return _search


def _get_code_exec():
    global _code_exec
    if _code_exec is None:
        from core.fabric.adapters.code_execution_adapter import CodeExecutionAdapter
        _code_exec = CodeExecutionAdapter()
    return _code_exec


def _get_ag2():
    global _ag2
    if _ag2 is None:
        from core.fabric.adapters.ag2_adapter import AG2Adapter
        _ag2 = AG2Adapter()
    return _ag2


# ---- 路由胶水 --------------------------------------------------

def _route(capability: str, payload: Dict[str, Any]) -> Any:
    """把 OrchestrationChiplet 的能力调用派发给真实适配器。"""
    from core.fabric.adapter import InvokeRequest, InvokeResult
    from core.fabric.capability import Capability

    if capability == "web.search":
        ad = _get_search()
        # 从各种可能的 payload 字段里提取搜索查询
        query = payload.get("query") or payload.get("task") or ""
        if not query and "content" in payload:
            query = str(payload.get("content", ""))
        query = query.strip()[:300]
        if not query:
            return InvokeResult(ok=False, error="autopilot: 搜索步缺少查询词")
        return ad.invoke(InvokeRequest(
            capability="web.search",
            payload={"type": "search", "query": query, "count": 5},
        ))

    if capability == "action.code_exec":
        ad = _get_code_exec()
        code = payload.get("code") or payload.get("task") or ""
        if not code and "content" in payload:
            code = str(payload.get("content", ""))
        # 如果内容是推理步的冗长输出，尝试从中提取可执行命令
        code = _extract_cmd_from_text(code.strip()[:2000])
        if not code:
            return InvokeResult(ok=False, error="autopilot: 代码执行步缺少可执行命令")
        return ad.invoke(InvokeRequest(
            capability="action.code_exec",
            payload={"code": code, "language": _guess_language(code)},
        ))

    if capability in ("inference.llm", "cognition.reasoning", "cognition.planning"):
        ag2 = _get_ag2()
        from core.fabric.capability import Capability
        topic = payload.get("task") or payload.get("content") or payload.get("text") or "处理上游结果"
        if len(topic) > 1000:
            topic = topic[:1000]
        # 当推理步的入参疑似来自搜索步（含 URL / "Search Results"），且下
        # 一步大概率是 code_exec 时，强制 LLM 输出可执行命令而非人话描述。
        if "search" in topic[:200].lower() or "http" in topic[:500].lower() or "URL" in topic:
            cmd = _extract_command_direct(topic)
            if cmd:
                return InvokeResult(ok=True, data={"content": cmd, "command": cmd})
            # 直接提取失败时回落 ag2 群聊
        return ag2.invoke(InvokeRequest(
            capability=Capability.GROUP_ORCHESTRATION.value,
            payload={"text": topic},
        ))

    if capability == "memory.semantic":
        return InvokeResult(ok=True, data={"content": "memory not yet wired in autopilot"})

    return InvokeResult(ok=False, error=f"autopilot: 不支持的能力 {capability}")


def _extract_command_direct(topic: str) -> str:
    """从搜索结果里直接提取安装命令（轻量 LLM 调用，绕过 ag2 群聊噪音）。

    返回干净的命令字符串如 "winget install ffmpeg"，失败返回空字符串。
    """
    try:
        from openai import OpenAI
        import os as _os
        api_key = _os.environ.get("ZHIPU_API_KEY", "")
        if not api_key:
            return ""
        client = OpenAI(
            api_key=api_key,
            base_url="https://open.bigmodel.cn/api/paas/v4",
        )
        prompt = (
            f"从以下搜索结果中提取在 Windows 上安装软件的一条终端命令。"
            f"只输出命令本身（如 winget install xxx 或 choco install xxx），"
            f"不要任何解释、markdown、反引号。如果搜索结果是中文文章，"
            f"从中找到 Windows 安装步骤并提取具体命令。\n\n搜索结果:\n{topic[:1500]}"
        )
        resp = client.chat.completions.create(
            model="glm-4-flash",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=100,
        )
        cmd = resp.choices[0].message.content.strip()
        # 清洗：去反引号、去 markdown 标记、去行首的 - * 等
        cmd = re.sub(r"^```[\w]*\s*|```$", "", cmd, flags=re.MULTILINE).strip()
        cmd = re.sub(r"^[-*•]\s*", "", cmd).strip()
        # 只要第一行（最可能是命令的那行）
        cmd = cmd.split("\n")[0].strip()
        return cmd if len(cmd) > 3 and len(cmd) < 200 else ""
    except Exception:
        logger.warning("_extract_command_direct 失败", exc_info=True)
        return ""


def _extract_cmd_from_text(text: str) -> str:
    """从推理步的冗长文本里提取可执行命令（兜底，防止 verbose ag2 文本灌入 code_exec）。"""
    if not text:
        return ""
    # 如果本身就是一行干净命令，直接返回
    text = text.strip()
    if len(text) < 300 and not "\n" in text:
        return text

    # 否则从多行文本里找命令行
    cmd_prefixes = ["winget ", "choco ", "pip ", "npm ", "python ", "brew ", "apt ",
                    "curl ", "wget ", "git clone", "docker ", "echo "]
    for line in text.split("\n"):
        line = line.strip().strip("`\"'")
        for prefix in cmd_prefixes:
            if line.lower().startswith(prefix):
                return line
    # 没找到 → 返回原文本（让 code_exec 自己试）
    return text


def _guess_language(code: str) -> str:
    """从代码内容推测语言。"""
    low = code.strip().lower()
    if low.startswith(("echo ", "ls ", "pip ", "npm ", "apt ", "brew ", "choco ", "winget ")):
        return "bash"
    if any(kw in low for kw in ("function", "const ", "let ", "var ", "console.")):
        return "javascript"
    return "bash"  # 默认 bash（安装/系统命令最常见）


# ---- 主入口 ------------------------------------------------------

def run(task: str, planner: str = "ag2") -> Dict[str, Any]:
    """执行一个自主任务。

    Args:
        task: 自然语言任务（如 "安装 ffmpeg 并验证"）
        planner: "ag2"（LLM 规划，需智谱 key）或 "heuristic"（纯本地关键词）

    Returns:
        {
            "task": str,
            "planner": str,
            "plan": str | None,
            "steps": [...],
            "execution": {ok_steps, failed_steps, trace, final},
            "duration_s": float,
        }
    """
    from core.fabric.adapter import InvokeRequest, InvokeResult
    from core.fabric.capability import Capability
    from kernel.plugins.plan_bridge import parse_plan_to_steps, heuristic_plan
    from kernel.plugins.orchestration_chiplet import OrchestrationChiplet

    start = time.time()
    caps = [
        "web.search", "action.code_exec", "inference.llm",
        "memory.semantic", "cognition.reasoning", "cognition.planning",
    ]

    # ---- 1. 规划 ----
    plan_text: Optional[str] = None
    steps: List[Dict[str, Any]] = []
    used_planner = planner

    if planner == "ag2":
        try:
            ag2 = _get_ag2()
            if ag2.health():
                res = ag2.invoke(InvokeRequest(
                    capability=Capability.PLANNING.value,
                    payload={"topic": task},
                ))
                if isinstance(res, InvokeResult) and res.ok and res.data:
                    plan_text = (res.data.get("plan") or "").strip() or None
                    if plan_text:
                        steps = parse_plan_to_steps(plan_text, caps)
        except Exception:
            logger.warning("ag2 规划失败，降级 heuristic", exc_info=True)

    if not steps:
        steps = heuristic_plan(task, caps)
        used_planner = "heuristic"
        plan_text = None

    if not steps:
        return {
            "task": task, "planner": used_planner,
            "error": "无法生成任何执行步骤",
            "duration_s": round(time.time() - start, 1),
        }

    # ---- 2. 执行 ----
    oc = OrchestrationChiplet(route_fn=_route)
    exe_res = oc.invoke(InvokeRequest(
        capability="workflow.execute",
        payload={"initial": {"task": task}, "steps": steps},
    ))

    data = exe_res.data if isinstance(exe_res, InvokeResult) else {}
    duration = round(time.time() - start, 1)

    # ---- 3. 汇总 ----
    # 提取最后成功的输出
    final = None
    for t in reversed(data.get("trace", [])):
        if t.get("ok") and t.get("output") is not None:
            final = str(t.get("output", ""))[:500]
            break

    # ---- 4. 结构化 Trace（原则 8：可观测性）----
    trace = _build_structured_trace(task, used_planner, plan_text, steps, data, duration)
    _save_trace(trace)

    # ---- 5. 置信度评分（原则 6：量化置信）----
    confidence = _score_confidence(data, steps)

    return {
        "task": task,
        "planner": used_planner,
        "plan": plan_text,
        "steps": [
            {"capability": s["capability"], "in": s.get("in", s.get("in_from", ""))}
            for s in steps
        ],
        "execution": {
            "ok_steps": data.get("ok_steps", 0),
            "failed_steps": data.get("failed_steps", 0),
            "trace": [
                {
                    "step": t.get("step"),
                    "capability": t.get("capability", ""),
                    "ok": t.get("ok"),
                    "summary": str(t.get("summary", t.get("output", "")))[:200],
                }
                for t in data.get("trace", [])
            ],
            "final": final,
        },
        "confidence": confidence,
        "trace_id": trace["task_id"],
        "duration_s": duration,
    }


# ---- 结构化 Trace（原则 8）----------------------------------------

_TRACE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "_traces")
_TRACE_MAX = 500  # 最多保留 500 条，防磁盘打满


def _build_structured_trace(task, planner, plan_text, steps, data, duration):
    """构建符合原则8规范的JSON Trace。"""
    import uuid as _uuid
    raw_trace = data.get("trace", [])
    return {
        "task_id": str(_uuid.uuid4())[:8],
        "timestamp": datetime.datetime.now().isoformat(),
        "input": {"task": task, "planner": planner, "plan": plan_text},
        "steps": [
            {
                "capability": t.get("capability", s.get("capability", "")),
                "ok": t.get("ok", False),
                "output": str(t.get("out", t.get("output", t.get("summary", ""))))[:500],
                "error": str(t.get("error", ""))[:300] if not t.get("ok") else "",
            }
            for s, t in zip(steps, raw_trace)
        ],
        "output": {
            "ok_steps": data.get("ok_steps", 0),
            "failed_steps": data.get("failed_steps", 0),
        },
        "metrics": {
            "latency_ms": round(duration * 1000),
            "ok_steps": data.get("ok_steps", 0),
            "failed_steps": data.get("failed_steps", 0),
        },
    }


def _save_trace(trace: dict) -> None:
    """保存结构化 trace 到磁盘（原则 8 落盘，原则 9 可验证）。"""
    try:
        os.makedirs(_TRACE_DIR, exist_ok=True)
        # 轮转清理
        existing = sorted(os.listdir(_TRACE_DIR))
        if len(existing) >= _TRACE_MAX:
            for old in existing[:_TRACE_MAX // 5]:  # 删最旧的 20%
                try:
                    os.remove(os.path.join(_TRACE_DIR, old))
                except OSError:
                    pass
        fname = f"trace_{trace['task_id']}_{int(time.time())}.json"
        with open(os.path.join(_TRACE_DIR, fname), "w", encoding="utf-8") as f:
            json.dump(trace, f, ensure_ascii=False, indent=2)
    except Exception:
        logger.warning("保存 trace 失败", exc_info=True)


# ---- 置信度评分（原则 6）-----------------------------------------

def _score_confidence(data: dict, steps: list) -> dict:
    """三级置信度评分（低/中/高）。

    原则 6 落地：输出附带结构化原始指标作为置信参考。
    """
    ok = data.get("ok_steps", 0)
    fail = data.get("failed_steps", 0)
    total = len(steps)
    trace = data.get("trace", [])

    search_results = 0
    exit_codes_ok = 0
    for t in trace:
        out = str(t.get("output", t.get("summary", "")))
        if "exe" in out.lower() or "code_exec" in t.get("capability", ""):
            if t.get("ok"):
                exit_codes_ok += 1
        if "search" in t.get("capability", "").lower():
            # 估算搜索结果条数
            search_results += out.count("URL") + out.count("http")

    # 三级判定
    if fail > 0 and ok == 0:
        level = "low"
        label = "🔴 低置信"
    elif total > 0 and ok / total >= 0.8:
        level = "high"
        label = "🟢 高置信"
    else:
        level = "medium"
        label = "🟡 中置信"

    return {
        "level": level,
        "label": label,
        "metrics": {
            "ok_steps": ok,
            "failed_steps": fail,
            "total_steps": total,
            "search_results_approx": search_results,
            "code_exec_exit_ok": exit_codes_ok,
            "success_rate": f"{ok/total*100:.0f}%" if total > 0 else "N/A",
        },
    }


# ---- CLI ---------------------------------------------------------

def _print_result(r: Dict[str, Any]) -> None:
    """友好打印执行结果。"""
    exe = r.get("execution", {})
    trace = exe.get("trace", [])

    print(f"\n{'='*60}")
    print(f"任务: {r['task']}")
    print(f"规划器: {r['planner']}")
    print(f"耗时: {r['duration_s']}s")
    print(f"结果: {exe.get('ok_steps',0)} 步成功, {exe.get('failed_steps',0)} 步失败")
    print(f"{'='*60}")

    if r.get("plan"):
        print(f"\n--- AG2 规划 ---")
        for line in r["plan"].split("\n"):
            if line.strip():
                print(f"  {line.strip()}")

    print(f"\n--- 执行步骤 ---")
    for i, s in enumerate(r.get("steps", [])):
        cap = s["capability"]
        t = trace[i] if i < len(trace) else {}
        ok = "✅" if t.get("ok") else "❌"
        summary = t.get("summary", "").replace("\n", " ")[:120]
        print(f"  {i+1}. [{cap}] {ok} {summary}")

    final = exe.get("final")
    if final:
        print(f"\n--- 最终输出 ---")
        print(f"  {final}")

    if r.get("error"):
        print(f"\n--- 错误 ---")
        print(f"  {r['error']}")


def main() -> None:
    """CLI 入口：python -m kernel.autopilot "<任务描述>"

    环境要求：
      - .env 中 ZHIPU_API_KEY 已配置（ag2 规划必需）
      - 可选：AOS_LLM_MODEL / AOS_LLM_BASE_URL 覆盖默认智谱 glm-4-flash
    """
    if len(sys.argv) < 2:
        print("用法: python -m kernel.autopilot \"<任务描述>\"")
        print("示例:")
        print('  python -m kernel.autopilot "搜索 Python requests 最新版本并安装"')
        print('  python -m kernel.autopilot "在 Windows 上安装 ffmpeg"')
        sys.exit(1)

    task = " ".join(sys.argv[1:])
    print(f"🚀 AOS 自主执行: {task}")

    # 自动加载 .env
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
    except Exception:
        pass

    r = run(task)
    _print_result(r)


if __name__ == "__main__":
    main()
