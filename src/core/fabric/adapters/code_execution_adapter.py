"""代码执行适配器 —— AOS fabric 的 CODE_EXECUTION 平面。

把已有的 SandboxManager（subprocess 隔离执行 Python/JS/Bash）包成 fabric
adapter，使 OrchestrationChiplet 能经 route() 把 action.code_exec 步骤委派
给真实执行器。这是「think→do」闭环里「do」的落地点之一。

设计原则（与 SearchAdapter 一致）：**不弄虚**。
- 代码必须真实执行并返回 stdout/stderr；
- 从上游 LLM 产出里提取代码块（```python ... ```），提取不到就如实失败；
- 不编造输出、不假装成功。

payload 约定（OrchestrationChiplet 透传）：
  - 首步：{"task": "写一段 Python 计算斐波那契"} 或 {"code": "print(1+1)"}
  - 链式：{"content": "上游 LLM 产出的文本（含代码块）"}（in_from: previous）
"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional

from ..adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from ..capability import Capability

logger = logging.getLogger(__name__)

# 从文本中提取 ```python ... ``` 代码块
_CODE_BLOCK_RE = re.compile(
    r"```(?:python|py|javascript|js|bash|sh|shell)?\s*\n(.*?)```",
    re.S | re.I,
)
# 语言别名 → SandboxManager 认的 language 参数
_LANG_MAP = {
    "python": "python", "py": "python",
    "javascript": "javascript", "js": "javascript",
    "bash": "bash", "sh": "bash", "shell": "bash",
}


class CodeExecutionAdapter(BaseAgentAdapter):
    """把 SandboxManager 暴露为 fabric 的 action.code_exec 能力供给方。"""

    def __init__(self) -> None:
        from execution.sandbox import SandboxManager
        self._sandbox_mgr = SandboxManager()
        # 每个适配器实例持有一个长存活沙箱，避免每步都 create+destroy
        result = self._sandbox_mgr.create_sandbox(name="fabric-code-exec")
        self._default_sid = result.get("sandbox", {}).get("id", "")
        if not self._default_sid:
            logger.error("CodeExecutionAdapter: 沙箱创建失败")
        else:
            logger.info("CodeExecutionAdapter: 沙箱就绪 sid=%s", self._default_sid)

    @property
    def engine_id(self) -> str:
        return "code-exec"

    def advertise_capabilities(self) -> list[Capability]:
        return [Capability.CODE_EXECUTION]

    def health(self) -> bool:
        return bool(self._default_sid)

    def invoke(self, req: InvokeRequest) -> InvokeResult:
        if not self._default_sid:
            return InvokeResult(ok=False, error="沙箱未就绪")

        payload = req.payload or {}
        code, language = self._extract_code(payload)

        if not code:
            # 通电缝：纯自然语言代码需求（如"写一个计算器"）离线无 LLM 时，
            # 若匹配 code_team 已知模板，则柔性回落到 code_team 生成+真实执行，
            # 让离线也能闭环；不匹配模板则如实失败（不编）。
            fb = self._try_nl_generate_fallback(payload)
            if fb is not None:
                return fb
            return InvokeResult(
                ok=False,
                error="未能从输入中提取可执行代码（需要 code 字段或 ```python 代码块）",
            )

        result = self._sandbox_mgr.execute_code(
            self._default_sid, code, language=language, timeout=30,
        )

        if result.get("success"):
            return InvokeResult(ok=True, data={
                "content": result.get("output", ""),
                "output": result.get("output", ""),
                "language": language,
                "duration": result.get("duration", 0),
                "engine": "sandbox",
            })
        return InvokeResult(
            ok=False,
            error=result.get("error", "代码执行失败"),
            data={"stderr": result.get("error", ""), "language": language},
        )

    @staticmethod
    def _extract_code(payload: dict[str, Any]) -> tuple[str, str]:
        """从 payload 里提取代码和语言。

        优先级：
        1. payload["code"] — 显式代码字段（最可靠）
        2. payload["content"] — 上游 LLM 产出，从中抽取代码块
        3. payload["task"] — 首步入参，尝试抽取代码块或直接当代码
        """
        # 1) 显式 code 字段
        code = (payload.get("code") or "").strip()
        if code:
            lang = (payload.get("language") or "python").lower()
            lang = _LANG_MAP.get(lang, "python")
            return code, lang

        # 2) 从 content / task / text 里提取代码块
        text = (payload.get("content")
                or payload.get("task")
                or payload.get("text")
                or "").strip()
        if not text:
            return "", "python"

        m = _CODE_BLOCK_RE.search(text)
        if m:
            block = m.group(1).strip()
            # 从 ```标记 里取语言
            lang_label = _CODE_BLOCK_RE.search(text)
            lang = "python"
            if lang_label:
                full = text[lang_label.start():lang_label.start() + 30]
                lm = re.match(r"```(\w+)", full)
                if lm:
                    lang = _LANG_MAP.get(lm.group(1).lower(), "python")
            return block, lang

        # 3) 从混合文本中提取行内代码（"执行代码 print(42)" → "print(42)"）
        #    逐个关键词查找，取最长匹配（避免"执行"匹配到"代码 print"的歧义）
        for kw in ("代码", "code", "执行", "运行", "exec", "run"):
            idx = text.lower().find(kw.lower())
            if idx < 0:
                continue
            after = text[idx + len(kw):].strip().strip(":：` ")
            if after and re.search(r"[()=]|print|def|import|from|console", after):
                return after, "python"

        # 4) 如果文本本身就像代码（以代码关键词开头且无中文），直接执行
        _HAS_CJK = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")
        _CODE_START = re.compile(
            r"^(print|def|import|from|class|if|for|while|with|try|var |const |let |echo )\b"
        )
        if _CODE_START.match(text) and not _HAS_CJK.search(text):
            return text, "python"

        # 提取不到代码 → 如实返回空
        return "", "python"

    @staticmethod
    def _try_nl_generate_fallback(
        payload: dict[str, Any],
    ) -> Optional[InvokeResult]:
        """NL 代码需求离线回落：匹配 code_team 模板则生成+执行，否则 None。

        仅当输入是「写/生成 X 代码」类自然语言、且匹配 code_team 的已知模板
        （calculator/sort/fibonacci/greet）时才回落——避免对「写个聊天机器人」
        这类无法生成的任务假装能办（理念6/9 诚实）。生成复用 code_team 的
        heuristic 脚手架（离线可跑），执行是真实 subprocess（不编）。

        返回 InvokeResult（成功时 engine_id="code-team"，data 含 generated_by/
        via_fallback/files 供调用方完全透明）；不应回落时返回 None（调用方继续
        走原「未能提取代码」失败分支）。
        """
        text = (payload.get("requirement") or payload.get("task")
                or payload.get("text") or payload.get("content") or "").strip()
        if not text:
            return None
        try:
            from kernel.plugins.code_team import CodeTeamOrchestrator, _resolve_kind
        except Exception:  # 模块不可用（极少见）→ 不回落
            return None
        # 仅模板类需求回落，避免假装能办通用代码生成
        if _resolve_kind(text) is None:
            return None
        lang = (payload.get("language") or payload.get("lang") or "python").lower()
        try:
            result = CodeTeamOrchestrator(llm_generate=None).run(text, lang=lang)
        except Exception as e:  # noqa: BLE001
            logger.warning("code_exec NL 回落生成失败: %s", e)
            return None
        exec_res = result.get("execution") or {}
        files = result.get("files") or {}
        ok = bool(result.get("ok", False)) and bool(exec_res.get("ok", False))
        content = exec_res.get("output") or ""
        if ok:
            return InvokeResult(ok=True, data={
                "content": content,
                "output": content,
                "language": result.get("lang", lang),
                "duration": 0,
                "engine": "code-team",
                "generated_by": "code_team",
                "via_fallback": True,
                "files": files,
                "execution": exec_res,
                "plan": result.get("plan"),
            }, engine_id="code-team")
        # 生成/执行未通过 → 诚实失败，附生成文件供诊断
        return InvokeResult(
            ok=False,
            error=exec_res.get("error") or "代码团队生成+执行未通过",
            data={"engine": "code-team", "generated_by": "code_team",
                  "files": files, "execution": exec_res,
                  "quality": result.get("quality")},
            engine_id="code-team",
        )
