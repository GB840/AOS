"""知络 KnowMesh 本地知识库适配器（memory.knowledge）—— 单创OS 可审计文档知识库 provider。

真相（已对 KnowMesh 官方仓库 + 磁盘代码 + 运行实例三重核实）：
- KnowMesh 是 shineway-tech 出品的 **local-first 文档知识库编译器**（Node.js ≥24，
  非 Python、非 MCP、非多 Agent 共享外脑）。其对外集成边界 = **HTTP API only**
  （默认 127.0.0.1:7457），官方明确「不提供 MCP Server / 不默认开放广域访问认证」。
- 能力契约（来自运行实例 /api/integration/manifest，2026-07-query-runtime.1）：
  * POST /kb/{knowledgeBaseId}/api/query  —— 带引用问答（body: {question, scope, filters}）
  * GET  /kb/{knowledgeBaseId}/api/search —— 检索（param: q）
  查询是 **scoped** 的：必须指定 knowledgeBaseId。运行实例的诊断显示
  availableCount=0、queryRuntime=blocked(knowledge_base_required) —— 即服务在跑
  但**还没有任何知识库**，查询会被诚实拒绝（这是真实现状，不是 bug）。
- AOS 把 KnowMesh 当「可审计、带引用、可回滚的本地文档知识库 provider」接入
  MEMORY_KNOWLEDGE 能力，复用已有能力枚举，不造新轮子。

设计对齐 AOS 铁律：
- **零依赖**：仅用 stdlib urllib，不引入 JS/Node SDK（官方 SDK 是 JS-only）。
- **诚实降级（理念6）**：服务不可达 / KB 未配置 / 查询未命中 → invoke 返回
  ok=False 并附**真实原因**（如 knowledge_base_required），绝不谎报命中。
- **协议诚实**：supported_protocols() 返回 ["HTTP"]，不冒充 MCP。
- **本地优先零成本最强隐私** → 档位 HIGH（与 mem0 / comfyui 同级）。
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from core.fabric.adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from core.fabric.capability import Capability, TIER_HIGH

logger = logging.getLogger(__name__)

_ENV_BASE_URL = "KNOWMESH_BASE_URL"
_ENV_KB_ID = "KNOWMESH_KB_ID"
_ENV_TIMEOUT = "KNOWMESH_TIMEOUT"
_ENV_ENABLED = "AOS_KNOWMESH_ENABLED"

_DEFAULT_BASE_URL = "http://127.0.0.1:7457"
_DEFAULT_TIMEOUT = 30


class KnowMeshUnavailable(Exception):
    """KnowMesh 服务不可达 / 非 2xx / 返回非 JSON 或错误负载。"""


class KnowmeshAdapter(BaseAgentAdapter):
    """知络 KnowMesh 本地知识库适配器：把 memory.knowledge 调用翻译为 HTTP 查询。

    薄胶水层，不算重造知识库引擎（KnowMesh 是真实开源 OSS）。AOS 只标准化
    「怎么调它的 HTTP API」。诚实失败：KB 未建 / 查询未命中时由上层 agent 降级。
    """

    @property
    def engine_id(self) -> str:
        return "knowmesh"

    # ── 可注入的子类钩子：便于离线测试时替换 HTTP 调用（对齐 mediakit 的 _run）──
    def _http(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        body: dict | None = None,
        headers: dict | None = None,
    ) -> dict:
        """对 KnowMesh 发一次 HTTP 请求，返回解析后的 JSON dict。

        默认走真实 urllib；测试可 monkeypatch 本方法以离线验证 adapter 逻辑。
        """
        base = os.environ.get(_ENV_BASE_URL, _DEFAULT_BASE_URL).rstrip("/")
        url = base + path
        if params:
            url += "?" + urlencode(params)
        data = None
        hdrs = {"accept": "application/json"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            hdrs["content-type"] = "application/json"
        if headers:
            hdrs.update(headers)

        req = Request(url, data=data, headers=hdrs, method=method.upper())
        timeout = int(os.environ.get(_ENV_TIMEOUT, _DEFAULT_TIMEOUT))
        try:
            with urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", "replace")
        except HTTPError as e:  # 非 2xx（含 knowledge_base_required 等）
            detail = ""
            try:
                detail = e.read().decode("utf-8", "replace")[:500]
            except Exception:  # noqa: BLE001
                pass
            raise KnowMeshUnavailable(f"KnowMesh HTTP {e.code} @ {path}: {detail}") from e
        except Exception as e:  # noqa: BLE001 - 网络不可达 / 超时
            raise KnowMeshUnavailable(f"KnowMesh 不可达 @ {path}: {e}") from e

        if not raw.strip():
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            raise KnowMeshUnavailable(f"KnowMesh 返回非 JSON @ {path}: {raw[:200]}")

    def advertise_capabilities(self) -> list:
        # 复用已有能力枚举 memory.knowledge（RAG / Graph-RAG knowledge hub），不新增。
        return [Capability.MEMORY_KNOWLEDGE]

    def tier(self) -> str:
        # 本地优先、零成本、最强隐私 → 高档（与 mem0 / comfyui 同级）。
        return TIER_HIGH

    def supported_protocols(self) -> list[str]:
        # 诚实：KnowMesh 只有 HTTP API（官方无 MCP Server），不冒充 MCP。
        return ["HTTP"]

    def health(self) -> bool:
        """存活探测：GET 集成清单返回 2xx 即视为服务可达。

        - AOS_KNOWMESH_ENABLED=0 → 强制关闭（不参与路由，不污染主流程）。
        - 更深层的「是否有知识库」属于就绪度（readiness），由 health_detail /
          invoke 诚实上报，不影响存活判定。
        """
        if os.environ.get(_ENV_ENABLED, "1").strip() == "0":
            return False
        try:
            self._http("GET", "/api/integration/manifest")
            return True
        except Exception as e:  # noqa: BLE001
            logger.debug("KnowMesh health probe failed: %s", e)
            return False

    def health_detail(self) -> dict:
        base_url = os.environ.get(_ENV_BASE_URL, _DEFAULT_BASE_URL)
        kb_id = os.environ.get(_ENV_KB_ID, "")
        try:
            diag = self._http("GET", "/api/integration/diagnostics")
            svc = diag.get("service", {})
            kb = diag.get("knowledgeBase", {})
            rt = (diag.get("readiness") or {}).get("queryRuntime", {})
            available = True
            note = "就绪：KnowMesh HTTP API 可达。"
        except Exception as e:  # noqa: BLE001
            return {
                "engine_id": self.engine_id,
                "available": False,
                "base_url": base_url,
                "kb_id": kb_id,
                "error": str(e),
                "note": "KnowMesh 服务不可达：确认 D:/KnowMesh 已 `node ./src/cli/knowmesh.mjs start`。",
            }
        notes = []
        if not kb_id:
            notes.append("未设置 KNOWMESH_KB_ID：查询为 scoped，必须指定 knowledgeBaseId。")
        if kb.get("availableCount", 0) == 0:
            notes.append(
                f"KnowMesh 当前 availableCount=0（queryRuntime={rt.get('status')}，"
                f"{rt.get('reason')}）：需先在 KnowMesh 创建/选定知识库再查询。"
            )
        return {
            "engine_id": self.engine_id,
            "available": available,
            "base_url": base_url,
            "service": {
                "host": svc.get("host"),
                "port": svc.get("port"),
                "remoteAccess": svc.get("remoteAccess"),
            },
            "kb_id": kb_id,
            "kb_available_count": kb.get("availableCount"),
            "query_runtime": rt.get("status"),
            "advertises": [
                c.value if hasattr(c, "value") else str(c)
                for c in self.advertise_capabilities()
            ],
            "protocols": self.supported_protocols(),
            "note": " ".join(notes) or note,
        }

    def invoke(self, req: InvokeRequest) -> InvokeResult:
        if req.capability != Capability.MEMORY_KNOWLEDGE:
            cap_s = req.capability.value if hasattr(req.capability, "value") else str(req.capability)
            return InvokeResult(
                ok=False,
                error=f"KnowmeshAdapter 仅服务 {Capability.MEMORY_KNOWLEDGE.value}，收到 {cap_s}",
                engine_id=self.engine_id,
            )

        payload = req.payload or {}
        action = (payload.get("action") or "query").strip().lower()

        try:
            # 就绪度 / 连接状态上报（不依赖 KB）
            if action in ("status", "diagnostics"):
                diag = self._http("GET", "/api/integration/diagnostics")
                return InvokeResult(
                    ok=True,
                    data={"diagnostics": diag, "kb_id": os.environ.get(_ENV_KB_ID, "")},
                    engine_id=self.engine_id,
                )

            # 查询 / 检索都需指定 knowledgeBaseId（scoped）
            kb_id = payload.get("kb_id") or os.environ.get(_ENV_KB_ID, "")
            if not kb_id:
                return InvokeResult(
                    ok=False,
                    error=(
                        "KNOWMESH_KB_ID 未配置：KnowMesh 查询为 scoped，必须指定 "
                        "knowledgeBaseId；且当前运行实例 availableCount=0"
                        "（knowledge_base_required）。请先在 KnowMesh 创建/选定知识库，"
                        "再把该 id 设到 KNOWMESH_KB_ID。"
                    ),
                    engine_id=self.engine_id,
                )
            safe_kb = quote(kb_id, safe="")

            if action == "search":
                q = payload.get("query") or payload.get("q") or ""
                if not q:
                    return InvokeResult(
                        ok=False, error="search 需 query/q 参数。", engine_id=self.engine_id
                    )
                data = self._http(
                    "GET", f"/kb/{safe_kb}/api/search", params={"q": q}
                )
                return InvokeResult(
                    ok=True,
                    data={"kb_id": kb_id, "search": data},
                    engine_id=self.engine_id,
                )

            if action == "query":
                question = payload.get("question") or payload.get("query") or ""
                if not question:
                    return InvokeResult(
                        ok=False, error="query 需 question 参数。", engine_id=self.engine_id
                    )
                body = {
                    "question": question,
                    "scope": payload.get("scope") or {},
                    "filters": payload.get("filters") or {},
                }
                data = self._http("POST", f"/kb/{safe_kb}/api/query", body=body)
                status = data.get("status")
                if status == "answered":
                    return InvokeResult(
                        ok=True,
                        data={
                            "kb_id": kb_id,
                            "question": question,
                            "answer": (data.get("answer") or {}).get("text", ""),
                            "citations": data.get("citations") or [],
                            "feedback_endpoint": (data.get("feedback") or {}).get("endpoint"),
                            "raw": data,
                        },
                        engine_id=self.engine_id,
                    )
                # 未命中（out_of_scope / insufficient_evidence / no_index /
                # blocked_by_quality / knowledge_base_required 等）：诚实返回真实状态。
                reason = ""
                err = data.get("error")
                if isinstance(err, dict):
                    reason = err.get("message") or err.get("code") or ""
                elif isinstance(err, str):
                    reason = err
                return InvokeResult(
                    ok=False,
                    error=f"KnowMesh 查询未命中（status={status}）"
                    f"{('：' + reason) if reason else ''}",
                    engine_id=self.engine_id,
                )

            return InvokeResult(
                ok=False,
                error=f"不支持的 action: {action}（支持 query / search / status）",
                engine_id=self.engine_id,
            )
        except KnowMeshUnavailable as e:
            return InvokeResult(
                ok=False, error=f"KnowMesh 调用失败：{e}", engine_id=self.engine_id
            )
        except Exception as e:  # noqa: BLE001
            return InvokeResult(
                ok=False, error=f"KnowMesh 内部异常：{e}", engine_id=self.engine_id
            )
