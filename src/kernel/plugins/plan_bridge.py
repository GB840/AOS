"""把自然语言 plan 桥接成 OrchestrationChiplet 的 steps[]。

这是「think→do」闭环的接缝：AG2 / cognition.planning 返回的是**自由文本**
计划，而编排芯粒（OrchestrationChiplet）需要**结构化 steps[]**。本模块负责
把文本解析成有序步骤，并把每步语义映射到 AOS 当前通电的能力，保证编排到的
引擎一定 live——不会因解析出「不存在的能力」导致整条流水线崩。

设计要点（对应视频观点的落地）：
  - 逻辑上分工（每步不同 capability）被保留；
  - 物理上仍是内核经统一 route() 调度（故障隔离照样生效），不是自治多 Agent；
  - 不依赖外部 LLM 也能跑（heuristic 降级），murdercycle 不死。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

# 步骤语义关键词 -> capability 候选（按优先级）。解析时取「当前通电能力中
# 最靠前匹配」的那个，保证编排到的引擎一定 live。
# 顺序约定：**意图/动作动词在前，媒体名词在后**——否则 "search ... photo"
# 会被 "photo" 误命中成 media.image。动作动词（search/find/run/send/write…）
# 代表用户真实意图，应优先于媒体类型名词（image/photo/video）。
_KEYWORD_CAP_MAP: List[Tuple[str, str]] = [
    # 动作 / 意图（动词）优先
    ("search", "web.search"),
    ("web", "web.search"),
    ("browse", "action.aci"),
    ("find", "web.search"),
    ("click", "action.aci"),
    ("navigate", "action.aci"),
    ("code", "action.code_exec"),
    ("exec", "action.code_exec"),
    ("script", "action.code_exec"),
    ("run", "action.code_exec"),
    ("compile", "action.code_exec"),
    ("send", "channel.access"),
    ("message", "channel.access"),
    ("notify", "channel.access"),
    ("reply", "channel.access"),
    ("chat", "channel.access"),
    ("post", "channel.access"),
    # 中文动作 / 意图（动词）优先，与英文动词同组、同优先级约定
    ("搜索", "web.search"),
    ("查", "web.search"),
    ("找", "web.search"),
    ("浏览", "action.aci"),
    ("网页", "web.search"),
    ("代码", "action.code_exec"),
    ("执行", "action.code_exec"),
    ("运行", "action.code_exec"),
    ("脚本", "action.code_exec"),
    ("发送", "channel.access"),
    ("消息", "channel.access"),
    ("通知", "channel.access"),
    ("回复", "channel.access"),
    ("聊天", "channel.access"),
    ("发布", "channel.access"),
    ("记住", "memory.semantic"),
    ("存储", "memory.semantic"),
    ("保存", "memory.semantic"),
    ("知识", "memory.knowledge"),
    ("记忆", "memory.semantic"),
    ("回忆", "memory.semantic"),
    ("推理", "cognition.reasoning"),
    ("思考", "cognition.reasoning"),
    ("分析", "cognition.reasoning"),
    ("规划", "cognition.planning"),
    ("总结", "inference.llm"),
    ("写", "inference.llm"),
    ("起草", "inference.llm"),
    ("文本", "inference.llm"),
    ("回答", "inference.llm"),
    ("解释", "inference.llm"),
    ("翻译", "inference.llm"),
    ("remember", "memory.semantic"),
    ("store", "memory.semantic"),
    ("save", "memory.semantic"),
    ("knowledge", "memory.knowledge"),
    ("memory", "memory.semantic"),
    ("recall", "memory.semantic"),
    ("reason", "cognition.reasoning"),
    ("think", "cognition.reasoning"),
    ("analyze", "cognition.reasoning"),
    ("plan", "cognition.planning"),
    ("summar", "inference.llm"),
    ("write", "inference.llm"),
    ("draft", "inference.llm"),
    ("text", "inference.llm"),
    ("answer", "inference.llm"),
    ("explain", "inference.llm"),
    ("translate", "inference.llm"),
    # 媒体类型名词（生成意图）放最后
    ("image", "media.image"),
    ("picture", "media.image"),
    ("draw", "media.image"),
    ("paint", "media.image"),
    ("photo", "media.image"),
    ("video", "media.video"),
    ("movie", "media.video"),
    ("clip", "media.video"),
    # 中文媒体类型名词（生成意图）放最后，与英文媒体同组
    ("图片", "media.image"),
    ("图", "media.image"),
    ("画", "media.image"),
    ("绘制", "media.image"),
    ("照片", "media.image"),
    ("视频", "media.video"),
    ("影片", "media.video"),
]

# 兜底：没有任何关键词命中时映射到的通用能力（需当前通电）。
_FALLBACK_CAP = "inference.llm"

# AG2 规划器产出的能力标签，如 [web.search] / [media.image]
_TAG_RE = re.compile(r"\[([a-z][a-z0-9]*(?:\.[a-z0-9]+)+)\]")


def _pick_capability(step_text: str, available: List[str]) -> str:
    # 优先认 AG2 明确给出的能力标签（如 [web.search]），最贴合规划意图。
    m = _TAG_RE.search(step_text)
    if m and m.group(1) in available:
        return m.group(1)
    low = step_text.lower()
    for kw, cap in _KEYWORD_CAP_MAP:
        if kw in low and cap in available:
            return cap
    if _FALLBACK_CAP in available:
        return _FALLBACK_CAP
    # 关键词都不在可用能力里 → 取可用能力的第一个，至少不让流水线空转。
    return available[0] if available else _FALLBACK_CAP


def _extract_steps(plan_text: str) -> List[str]:
    """从自由文本计划里提取有序步骤句。

    支持 AG2 group.chat 常见输出形态：
      - 编号：1. / 1) / Step 1: / Task 1: / Step 1 -
      - 序号词：First: / Second: / Finally: / Next:
      - 无序：- / * / •
    匹配不到任何编号行时退化为按句子/换行切（保底不空转）。
    """
    lines = [ln.strip() for ln in plan_text.splitlines() if ln.strip()]
    steps: List[str] = []
    pat = re.compile(
        r"^(?:step\s*\d+[\.:]?|task\s*\d+[\.:]?|\d+[\.\)]|[-*•]\s+"
        r"|(?:first|second|third|fourth|fifth|next|then|finally|last)[\:\s-]+)"
        r"\s*(.*)$", re.I)
    for ln in lines:
        m = pat.match(ln)
        if m:
            body = m.group(1).strip().strip("-*•").strip()
            if body:
                steps.append(body)
    if not steps:
        # 没匹配到编号行 → 退化按句子/换行切。
        chunks = re.split(r"(?:\n+|\.\s+|\;\s+)", plan_text)
        steps = [c.strip(" .;-") for c in chunks if len(c.strip()) > 4]
    return steps


def parse_plan_to_steps(plan_text: str, available_caps: List[str]) -> List[Dict[str, Any]]:
    """把自然语言 plan 文本解析成 OrchestrationChiplet 的 steps[]。

    - 每步按语义关键词映射到当前通电能力（available_caps）；
    - 首步入参带 task 原文，后续步 in_from=previous 串成流水线；
    - 兜底保证至少一步（不会因解析失败让流水线空转）。
    """
    steps_text = _extract_steps(plan_text)
    if not steps_text:
        steps_text = [plan_text]
    steps: List[Dict[str, Any]] = []
    for i, txt in enumerate(steps_text):
        cap = _pick_capability(txt, available_caps)
        # 剥掉 AG2 明确给出的 [cap] 标签，避免把标签泄漏进下游 step 的入参。
        clean = _TAG_RE.sub("", txt).strip(" .;-").strip()
        if i == 0:
            steps.append({"capability": cap, "in": {"task": clean}})
        else:
            steps.append({"capability": cap, "in_from": "previous"})
    return steps


def heuristic_plan(task: str, available_caps: List[str]) -> List[Dict[str, Any]]:
    """纯本地规划（无 LLM）：把任务按语义/连词拆成步骤，映射到通电能力。

    当 AG2 不可用（无 key / 未安装 / 调用失败）时作为降级 planner，保证
    run_task 端到端仍可跑通——证明「think→do」闭环的 machinery 不依赖外部 LLM。
    """
    parts = re.split(
        r"(?:,\s*|\s*，\s*|\s*、\s*|\bthen\b|\band then\b|\bafter that\b|\bnext\b"
        r"|并|然后|接着|之后再|随后)",
        task, flags=re.I)
    parts = [p.strip(" .;") for p in parts if len(p.strip()) > 1]
    if not parts:
        parts = [task]
    steps: List[Dict[str, Any]] = []
    for i, p in enumerate(parts):
        cap = _pick_capability(p, available_caps)
        if i == 0:
            steps.append({"capability": cap, "in": {"task": p}})
        else:
            steps.append({"capability": cap, "in_from": "previous"})
    return steps
