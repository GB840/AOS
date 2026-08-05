"""AOS 自主闭环（Autopilot）：一句话任务 → 自己搜 → 自己装 → 回来汇报。

把 ag2 规划 + plan_bridge 解析 + OrchestrationChiplet 编排 + 真实适配器
（搜索 / 代码执行 / LLM 推理 / 记忆）串成一条自给自足的管道。

使用方式：
  python -m kernel.autopilot "在本地装好 ffmpeg 并验证"
  python -m kernel.autopilot "搜索最新的开源语音识别模型并评估是否适合 Windows"

设计原则：
  - 默认经 FabricHub 统一路由（统一能力路由 / 故障转移 / 白盒蒸馏）
  - FabricHub 构造失败时透明降级到本地惰性适配器（零阻塞）
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
import hashlib
import threading
from typing import Any, Dict, List, Optional
from core.fabric.adapter import InvokeResult, InvokeRequest, extract_text
from core.fabric.adapters.ag2_adapter import _dedup_text
from kernel.run_state_store import (
    create_run, save_checkpoint, load_checkpoint, mark_done,
)
from kernel.compliance import check_capability, policy_enforce_enabled
from kernel.evolution_distiller import EvolutionDistiller
from kernel.causal import CausalModel

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


_repo: Any = None


def _get_repo():
    """仓库自进化芯粒惰性单例（action.repo）。"""
    global _repo
    if _repo is None:
        from kernel.plugins.repo_agent import RepoAgent
        _repo = RepoAgent()
    return _repo


# ---- ⑤ 融合 FabricHub 单一内核路由（默认启用）---------------------------
# 默认走 FabricHub 统一路由：所有真实适配器调用经 FabricHub.route() 统一派发——
# 统一能力路由 / 运行时故障转移 / 策略边界 / 白盒蒸馏（理念5/8），消除「autopilot
# 绕开 FabricHub 自成一路」的双轨债。首次 _dispatch 触发惰性构造（可能较慢，因
# 需加载 20+ 适配器），后续调用复用单例。构造失败时透明降级到本地惰性适配器。
# 设 AOS_AUTOPILOT_USE_FABRICHUB=0 可显式关闭（保留快启动设计，用于 CLI 一次性任务）。
_AUTOPILOT_USE_HUB = os.environ.get("AOS_AUTOPILOT_USE_FABRICHUB", "1") == "1"
_HUB = None
_HUB_ATTEMPTED = False  # 避免重复尝试构造（失败后不再重试）


def _get_hub():
    """返回 FabricHub 单例；构造失败或显式关闭时返回 None（走本地适配器）。"""
    global _HUB, _HUB_ATTEMPTED
    if not _AUTOPILOT_USE_HUB:
        return None
    if _HUB is None and not _HUB_ATTEMPTED:
        _HUB_ATTEMPTED = True
        try:
            logger.info("autopilot: 首次路由经 FabricHub 统一派发（惰性构造中…）")
            from kernel.plugins.fabric_hub import get_fabric_hub
            _HUB = get_fabric_hub()
        except Exception:  # noqa: BLE001
            logger.warning("autopilot: FabricHub 构造失败，透明降级到本地适配器",
                           exc_info=True)
    return _HUB


def _dispatch(capability: str, payload: Dict[str, Any]) -> Any:
    """真实适配器调用：默认经 FabricHub 统一路由，构造失败时降级到本地惰性适配器。

    两条路径最终命中同一底层适配器，返回 InvokeResult(.data 同构)；
    autopilot 的真实闸门 / 量化指标逻辑无需改动即可作用于两条路径。
    """
    # 仓库自进化芯粒（action.repo）：本地确定性操作、故障隔离点，不经 FabricHub
    # 路由（语义固定、无需引擎故障转移；也避免 hub 未注册 action.repo 时失败）。
    if capability == "action.repo":
        return _get_repo().invoke(InvokeRequest(capability=capability, payload=payload))
    # 单创OS 编排：把创业目标映射到 OPC 5 岗位（复用注册表，不重造）
    if capability == "opc.orchestrate":
        from kernel.plugins.singlechuang import plan_company
        goal = payload.get("task") or payload.get("goal") or ""
        industry = payload.get("industry") or "default"
        data = plan_company(goal, industry)
        return InvokeResult(ok=bool(goal), data=data)
    # 多智能体互动课堂生成（OpenMAIC，MIT 开源；HTTP 桥接，本地隔离故障域，
    # 不经 FabricHub 路由——语义固定、避免 hub 未注册 edu.course_gen 时失败）。
    if capability == "edu.course_gen":
        from kernel.plugins.openmaic_bridge import generate_course
        return generate_course(payload)
    hub = _get_hub()
    if hub is not None:
        # cognition.* 在 hub 注册表里统一归到 inference.llm 派发
        cap = "inference.llm" if capability in ("cognition.reasoning", "cognition.planning") else capability
        return hub.route(cap, payload)
    # 本地兜底：hub 构造失败或显式关闭（AOS_AUTOPILOT_USE_FABRICHUB=0）时走此路径
    if capability == "web.search":
        return _get_search().invoke(InvokeRequest(capability=capability, payload={
            "query": payload.get("query") or payload.get("task") or payload.get("instruction") or "",
            "engine": payload.get("engine") or payload.get("engine_hint"),
        }))
    if capability == "action.code_exec":
        return _get_code_exec().invoke(InvokeRequest(capability=capability, payload=payload))
    if capability in ("inference.llm", "cognition.reasoning", "cognition.planning"):
        ag2 = _get_ag2()
        material = payload.get("content") or payload.get("task") or ""
        text = ag2.produce_text(material)
        return InvokeResult(ok=bool(text and text.strip()),
                            data={"content": text or "", "output": text or ""})
    return InvokeResult(ok=False, error=f"autopilot: _dispatch 不支持的能力 {capability}")


# ---- 因果反思闭环（D5 决策论层接入 autopilot 反思链路）-----------------
# 把 autopilot 每步的「真实成败 + 引擎」喂进白盒蒸馏器，反思时经 CausalModel 的
# counterfactual / best_action 选「换做法」引擎，使反思从「LLM 猜」变为「数据支撑」。
# 默认 **常驻开启**（不再 opt-in）：优先复用 FabricHub 蒸馏器；FabricHub 不可用时
# 自动建本地蒸馏器落盘；仅 AOS_AUTOPILOT_DISTILL_OFF=1 才彻底关闭（零足迹调试）。
_DISTILLER: Optional[EvolutionDistiller] = None
_DISTILLER_INITED = False

# 引擎相对成本（仅用于决策论层 best_action 的 cost 权重；数值为相对量级，非真实计费）。
# 免费本机/HTML 源为 0；需远程 key/计费的源更高 → 成功率相近时优先选免费的，实现降本。
_ENGINE_COST = {
    "anysearch": 0.1, "baidu": 0.0, "bing": 0.0, "duckduckgo": 0.0,
    "jina": 0.1, "searxng": 0.0, "zhipu": 0.4,
}


def _get_causal_distiller() -> Optional[EvolutionDistiller]:
    """返回可复用的白盒蒸馏器（供因果反思消费），无可用则 None（诚实跳过）。"""
    global _DISTILLER, _DISTILLER_INITED
    if _DISTILLER_INITED:
        return _DISTILLER
    _DISTILLER_INITED = True
    # 0) 显式关闭开关：AOS_AUTOPILOT_DISTILL_OFF=1 退回 None（极端调试用）
    if os.environ.get("AOS_AUTOPILOT_DISTILL_OFF") == "1":
        return None
    # 1) 优先复用 FabricHub 已在路由热路径喂好的蒸馏器（零额外开销）
    try:
        from kernel.plugins.fabric_hub import get_fabric_hub
        hb = get_fabric_hub()
        if hb is not None and getattr(hb, "_distiller", None) is not None:
            _DISTILLER = hb._distiller
            return _DISTILLER
    except Exception:
        logger.warning("获取 FabricHub 蒸馏器失败，退回本地", exc_info=True)
    # 2) 默认本地蒸馏器：FabricHub 不可用时自动落盘（不再要求 opt-in env）
    try:
        store = os.environ.get("AOS_AUTOPILOT_DISTILL_STORE") or os.path.join(
            os.path.dirname(__file__), "..", "..", "data", "workspaces",
            "autopilot", "distill.jsonl")
        _DISTILLER = EvolutionDistiller(store_path=store)
        return _DISTILLER
    except Exception:
        logger.warning("创建 autopilot 蒸馏器失败", exc_info=True)
    return None


def _feed_distiller(capability: str, result: Any) -> None:
    """把一步的真实成败 + 引擎喂进白盒蒸馏器（opt-in，热路径安全）。

    为什么：否则 CausalModel.from_distiller 永远空 → 反思调 counterfactual
    只会返回 unknown，因果闭环断开。改变之后：autopilot 的每条真实 Trace 都成为
    可复核的干预样本，反思能基于「哪个引擎更值」做数据决策而非 LLM 瞎猜。
    """
    d = _get_causal_distiller()
    if d is None or not isinstance(result, InvokeResult) or not isinstance(result.data, dict):
        return
    engine = result.data.get("engine")
    if not engine:
        return  # 该能力未暴露引擎（如纯本地 code_exec），无因果候选可记
    rm = result.data.get("real_metrics") or {}
    ok_real = bool(result.ok) and (rm.get("is_real") is True)
    try:
        d.record_outcome(capability, engine, ok_real)
    except Exception:
        logger.warning("喂蒸馏器失败", exc_info=True)


def _causal_reflection_hint(failed_cap: str, distiller: EvolutionDistiller) -> Optional[Dict[str, Any]]:
    """用因果决策论层为失败能力选「换做法」引擎（D5 落地反思闭环）。

    为什么：反思若只靠 LLM 猜「下次换什么引擎」，是黑盒、不可复核、易重复失败。
    改变之后：直接复用白盒蒸馏器的 (能力,引擎)→成败，经 CausalModel.best_action
    在『成功率×成本×时延』带权下选最优引擎，并 counterfactual 给出可复核证据
    （Δ成功率 / Δ效用 / Wilson 置信区间 / 标注观测相关非已证因果）。
    样本不足（候选<2 或任一方<MIN_SAMPLES）诚实返回 None——绝不编造换做法建议。
    """
    model = CausalModel().from_distiller(distiller)
    cands: List[str] = []
    for k in distiller.stats:
        if k.startswith(failed_cap + "::"):
            act = k.split("::", 1)[1]
            if model.effect_of(failed_cap, act)["success_rate"] is not None:
                cands.append(act)
    if len(cands) < 2:
        return None  # 证据不足，诚实不瞎建议
    weights = {"rate": 1.0, "cost": 0.3, "latency": 0.2}
    best = model.best_action(failed_cap, cands, weights=weights)
    if not best:
        return None
    # 选最差候选做反事实基线，给出「换到 best 能好多少」的可复核证据
    worst = min(cands, key=lambda a: model.effect_of(failed_cap, a)["success_rate"])
    cf = model.counterfactual(
        failed_cap, worst, best["action"],
        costs={c: _ENGINE_COST.get(c, 0.0) for c in cands})
    return {
        "capability": failed_cap,
        "suggested_engine": best["action"],
        "best_success_rate": best["success_rate"],
        "best_ci": (best.get("ci_low"), best.get("ci_high")),
        "best_confidence": best.get("confidence"),
        "inference_type": best.get("inference_type"),
        "utility": best.get("utility"),
        "evidence": cf,
    }


def _compute_causal_hints(failed: List[str], distiller: Optional[EvolutionDistiller]):
    """对失败步列表算因果换做法建议，返回 (提示文本块, {cap: hint})。

    纯函数、可单测：从失败步文本里解析能力标签，逐一查因果建议；无蒸馏器或
    样本不足则双双返回空——反思退化回质疑 agent 诊断，绝不伪造证据。
    """
    hints: Dict[str, Any] = {}
    if distiller is not None:
        for f in failed:
            m = re.match(r"步骤\d+\[([^\]]+)\]", f)
            cap = m.group(1) if m else None
            if cap and cap not in hints:
                h = _causal_reflection_hint(cap, distiller)
                if h:
                    hints[cap] = h
    if not hints:
        return "", {}
    lines = []
    for cap, h in hints.items():
        ev = h.get("evidence") or {}
        lines.append(
            f"  - [{cap}] 因果证据建议改用引擎「{h['suggested_engine']}」"
            f"（成功率 {h['best_success_rate']:.2f}，95%CI "
            f"[{h['best_ci'][0]:.2f},{h['best_ci'][1]:.2f}]，置信 {h['best_confidence']}；"
            f"{ev.get('reason', '')}）。"
            f"注意：此为观测相关（{h['inference_type']}），非已证因果，仅供换做法参考。"
        )
    block = ("\n【因果反思建议（白盒蒸馏+决策论层，数据支撑的换做法，非 LLM 猜测）】\n"
             + "\n".join(lines) + "\n")
    return block, hints


def _attach_engine_hints(steps: List[Dict[str, Any]], hints: Dict[str, Any]) -> None:
    """把因果建议的引擎打到重设计步骤上，路由时优先采用（engine_hint）。"""
    for s in steps:
        cap = s.get("capability")
        if cap in hints and "engine_hint" not in s:
            s["engine_hint"] = hints[cap]["suggested_engine"]


# ---- 推理超时守护（ag2 无内部超时，挂死会拖垮整条自主环）----
_AG2_TIMEOUT = float(os.environ.get("AOS_AG2_TIMEOUT", "120"))
_TIMEOUT = object()


def _call_with_timeout(fn, timeout=_AG2_TIMEOUT):
    """守护线程跑 fn，超时返回 _TIMEOUT（fn 仍在后台跑但被遗弃，下次会重建 ag2）。

    用于 ag2 推理无内部超时、可能挂死时，保证上层能降级到 ollama/heuristic，
    不被单次 ag2 卡死拖垮整个自主环。fn 抛异常会在主线程原样重抛，交上层 except 降级。
    """
    box: Dict[str, Any] = {}
    def _run():
        try:
            box["r"] = fn()
        except Exception as e:  # noqa: BLE001
            box["e"] = e
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        return _TIMEOUT
    if "e" in box:
        raise box["e"]
    return box.get("r")


def _reset_ag2():
    """作废缓存的 ag2 单例（超时/卡死后强制下次重建，避免复用粘死实例）。"""
    global _ag2
    _ag2 = None


def _zhipu_generate(prompt: str, timeout: float = 90.0) -> Optional[str]:
    """智谱直连文本生成（ag2 不可用时的真实 LLM 后端，已验证可用，零新依赖）。

    复用 kernel.plugins.zhipu_chat（a959ba6 实做，ZHIPU_API_KEY 已配置），
    失败返 None 不抛，超时经 _call_with_timeout 守护，绝不拖垮自主环。
    """
    try:
        from kernel.plugins.zhipu_chat import zhipu_chat
        messages = [{"role": "user", "content": prompt}]
        return _call_with_timeout(
            lambda: zhipu_chat(messages, max_tokens=1024), timeout
        )
    except Exception:  # noqa: BLE001
        logger.warning("智谱直连生成失败", exc_info=True)
        return None


def _openai_compat_generate(prompt: str, timeout: float = 90.0) -> Optional[str]:
    """OpenAI 兼容端点生成（stdlib only），读取 AOS_LLM_BASE_URL / AOS_LLM_MODEL。

    这是「开源默认路由」的真实落地：支持任何开源推理服务
    （Ollama :11434/v1、vLLM、LM Studio 等），无需第三方闭源 key，
    直接兑现用户「无 API 分成」诉求。无该 env 时返回 None（交给 Ollama 兜底）。
    """
    base = os.environ.get("AOS_LLM_BASE_URL")
    if not base:
        return None
    import json as _json
    import urllib.request
    model = os.environ.get("AOS_LLM_MODEL", "qwen3:8b")
    url = base.rstrip("/") + "/chat/completions"
    body = _json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1024,
        "temperature": 0.3,
    }).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = _json.loads(resp.read().decode("utf-8"))
        return (data.get("choices") or [{}])[0].get("message", {}).get("content") or None
    except Exception:  # noqa: BLE001
        logger.warning("OpenAI 兼容端点生成失败: %s", base, exc_info=True)
        return None


def _llm_generate(prompt: str, *, allow_zhipu: bool = True) -> Optional[str]:
    """统一 LLM 生成入口，落实「开源默认 + 智谱 opt-in」：

    1) AOS_LLM_BASE_URL（开源/OpenAI 兼容，如 Ollama、vLLM）→ 默认优先
    2) 本机 Ollama（AOS_OLLAMA_URL，模型读 AOS_LLM_MODEL）→ 默认兜底
    3) 智谱仅当 ZHIPU_API_KEY 且 AOS_ZHIPU_OPTIN=1 才启用（opt-in，非默认）
    4) 都不通 → 返 None（交上层诚实降级，绝不谎报）
    """
    # 1) 开源/OpenAI 兼容端点优先
    out = _openai_compat_generate(prompt)
    if out:
        return out
    # 2) 本机 Ollama 兜底
    try:
        ollama_out = _ollama_generate(prompt, model=os.environ.get("AOS_LLM_MODEL"))
        if ollama_out:
            return ollama_out
    except Exception:  # noqa: BLE001
        pass
    # 3) 智谱 opt-in（默认关闭，需显式开关）
    if allow_zhipu and os.environ.get("AOS_ZHIPU_OPTIN") == "1" and os.environ.get("ZHIPU_API_KEY"):
        return _zhipu_generate(prompt)
    return None


def _build_plan_prompt(task: str) -> str:
    """构造给智谱的规划 prompt：要求输出 AOS 能力标签步骤。"""
    return (
        "你是 AOS 自主执行环的规划 agent。\n"
        f"任务：{task}\n\n"
        "把任务拆成可执行步骤，每行一个步骤，用 AOS 能力标签前缀：\n"
        "  web.search= 联网搜索信息\n"
        "  action.code_exec= 执行代码或命令\n"
        "  inference.llm= 纯推理/生成文本\n"
        "  memory.semantic= 存取语义记忆\n"
        "  file.write= 写文件\n"
        "不要解释，只输出步骤计划，每行一个步骤。"
    )


# ---- 路由胶水 --------------------------------------------------

def _make_noninteractive(code: str) -> str:
    """给常见安装命令补非交互参数，避免卡在许可确认。"""
    low = code.lower()
    if low.startswith("winget install") and "--accept" not in low:
        return code.rstrip() + " --accept-package-agreements --accept-source-agreements"
    if low.startswith("choco install") and "-y" not in low and "--yes" not in low:
        return code.rstrip() + " -y"
    return code


# 自主智能体绝不应执行的远程写 / 破坏性命令（defense-in-depth，沙箱黑名单之外再加一层）。
# 沙箱已挡 rm -rf / format / dd 等；这里专堵「未经人工确认就改远端/破坏本地」的操作。
_REFUSE_CMDS = ("git push", "git reset --hard", "git clean", "git checkout --", "sudo ")


def _refuse_if_dangerous(code: str) -> str | None:
    """若命令含远程写/破坏性操作，返回拒绝原因；否则返回 None（放行）。

    自主智能体的铁律：绝不在无人确认时 push 代码到远端、重置/清理 git 工作区、
    或以 sudo 提权执行。这些必须由人在回路里显式批准。
    """
    low = " " + code.lower() + " "
    for token in _REFUSE_CMDS:
        if token in low:
            return f"自主智能体禁止执行高危/远程写命令「{token.strip()}」；需人工确认后再做"
    return None


# 识别 `python -c "..."` / `python3 -c '...'` 这类内联 Python 命令，抽出内部源码，
# 避免经 `cmd /c` 跑时嵌套引号脆弱、且被当成纯 Python 文件写盘导致语法错。
_INLINE_PY_RE = re.compile(
    r"^(?:py|python3?)\s+-c\s+(?:\"([^\"]*)\"|'([^']*)'|\s*(\S.*))$", re.S
)


def _normalize_code_exec(code: str) -> tuple[str, str | None]:
    """归一化代码执行命令。

    返回 (code, forced_language)：
      - 若为 `python -c "..."` → 抽出内部 Python 源码，forced_language="python"
        （交给 CodeExecutionAdapter 当真实 .py 源码跑，绕开 cmd 引号脆弱性）；
      - 否则原样返回，forced_language=None（由 _guess_language 决定）。
    """
    m = _INLINE_PY_RE.match(code.strip())
    if m:
        inner = (m.group(1) or m.group(2) or m.group(3) or "").strip()
        if inner:
            return inner, "python"
    return code, None


# 识别 python 写文件语句：open(path,'w'[,encoding=...]).write(<literal>)
_WRITE_RE = re.compile(
    r"(open\(\s*r?['\"][^'\"]+['\"]\s*,\s*['\"]w['\"]"
    r"(?:\s*,\s*encoding\s*=\s*['\"][^'\"]+['\"])?\s*\)\s*\.\s*write\s*\()"
    r"(.*?)(\s*\)\s*$)", re.S,
)


def _substitute_file_content(code: str, prev_text: str) -> str:
    """若 python 写文件步骤的 write() 内容是空壳占位符（'...' / 'TODO' / 过短），
    且上游有真实文本产出，则用上游文本替换，避免写一坨占位符到文件。

    这是「搜→推→写文件」闭环的关键接缝：规划时 ag2 还不知道文件内容，
    只能写 '...' 占位；执行时上游推理已产出真实文本，这里回填。
    """
    if not prev_text or len(prev_text.strip()) < 10:
        return code
    m = _WRITE_RE.search(code)
    if not m:
        return code
    literal = m.group(2).strip()
    # 判断是否是空壳：含占位符标记（<CONTENT> / ... / TODO），或长度远小于上游文本。
    # ag2 规划时无法预知文件内容，统一用 <CONTENT> 占位，由本函数回填真实上游产出。
    is_stub = (
        "..." in literal or "TODO" in literal or "placeholder" in literal.lower()
        or ("<" in literal and ">" in literal)
        or literal in ("''", '""')
        or (len(literal.strip("'\" ")) < 20 and len(prev_text) > 40)
    )
    if not is_stub:
        return code
    # 用上游文本替换 write() 内容，做 Python 字符串转义（单引号包）
    safe = (
        prev_text.replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace("\r", "")
        .replace("\n", "\\n")
    )
    new_write = f"{m.group(1)}'{safe}'{m.group(3)}"
    return code[:m.start()] + new_write + code[m.end():]


def _pkg_name(code: str) -> str:
    """从 'winget install ffmpeg' / 'choco install ffmpeg -y' 提取包名。"""
    m = re.search(r"install\s+([A-Za-z0-9._\-]+)", code)
    return m.group(1).lower() if m else ""


# 直接下载安装方案（不依赖 winget/choco/管理员，写用户目录）。
# 随需扩展：加一个包名 → {url, exe} 即可。
_DIRECT_DOWNLOAD: Dict[str, Dict[str, str]] = {
    "ffmpeg": {
        "url": "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
        "exe": "ffmpeg.exe",
    },
}


def _safe_decode(raw) -> str:
    """把子进程输出字节安全地解码为 str（消灭 UnicodeDecodeError）。

    中文 Windows 子进程按 cp936(GBK) 输出，按 UTF-8 解码会崩。
    策略：utf-8 → cp936/gbk 回落，最后 errors='replace' 兜底。
    """
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    for enc in ("utf-8", "cp936", "gbk"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


def _add_to_user_path(bin_dir: str) -> None:
    """把目录追加到用户级 PATH（持久）。

    优先用 PowerShell .NET 写法（[Environment]::SetEnvironmentVariable），
    无 cmd `setx` 的 1024 字符截断限制；失败回落 setx。
    """
    import subprocess as _sp
    import os as _os
    ps = (
        '[Environment]::SetEnvironmentVariable('
        f'"Path", ([Environment]::GetEnvironmentVariable("Path","User") + ";{bin_dir}"), "User")'
    )
    try:
        _sp.run(["powershell", "-NoProfile", "-Command", ps],
                capture_output=True, timeout=30)
    except Exception:
        cur = _os.environ.get("PATH", "")
        _sp.run(["setx", "PATH", f"{cur};{bin_dir}"],
                capture_output=True, timeout=30)


def _try_direct_install(pkg: str) -> Any:
    """纯 Python 下载 + 解压 + 加 PATH（无需 winget/choco/管理员）。

    已安装则跳过下载直接验证（自主：不重复装）。
    """
    from core.fabric.adapter import InvokeResult
    import os as _os
    import shutil
    import subprocess as _sp
    import urllib.request
    import zipfile
    spec = _DIRECT_DOWNLOAD.get(pkg)
    if not spec:
        return InvokeResult(ok=False, error=f"autopilot: 无 {pkg} 的直接下载方案")
    try:
        base = _os.path.join(
            _os.environ.get("LOCALAPPDATA", _os.path.expanduser("~")),
            "aos_tools", pkg,
        )
        _os.makedirs(base, exist_ok=True)

        # 0) 已装则跳过下载（自主：不重复下载 161MB）
        bin_dir = None
        for root, _, files in _os.walk(base):
            if spec["exe"] in files:
                bin_dir = root
                break

        if not bin_dir:
            zip_path = _os.path.join(base, f"{pkg}.zip")
            # 1) 下载
            req = urllib.request.Request(spec["url"], headers={"User-Agent": "AOS-autopilot"})
            with urllib.request.urlopen(req, timeout=300) as resp, open(zip_path, "wb") as f:
                shutil.copyfileobj(resp, f)
            # 2) 校验zip完整性
            with zipfile.ZipFile(zip_path) as zf:
                bad_file = zf.testzip()
                if bad_file:
                    _os.remove(zip_path)
                    return InvokeResult(ok=False, error=f"autopilot: zip文件损坏，坏文件: {bad_file}")
            # 3) 解压
            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(base)
            # 4) 找 exe 所在目录
            for root, _, files in _os.walk(base):
                if spec["exe"] in files:
                    bin_dir = root
                    break
            if not bin_dir:
                return InvokeResult(ok=False, error="autopilot: 解压后未在包内找到 " + spec["exe"])

        # 4) 加 PATH（持久用户级，优先 .NET 写法避免 setx 1024 截断）
        cur = _os.environ.get("PATH", "")
        if bin_dir not in cur.split(";"):
            print(f"[autopilot] 即将修改用户PATH，添加: {bin_dir}")
            _add_to_user_path(bin_dir)
            _os.environ["PATH"] = f"{cur};{bin_dir}"
            print(f"[autopilot] 已添加到PATH: {bin_dir}")

        # 5) 验证（硬门槛：ffmpeg.exe -version 必须成功才报 ✅）
        exe = _os.path.join(bin_dir, spec["exe"])
        ver = _sp.run([exe, "-version"], capture_output=True, timeout=30)
        vout = _safe_decode(ver.stdout)
        verr = _safe_decode(ver.stderr)
        if ver.returncode != 0:
            return InvokeResult(ok=False, error="autopilot: 安装后验证失败: " +
                                (verr or vout or "无输出")[:300])
        return InvokeResult(ok=True, data={
            "content": f"{pkg} 已安装到 {bin_dir}\n" + (vout or "")[:300],
            "output": f"{pkg} 已安装到 {bin_dir}",
        })
    except Exception as e:  # noqa: BLE001 - 兜底把异常转成可读错误
        return InvokeResult(ok=False, error=f"autopilot: 直接安装 {pkg} 异常: {e}")


_LAST_TEXT = ""  # 最近一次上游（搜索/推理）文本产出，供 code_exec 步骤填补 <占位符>


def _capture_text(capability: str, result) -> None:
    """记住非代码步骤的文本产出，供后续命令填补 <version_number> 之类占位符。

    策略：
      - 跳过 action.code_exec 与 memory.semantic 这类无意义/no-op 文本
        （后者固定返回 "memory not yet wired..."，会污染占位符来源）；
      - 优先保留「含具象值（版本号/路径/URL/数字）」的文本，让 <version>
        等占位符能填到真值而非被废话覆盖。
    """
    global _LAST_TEXT
    if capability in ("action.code_exec", "memory.semantic"):
        return
    if isinstance(result, InvokeResult) and result.ok and result.data:
        t = extract_text(result.data)
        if not t:
            return
        _sig = r"\d+(?:\.\d+){1,3}|[A-Za-z]:[\\/]|https?://"
        cur_has = bool(re.search(_sig, _LAST_TEXT))
        new_has = bool(re.search(_sig, t))
        if new_has and (not cur_has or len(t) > len(_LAST_TEXT)):
            _LAST_TEXT = t
        elif not cur_has and len(t) > len(_LAST_TEXT):
            _LAST_TEXT = t


def _extract_value_from_text(text: str, token: str) -> str:
    """据占位符名从上游文本抽具象值（版本号/路径/URL/数字）。抽不到返回空（不编造）。"""
    if not text:
        return ""
    low = token.lower()
    if "version" in low or " ver" in low:
        m = re.search(r"\d+(?:\.\d+){1,3}", text)
        return m.group(0) if m else ""
    if "url" in low:
        m = re.search(r"https?://[^\s\"'<>]+", text)
        return m.group(0) if m else ""
    if any(k in low for k in ("path", "dir", "file", "目录", "路径", "文件")):
        m = re.search(r"[A-Za-z]:[\\/][^\s\"'<>|]+|/[^\s\"'<>|]+", text)
        return m.group(0) if m else ""
    if "number" in low or "num" in low or "count" in low:
        m = re.search(r"\d+(?:\.\d+)?", text)
        return m.group(0) if m else ""
    m = re.search(r"\d+(?:\.\d+){1,3}", text)
    return m.group(0) if m else ""


def _fill_placeholders(code: str) -> str:
    """用 _LAST_TEXT 填补命令里的 <占位符>（如 ag2 规划的 echo <version_number>）。

    有依据才填；填不到就保留原样，让执行器报清晰错误（绝不伪造值）。
    """
    def _repl(m):
        val = _extract_value_from_text(_LAST_TEXT, m.group(1).strip())
        return val if val else m.group(0)
    return re.sub(r"<([^<>]+)>", _repl, code)


def _ensure_parent_dirs(code: str) -> None:
    """为命令里的 `> file` / `>> file` 重定向目标自动建父目录。

    避免「目录不存在 → 重定向静默失败」这类自治任务卡点。
    """
    for m in re.finditer(r"[1-2]?>[1-2]?\s*([^\s|&;<>]+)", code):
        p = m.group(1).strip().strip('"\'')
        if os.path.isabs(p) or (len(p) > 1 and p[1] == ":"):
            d = os.path.dirname(p)
            if d:
                try:
                    os.makedirs(d, exist_ok=True)
                except Exception:
                    pass


def _route(capability: str, payload: Dict[str, Any]) -> Any:
    """把 OrchestrationChiplet 的能力调用派发给真实适配器。"""

    # 派发边界策略校验（理念6 诚实：让 PolicyEngine 在真实路径上具有约束力）。
    # 默认审计模式仅记录；设 AOS_POLICY_ENFORCE=1 时命中 deny 规则即阻断，
    # 不会误伤可信 system 体的合法 code_exec（r010 已放行）。
    verdict = check_capability(capability, actor="system")
    if not verdict["allowed"] and policy_enforce_enabled():
        return InvokeResult(
            ok=False,
            error=f"autopilot: 策略拒绝 {capability}（{verdict['matched_rule']}：{verdict['reason']}）",
        )

    if capability == "edu.course_gen":
        # 复用 _dispatch 的本地隔离路径（不经 hub，避免未注册能力时失败）。
        # 真实闸门：OpenMAIC 未启用或生成未成功 -> generate_course 返回 ok=False，
        # 绝不谎报成功（宪法 §6 诚实）。
        res = _dispatch("edu.course_gen", payload)
        if not (isinstance(res, InvokeResult) and res.ok):
            return InvokeResult(
                ok=False,
                error="autopilot: " + (res.error if isinstance(res, InvokeResult) else "课程生成失败"),
            )
        return res

    if capability == "web.search":
        # 从各种可能的 payload 字段里提取搜索查询（兼容 ag2 规划的
        # instruction="search ..." / query / task / content 形态）
        query = (
            payload.get("query") or payload.get("task")
            or payload.get("instruction") or ""
        )
        if not query and "content" in payload:
            query = str(payload.get("content", ""))
        query = _clean_search_query(query)
        if not query:
            return InvokeResult(ok=False, error="autopilot: 搜索步缺少查询词")
        # opt-in 经 FabricHub 路由；否则本地 SearchAdapter（见 _dispatch）
        engine_hint = payload.get("engine_hint") or payload.get("engine")
        result = _dispatch("web.search", {"type": "search", "query": query, "count": 5,
                                          "engine": engine_hint})
        _capture_text(capability, result)
        rm = _search_real_metrics(result)
        # 真实闸门：搜索必须真返回结果才算这步成立（空结果=敷衍，判失败）
        return InvokeResult(
            ok=rm["is_real"],
            data={**(result.data or {}), "real_metrics": rm},
        )

    if capability == "action.code_exec":
        # 优先用 ag2 规划的干净指令（如 "winget install ffmpeg"）
        code = payload.get("instruction") or payload.get("code") or payload.get("task") or ""
        if not code and "content" in payload:
            code = str(payload.get("content", ""))
        # 上游文本（上一步推理/搜索产出）——写文件步骤可能要把它落盘
        # extract_text 已对 content/text 等同值字段去重；再经 _dedup_text 兜底
        # 截掉模型偶发的整段重复，确保落盘是单份（不翻倍）。
        prev_text = _dedup_text(extract_text(payload))
        # 如果内容是推理步的冗长输出，尝试从中提取可执行命令
        code = _extract_cmd_from_text(code.strip()[:2000])
        if not code:
            return InvokeResult(ok=False, error="autopilot: 代码执行步缺少可执行命令")
        # 安全闸：拒绝 git push / reset --hard / clean / checkout -- / sudo 等
        # 远程写或破坏性命令（自主智能体铁律，defense-in-depth）。
        refuse = _refuse_if_dangerous(code)
        if refuse:
            return InvokeResult(ok=False, error="autopilot: " + refuse)
        # 归一化：识别 `python -c "..."` 抽出内部源码，当真实 Python 跑，
        # 避免经 cmd /c 时嵌套引号脆弱 + 被当纯 .py 文件写盘导致语法错。
        code, forced_lang = _normalize_code_exec(code)
        # 抽写文件路径，供「真实闸门」校验是否真落盘非空内容
        write_path = _extract_write_path(code)
        # 填补 <占位符>（如 ag2 规划的 <version_number>），再自动建重定向父目录
        code = _fill_placeholders(code)
        # 若 python -c 写文件，但 write(...) 里是占位符/空壳（ag2 规划时还没有
        # 真实内容，常写 '...' / 'TODO'），用上游真实产出(prev_text)替换，
        # 让「搜→推→写文件」闭环落真实内容，而不是写一坨占位符。
        if forced_lang == "python":
            code = _substitute_file_content(code, prev_text)
        _ensure_parent_dirs(code)
        # 自主安装：给 winget / choco 补非交互参数（不卡在许可确认）
        code = _make_noninteractive(code)
        # 先按规划执行（winget / choco / pip 等）；opt-in 经 FabricHub 路由，
        # 否则本地 CodeExecutionAdapter（见 _dispatch）
        res = _dispatch("action.code_exec", {
            "code": code, "language": forced_lang or _guess_language(code),
        })
        # 安装器回填：winget/choco 不在 PATH / 没装 → 直接下载解压到用户目录
        # 并加 PATH，不依赖任何外部安装器，也不需要管理员权限。
        if not res.ok and "install" in code.lower():
            pkg = _pkg_name(code)
            if pkg:
                fb = _try_direct_install(pkg)
                if fb.ok:
                    return fb
                # 回填也失败 → 两次错误都带上，方便诊断（原则 8 可观测）
                res = InvokeResult(
                    ok=False,
                    error=f"{res.error or ''} | 直接安装回退也失败: {fb.error or ''}",
                )
        rm = _code_exec_real_metrics(res, write_path)
        data = {**(res.data or {}), "real_metrics": rm}
        # 落盘回填：若本步把内容写进了真实文件（如「写报告」），把落盘文本回填到
        # 顶层 content/output。否则 last_success_out 的 content 为空，紧随其后的
        # memory.semantic / 推理步会因「无上游真实内容」被诚实闸门挡住，导致记忆
        # 永不落盘。回填读的是刚刚真实写出的文件，内容确定、不臆造。
        try:
            _wb = int(rm.get("wrote_bytes") or 0)
        except Exception:
            _wb = 0
        _wf = rm.get("wrote_file")
        if _wf and _wb > 0 and not str(data.get("content", "")).strip():
            try:
                with open(_wf, "r", encoding="utf-8", errors="replace") as _fh:
                    _fc = _fh.read()
                if _fc.strip():
                    data["content"] = _fc
                    data["output"] = _fc
            except Exception:
                pass
        # 真实闸门：要么有 stdout 输出，要么真写进了非空文件，否则算空转(敷衍)判失败
        return InvokeResult(
            ok=rm["is_real"],
            data=data,
        )

    if capability in ("inference.llm", "cognition.reasoning", "cognition.planning"):
        material = payload.get("task") or payload.get("content") or payload.get("text") or "处理上游结果"
        instruction = payload.get("instruction") or ""
        original_task = payload.get("original_task") or ""
        # 把「原始任务 + 步骤指令 + 上游材料」合成清晰 prompt，交给单角色 writer
        # agent 合成正文。重点：必须显式给出 original_task，否则 writer 只能看到
        # 上游材料（搜索结果）而把它原样回显，写不出真正的报告。
        prompt_parts = []
        if original_task:
            prompt_parts.append(f"用户原始任务：{original_task}")
        if instruction:
            prompt_parts.append(f"本步要求：{instruction}")
        prompt_parts.append(
            "请基于下方参考材料撰写正文，必须用自己的话综合、提炼，"
            "不要照抄材料原文，也不要重复贴出搜索结果列表。"
        )
        prompt_parts.append(f"参考材料：\n{material}")
        topic = "\n\n".join(prompt_parts)
        if len(topic) > 2000:
            topic = topic[:2000]
        # opt-in 经 FabricHub 路由；否则本地 ag2.produce_text（见 _dispatch）
        res = _dispatch(capability, {"task": topic, "content": topic})
        if not (isinstance(res, InvokeResult) and res.ok and extract_text(res.data)):
            err = (res.error if isinstance(res, InvokeResult) else "") or "推理步未产出文本"
            return InvokeResult(ok=False, error="autopilot: " + str(err))
        result = res
        _capture_text(capability, result)
        rm = _inference_real_metrics(result)
        # 真实闸门：产出过短/像拒绝话术 → 视为敷衍，判失败（不谎报成功）
        return InvokeResult(
            ok=rm["is_real"],
            data={**result.data, "real_metrics": rm},
        )

    if capability == "action.repo":
        # 仓库自进化芯粒：本地确定性操作，经 _dispatch 走隔离的 repo 芯粒
        res = _dispatch("action.repo", payload)
        rm = {"is_real": bool(getattr(res, "ok", False))}
        return InvokeResult(ok=res.ok, data={**(res.data or {}), "real_metrics": rm})

    if capability == "memory.semantic":
        # 真实落盘：把上游产出的知识存进语义记忆（文件后端，离线确定可用，
        # 不依赖 mem0/ollama 是否在跑——避免「后端没起却谎报成功」）。
        # 上游真实产出经 dedup 后作为记忆内容（与 code_exec 取上游同款）。
        prev_text = _dedup_text(extract_text(payload))
        if not prev_text or len(prev_text.strip()) < 10:
            # 没有上游真实内容可存 → 诚实判失败，绝不谎报「已记忆」
            result = InvokeResult(ok=False, error="autopilot: 记忆步无上游真实内容可存")
            _capture_text(capability, result)
            return result
        entry = _save_semantic_memory(
            task=payload.get("original_task") or payload.get("task") or "",
            content=prev_text,
        )
        result = InvokeResult(ok=True, data={
            "content": f"已记忆：{entry['preview']}",
            "real_metrics": {
                "is_real": True,
                "stored_bytes": entry["stored_bytes"],
                "hash": entry["hash"][:8],
            },
        })
        _capture_text(capability, result)
        return result

    result = InvokeResult(ok=False, error=f"autopilot: 不支持的能力 {capability}")
    _capture_text(capability, result)
    return result


def _extract_cmd_from_text(text: str) -> str:
    """从推理/规划步的文本里提取可执行命令（兜底，防 verbose 文本灌入 code_exec）。

    - 单行且较短 → 直接当命令；
    - 多行 → 优先取「行首就是命令前缀」的行；找不到再取「行内含命令前缀」的
      行（从前缀位置截到行尾，能处理「用 bash 执行 echo xxx」这类裹挟）。
    """
    if not text:
        return ""
    text = text.strip()
    if "\n" not in text and len(text) < 500:
        # 单行短文本也要过防御检查——防反思把 LLM 拒答短段落当命令
        if _looks_like_text_not_code(text):
            return ""
        return text

    cmd_prefixes = [
        "winget ", "choco ", "pip ", "pip3 ", "npm ", "node ", "python ", "py ",
        "brew ", "apt ", "apt-get ", "curl ", "wget ", "git clone", "git ",
        "docker ", "echo ", "powershell ", "cmd ", "mkdir ", "copy ", "move ",
        "ren ", "rmdir ", "sh ", "bash ",
    ]
    start_match = None
    inline_match = None
    for line in text.split("\n"):
        line = line.strip().strip("`\"'")
        low = line.lower()
        for prefix in cmd_prefixes:
            if low.startswith(prefix):
                start_match = line
                break
            if not inline_match and prefix.strip() and prefix.strip() in low:
                idx = low.find(prefix.strip())
                inline_match = line[idx:].strip()
        if start_match:
            break

    if start_match:
        return start_match
    if inline_match:
        return inline_match
    # 没找到命令前缀 → 检查文本是否像文档/段落而非代码
    # 防反思重设计把 LLM 产出的研报/拒答文本当 code_exec 代码丢给 sandbox
    # （真机验证暴露：反思产 code_exec 步把研报 Markdown / LLM 拒答段落当 Bash 执行→死循环）
    if _looks_like_text_not_code(text):
        return ""  # 返回空 → 触发"缺少可执行命令"错误，不把文本丢给 sandbox
    # 没找到 → 返回原文本（让 code_exec 自己试）
    return text


def _looks_like_text_not_code(text: str) -> bool:
    """检测文本是否像文档/段落而非可执行代码。

    防反思重设计把 LLM 产出的研报/拒答文本当 code_exec 代码丢给 sandbox。
    三种判据（任一命中即判为非代码）：
    1. 以 Markdown 标题（#/##/###）开头且不含代码语法
    2. 以中文开头 + 长度>100 + 不含代码语法（如 LLM 拒答段落、研报正文）
    3. 以常见中文段落开头词（由于/为了/以下/如下/随着/根据）开头且不含代码语法
    """
    if not text:
        return False
    stripped = text.strip()
    if not stripped:
        return False

    # 代码语法特征——含任一即不拦（可能是带注释的代码）
    code_hints = (
        "def ", "import ", "from ", "print(", "pip ", "winget ", "npm ",
        "python ", "py ", "echo ", "git ", "curl ", "wget ", "bash ", "sh ",
        "mkdir ", "cp ", "mv ", "rm ", "cat ", "ls ", "cd ", "= ", "()",
        "func ", "var ", "let ", "const ", "return ", "->", "=>",
    )
    text_low = stripped.lower()
    has_code_syntax = any(h in text_low for h in code_hints)
    if has_code_syntax:
        return False

    first_line = stripped.split("\n", 1)[0].lstrip()

    # 判据1: Markdown 标题开头（无长度限制——标题就是标题）
    if first_line.startswith(("# ", "## ", "### ")):
        return True

    # 判据3: 常见中文段落开头词（无长度限制——开头词本身够特征）
    cn_paragraph_starters = ("由于", "为了", "以下", "如下", "随着", "根据",
                              "基于", "通过", "关于", "针对", "本次", "当前")
    if any(first_line.startswith(s) for s in cn_paragraph_starters):
        return True

    # 判据2: 以中文开头 + 长度>100（LLM 拒答长段落、研报正文）
    if len(stripped) > 100 and first_line and "\u4e00" <= first_line[0] <= "\u9fff":
        return True

    # 判据4: 含大量中文（占比>30%）且无代码语法——研报/文档段落常含英文术语但主体是中文
    # （如 "Node）与边（Edge）。每个节点维护一个共享的状态对象..." 以英文开头但主体是中文）
    if len(stripped) > 50:
        cn_chars = sum(1 for c in stripped if "\u4e00" <= c <= "\u9fff")
        if cn_chars / len(stripped) > 0.3:
            return True

    return False


def _guess_language(code: str) -> str:
    """从代码内容推测语言。"""
    low = code.strip().lower()
    if low.startswith(("echo ", "ls ", "pip ", "npm ", "apt ", "brew ", "choco ", "winget ")):
        return "bash"
    if any(kw in low for kw in ("function", "const ", "let ", "var ", "console.")):
        return "javascript"
    return "bash"  # 默认 bash（安装/系统命令最常见）


def _clean_search_query(raw: str) -> str:
    """清洗 ag2 规划出的搜索指令，剥掉前缀动词(search/find/查询)与包裹引号。

    ag2 常产出 `search "SQLite vs PostgreSQL"` 这类裹挟形式，直接当 query 会
    把 "search" 和引号带进去。这里还原成干净查询词。
    """
    q = (raw or "").strip().strip('"\'')
    q = re.sub(
        r"^(?:search|find|lookup|查询|搜(?:索)?|查(?:找|询)?|找)\s*[:：]?\s*",
        "", q, flags=re.I,
    ).strip()
    q = q.strip('"\'')
    return q[:300]


# ---- 真实产出校验（求是引擎式：每步必须真有产出，空转/敷衍判失败）----

_OPEN_PATH_RE = re.compile(r"open\(\s*r?['\"]([^'\"]+)['\"]\s*,\s*['\"]w", re.I)
# 推理步拒答/空话识别：仅匹配明确的「拒绝/无能」短语（避免把真实短回答误判为失败）。
# 设计取舍（Reflexion 教训：评估器质量决定系统上限，但过严会假阴性→把真成功当失败）：
# 不收录「我是/作为」这类中性词，只收明确的拒答信号。
_REFUSAL_RE = re.compile(
    r"(抱歉|对不起|无法(提供|完成|做到|访问|执行)|不能(提供|完成|做到|访问|执行)|"
    r"不予(提供|处理)|拒绝|没有(权限|访问|相关信息)|"
    r"refuse|cannot|can'?t|won'?t|unable to|i am unable|i cannot|sorry,? but)",
    re.I,
)


def _extract_write_path(code: str) -> Optional[str]:
    """从 python 写文件代码里抽目标路径（open('PATH','w'...) 的第一个参数）。"""
    m = _OPEN_PATH_RE.search(code or "")
    return m.group(1) if m else None


def _search_real_metrics(res: Any) -> Dict[str, Any]:
    """搜索步真实指标：真实返回的结果条数（带 url 才算）。"""
    data = res.data if isinstance(res, InvokeResult) else {}
    results = (data or {}).get("results") or []
    n = len(results) if isinstance(results, list) else 0
    if not n:
        n = str((data or {}).get("content", "")).count("http")  # 兜底
    return {
        "is_real": bool(n) and (res.ok if isinstance(res, InvokeResult) else False),
        "result_count": n,
        "engine": (data or {}).get("engine", ""),
    }


def _code_exec_real_metrics(res: Any, write_path: Optional[str]) -> Dict[str, Any]:
    """代码执行步真实指标：要么有 stdout 实质输出，要么真写进非空文件。"""
    if not (isinstance(res, InvokeResult) and res.ok):
        return {"is_real": False, "exit_ok": False, "stdout_len": 0,
                "wrote_file": write_path, "wrote_bytes": 0}
    out = ((res.data or {}).get("output", "") or "")
    stdout_len = len(out.strip())
    wrote_bytes = 0
    if write_path and os.path.isabs(write_path):
        try:
            wrote_bytes = os.path.getsize(write_path) if os.path.exists(write_path) else 0
        except OSError:
            wrote_bytes = 0
    is_real = (stdout_len > 0) or (wrote_bytes > 0)
    return {"is_real": is_real, "exit_ok": True, "stdout_len": stdout_len,
            "wrote_file": write_path, "wrote_bytes": wrote_bytes}


def _inference_real_metrics(res: Any) -> Dict[str, Any]:
    """推理步真实指标：产出过短或开头是拒答话术 → 视为敷衍。"""
    data = res.data if isinstance(res, InvokeResult) else {}
    text = (data or {}).get("content") or (data or {}).get("output") or ""
    c = len(text.strip())
    refusal = c < 30 or bool(_REFUSAL_RE.search(text.strip()[:80]))
    return {"is_real": (isinstance(res, InvokeResult) and res.ok) and not refusal,
            "char_count": c, "refusal": refusal}


def _verify_deliverable(task: str, trace: List[Dict[str, Any]]) -> Dict[str, Any]:
    """若任务要求产出某文件，验证它是否真实落盘且有内容（最终真实闸门）。

    不凭空编造：只在任务文本出现明确绝对路径/带扩展名路径时才检查。
    """
    # 路径体排除 CJK 标点与 '='：否则 `.md；memory.semantic` 这种「路径+后续指令」
    # 会被贪心匹配成「D:\\...\\e2e_verify_report.md；memory.semantic」，误把 .semantic
    # 当扩展名，导致 target 错乱、exists 判定为假、verdict 谎报「未完成」。
    _PATH_BODY = r"[^\s\"'<>|；;，。！？：、=]"
    paths = re.findall(r"[A-Za-z]:[\\/]" + _PATH_BODY + r"+(?:\.[A-Za-z0-9]+)", task)
    paths += re.findall(
        r"(?:存[到]?|写到|输出[到]?|save[ _]?to|write[ _]?to)\s*[:：]?\s*(" + _PATH_BODY + r"+\.[A-Za-z0-9]+)",
        task, re.I,
    )
    if not paths:
        return {"requested": False}
    target = paths[0]
    exists = os.path.exists(target)
    size = os.path.getsize(target) if exists else 0
    # 归一化路径分隔符再比（trace 里 wrote_file 用 '/'，任务文本用 '\\'，Windows 下等价）。
    # 否则字符串不等 → trace_wrote 恒为 False，reason 会谎称「trace 未见真实写入」。
    _norm = lambda p: os.path.normpath(p) if p else ""
    wrote = any(
        _norm((t.get("real_metrics") or {}).get("wrote_file")) == _norm(target)
        and (t.get("real_metrics") or {}).get("wrote_bytes", 0) > 0
        for t in trace
    )
    return {
        "requested": True, "target": target, "exists": exists,
        "bytes": size, "trace_wrote": wrote, "satisfied": exists and size > 0,
    }


# ---- 主入口 ------------------------------------------------------

# 反思/重设计上限：单任务最多额外反思 N 轮（总计 ≤ N+1 次执行），
# 绝不让「反思→失败→再反思」无限循环（求是引擎式：失败就改，但改有上限）。
# 动态化：按任务复杂度给反思预算——简单任务省算力，复杂任务给足重试空间
# （SWE-bench top agent 平均反思 5-8 轮，简单任务无需那么多轮）。
MAX_REFLECT_SIMPLE = 2   # <3 关键词
MAX_REFLECT_MEDIUM = 4   # 3-6 关键词
MAX_REFLECT_COMPLEX = 8  # >6 关键词
MAX_REFLECT = MAX_REFLECT_SIMPLE  # 默认/兼容引用（run() 会按任务复杂度覆盖）

# 默认本地反思 LLM（ollama）模型。
# 必须「能产出 AOS 计划格式（能力前缀步骤）」——这是 ③ 级自进化真闭环成立的前提。
# 已知 minicpm-mem:latest / minicpm5-1b 是 chat 鹦鹉：对反思 prompt 只鹦鹉学舌、
# 零能力前缀步骤输出，会让闭环静默降级成 heuristic 假闭环（违反理念8白盒可进化）。
# 故选格式遵循型 instruct/coder 模型为默认；可用 AOS_REFLECT_OLLAMA_MODEL 覆盖。
DEFAULT_REFLECT_OLLAMA_MODEL = "qwen2.5-coder:7b"

# 成本硬停：防止任务无限烧资源（时间 + LLM 调用次数双上限）
MAX_DURATION_SEC = float(os.environ.get("AOS_AUTOPILOT_MAX_DURATION", "600"))  # 默认 10 分钟
MAX_LLM_CALLS = int(os.environ.get("AOS_AUTOPILOT_MAX_LLM_CALLS", "20"))  # 默认 20 次


def _max_reflect_for(task: str) -> int:
    """按任务复杂度算反思预算（关键词数近似任务难度）。"""
    words = [w for w in re.split(r"\s+", task.strip()) if w]
    cjk = re.findall(r"[一-鿿]", task)
    kw = len(words) + len(cjk)
    if kw > 6:
        return MAX_REFLECT_COMPLEX
    if kw >= 3:
        return MAX_REFLECT_MEDIUM
    return MAX_REFLECT_SIMPLE

# AOS 自主环支持的能力全集（规划/解析共用）
_CAPS = [
    "web.search", "action.code_exec", "inference.llm",
    "memory.semantic", "cognition.reasoning", "cognition.planning",
]


def _parallel_enabled() -> bool:
    """多线程并行执行总开关（opt-in，默认关，保证零回归）。

    AOS_AUTOPILOT_PARALLEL=1/true/yes/on 时，规划阶段尝试识别独立子任务产出
    parallel_groups，交给 OrchestrationChiplet 并发执行；否则永远串行（既有行为）。
    """
    return os.environ.get("AOS_AUTOPILOT_PARALLEL", "").strip().lower() in (
        "1", "true", "yes", "on")


def _max_parallel(tenant_id: Optional[str] = None) -> int:
    """单个并行组的最大并发步数上限（默认 3，防线程/资源打满）。

    自适应接管（理念2.5 反思闭环真作用于行为）：env 给的是**上限基线**，
    内核自适应中枢若因失稳压低了并发（AdaptiveCore.reduce_concurrency），
    这里取二者较小值 —— 稳态说的「降并发」在这里真的生效，不是记个日志。
    """
    try:
        base = max(1, int(os.environ.get("AOS_MAX_PARALLEL", "3")))
    except ValueError:
        base = 3
    try:
        return _get_autopilot_core(tenant_id).effective_concurrency(base)
    except Exception:
        return base


def _cap_parallel_groups(groups, max_workers: int):
    """把超过上限的并行组切成 ≤max_workers 的连续子组（子组间顺序、组内并发）。

    切分保持「从0起连续前缀」不变（引擎约束），是安全的并发节流，不改变覆盖范围。
    """
    if not groups:
        return groups
    out = []
    for g in groups:
        if len(g) <= max_workers:
            out.append(g)
        else:
            for k in range(0, len(g), max_workers):
                out.append(g[k:k + max_workers])
    return out


def _plan(task: str, planner: str, tenant_id: Optional[str] = None):
    """规划一次：返回 (plan_text, steps, parallel_groups, used_planner)。

    ag2 不可用透明降级 heuristic。parallel_groups 仅在 AOS_AUTOPILOT_PARALLEL 开启
    且识别出独立子任务时非 None，否则为 None（完全串行，零回归）。
    """
    from core.fabric.adapter import InvokeRequest, InvokeResult
    from core.fabric.capability import Capability
    from kernel.plugins.plan_bridge import (
        parse_plan_to_steps, heuristic_plan,
        plan_with_parallelism, parse_plan_with_parallelism,
    )

    parallel_on = _parallel_enabled()
    plan_text: Optional[str] = None
    steps: List[Dict[str, Any]] = []
    parallel_groups = None
    used_planner = planner

    if planner == "ag2":
        try:
            ag2 = _get_ag2()
            if ag2.health():
                res = _call_with_timeout(
                    lambda: ag2.invoke(InvokeRequest(
                        capability=Capability.PLANNING.value,
                        payload={"topic": task},
                    )),
                    _AG2_TIMEOUT,
                )
                if res is _TIMEOUT:
                    logger.warning("ag2 规划超时(>%ss)，降级 heuristic", _AG2_TIMEOUT)
                    _reset_ag2()
                elif isinstance(res, InvokeResult) and res.ok and res.data:
                    plan_text = (res.data.get("plan") or "").strip() or None
                    if plan_text:
                        if parallel_on:
                            steps, parallel_groups = parse_plan_with_parallelism(plan_text, _CAPS)
                        else:
                            steps = parse_plan_to_steps(plan_text, _CAPS)
        except Exception:
            logger.warning("ag2 规划失败，降级 heuristic", exc_info=True)

    if not steps:
        # 开源默认路由：Ollama/vLLM（AOS_LLM_BASE_URL）或本机 Ollama 优先；
        # 仅 planner=="auto" 且显式 AOS_ZHIPU_OPTIN 时才退化到智谱（opt-in）。
        if planner in ("ollama", "open_source", "local", "auto"):
            try:
                otext = _llm_generate(_build_plan_prompt(task),
                                      allow_zhipu=(planner == "auto"))
                if otext:
                    osteps = parse_plan_to_steps(otext, _CAPS)
                    if osteps:
                        steps = osteps
                        plan_text = otext.strip() or plan_text
                        used_planner = "open_source"
                        logger.info("规划使用开源 LLM（Ollama/vLLM）")
            except Exception:  # noqa: BLE001
                logger.warning("开源规划失败，降级", exc_info=True)
        # 智谱直连作为 ag2 不可用时的高质量 LLM 规划后端（已验证可用，零新依赖）
        if not steps and planner in ("ag2", "zhipu"):
            try:
                ztext = _zhipu_generate(_build_plan_prompt(task))
                if ztext:
                    zsteps = parse_plan_to_steps(ztext, _CAPS)
                    if zsteps:
                        steps = zsteps
                        plan_text = ztext.strip() or plan_text
                        used_planner = "zhipu"
                        logger.info("规划改用智谱直连（ag2 不可用）")
            except Exception:
                logger.warning("智谱规划失败，降级 heuristic", exc_info=True)
        if not steps:
            if parallel_on:
                steps, parallel_groups = plan_with_parallelism(task, _CAPS)
            else:
                steps = heuristic_plan(task, _CAPS)
            used_planner = "heuristic"
            plan_text = None

    # 出门检：过滤掉 hub 实际未通电的能力步（避免执行必失败的步浪费反思轮次）
    hub = _get_hub()
    if hub is not None and steps:
        try:
            live_caps = set(hub._known_capabilities())
            before = len(steps)
            steps = [s for s in steps
                     if s.get("capability") in live_caps
                     or s.get("capability") in _CAPS]  # _CAPS 是 autopilot 自有能力，保留
            filtered = before - len(steps)
            if filtered:
                logger.info("出门检：过滤 %d 个 hub 未通电能力步", filtered)
        except Exception:  # noqa: BLE001
            pass  # 出门检失败不阻塞规划

    if parallel_groups:
        parallel_groups = _cap_parallel_groups(parallel_groups, _max_parallel(tenant_id))
        if parallel_groups:
            logger.info("并行规划已激活：%d 组 %s（首轮并发执行）",
                        len(parallel_groups), parallel_groups)
    return plan_text, steps, parallel_groups, used_planner


def _execute(task: str, steps: List[Dict[str, Any]], seed_context: Optional[Dict[str, Any]] = None,
             parallel_groups=None, on_step=None):
    """执行一轮步骤（每轮新建 OrchestrationChiplet，保证上下文干净）。

    返回 (exe_res, recorded)：recorded 是本轮回所有「成功步」的真实产出
    （capability + 完整 out），供跨轮上下文续接与反思记忆使用。
    seed_context：上轮已成功步的真实产出，作为本轮首步的 in_from:previous 起点
    （求是引擎式反思：保留成功经验、只重设计失败处之后的下一步，不重跑、不回归）。
    parallel_groups：非 None 时透传给编排芯粒，触发组内并发执行（仅首轮用，
    反思重设计后的轮次保持串行以保安全）。
    """
    from core.fabric.adapter import InvokeRequest
    from kernel.plugins.orchestration_chiplet import OrchestrationChiplet

    recorded: List[Dict[str, Any]] = []

    def _rec_route(capability: str, payload: Dict[str, Any]):
        res = _route(capability, payload)
        # 仅记录成功且真实的步产出（real_metrics.is_real 为真），供续接用
        if isinstance(res, InvokeResult) and res.ok and isinstance(res.data, dict):
            if (res.data.get("real_metrics") or {}).get("is_real"):
                recorded.append({"capability": capability, "out": res.data})
                # 中间对齐检查：每 3 步验一次方向（纯本地计算，零延迟）
                if len(recorded) % 3 == 0:
                    acc_text = " ".join(
                        str((r.get("out") or {}).get("content", ""))[:200]
                        for r in recorded[-3:]
                    )
                    task_toks = _tokenize(task)
                    out_toks = _tokenize(acc_text)
                    if task_toks:
                        overlap = len(task_toks & out_toks) / len(task_toks)
                        if overlap < 0.05:
                            logger.warning(
                                "autopilot: 第 %d 步后方向可能偏了"
                                "（关键词重叠 %.2f）", len(recorded), overlap)
        # 因果反思闭环：把每步真实成败+引擎喂进白盒蒸馏器（opt-in）
        _feed_distiller(capability, res)
        # 实时进度钩子：每步完成后通知前端（落盘 checkpoint，前端轮询可见逐步过程）
        if on_step is not None:
            try:
                on_step({
                    "done": len(recorded),
                    "total": len(steps),
                    "capability": capability,
                    "ok": isinstance(res, InvokeResult) and bool(res.ok),
                    "last_out": (recorded[-1]["out"] if recorded else None),
                })
            except Exception:  # noqa: BLE001
                pass
        return res

    oc = OrchestrationChiplet(route_fn=_rec_route)
    payload = {"initial": {"task": task}, "steps": steps}
    if seed_context:
        payload["seed_context"] = seed_context
    if parallel_groups:
        payload["parallel_groups"] = parallel_groups
    exe_res = oc.invoke(InvokeRequest(capability="workflow.execute", payload=payload))
    return exe_res, recorded


def _pick_final_output(task: str, trace: List[Dict[str, Any]]) -> Optional[str]:
    """选「最终输出」：优先真实落盘的交付物内容，否则取最后一个真实且有实质的步。

    修复：旧逻辑取「最后一个 ok 步的 out」，导致报告显示的是 memory no-op 步
    （{'content': 'memory not yet wired'}）而非真实报告——系统连交付物都没理解。
    """
    # 1) 任务要求产出文件且已真实落盘 → 读回文件头部（最真实的交付物）
    for p in re.findall(r"[A-Za-z]:[\\/][^\s\"'<>|]+(?:\.[A-Za-z0-9]+)", task):
        if os.path.exists(p) and os.path.getsize(p) > 0:
            try:
                with open(p, encoding="utf-8", errors="replace") as f:
                    return f.read()[:500]
            except OSError:
                pass
    # 2) 否则取最后一个「真实(is_real)且带实质文本」的步（优先 content 字段，
    #    避开 action.code_exec 的 {'output':'written'} 这类动作回执）
    for t in reversed(trace):
        rm = t.get("real_metrics") or {}
        is_real = rm.get("is_real")
        if is_real is None:
            is_real = t.get("real")  # 执行 trace 用 'real' 字段
        if not (is_real and t.get("ok")):
            continue
        out = t.get("out") or t.get("output")
        content = (out or {}).get("content") if isinstance(out, dict) else ""
        if isinstance(content, str) and len(content.strip()) > 20:
            return content[:500]
    # 3) 兜底：任何真实步的 out 字符串
    for t in reversed(trace):
        rm = t.get("real_metrics") or {}
        is_real = rm.get("is_real")
        if is_real is None:
            is_real = t.get("real")
        if is_real and t.get("ok"):
            out = t.get("out") or t.get("output")
            if out is not None:
                return str(out)[:500]
    return None


def _needs_reflection(r: Dict[str, Any]) -> bool:
    """是否还需反思重设计：未完成 / 部分完成但未落盘产物 → 需反思；完成 → 停。"""
    status = (r.get("verdict") or {}).get("status", "")
    if status.startswith("完成"):
        return False
    if "产物已真实落盘" in status:  # 部分完成但东西已真出来，算达成
        return False
    return True


# ---- 反思记忆（求是引擎 Meta-Trace / Reflexion episodic memory 的轻量落地）----
# 把每轮反思提炼出的「失败根因→教训」持久化到磁盘(JSONL)，供后续任务/同任务
# 反思时作为额外上下文注入质疑 agent。有界：仅保留最近 N 条，避免噪声累积与
# 上下文膨胀（Reflexion：memory 通常只保留最近 1-3 次反思）。
_REFLECTION_MEMORY_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "_traces", "reflection_memory.jsonl"
)
_REFLECTION_MEMORY_MAX = 200
_REFLECTION_MEMORY_SHORT_TTL_DAYS = 7
_REFLECTION_MEMORY_LONG_TTL_DAYS = 90
_REFLECTION_LOCK = threading.Lock()


def _tokenize(text: str) -> set:
    """极简分词：英文/数字按词、CJK 按字，用于任务相似度匹配。"""
    toks = re.findall(r"[a-z0-9]+|[一-鿿]", (text or "").lower())
    return set(toks)


def _load_lessons(task: str, limit: int = 3) -> List[Dict[str, Any]]:
    """载入与当前任务最相关的历史反思教训（按 token 重叠打分，取 top-limit）。
    
    TTL生命周期淘汰：
    - 短期故障记忆（快速淘汰）：7天
    - 长期环境偏好（长周期保留）：90天
    - 热度权重：长期未被命中的自动降级淘汰
    """
    with _REFLECTION_LOCK:
        try:
            if not os.path.exists(_REFLECTION_MEMORY_PATH):
                return []
            q = _tokenize(task)
            scored = []
            now = datetime.datetime.now()
            with open(_REFLECTION_MEMORY_PATH, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except Exception:
                        continue
                    # TTL过滤：短期故障记忆7天，长期环境偏好90天
                    ts_str = rec.get("ts", "")
                    if not ts_str:
                        continue
                    try:
                        ts = datetime.datetime.fromisoformat(ts_str)
                    except Exception:
                        continue
                    days_old = (now - ts).days
                    # 判断是短期故障记忆还是长期环境偏好
                    # 短期：包含"失败"、"错误"、"异常"等关键词
                    is_short_term = any(
                        kw in rec.get("lesson", "").lower()
                        for kw in ["失败", "错误", "异常", "error", "fail"]
                    )
                    ttl_days = (
                        _REFLECTION_MEMORY_SHORT_TTL_DAYS
                        if is_short_term
                        else _REFLECTION_MEMORY_LONG_TTL_DAYS
                    )
                    if days_old > ttl_days:
                        continue
                    base = _tokenize(rec.get("task", "") + " " + rec.get("failed_cap", ""))
                    overlap = len(q & base)
                    if overlap:
                        scored.append((overlap, rec))
            scored.sort(key=lambda x: x[0], reverse=True)
            return [r for _, r in scored[:limit]]
        except Exception:
            logger.warning("载入反思记忆失败", exc_info=True)
            return []


def _save_lesson(task: str, failed_cap: str, error: str, lesson: str) -> None:
    """追加一条反思教训到记忆（有界轮转）。绝不写空/无意义记录。"""
    if not lesson or len(lesson.strip()) < 10:
        return
    rec = {
        "ts": datetime.datetime.now().isoformat(),
        "task": task,
        "failed_cap": failed_cap,
        "error": (error or "")[:200],
        "lesson": lesson.strip(),
    }
    with _REFLECTION_LOCK:
        try:
            os.makedirs(os.path.dirname(_REFLECTION_MEMORY_PATH), exist_ok=True)
            # 轮转：超上限删最旧 20%
            if os.path.exists(_REFLECTION_MEMORY_PATH):
                with open(_REFLECTION_MEMORY_PATH, encoding="utf-8") as f:
                    lines = [l for l in f if l.strip()]
                if len(lines) >= _REFLECTION_MEMORY_MAX:
                    lines = lines[_REFLECTION_MEMORY_MAX // 5:]
                    with open(_REFLECTION_MEMORY_PATH, "w", encoding="utf-8") as f:
                        f.writelines(lines)
            with open(_REFLECTION_MEMORY_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception:
            logger.warning("保存反思记忆失败", exc_info=True)


# ---- 语义记忆（任务→真实产出的知识沉淀，长程自主） ----
# 与反思教训记忆共用 _traces/ 目录与有界轮转风格，但存的是「任务→真实产出」
# 的语义知识（求是引擎 Meta-Trace 同类思想：系统应跨任务累积知识，而非每轮
# 从零开始）。文件后端离线确定可用，不依赖 mem0/ollama 是否在跑——
# 避免「后端没起却谎报成功」这种违背「绝不伪造发现」的坑。
# 语义记忆路径 + 并发锁统一由 kernel.semantic_state 提供：
# autopilot（写侧）与 fabric_hub（读 / 回退写侧）共用同一把锁，避免并发读写写坏 JSONL。
from kernel.semantic_state import (
    SEMANTIC_MEMORY_PATH as _SEMANTIC_MEMORY_PATH,
    SEMANTIC_LOCK as _SEMANTIC_LOCK,
)
_SEMANTIC_MEMORY_MAX = 500


def _save_semantic_memory(task: str, content: str) -> Dict[str, Any]:
    """把一次任务产出的知识真实落盘到语义记忆，返回记录摘要。"""
    import hashlib
    h = hashlib.sha256(content.encode("utf-8")).hexdigest()
    preview = content.strip()[:200].replace("\n", " ")
    record = {
        "ts": datetime.datetime.now().isoformat(),
        "task": (task or "")[:200],
        "hash": h,
        "preview": preview,
        "content": content[:6000],  # 单条上限，避免过大
        "bytes": len(content.encode("utf-8")),
    }
    try:
        with _SEMANTIC_LOCK:
            os.makedirs(os.path.dirname(_SEMANTIC_MEMORY_PATH), exist_ok=True)
            if os.path.exists(_SEMANTIC_MEMORY_PATH):
                with open(_SEMANTIC_MEMORY_PATH, encoding="utf-8") as f:
                    lines = [l for l in f if l.strip()]
                if len(lines) >= _SEMANTIC_MEMORY_MAX:
                    lines = lines[_SEMANTIC_MEMORY_MAX // 5:]
                    with open(_SEMANTIC_MEMORY_PATH, "w", encoding="utf-8") as f:
                        f.writelines(lines)
            with open(_SEMANTIC_MEMORY_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        logger.warning("保存语义记忆失败", exc_info=True)
    return {"hash": h, "preview": preview, "stored_bytes": record["bytes"]}


def _reflect_and_redesign(task: str, r: Dict[str, Any], cycle: int, prior_success: Optional[List[Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
    """求是引擎式『质疑与风险检查 agent』：诊断上轮失败根因，重设计下一步计划。

    绝不伪造：只用 trace 里的真实错误/产出喂给推理，让它产出修正后的步骤；
    解析不出有效步骤则返回 None（不再硬凑，避免无限循环）。
    """
    from kernel.plugins.plan_bridge import parse_plan_to_steps

    trace = (r.get("execution") or {}).get("trace", [])
    if not trace:
        return None
    failed, succeeded = [], []
    for i, t in enumerate(trace):
        cap = t.get("capability", "?")
        # 兼容两种 trace：原始 trace 带 real_metrics，执行 trace 带 real
        is_real = (t.get("real_metrics") or {}).get("is_real")
        if is_real is None:
            is_real = t.get("real")
        if not t.get("ok") or is_real is False:
            failed.append(f"步骤{i+1}[{cap}] 失败/空转：{(t.get('summary') or '')[:200]}")
        elif t.get("ok"):
            succeeded.append(f"步骤{i+1}[{cap}] 成功")
    if not failed:
        return None  # 没有可反思的失败

    # 因果反思建议（D5 决策论层）：用白盒蒸馏器的 (能力,引擎)→成败，经 CausalModel
    # 选「换做法」引擎并给出可复核证据，注入下方提示词 + 给重设计步骤打 engine_hint。
    # 无蒸馏器或样本不足则 causal_block/hints 皆空，反思退化回质疑 agent 诊断。
    causal_block, causal_hints = _compute_causal_hints(failed, _get_causal_distiller())

    # 上轮已成功步的真实产出（供本轮续接，不重跑、不回归）
    prior_parts = []
    for s in (prior_success or []):
        cap = s.get("capability", "?")
        out = s.get("out") or {}
        txt = extract_text(out) if isinstance(out, dict) else str(out)
        prior_parts.append(f"  - [{cap}] 已成功，产出摘要：{(txt or '')[:300]}")
    prior_block = (
        "【上轮已成功、本轮无需重做的步及其真实产出】\n"
        + ("\n".join(prior_parts) or "  （无）") + "\n"
    ) if prior_parts else ""

    # 跨任务历史教训（Meta-Trace）：与当前任务相似的过往失败→修正经验
    lessons = _load_lessons(task, limit=3)
    lesson_block = ""
    if lessons:
        lesson_lines = []
        for L in lessons:
            lesson_lines.append(
                f"  - 过往类似任务失败于[{L.get('failed_cap','?')}]："
                f"{L.get('error','')[:120]} → 教训：{L.get('lesson','')[:200]}"
            )
        lesson_block = (
            "\n【历史相似教训（请优先规避这些已知失败做法）】\n"
            + "\n".join(lesson_lines) + "\n"
        )

    prompt = (
        causal_block +
        f"你是 AOS 自主执行环的『质疑与风险检查 agent』。\n"
        f"原始目标：{task}\n\n"
        f"上一轮执行中，以下步失败或空转（附真实错误）：\n"
        + "\n".join(f"  - {f}" for f in failed) + "\n\n"
        "已成功的步：\n" + ("\n".join(f"  - {s}" for s in succeeded) or "  （无）") + "\n\n"
        + prior_block + lesson_block +
        "请诊断根因，并只产出【从失败处继续、直到完成原始目标所需的『剩余步骤』】"
        "——已经成功的步不要重做。\n"
        "计划每行一个步骤，用 AOS 能力标签前缀（如 web.search= / inference.llm= / "
        "action.code_exec= / memory.semantic=）。不要解释，只输出剩余步骤计划。"
    )
    # 反思推理三后端降级：ag2 → 本地 ollama → heuristic 重试（绝不伪造新计划）
    # 1) ag2（首选，质量最高）
    try:
        ag2 = _get_ag2()
        text = _call_with_timeout(lambda: ag2.produce_text(prompt), _AG2_TIMEOUT)
        if text is _TIMEOUT:
            logger.warning("反思 ag2 超时(>%ss)，降级 ollama", _AG2_TIMEOUT)
            _reset_ag2()
        elif text:
            steps = parse_plan_to_steps(text, _CAPS)
            if steps:
                _attach_engine_hints(steps, causal_hints)
                if _is_meaningful_redesign(steps, failed, causal_hints):
                    return _finalize_reflect(task, failed, text.strip(), steps, "ag2",
                                             causal_hints=causal_hints)
                logger.warning("ag2 反思产出假重设计，降级 ollama")
    except Exception as e:  # noqa: BLE001
        logger.warning("反思 ag2 失败，降级智谐/ollama: %s", e)
    # 1.5) 开源默认 LLM 反思后端（Ollama/vLLM 优先），智谱仅 opt-in 兜底
    try:
        ztext = _llm_generate(prompt, allow_zhipu=True)
        if ztext:
            zsteps = parse_plan_to_steps(ztext, _CAPS)
            if zsteps:
                _attach_engine_hints(zsteps, causal_hints)
                if _is_meaningful_redesign(zsteps, failed, causal_hints):
                    return _finalize_reflect(task, failed, ztext.strip(), zsteps, "zhipu",
                                             causal_hints=causal_hints)
                logger.warning("智谱反思产出假重设计，降级 ollama")
    except Exception as e:  # noqa: BLE001
        logger.warning("反思 智谱失败，降级 ollama: %s", e)
    # 2) 本地 ollama（ag2 dead / 无 key 时的真实 LLM 反思后端）
    try:
        text = _ollama_generate(prompt)
        if text:
            steps = parse_plan_to_steps(text, _CAPS)
            if steps:
                _attach_engine_hints(steps, causal_hints)
                if _is_meaningful_redesign(steps, failed, causal_hints):
                    return _finalize_reflect(task, failed, text.strip(), steps, "ollama",
                                             causal_hints=causal_hints)
                logger.warning("ollama 反思产出假重设计（换说法不换做法），降级 heuristic")
            else:
                # 白盒守卫：模型返回了文本但解析不出 AOS 计划格式（疑似 chat 鹦鹉），
                # 明确记录而非静默掉，避免 ③ 假闭环不可见（理念8：白盒才可进化）。
                logger.warning(
                    "ollama 反思未产出 AOS 计划格式步骤（模型疑似 chat 鹦鹉），降级 heuristic")
        else:
            logger.warning("ollama 反思返回空文本，降级 heuristic")
    except Exception as e:  # noqa: BLE001
        logger.warning("反思 ollama 失败，降级 heuristic 重试: %s", e)
    # 3) heuristic 兜底：重试上轮失败步（不编造新计划，仅重发失败能力）
    heur = _heuristic_reflect(r)
    if heur:
        _attach_engine_hints(heur["steps"], causal_hints)
        return _finalize_reflect(task, failed, heur["plan"], heur["steps"], "heuristic",
                                 causal_hints=causal_hints)
    logger.warning("反思三后端均不可用且无失败步可重试，停止避免空转")
    return None


def _is_meaningful_redesign(steps: List[Dict[str, Any]], failed: List[str],
                            causal_hints: Dict[str, Any]) -> bool:
    """检查重设计是否真的换了做法（防"换说法不换做法"的假反思）。

    规则：新计划首步的 capability 若与某失败步相同，且无 engine_hint
    （因果模型没建议换引擎），则判定为"原地重试伪装成反思"→ 拒绝。
    有 engine_hint 说明因果模型选了不同引擎 → 放行（真换了做法）。
    """
    if not steps or not failed:
        return True
    # 从 failed 文本提取失败的 capability（格式："步骤N[cap] 失败/空转：..."）
    failed_caps = set()
    for f in failed:
        m = re.match(r"步骤\d+\[([^\]]+)\]", f)
        if m:
            failed_caps.add(m.group(1))
    first_cap = steps[0].get("capability", "")
    if first_cap in failed_caps and "engine_hint" not in steps[0]:
        logger.info("反思拒绝：首步 [%s] 与失败步相同且无引擎切换，判定为假反思", first_cap)
        return False
    return True


def _finalize_reflect(task, failed, plan_text, steps, engine,
                      causal_hints: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """沉淀教训（求是引擎 Meta-Trace / Reflexion episodic）并封装反思结果。"""
    new_first = steps[0].get("capability", "?")
    lesson = (
        f"原失败：{'；'.join(failed)[:200]}。"
        f"修正后改为从[{new_first}]继续，避免重做已成功步（反思引擎={engine}）。"
    )
    _save_lesson(
        task,
        (failed[0].split(']')[0].split('[')[-1] if failed else "?"),
        failed[0] if failed else "",
        lesson,
    )
    result = {"plan": plan_text, "steps": steps, "engine": engine}
    if causal_hints:
        result["causal_hints"] = {cap: h["suggested_engine"]
                                  for cap, h in causal_hints.items()}
    return result


def _ollama_generate(prompt: str, model: Optional[str] = None) -> Optional[str]:
    """本地 ollama 文本生成（stdlib only，无第三方依赖）。

    反思三后端降级链的真实 LLM 环节（ag2 → zhipu → ollama → heuristic）。
    默认模型见 DEFAULT_REFLECT_OLLAMA_MODEL：必须是能产出 AOS 计划格式
    （能力前缀步骤）的模型，否则闭环会静默降级成 heuristic 假闭环。
    超时 60s 防挂死（兼容 7B 模型冷加载），失败抛异常交上层降级到 heuristic。
    """
    import json as _json
    import urllib.request
    model = model or os.environ.get("AOS_REFLECT_OLLAMA_MODEL",
                                     DEFAULT_REFLECT_OLLAMA_MODEL)
    url = os.environ.get("AOS_OLLAMA_URL", "http://localhost:11434/api/generate")
    body = _json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.3, "num_predict": 300},
    }).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = _json.loads(resp.read().decode("utf-8"))
    return data.get("response") or None


def _heuristic_reflect(r) -> Optional[Dict[str, Any]]:
    """无 LLM 时的降级反思：重试上轮失败步（保持原 capability，不编造新计划）。

    仅当确有失败步时返回剩余步；否则 None（不空转）。重试受 MAX_REFLECT 上限约束，
    不会无限循环。这是「诚实兜底」——重发失败步可能成功（瞬时/依赖就绪），
    但绝不假装推理出了新策略。
    """
    trace = (r.get("execution") or {}).get("trace", [])
    retry_caps: List[str] = []
    for t in trace:
        is_real = (t.get("real_metrics") or {}).get("is_real")
        if is_real is None:
            is_real = t.get("real")
        if not t.get("ok") or is_real is False:
            retry_caps.append(t.get("capability") or "inference.llm")
    if not retry_caps:
        return None
    steps = [{"capability": c, "in_from": "previous"} for c in retry_caps]
    return {"plan": "（heuristic 重试失败步）", "steps": steps}


def _assemble(task, used_planner, plan_text, steps, exe_res, cycle, start) -> Dict[str, Any]:
    """汇总一轮执行：trace / 置信 / 判定 / 最终输出。"""
    data = exe_res.data if isinstance(exe_res, InvokeResult) else {}
    duration = round(time.time() - start, 1)
    trace = data.get("trace", []) or []
    final = _pick_final_output(task, trace)

    trace_obj = _build_structured_trace(task, used_planner, plan_text, steps, data, duration, trace)
    _save_trace(trace_obj)

    confidence = _score_confidence(data, steps, trace)
    verdict = _verdict(task, data, trace, confidence)

    return {
        "task": task,
        "planner": used_planner,
        "plan": plan_text,
        "cycle": cycle,
        "steps": [
            {
                "capability": s["capability"],
                "in": s.get("in", s.get("in_from", "")),
                "real": (trace[i].get("real_metrics") or {}).get("is_real")
                if i < len(trace) else None,
            }
            for i, s in enumerate(steps)
        ],
        "execution": {
            "ok_steps": data.get("ok_steps", 0),
            "failed_steps": data.get("failed_steps", 0),
            "trace": [
                {
                    "step": t.get("step"),
                    "capability": t.get("capability", ""),
                    "engine": t.get("engine"),
                    "ok": t.get("ok"),
                    "real": (t.get("real_metrics") or {}).get("is_real"),
                    "out": str(t.get("out") or "")[:500],
                    "error": str(t.get("error") or "")[:300],
                }
                for t in trace
            ],
            "final": final,
        },
        "confidence": confidence,
        "verdict": verdict,
        "trace_id": trace_obj["task_id"],
        "duration_s": duration,
    }


def _new_run_id(task: str) -> str:
    """短稳定 run_id：task 哈希 + 时间戳，避免重名冲突且可读定位。"""
    h = hashlib.sha256((task + str(time.time())).encode("utf-8")).hexdigest()[:12]
    return f"run_{h}"


class _RunState:
    """autopilot.run() 的可序列化状态容器（进程级 → 落盘 checkpoint）。

    把原本散在 run() 局部变量里的 task/steps/prior_success/reflection_log/cycle
    收拢成一个对象，使其能被 sqlite 持久化并在 resume_run 时完整还原。
    """

    def __init__(self, task: str, planner: str, plan_text: str, steps, max_reflect: int = None,
                 per_run_id: str = "", parallel_groups=None, tenant_id: Optional[str] = None):
        self.task = task
        self.planner = planner
        # 多租户隔离标识：随 checkpoint 一起落盘，resume_run 续跑时仍回到本租户中枢
        self.tenant_id = tenant_id
        self.plan_text = plan_text
        self.steps = steps
        # 首轮并发分组（opt-in）；反思重设计后置 None 保持串行（见 _advance_cycle）
        self.parallel_groups = parallel_groups
        self.prior_success: list = []
        self.reflection_log: list = []
        self.last: dict = {}
        self.all_traces: list = []  # 每轮执行后的完整 trace（累计，供前端展示全过程）
        self.cycle = -1
        self.start = time.time()
        self.run_id = _new_run_id(task)
        self.per_run_id = per_run_id
        self.max_reflect = max_reflect or MAX_REFLECT

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "task": self.task,
            "planner": self.planner,
            "plan_text": self.plan_text,
            "steps": self.steps,
            "parallel_groups": self.parallel_groups,
            "prior_success": self.prior_success,
            "reflection_log": self.reflection_log,
            "last": self.last,
            "all_traces": self.all_traces,
            "cycle": self.cycle,
            "start": self.start,
            "max_reflect": self.max_reflect,
            "per_run_id": self.per_run_id,
            "tenant_id": self.tenant_id,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "_RunState":
        s = cls(d["task"], d["planner"], d["plan_text"], d["steps"], max_reflect=d.get("max_reflect"),
                per_run_id=d.get("per_run_id", ""), parallel_groups=d.get("parallel_groups"),
                tenant_id=d.get("tenant_id"))
        s.prior_success = d.get("prior_success", [])
        s.reflection_log = d.get("reflection_log", [])
        s.last = d.get("last", {})
        s.all_traces = d.get("all_traces", [])
        s.cycle = d.get("cycle", -1)
        s.start = d.get("start", time.time())
        s.run_id = d["run_id"]
        return s


def _advance_cycle(s: _RunState) -> bool:
    """执行一个反思轮次：跑步骤 + 评估 + (可选)反思重设计。

    返回 True=需继续下一轮；False=已达成 / 达上限 / 反思无有效修正。
    调用方负责在调用后 save_checkpoint：崩溃若发生在 _execute 内部，本轮
    checkpoint 自然不会写，恢复时从上一已完成轮续跑（不重跑已完成轮次）。
    """
    global _LAST_TEXT
    s.cycle += 1
    # 成本硬停：超时间预算立即停止（防无限烧资源）
    elapsed = time.time() - s.start
    if elapsed > MAX_DURATION_SEC:
        logger.warning("autopilot: 超时间预算 %.0fs > %.0fs，硬停", elapsed, MAX_DURATION_SEC)
        s.reflection_log.append({
            "cycle": s.cycle, "action": "budget_stop",
            "reason": f"超时间预算 {elapsed:.0f}s > {MAX_DURATION_SEC:.0f}s",
        })
        return False
    _LAST_TEXT = ""  # 每轮重置占位符上下文（每轮独立执行）
    # 带上轮已成功产出作为起点（seed_context）
    seed = None
    if s.prior_success:
        last_out = s.prior_success[-1]["out"]
        seed = dict(last_out)
        seed_text = extract_text(last_out) if isinstance(last_out, dict) else ""
        if seed_text and "text" not in seed:
            seed["text"] = seed_text
    # 仅首轮（主执行轮）透传并行分组；反思重设计后的轮次保持串行以保安全
    pg = s.parallel_groups if s.cycle == 0 else None
    def _live_save(prog):
        snap = s.to_dict()
        snap["live"] = prog
        save_checkpoint(s.run_id, snap)
    core = _get_autopilot_core(getattr(s, "tenant_id", None))
    # 环节2：执行（高重度——核心链路死亡必记录学习，但绝不级联杀整轮）
    ok_exec, exec_pair, err_exec = StageGuard(core, "execute").run(
        lambda: _execute(s.task, s.steps, seed_context=seed, parallel_groups=pg, on_step=_live_save),
        severity="high", max_retry=0,
    )
    if not ok_exec or exec_pair is None:
        # 高重度环节死亡：结构化收尾（不崩、不级联），后续 _record_failure_memory 仍跑、仍落盘
        logger.error("autopilot: execute 环节死亡(%s)，本轮以结构化失败收尾", err_exec)
        s.last = {
            "task": s.task, "planner": s.planner,
            "error": f"execute 环节失败: {err_exec}",
            "execution": {"trace": []}, "verdict": {"status": "环节失败"},
            "confidence": 0.0,
        }
        try:
            _record_failure_memory(s.task, s.last, getattr(s, "tenant_id", None))
        except Exception:
            pass
        return False
    exe_res, recorded = exec_pair

    # 环节3：评估（动态——assemble 死则降级为最小结构，不阻断后续环节）
    ok_asm, r, err_asm = StageGuard(core, "assemble").run(
        lambda: _assemble(s.task, s.planner, s.plan_text, s.steps, exe_res, s.cycle, s.start),
        severity="dynamic",
        fallback=lambda e: {
            "task": s.task, "execution": exe_res or {"trace": []},
            "verdict": {"status": "部分完成(评估降级)"},
            "error": f"assemble 环节失败: {e}",
        },
        max_retry=0,
    )
    if not ok_asm or r is None:
        r = {"task": s.task, "execution": exe_res or {"trace": []},
             "verdict": {"status": "部分完成(评估降级)"},
             "error": f"assemble 环节失败: {err_asm}"}
    s.last = r
    s.all_traces.append({
        "cycle": s.cycle,
        "trace": r.get("execution", {}).get("trace", []),
        "verdict": r.get("verdict"),
        "confidence": r.get("confidence"),
    })
    if recorded:
        s.prior_success = recorded
    # 已达成（或产物已落盘的部分完成）→ 停
    if not _needs_reflection(r) or s.cycle >= s.max_reflect:
        return False
    # 触发反思：质疑 agent 诊断根因 → 重设计下一步计划
    # 环节4：反思重设计（动态——死则降级为「不重设计」，整轮继续/收尾，不级联）
    ok_refl, refl, err_refl = StageGuard(core, "reflect").run(
        lambda: _reflect_and_redesign(s.task, r, s.cycle + 1, prior_success=s.prior_success),
        severity="dynamic",
        fallback=lambda e: None,
        max_retry=0,
    )
    if not ok_refl or not refl or not refl.get("steps"):
        s.reflection_log.append({
            "cycle": s.cycle + 1, "action": "no_redesign",
            "reason": f"反思环节失败/降级: {err_refl}",
        })
        return False
    s.reflection_log.append({
        "cycle": s.cycle + 1, "action": "redesign",
        "engine": refl.get("engine", "ag2"),
        "failed": [
            t.get("capability") for t in r.get("execution", {}).get("trace", [])
            if not t.get("ok") or (t.get("real_metrics") or {}).get("is_real") is False
        ],
        "new_step_count": len(refl["steps"]),
        "preserved_success_steps": len(s.prior_success),
        "causal_hints": list((refl.get("causal_hints") or {}).items()),
    })
    s.steps = refl["steps"]
    s.plan_text = refl.get("plan") or s.plan_text
    return True


def _record_failure_memory(task: str, result: Dict[str, Any],
                           tenant_id: Optional[str] = None) -> None:
    """任务结束后，把失败步根因写入共享失败记忆库（与 AdaptiveCore/StageGuard 同源同实例）。

    这是把「失败学习」理念接活进 autopilot 主路径的关键：此前只有 LearningLoop
    包装层才记录失败，autopilot.run 主路径零引用失败记忆。现在即便直接调用
    autopilot.run，失败也会被学习、下次同类任务 PREFLIGHT 可直接命中修复。

    关键修正（自进化闭环「写→读」闭合）：写入走 AdaptiveCore 持有的同一记忆实例
    （core.record_failure → self.memory.add），而非新建 FailureMemory()。这样下一轮
    PREFLIGHT（core.fix_hints）读到的就是本轮刚写的记录，同一进程内即时闭环，
    真正「记了就用」，不再是只写不读的死日志。

    设计纪律：任何异常都吞掉，绝不破坏反思重设计主流程。
    """
    try:
        exe = result.get("execution", {})
        trace = exe.get("trace", []) or []
        failed = [t for t in trace if not t.get("ok")]
        if not failed:
            return
        core = _get_autopilot_core(tenant_id)
        for fs in failed:
            cap = fs.get("capability") or "action.code_exec"
            err = str((fs.get("summary") or "") + (fs.get("error") or ""))
            core.record_failure(task, cap, err)
    except Exception:
        logger.warning("autopilot: 失败记忆写入异常，已跳过", exc_info=True)


def _inject_fix_hints(task: str, hints: List[str]) -> str:
    """把已知修复提示注入任务描述（与 LearningLoop._inject_hints 同格式，统一一处）。

    仅在 PREFLIGHT 命中时调用，把上轮同类失败的已知修复前置进规划输入，
    使下一轮计划/执行能看到历史教训 —— 自进化闭环的「读回并改变行为」。
    """
    if not hints:
        return task
    uniq = hints[:3]
    hint_text = ";\n".join(uniq)
    return (
        f"{task}\n\n"
        f"[系统提示：上次执行失败，已分析根因。已知修复方案：\n{hint_text}\n"
        f"请使用这些修复方案重试，不要重复之前的错误做法。]"
    )


def _get_autopilot_core(tenant_id: Optional[str] = None) -> Any:
    """惰性取**该租户**的内核自适应中枢（避免模块级循环依赖：adaptive→learning_loop
    在方法内 import autopilot.run，故这里也惰性 import）。

    tenant_id=None → 共享默认实例（自用模式，行为与之前一致）；
    非空 → 该租户独占稳态与失败记忆库，教训不跨租户串味（母纲「主权归你」）。
    """
    from kernel.adaptive import get_adaptive_core
    return get_adaptive_core(tenant_id=tenant_id)


# 让 StageGuard 在本模块可见（供 run()/_advance_cycle 环节隔离使用）
from kernel.adaptive import StageGuard  # noqa: E402  (置于函数后，惰性确保无环)


def _maybe_install_default_auditor():
    """MEA Auditor 接线（只读审计关卡）：autopilot 跑任务时让 Gate 真正生效。

    仅在 run_state_store 尚未注册审计器时，接入默认环境事实审计器；
    若调用方（如测试）已 set_auditor，则不被覆盖。失败静默放行，绝不因审计器
    装配问题阻塞 run。
    """
    try:
        import kernel.run_state_store as _rss
        if _rss._AUDITOR is None:
            from kernel.auditor import build_default_auditor
            _rss.set_auditor(build_default_auditor())
    except Exception:  # noqa: BLE001
        pass


def run(task: str, planner: str = "ag2", run_id: Optional[str] = None,
        tenant_id: Optional[str] = None) -> Dict[str, Any]:
    """执行一个自主任务（求是引擎式：规划→执行→质疑→重设计→再执行…）。

    Args:
        task: 自然语言任务
        planner: "ag2"（LLM 规划）或 "heuristic"（本地关键词）
        run_id: 显式传入则复用该 run_id（外部指定），否则自动生成。
            每轮结束后写入 sqlite checkpoint，进程崩了可用 resume_run 续跑。
        tenant_id: 多租户隔离标识。None=自用模式（共享默认中枢，行为不变）；
            非空则本次运行的稳态、失败记忆、PREFLIGHT 读回全部限定在该租户内，
            教训不跨租户串味（四层架构第①层 + 母纲「主权归你，永不收割」）。

    Returns: 顶层含 reflection 字段（轮次/是否达上限）+ run_id。
    """
    start = time.time()
    _maybe_install_default_auditor()  # MEA：让 AuditorGate 在真实 run 中生效
    # 环节1：规划（动态——规划死则降级为「空计划」，以结构化结果收尾，不崩整轮）
    core = _get_autopilot_core(tenant_id)
    # PREFLIGHT（自进化闭环「读回」）：查共享失败记忆库，命中已知修复则注入规划输入，
    # 使下一轮计划/执行能看到历史教训、不再重复犯错。guard 防 LearningLoop 已注入时重复。
    plan_task = task
    if "已知修复方案" not in task:
        preflight = core.fix_hints(task=task, capability="action.code_exec")
        if preflight:
            plan_task = _inject_fix_hints(task, preflight)
            logger.info("autopilot PREFLIGHT: 命中 %d 条已知修复，已注入规划输入", len(preflight))
    _ok_plan, _plan_pair, _err_plan = StageGuard(core, "plan").run(
        lambda: _plan(plan_task, planner, tenant_id),
        severity="dynamic",
        fallback=lambda e: ("", [], None, "heuristic"),
        max_retry=0,
    )
    plan_text, steps, parallel_groups, used_planner = _plan_pair if _plan_pair else ("", [], None, "heuristic")
    if not steps:
        return {
            "task": task, "planner": used_planner,
            "error": f"规划环节失败，无法生成任何执行步骤（{_err_plan}）",
            "duration_s": round(time.time() - start, 1),
        }

    s = _RunState(task, used_planner, plan_text, steps, max_reflect=_max_reflect_for(task),
                  per_run_id=run_id, parallel_groups=parallel_groups, tenant_id=tenant_id)
    if run_id:
        s.run_id = run_id
    create_run(s.run_id, task, used_planner)
    save_checkpoint(s.run_id, s.to_dict())  # 立即落盘计划，前端可秒看「已规划 N 步」

    while _advance_cycle(s):
        save_checkpoint(s.run_id, s.to_dict())
    save_checkpoint(s.run_id, s.to_dict())  # 末轮最终态也落盘
    mark_done(s.run_id)

    # 失败学习：把失败步根因写入共享记忆库（接活理念，绝不破坏反思主流程）
    try:
        _record_failure_memory(task, s.last, tenant_id)
    except Exception:
        pass

    s.last["reflection"] = {
        "attempts": len(s.reflection_log) + 1,  # 总执行轮次
        "exhausted": _needs_reflection(s.last),  # True=达上限仍未达成
        "log": s.reflection_log,
    }
    s.last["run_id"] = s.run_id
    s.last["duration_s"] = round(time.time() - s.start, 1)
    if s.parallel_groups:
        s.last["parallel_groups"] = s.parallel_groups  # 供上层观测「本轮并发了哪些步」
    return s.last


def resume_run(run_id: str) -> Dict[str, Any]:
    """从磁盘 checkpoint 恢复一个中断的自主任务，从最后已完成轮次续跑。

    不重跑已完成的轮次（checkpoint 已保存其成功产出与步骤），只续跑断点之后。
    status 已是 done 却来 resume → 直接返回已存结果，不重跑。
    """
    _maybe_install_default_auditor()  # MEA：让 AuditorGate 在 resume 中同样生效
    snap = load_checkpoint(run_id)
    if not snap:
        return {"error": f"无 checkpoint: {run_id}"}
    s = _RunState.from_dict(snap["state"])
    if snap["status"] == "done":
        s.last.setdefault("run_id", run_id)
        return s.last

    while _advance_cycle(s):
        save_checkpoint(s.run_id, s.to_dict())
    save_checkpoint(s.run_id, s.to_dict())
    mark_done(s.run_id)

    s.last["reflection"] = {
        "attempts": len(s.reflection_log) + 1,
        "exhausted": _needs_reflection(s.last),
        "log": s.reflection_log,
        "resumed": True,
    }
    s.last["run_id"] = s.run_id
    s.last["duration_s"] = round(time.time() - s.start, 1)
    return s.last


# ---- 结构化 Trace（原则 8）----------------------------------------

_TRACE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "_traces")
_TRACE_MAX = 500  # 最多保留 500 条，防磁盘打满


def _build_structured_trace(task, planner, plan_text, steps, data, duration, trace=None):
    """构建符合原则8规范的JSON Trace。"""
    import uuid as _uuid
    raw_trace = trace if trace is not None else data.get("trace", [])
    # 提取memory_recall信息（如果有）
    memory_recall = None
    initial = data.get("initial", {})
    if initial and "memory" in initial:
        recalled = initial.get("memory", [])
        if recalled and isinstance(recalled, list):
            # 计算最高相似度分数
            max_score = 0.0
            for item in recalled:
                if isinstance(item, dict):
                    score = item.get("score", 0.0)
                    if isinstance(score, (int, float)) and score > max_score:
                        max_score = float(score)
            memory_recall = {
                "query": task,
                "similarity": round(max_score, 3),
                "count": len(recalled)
            }
    result = {
        "task_id": str(_uuid.uuid4())[:8],
        "timestamp": datetime.datetime.now().isoformat(),
        "input": {"task": task, "planner": planner, "plan": plan_text},
        "steps": [
            {
                "capability": t.get("capability", s.get("capability", "")),
                "ok": t.get("ok", False),
                "is_real": (t.get("real_metrics") or {}).get("is_real"),
                "real_metrics": t.get("real_metrics"),
                "output": str(
                    t.get("out", t.get("output", t.get("summary", "")))
                )[:500],
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
    if memory_recall:
        result["memory_recall"] = memory_recall
    return result


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

def _score_confidence(data: dict, steps: list, trace: list) -> dict:
    """三级置信度评分（低/中/高）—— 吃**真实指标**，不再数字符串凑数。

    原则 6 落地：输出附带结构化原始指标作为置信参考。
    """
    ok = data.get("ok_steps", 0)
    fail = data.get("failed_steps", 0)
    total = len(steps)
    real_steps = sum(1 for t in trace if (t.get("real_metrics") or {}).get("is_real"))
    search_results = sum(
        (t.get("real_metrics") or {}).get("result_count", 0)
        for t in trace if "search" in (t.get("capability") or "").lower()
    )
    wrote = [
        (t.get("real_metrics") or {}).get("wrote_file")
        for t in trace if (t.get("real_metrics") or {}).get("wrote_bytes", 0) > 0
    ]
    refusals = sum(1 for t in trace if (t.get("real_metrics") or {}).get("refusal"))

    # 三级判定（基于「真实步」占比，而非仅 ok 计数）
    if fail > 0 and real_steps == 0:
        level, label = "low", "🔴 低置信"
    elif total > 0 and real_steps / total >= 0.8 and fail == 0:
        level, label = "high", "🟢 高置信"
    else:
        level, label = "medium", "🟡 中置信"

    return {
        "level": level,
        "label": label,
        "metrics": {
            "ok_steps": ok,
            "failed_steps": fail,
            "total_steps": total,
            "real_steps": real_steps,
            "search_results": search_results,
            "files_written": wrote,
            "refusals": refusals,
            "success_rate": f"{ok/total*100:.0f}%" if total else "N/A",
        },
    }


def _check_goal_relevance(task: str, trace: list, threshold: float = 0.08) -> tuple:
    """检查最终产出与原始目标的相关性（防"每步都成功但方向错了"）。

    策略：从 trace 提取最终产出文本，与任务文本做关键词重叠度打分。
    重叠度低于 threshold → 判定相关性不足（不是"完成"，是"做成了但做错了"）。
    纯本地计算，不调 LLM，零额外延迟。

    Returns: (is_relevant: bool, score: float)
    """
    # 提取最终产出文本
    final_text = ""
    for t in reversed(trace):
        rm = t.get("real_metrics") or {}
        is_real = rm.get("is_real")
        if is_real is None:
            is_real = t.get("real")
        if not (is_real and t.get("ok")):
            continue
        out = t.get("out") or t.get("output") or {}
        if isinstance(out, dict):
            final_text = str(out.get("content") or out.get("output") or "")
        else:
            final_text = str(out)
        if len(final_text.strip()) > 20:
            break
    if not final_text.strip():
        return (True, 1.0)  # 无产出文本可判 → 不拦（交给其他闸门）

    # 分词：任务关键词 vs 产出文本
    task_tokens = _tokenize(task)
    out_tokens = _tokenize(final_text[:2000])
    if not task_tokens:
        return (True, 1.0)
    overlap = len(task_tokens & out_tokens)
    score = overlap / len(task_tokens)
    return (score >= threshold, round(score, 3))


def _verdict(task: str, data: dict, trace: list, confidence: dict) -> dict:
    """求是引擎式完成判定：明确「完成 / 部分完成 / 未完成」，不模棱两可。

    关键：若任务要求产出某文件，验证它是否真实落盘且有内容——
    这是「系统到底有没有真做成」的最终闸门，绝不凭步骤计数谎报。
    """
    fail = data.get("failed_steps", 0)
    real_steps = sum(1 for t in trace if (t.get("real_metrics") or {}).get("is_real"))
    deliverable = _verify_deliverable(task, trace)

    if deliverable.get("requested"):
        if deliverable.get("satisfied"):
            status = "完成 ✅" if fail == 0 else "部分完成 ⚠️（有步骤失败，但产物已真实落盘）"
            reason = ""
        else:
            status = "未完成 ❌"
            reason = (
                f"任务要求产出 {deliverable.get('target')}，但文件"
                f"{'不存在' if not deliverable.get('exists') else '为空'}"
                + ("" if deliverable.get("trace_wrote") else "；且执行 trace 未见真实写入")
            )
        return {"status": status, "deliverable": deliverable, "reason": reason}

    # 无明确产物要求：按真实步占比判定
    if fail == 0 and real_steps > 0:
        # P0 闸门：每步都成功 ≠ 方向对。检查产出与目标的相关性。
        relevant, rel_score = _check_goal_relevance(task, trace)
        if not relevant:
            return {"status": "部分完成 ⚠️", "deliverable": deliverable,
                    "reason": f"所有步骤均成功，但产出与目标相关性低"
                              f"（关键词重叠 {rel_score}），可能方向偏了"}
        return {"status": "完成 ✅", "deliverable": deliverable, "reason": ""}
    if real_steps > 0:
        # 文本型交付物判定：若推理步已产出足够长（>=200字）且与目标相关的实质文本，
        # 即使有其他步空转/失败，也判"完成"——文本型任务（研报/分析/总结）的交付物
        # 就是文本本身，已产出即达成，不应触发不必要的反思循环把文本当代码执行。
        # 修真机验证暴露的 bug：研报任务 LLM 已产出高质量研报，但因第2步空转被判
        # "部分完成"→触发反思→反思产 code_exec 把研报文本当 Bash 执行→死循环。
        has_substantial_text = any(
            (t.get("real_metrics") or {}).get("char_count", 0) >= 200
            and (t.get("real_metrics") or {}).get("is_real")
            and t.get("ok")
            and "inference" in (t.get("capability") or "")
            for t in trace
        )
        if has_substantial_text:
            relevant, rel_score = _check_goal_relevance(task, trace)
            if relevant:
                return {"status": "完成 ✅", "deliverable": deliverable,
                        "reason": f"虽有 {fail} 步空转，但核心推理步已产出实质文本"
                                  f"（{real_steps} 步真实，相关性 {rel_score}）"}
        return {"status": "部分完成 ⚠️", "deliverable": deliverable,
                "reason": f"{fail} 步失败/空转，但 {real_steps} 步有真实产出"}
    return {"status": "未完成 ❌", "deliverable": deliverable,
            "reason": "所有步骤均未产生真实产出（空转/敷衍）"}


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
    v = r.get("verdict", {})
    print(f"判定: {v.get('status', '—')}")
    if v.get("reason"):
        print(f"      ↳ {v.get('reason')}")
    print(f"置信: {r.get('confidence', {}).get('label', '—')}")
    # 反思/重设计闭环可见化（求是引擎式：失败→质疑→重设计→再执行）
    refl = r.get("reflection")
    if refl:
        attempts = refl.get("attempts", 1)
        exhausted = refl.get("exhausted")
        tag = "🔁 经反思自愈达成 ✅" if (attempts > 1 and not exhausted) else (
            "💥 达反思上限仍未达成 ❌" if exhausted else "⏩ 首轮即达成")
        print(f"反思: {tag}（共执行 {attempts} 轮）")
        for log in refl.get("log", []):
            if log.get("action") == "redesign":
                print(f"      ↳ 第{log['cycle']}轮反思：失败步 {log.get('failed')} → 重设计为 {log.get('new_step_count')} 步")
            else:
                print(f"      ↳ 第{log['cycle']}轮：{log.get('reason', '')}")
    print(f"{'='*60}")

    if r.get("plan"):
        print("\n--- AG2 规划 ---")
        for line in r["plan"].split("\n"):
            if line.strip():
                print(f"  {line.strip()}")

    print("\n--- 执行步骤（✅真实 / ⚪空转/no-op / ❌失败）---")
    for i, s in enumerate(r.get("steps", [])):
        cap = s["capability"]
        t = trace[i] if i < len(trace) else {}
        ok = t.get("ok")
        # 真实闸门标记：这步是否真产出了东西（绝不把 no-op 当成 ✅ 成功）
        real = t.get("real_metrics", {}).get("is_real")
        if not ok:
            ok_mark, real_mark = "❌", ""
        elif real is False:
            ok_mark, real_mark = "⚪", "空转/no-op"   # 明确标注，绝不给 ✅
        else:
            ok_mark = "✅"
            real_mark = "🟢真实" if real is True else ""
        # 失败步骤也要把真实错误打印出来（原则 8：可观测，不瞎子摸象）
        detail = t.get("summary") or t.get("error") or t.get("output") or ""
        summary = str(detail).replace("\n", " ")[:140]
        print(f"  {i+1}. [{cap}] {ok_mark}{(' '+real_mark) if real_mark else ''} {summary}")

    final = exe.get("final")
    if final:
        print("\n--- 最终输出 ---")
        print(f"  {final}")

    if r.get("error"):
        print("\n--- 错误 ---")
        print(f"  {r['error']}")


def main() -> None:
    """CLI 入口：python -m kernel.autopilot "<任务描述>"

    环境要求：
      - .env 中 ZHIPU_API_KEY 已配置（规划/反思默认走智谱直连，无需 ag2/ollama）
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
