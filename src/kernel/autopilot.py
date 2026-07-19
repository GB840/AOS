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


# ---- ⑤ 融合 FabricHub 单一内核路由（opt-in）---------------------------
# 默认关闭：autopilot 仍走自有惰性适配器单例，保留「零依赖 FabricHub 全量构造」
# 的快启动设计（见模块 docstring）。设 AOS_AUTOPILOT_USE_FABRICHUB=1 时，所有
# 真实适配器调用改经 FabricHub.route() 统一派发——统一能力路由 / 运行时故障转移
# / 策略边界（理念5），消除「autopilot 绕开 FabricHub 自成一路」的双轨债。
# 两种路径最终命中同一底层适配器，返回 InvokeResult(.data 同构)，故 autopilot
# 的真实闸门 / 量化指标逻辑无需改动即可作用于两条路径。
_AUTOPILOT_USE_HUB = os.environ.get("AOS_AUTOPILOT_USE_FABRICHUB", "0") == "1"
_HUB = None


def _get_hub():
    """返回 FabricHub 单例（opt-in）；未启用时返回 None（走本地适配器）。"""
    global _HUB
    if not _AUTOPILOT_USE_HUB:
        return None
    if _HUB is None:
        from kernel.plugins.fabric_hub import get_fabric_hub
        _HUB = get_fabric_hub()
    return _HUB


def _dispatch(capability: str, payload: Dict[str, Any]) -> Any:
    """真实适配器调用：opt-in 经 FabricHub 单一内核路由，否则走本地惰性适配器。

    两种路径最终都命中同一底层适配器，返回 InvokeResult(.data 同构)；
    autopilot 的真实闸门 / 量化指标逻辑因此无需改动即可作用于两条路径。
    """
    hub = _get_hub()
    if hub is not None:
        # cognition.* 在 hub 注册表里统一归到 inference.llm 派发
        cap = "inference.llm" if capability in ("cognition.reasoning", "cognition.planning") else capability
        return hub.route(cap, payload)
    # 本地兜底（默认）：保持零依赖 FabricHub 全量构造的快启动设计
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
# 默认零足迹（opt-in）：AOS_AUTOPILOT_DISTILL=1 才喂本地蒸馏器；若已走 FabricHub
# 路由（AOS_AUTOPILOT_USE_FABRICHUB=1）则直接复用其蒸馏器，不另起炉灶（理念4/8）。
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
    # 1) 优先复用 FabricHub 已在路由热路径喂好的蒸馏器（零额外开销）
    if os.environ.get("AOS_AUTOPILOT_USE_FABRICHUB") == "1":
        try:
            from kernel.plugins.fabric_hub import get_fabric_hub
            hb = get_fabric_hub()
            if hb is not None and getattr(hb, "_distiller", None) is not None:
                _DISTILLER = hb._distiller
                return _DISTILLER
        except Exception:
            logger.warning("获取 FabricHub 蒸馏器失败，退回本地", exc_info=True)
    # 2) opt-in 本地蒸馏器：仅 AOS_AUTOPILOT_DISTILL=1 才落盘（默认零足迹）
    if os.environ.get("AOS_AUTOPILOT_DISTILL") == "1":
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
    from typing import Tuple
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
    from core.fabric.adapter import InvokeRequest

    # 派发边界策略校验（理念6 诚实：让 PolicyEngine 在真实路径上具有约束力）。
    # 默认审计模式仅记录；设 AOS_POLICY_ENFORCE=1 时命中 deny 规则即阻断，
    # 不会误伤可信 system 体的合法 code_exec（r010 已放行）。
    verdict = check_capability(capability, actor="system")
    if not verdict["allowed"] and policy_enforce_enabled():
        return InvokeResult(
            ok=False,
            error=f"autopilot: 策略拒绝 {capability}（{verdict['matched_rule']}：{verdict['reason']}）",
        )

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


def _plan(task: str, planner: str):
    """规划一次：返回 (plan_text, steps, used_planner)。ag2 不可用透明降级 heuristic。"""
    from core.fabric.adapter import InvokeRequest, InvokeResult
    from core.fabric.capability import Capability
    from kernel.plugins.plan_bridge import parse_plan_to_steps, heuristic_plan

    plan_text: Optional[str] = None
    steps: List[Dict[str, Any]] = []
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
                        steps = parse_plan_to_steps(plan_text, _CAPS)
        except Exception:
            logger.warning("ag2 规划失败，降级 heuristic", exc_info=True)

    if not steps:
        steps = heuristic_plan(task, _CAPS)
        used_planner = "heuristic"
        plan_text = None
    return plan_text, steps, used_planner


def _execute(task: str, steps: List[Dict[str, Any]], seed_context: Optional[Dict[str, Any]] = None):
    """执行一轮步骤（每轮新建 OrchestrationChiplet，保证上下文干净）。

    返回 (exe_res, recorded)：recorded 是本轮回所有「成功步」的真实产出
    （capability + 完整 out），供跨轮上下文续接与反思记忆使用。
    seed_context：上轮已成功步的真实产出，作为本轮首步的 in_from:previous 起点
    （求是引擎式反思：保留成功经验、只重设计失败处之后的下一步，不重跑、不回归）。
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
        # 因果反思闭环：把每步真实成败+引擎喂进白盒蒸馏器（opt-in）
        _feed_distiller(capability, res)
        return res

    oc = OrchestrationChiplet(route_fn=_rec_route)
    payload = {"initial": {"task": task}, "steps": steps}
    if seed_context:
        payload["seed_context"] = seed_context
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
                return _finalize_reflect(task, failed, text.strip(), steps, "ag2",
                                         causal_hints=causal_hints)
    except Exception as e:  # noqa: BLE001
        logger.warning("反思 ag2 失败，降级 ollama: %s", e)
    # 2) 本地 ollama（ag2 dead / 无 key 时的真实 LLM 反思后端）
    try:
        text = _ollama_generate(prompt)
        steps = parse_plan_to_steps(text, _CAPS) if text else []
        if steps:
            _attach_engine_hints(steps, causal_hints)
            return _finalize_reflect(task, failed, text.strip(), steps, "ollama",
                                     causal_hints=causal_hints)
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

    ag2 不可用时的反思降级后端——本机 ollama 已装 minicpm-mem / minicpm5-1b
    等 1.1B 小模型，推理快、零远程 key。超时 30s 防挂死；失败抛异常交上层降级。
    """
    import json as _json
    import urllib.request
    model = model or os.environ.get("AOS_REFLECT_OLLAMA_MODEL", "minicpm-mem:latest")
    url = os.environ.get("AOS_OLLAMA_URL", "http://localhost:11434/api/generate")
    body = _json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.3, "num_predict": 300},
    }).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=25) as resp:
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
                    "ok": t.get("ok"),
                    "real": (t.get("real_metrics") or {}).get("is_real"),
                    "summary": str(t.get("summary") or t.get("error") or t.get("out") or t.get("output") or "")[:200],
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
    h = hashlib.md5((task + str(time.time())).encode("utf-8")).hexdigest()[:12]
    return f"run_{h}"


class _RunState:
    """autopilot.run() 的可序列化状态容器（进程级 → 落盘 checkpoint）。

    把原本散在 run() 局部变量里的 task/steps/prior_success/reflection_log/cycle
    收拢成一个对象，使其能被 sqlite 持久化并在 resume_run 时完整还原。
    """

    def __init__(self, task: str, planner: str, plan_text: str, steps, max_reflect: int = None, per_run_id: str = ""):
        self.task = task
        self.planner = planner
        self.plan_text = plan_text
        self.steps = steps
        self.prior_success: list = []
        self.reflection_log: list = []
        self.last: dict = {}
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
            "prior_success": self.prior_success,
            "reflection_log": self.reflection_log,
            "last": self.last,
            "cycle": self.cycle,
            "start": self.start,
            "max_reflect": self.max_reflect,
            "per_run_id": self.per_run_id,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "_RunState":
        s = cls(d["task"], d["planner"], d["plan_text"], d["steps"], max_reflect=d.get("max_reflect"), per_run_id=d.get("per_run_id", ""))
        s.prior_success = d.get("prior_success", [])
        s.reflection_log = d.get("reflection_log", [])
        s.last = d.get("last", {})
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
    _LAST_TEXT = ""  # 每轮重置占位符上下文（每轮独立执行）
    # 带上轮已成功产出作为起点（seed_context）
    seed = None
    if s.prior_success:
        last_out = s.prior_success[-1]["out"]
        seed = dict(last_out)
        seed_text = extract_text(last_out) if isinstance(last_out, dict) else ""
        if seed_text and "text" not in seed:
            seed["text"] = seed_text
    exe_res, recorded = _execute(s.task, s.steps, seed_context=seed)
    r = _assemble(s.task, s.planner, s.plan_text, s.steps, exe_res, s.cycle, s.start)
    s.last = r
    if recorded:
        s.prior_success = recorded
    # 已达成（或产物已落盘的部分完成）→ 停
    if not _needs_reflection(r) or s.cycle >= s.max_reflect:
        return False
    # 触发反思：质疑 agent 诊断根因 → 重设计下一步计划
    refl = _reflect_and_redesign(s.task, r, s.cycle + 1, prior_success=s.prior_success)
    if not refl or not refl.get("steps"):
        s.reflection_log.append({
            "cycle": s.cycle + 1, "action": "no_redesign",
            "reason": "反思未产出有效修正计划，停止避免空转",
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


def run(task: str, planner: str = "ag2", run_id: Optional[str] = None) -> Dict[str, Any]:
    """执行一个自主任务（求是引擎式：规划→执行→质疑→重设计→再执行…）。

    Args:
        task: 自然语言任务
        planner: "ag2"（LLM 规划）或 "heuristic"（本地关键词）
        run_id: 显式传入则复用该 run_id（外部指定），否则自动生成。
            每轮结束后写入 sqlite checkpoint，进程崩了可用 resume_run 续跑。

    Returns: 顶层含 reflection 字段（轮次/是否达上限）+ run_id。
    """
    start = time.time()
    plan_text, steps, used_planner = _plan(task, planner)
    if not steps:
        return {
            "task": task, "planner": used_planner,
            "error": "无法生成任何执行步骤",
            "duration_s": round(time.time() - start, 1),
        }

    s = _RunState(task, used_planner, plan_text, steps, max_reflect=_max_reflect_for(task), per_run_id=run_id)
    if run_id:
        s.run_id = run_id
    create_run(s.run_id, task, used_planner)

    while _advance_cycle(s):
        save_checkpoint(s.run_id, s.to_dict())
    save_checkpoint(s.run_id, s.to_dict())  # 末轮最终态也落盘
    mark_done(s.run_id)

    s.last["reflection"] = {
        "attempts": len(s.reflection_log) + 1,  # 总执行轮次
        "exhausted": _needs_reflection(s.last),  # True=达上限仍未达成
        "log": s.reflection_log,
    }
    s.last["run_id"] = s.run_id
    s.last["duration_s"] = round(time.time() - s.start, 1)
    return s.last


def resume_run(run_id: str) -> Dict[str, Any]:
    """从磁盘 checkpoint 恢复一个中断的自主任务，从最后已完成轮次续跑。

    不重跑已完成的轮次（checkpoint 已保存其成功产出与步骤），只续跑断点之后。
    status 已是 done 却来 resume → 直接返回已存结果，不重跑。
    """
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
        return {"status": "完成 ✅", "deliverable": deliverable, "reason": ""}
    if real_steps > 0:
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
