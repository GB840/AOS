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
from typing import Any, Dict, List, Tuple

# 步骤语义关键词 -> capability 候选（按优先级）。解析时取「当前通电能力中
# 最靠前匹配」的那个，保证编排到的引擎一定 live。
# 顺序约定：**意图/动作动词在前，媒体名词在后**——否则 "search ... photo"
# 会被 "photo" 误命中成 media.image。动作动词（search/find/run/send/write…）
# 代表用户真实意图，应优先于媒体类型名词（image/photo/video）。
_KEYWORD_CAP_MAP: List[Tuple[str, str]] = [
    # 复合短语优先（解决单字歧义："写代码"=生成 vs "执行代码"=执行）
    ("写代码打印", "action.code_exec"),
    ("写代码执行", "action.code_exec"),
    ("写代码运行", "action.code_exec"),
    ("写一段代码并执行", "action.code_exec"),
    ("生成代码并执行", "action.code_exec"),
    ("写代码", "inference.llm"),
    ("写一段", "inference.llm"),
    ("生成代码", "inference.llm"),
    ("编写代码", "inference.llm"),
    ("编写", "inference.llm"),
    ("改成", "inference.llm"),
    ("修改代码", "inference.llm"),
    ("改写", "inference.llm"),
    ("重构", "inference.llm"),
    # 动作 / 意图（动词）优先
    ("search", "web.search"),
    ("web", "web.search"),
    ("fetch", "web.fetch"),
    ("browse", "action.aci"),
    ("find", "web.search"),
    ("click", "action.aci"),
    ("navigate", "action.aci"),
    ("code", "action.code_exec"),
    ("exec", "action.code_exec"),
    ("script", "action.code_exec"),
    ("run", "action.code_exec"),
    ("compile", "action.code_exec"),
    ("read file", "action.file_access"),
    ("write file", "action.file_access"),
    ("open file", "action.file_access"),
    ("list file", "action.file_access"),
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
    ("读取链接", "web.fetch"),
    ("读网页", "web.fetch"),
    ("打开链接", "web.fetch"),
    ("抓取", "web.fetch"),
    ("链接", "web.fetch"),
    ("代码", "action.code_exec"),
    ("执行", "action.code_exec"),
    ("运行", "action.code_exec"),
    ("脚本", "action.code_exec"),
    ("读文件", "action.file_access"),
    ("写文件", "action.file_access"),
    ("打开文件", "action.file_access"),
    ("保存文件", "action.file_access"),
    ("列目录", "action.file_access"),
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
_TAG_RE = re.compile(r"\[([a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+)\]")
# AG2 输出形如 `N. [tool] <what to do>`：尖括号是格式分隔符，内部才是真实指令，
# 需**提取内部**而非整段删除（否则指令会丢）。
_ANGLE_RE = re.compile(r"<[^>]*>")
_ANGLE_INNER_RE = re.compile(r"<(.*?)>", re.S)


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


def _split_cap_prefix(txt: str, available_caps: List[str]):
    """从 `capname = ` / `capname: ` 前缀提取能力名（ag2 显式标注）。

    AG2 规划常产出 `web.search = search "..."` / `inference.llm = analyze ...`
    这类带能力前缀的步骤。前缀即真实意图，比关键词推断可靠——否则
    "analyze search results" 会被 "search" 误命中成 web.search。
    仅当前缀确为可用能力时才采纳，避免误吞普通文本。返回 (cap_or_None, body)。
    """
    m = re.match(r"^\s*([a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+)\s*[=:]\s*", txt, re.I)
    if m and m.group(1).lower() in available_caps:
        return m.group(1).lower(), txt[m.end():].strip()
    return None, txt


def parse_plan_to_steps(plan_text: str, available_caps: List[str]) -> List[Dict[str, Any]]:
    """把自然语言 plan 文本解析成 OrchestrationChiplet 的 steps[]。

    - 优先从 AG2 显式标注的 `cap = ` 前缀提取能力（最可靠）；
    - 兜底按语义关键词映射（可用能力必须 live，不会编排到不存在的引擎）；
    - 首步入参带 task 原文，后续步 in_from=previous 串成流水线；
    - 兜底保证至少一步（不会因解析失败让流水线空转）。
    """
    steps_text = _extract_steps(plan_text)
    if not steps_text:
        steps_text = [plan_text]
    steps: List[Dict[str, Any]] = []
    for i, txt in enumerate(steps_text):
        # 优先从 ag2 显式前缀 `<cap> = ` / `<cap>: ` 提取能力（ag2 已标注，
        # 比关键词推断可靠；避免 "analyze search results" 误命中 web.search）。
        cap, body = _split_cap_prefix(txt, available_caps)
        if cap is None:
            cap = _pick_capability(txt, available_caps)
            body = txt
        # 再剥 [cap] 标签（兜底兼容 N. [web.search] <...> 形式）
        body = _TAG_RE.sub("", body).strip(" .;-").strip()
        # 处理 <...>：仅当整段被 <...> 包裹（AG2 格式分隔符）才提取内部；
        # 若 <...> 只是命令里的内联占位符（如 `echo <version>`），保留原样，
        # 交由 autopilot._fill_placeholders 从上游文本填值（不丢、不伪造）。
        if re.fullmatch(r"<[^>]*>", body):
            clean = body[1:-1].strip()
        else:
            clean = body
        if i == 0:
            steps.append({"capability": cap, "in": {"task": clean}})
        else:
            # in_from: previous 时也保留 clean 指令作 fallback——
            # 如果上一步输出是不可执行文本（如搜索结果），
            # 下游可用 clean 覆盖之（如 code_exec 拿 ag2 给出的 winget install 命令）
            steps.append({"capability": cap, "in_from": "previous", "instruction": clean})
    return steps


def _bridge_prompt(prev_cap: str, next_cap: str, next_task: str) -> str:
    """为 LLM 桥接步生成上下文感知的 prompt。

    当前后两步能力不同（如搜索→代码执行），中间需要 LLM 把上游产出
    转换成下游可消费的输入（如搜索结果→Python 代码）。
    """
    if next_cap == "action.code_exec":
        return (f"根据以上结果，写一段Python代码来完成以下任务：{next_task}。"
                f"从上游结果中提取关键数据（如版本号、名称、数值等），用代码处理或打印。"
                f"只输出```python代码块```，不要多余解释。")
    if next_cap == "channel.access":
        return f"根据以上结果，撰写一条要发送的消息，主题：{next_task}"
    if next_cap == "memory.semantic":
        return f"根据以上结果，提取要记忆的关键信息：{next_task}"
    if next_cap == "media.image":
        return f"根据以上结果，生成一段英文图像描述提示词：{next_task}"
    if next_cap == "media.video":
        return f"根据以上结果，生成一段视频描述提示词：{next_task}"
    if next_cap == "web.search":
        return f"根据以上结果，提取一个简洁的搜索关键词：{next_task}"
    if next_cap == "web.fetch":
        return f"根据以上结果，提取一个最相关的URL链接（只要URL本身）：{next_task}"
    if next_cap == "action.file_access":
        return f"根据以上结果，生成文件操作指令（格式：action=read/write/list, path=文件路径, content=内容）：{next_task}"
    return f"根据以上结果，为以下任务生成具体内容：{next_task}"


def heuristic_plan(task: str, available_caps: List[str]) -> List[Dict[str, Any]]:
    """纯本地规划（无 LLM）：把任务按语义/连词拆成步骤，映射到通电能力。

    当 AG2 不可用（无 key / 未安装 / 调用失败）时作为降级 planner，保证
    run_task 端到端仍可跑通——证明「think→do」闭环的 machinery 不依赖外部 LLM。

    桥接增强：当连续两步能力不同（如搜索→代码执行）且 inference.llm 通电时，
    自动在中间插入一个 LLM 推理步骤，把上游产出转换成下游可消费的输入。
    这是「想」的接缝——没有它，搜索结果直接喂给代码执行器会因提取不到代码而失败。
    """
    parts = re.split(
        r"(?:,\s*|\s*，\s*|\s*、\s*|\bthen\b|\band then\b|\bafter that\b|\bnext\b"
        r"|并|然后|接着|之后再|随后)",
        task, flags=re.I)
    parts = [p.strip(" .;") for p in parts if len(p.strip()) > 1]
    if not parts:
        parts = [task]

    # 先把每段映射到能力，再决定是否插入桥接
    part_caps = [(p, _pick_capability(p, available_caps)) for p in parts]
    has_llm = "inference.llm" in available_caps

    steps: List[Dict[str, Any]] = []
    for i, (p, cap) in enumerate(part_caps):
        if i == 0:
            steps.append({"capability": cap, "in": {"task": p}})
        else:
            prev_cap = part_caps[i - 1][1]
            # 能力不同 + LLM 可用 → 插入桥接推理步
            # 例外：下游是 action.code_exec 且上游是 inference.llm 时不插桥接——
            # CodeExecutionAdapter 自带 _extract_code 能从 LLM 输出提取代码，
            # 桥接反而会让 LLM 重新生成代码（可能引入 bug）。
            # 但上游是 web.search 等非 LLM 源时仍需桥接（搜索结果不是代码，
            # 需要 LLM 基于搜索结果生成代码）。
            skip_bridge = (cap == "action.code_exec" and prev_cap == "inference.llm")
            if prev_cap != cap and has_llm and not skip_bridge:
                steps.append({
                    "capability": "inference.llm",
                    "in_from": "previous",
                    "prompt": _bridge_prompt(prev_cap, cap, p),
                })
            steps.append({"capability": cap, "in_from": "previous"})
    return steps
