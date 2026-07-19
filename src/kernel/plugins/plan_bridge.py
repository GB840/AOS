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
    ("汇总", "inference.llm"),
    ("归纳", "inference.llm"),
    ("概括", "inference.llm"),
    ("整理", "inference.llm"),
    ("生成报告", "inference.llm"),
    ("写报告", "inference.llm"),
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


def _pick_capability_explicit(step_text: str, available: List[str]) -> Tuple[str, bool]:
    """选能力并返回 (cap, matched)。

    matched=True 表示由 [标签] 或关键词**显式命中**；False 表示落到兜底
    （_FALLBACK_CAP 或 available[0]）。并行规划的「列举继承」需要区分这两种情况：
    "搜索A、B、C" 里 "B"/"C" 无动词会落兜底，应继承前一段的 web.search 而非当真。
    """
    # 优先认 AG2 明确给出的能力标签（如 [web.search]），最贴合规划意图。
    m = _TAG_RE.search(step_text)
    if m and m.group(1) in available:
        return m.group(1), True
    low = step_text.lower()
    for kw, cap in _KEYWORD_CAP_MAP:
        if kw in low and cap in available:
            return cap, True
    if _FALLBACK_CAP in available:
        return _FALLBACK_CAP, False
    # 关键词都不在可用能力里 → 取可用能力的第一个，至少不让流水线空转。
    return (available[0] if available else _FALLBACK_CAP), False


def _pick_capability(step_text: str, available: List[str]) -> str:
    """选能力（薄封装，保持既有调用方行为完全不变）。"""
    return _pick_capability_explicit(step_text, available)[0]


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


# ————————————————————————————————————————————————————————————————
# 依赖感知并行规划（opt-in，对齐九大理念之「不手配自闭环」+ 铁律「拿不准就串行」）
# ————————————————————————————————————————————————————————————————
#
# 背景：OrchestrationChiplet 早已内置并发引擎（_invoke_parallel + ThreadPoolExecutor），
# 但既有规划器（heuristic_plan / parse_plan_to_steps）永远产出 in_from:previous 线性链、
# 从不产出 parallel_groups → 并发引擎 100% 闲置、系统只会串行干活。本模块补上「规划→分组」
# 这一段，让独立子任务能被识别成 parallel_groups 真正并发。
#
# 引擎约束（决定检测策略，必须遵守，否则会打乱执行顺序或引发竞态）：
#   1. 并发组内步骤共享 state，若用 in_from:previous 会在 state.last_success_out 上竞态
#      → 并行步必须自带独立 in:{task}（无上游依赖才能安全并发）。
#   2. 引擎「先跑所有并行组、再顺序补跑未覆盖步」→ 并行组必须覆盖【从0起的连续前缀】，
#      否则前缀里的顺序步会被挪到并行组之后执行，破坏先后语义。
#
# 保守纪律（宁串勿并）：仅当能从任务里拆出 ≥2 个「同能力、相邻、以并列/列举连词分隔
# （非顺序连词）、且能力属并行安全类」的独立子任务时才并行；拿不准一律 parallel_groups=None
# 完全退回既有串行语义（零回归）。

# 并行安全能力白名单：无副作用、可独立并发的只读/生成类能力。
# 有副作用或强顺序性的能力（代码执行/文件写/消息发送/浏览器动作）一律不并行。
_PARALLEL_SAFE_CAPS = {
    "web.search", "web.fetch", "inference.llm",
    "memory.semantic", "memory.knowledge",
    "cognition.reasoning", "media.image", "media.video",
}

# 顺序连词（表示步骤间有先后依赖，绝不并行）。用于分类边界。
_SEQ_CONNECTIVES = {
    "然后", "接着", "之后再", "随后", "之后",
    "and then", "after that", "afterwards", "then", "next", "finally",
}

# 收尾/汇总结束类动词：语义上必须吃前序结果、放在最后，绝不并入并行组。
# 即便前面以「并/并且/and」连接，也强制为顺序步（如「搜索A、B、C 并汇总」→ 汇总顺序）。
_FINALIZE_VERBS = ("汇总", "总结", "归纳", "概括", "整理", "生成报告", "写报告", "输出报告")

# 列举量词尾巴（如「三个主题」「这几个」），拼到末项搜索词上无意义，剥掉让查询干净。
_QUANTIFIER_RE = re.compile(r"(三个主题|这几个主题|这些主题|三个问题|几个方面|相关内容)$")

# 边界分词：捕获顺序 + 并列两类连词。**长词在前**（"之后再">"之后"、
# "and then">"and"、"并行地">"并行">"并且">"并"），避免被短词抢先匹配。
_BOUNDARY_RE = re.compile(
    r"("
    # —— 顺序连词（先后依赖）——
    r"然后|接着|之后再|随后|之后"
    r"|\band then\b|\bafter that\b|\bafterwards\b|\bthen\b|\bnext\b|\bfinally\b"
    # —— 并列/列举连词（相互独立）——
    r"|同时|分别|并行地|并行|并且"
    r"|、|，|,"
    r"|\bin parallel\b|\bsimultaneously\b|\bconcurrently\b|\bas well as\b"
    r"|\band\b|并"
    r")",
    re.I,
)

# ag2 规划器可选追加一行 `PARALLEL: 1,3` 声明可并发步号（1-based）。
_PARALLEL_LINE_RE = re.compile(r"^\s*PARALLEL\s*[:：]\s*(.+)$", re.I | re.M)


def _boundary_kind(sep: str) -> str:
    """把捕获到的连词分类为 'seq'（顺序依赖）或 'par'（并列独立）。"""
    return "seq" if sep.strip().lower() in _SEQ_CONNECTIVES else "par"


def _split_with_boundaries(task: str) -> List[Dict[str, Any]]:
    """按连词切分任务，保留每段之前的边界类型。

    返回 [{"text": 段文本, "kind": None/'seq'/'par'}, ...]（首段 kind=None）。
    跨越被丢弃的极短段合并边界时，seq 优先（更保守：只要有先后语义就当依赖）。
    """
    raw = _BOUNDARY_RE.split(task)
    parts: List[Dict[str, Any]] = []
    pending_kind: Any = None
    for i, tok in enumerate(raw):
        if i % 2 == 1:  # 分隔符
            k = _boundary_kind(tok)
            pending_kind = "seq" if (pending_kind == "seq" or k == "seq") else "par"
            continue
        text = (tok or "").strip(" .;，。、\t")
        text = _QUANTIFIER_RE.sub("", text).strip(" .;，。、\t")
        if not text:
            # 仅跳过空/纯标点碎片；单字列举项（如 "搜索A、B、C" 里的 B/C）是合法步骤
            continue
        # 收尾动词（汇总/总结…）强制顺序步：必须吃前序结果、放最后，不进并行组。
        kind = "seq" if any(v in text for v in _FINALIZE_VERBS) else pending_kind
        parts.append({"text": text, "kind": kind})
        pending_kind = None
    return parts


def _assign_caps(parts: List[Dict[str, Any]], available: List[str]) -> List[str]:
    """给每段分配能力，支持「列举继承」：并列连词后、本段无显式动词（落兜底）
    且上一段是并行安全能力时，继承上一段能力（如 搜索A、B、C → 三段都 web.search）。
    """
    caps: List[str] = []
    for i, p in enumerate(parts):
        cap, matched = _pick_capability_explicit(p["text"], available)
        if (i > 0 and p["kind"] == "par" and not matched
                and caps[i - 1] in _PARALLEL_SAFE_CAPS):
            cap = caps[i - 1]
        caps.append(cap)
    return caps


def plan_with_parallelism(
    task: str, available_caps: List[str]
) -> Tuple[List[Dict[str, Any]], Any]:
    """本地并行规划（无 LLM）：返回 (steps, parallel_groups)。

    parallel_groups=None 表示完全串行（退回 heuristic_plan 既有语义，零回归）。
    仅识别「从第0段起、以并列连词相连、同能力、并行安全」的最长前缀游程作为一个
    并行组；其余段保持顺序（in_from:previous + 可选桥接推理步）。
    """
    parts = _split_with_boundaries(task)
    if len(parts) < 2:
        return heuristic_plan(task, available_caps), None

    caps = _assign_caps(parts, available_caps)
    base_cap = caps[0]

    # 找从第0段起的最长「并列 + 同能力 + 并行安全」前缀游程
    run_len = 1
    if base_cap in _PARALLEL_SAFE_CAPS:
        for i in range(1, len(parts)):
            if parts[i]["kind"] == "par" and caps[i] == base_cap:
                run_len += 1
            else:
                break

    if run_len < 2:
        # 拆不出 ≥2 个独立同能力步 → 完全退回既有串行规划（零回归）
        return heuristic_plan(task, available_caps), None

    steps: List[Dict[str, Any]] = []
    # 前 run_len 段：独立并行步，各自带 in:{task}（无 in_from 依赖，杜绝并发竞态）
    for i in range(run_len):
        steps.append({"capability": caps[i], "in": {"task": parts[i]["text"]}})
    # 余部：与既有串行语义一致（in_from:previous + 可选桥接）
    has_llm = "inference.llm" in available_caps
    for i in range(run_len, len(parts)):
        cap = caps[i]
        prev_cap = caps[i - 1]
        skip_bridge = (cap == "action.code_exec" and prev_cap == "inference.llm")
        if prev_cap != cap and has_llm and not skip_bridge:
            steps.append({
                "capability": "inference.llm",
                "in_from": "previous",
                "prompt": _bridge_prompt(prev_cap, cap, parts[i]["text"]),
            })
        steps.append({"capability": cap, "in_from": "previous"})

    return steps, [list(range(run_len))]


def _extract_parallel_line(plan_text: str, n_steps: int) -> Any:
    """从 ag2 计划文本解析 `PARALLEL: 1,3` 声明为 0-based 并行组。

    严格校验：步号在范围内、每组 ≥2 步、且所有并行步合起来必须构成【从0起的
    连续前缀】（引擎约束）。任一不满足 → 返回 None（保守退回串行）。
    """
    groups: List[List[int]] = []
    for m in _PARALLEL_LINE_RE.finditer(plan_text):
        idxs: List[int] = []
        for tok in re.split(r"[,\s、，]+", m.group(1).strip()):
            tok = tok.strip()
            if tok.isdigit():
                v = int(tok) - 1  # ag2 用 1-based 步号
                if 0 <= v < n_steps:
                    idxs.append(v)
        seen: set = set()
        clean: List[int] = []
        for v in idxs:
            if v not in seen:
                seen.add(v)
                clean.append(v)
        if len(clean) >= 2:
            groups.append(clean)
    if not groups:
        return None
    covered = sorted({i for g in groups for i in g})
    if covered != list(range(len(covered))):
        # 非「从0起连续前缀」→ 引擎会把前缀顺序步挪到并行组之后，破坏语义 → 弃用
        return None
    return groups


def parse_plan_with_parallelism(
    plan_text: str, available_caps: List[str]
) -> Tuple[List[Dict[str, Any]], Any]:
    """解析 ag2 计划文本为 (steps, parallel_groups)，支持 `PARALLEL:` 声明。

    parallel_groups=None 表示串行（无 PARALLEL 行或声明不合法时，零回归）。
    被并行组覆盖的步会把 in_from:previous 改成独立 in:{task}（消除并发竞态）。
    """
    steps = parse_plan_to_steps(plan_text, available_caps)
    groups = _extract_parallel_line(plan_text, len(steps))
    if not groups:
        return steps, None
    covered = {i for g in groups for i in g}
    for i in covered:
        st = steps[i]
        if "in_from" in st:
            instr = st.get("instruction") or st.get("prompt") or ""
            steps[i] = {"capability": st["capability"], "in": {"task": instr}}
    return steps, groups
