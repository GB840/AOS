"""
IMA Skill Module - 腾讯 IMA 知识库集成

IMA = 腾讯 IMA Copilot 智能工作台，提供云端知识库与笔记能力。
本模块将 IMA 作为 AOS 技能接入，提供：
- 知识库检索 (search_knowledge)
- 知识库列表 / 浏览 (search_knowledge_base / get_knowledge_base / list_knowledge)
- 笔记创建 (create_note) — 用于结构化交接链 / 长期记忆

接入：直连 IMA OpenAPI (https://ima.qq.com/openapi)，认证用
ima-openapi-clientid + ima-openapi-apikey 两个 HTTP Header。
凭证优先级：环境变量 IMA_OPENAPI_CLIENTID / IMA_OPENAPI_APIKEY。

接口依据腾讯官方 OpenAPI 文档核实（2026-07-15 搜证）：
- 知识库: openapi/wiki/v1/*
- 笔记:   openapi/note/v1/*
纯标准库 urllib 实现，无新增第三方依赖（遵循 Ponytail 阶梯）。
"""

import os
import json
import logging
import uuid
import urllib.request
import urllib.error
from typing import Dict, Any, Optional

from .base import Skill

# 结构化交接信封（AOS 多 Agent / 多会话交接链，存 IMA 知识库）
from core.fabric.handoff import HandoffEnvelope, review_handoff, store_handoff

logger = logging.getLogger(__name__)

IMA_BASE_URL = "https://ima.qq.com"
# 给定 Client ID（用户 2026-07-15 提供）；API Key 需用户在 .env 配置 IMA_OPENAPI_APIKEY
DEFAULT_CLIENT_ID = "b1f8f7574dc75ac48e7bb0624ff72482"

IMA_OPERATIONS = {
    "search_knowledge": {
        "name": "search_knowledge",
        "description": "在指定知识库内语义检索知识条目",
        "input_desc": "检索关键词 + knowledge_base_id",
        "output_desc": "命中的知识条目（含高亮片段）",
        "example": "query='AOS 路由策略', knowledge_base_id='kb_xxx'",
    },
    "search_knowledge_base": {
        "name": "search_knowledge_base",
        "description": "搜索 / 列出可用知识库",
        "input_desc": "关键词（空则列出全部）",
        "output_desc": "知识库列表",
        "example": "query='AOS'",
    },
    "get_knowledge_base": {
        "name": "get_knowledge_base",
        "description": "获取知识库元信息",
        "input_desc": "知识库 id 列表",
        "output_desc": "知识库名称 / 描述 / 推荐问题",
        "example": "ids=['kb_xxx']",
    },
    "list_knowledge": {
        "name": "list_knowledge",
        "description": "浏览知识库内容 / 文件夹",
        "input_desc": "knowledge_base_id（可选 folder_id 进入子文件夹）",
        "output_desc": "知识条目 / 文件夹列表",
        "example": "knowledge_base_id='kb_xxx'",
    },
    "create_note": {
        "name": "create_note",
        "description": "创建笔记（用于结构化交接 / 长期记忆存储）",
        "input_desc": "title + content",
        "output_desc": "笔记创建结果",
        "example": "title='交接-2026-07-15', content='...'",
    },
    "store_handoff": {
        "name": "store_handoff",
        "description": "结构化交接：构造 HandoffEnvelope → 只读审查 → 存入 IMA 知识库",
        "input_desc": "title/summary/confirmed_facts/assumptions/risk_boundary/open_questions/handoff_to/source/tags",
        "output_desc": "审查结果 + IMA 笔记 note_id",
        "example": "title='IM集成交接', summary='...', confirmed_facts=[...], handoff_to='下一手'",
    },
    "get_handoff": {
        "name": "get_handoff",
        "description": "读回结构化交接：按 doc_id 取 IMA 笔记 → 解析回 HandoffEnvelope → 审查",
        "input_desc": "doc_id（store_handoff 返回的 note_id）",
        "output_desc": "结构化信封 + 审查结果 + 原始笔记文本",
        "example": "doc_id='7482930863560973'",
    },
    "search_handoffs": {
        "name": "search_handoffs",
        "description": "检索历史交接笔记（按关键词搜 IMA 笔记正文，默认关键词'交接'）",
        "input_desc": "query（默认'交接'）/ limit",
        "output_desc": "命中的历史交接笔记列表（docid/title/summary）",
        "example": "query='交接', limit=20",
    },
}


class IMASkill(Skill):
    """
    IMA 知识库技能

    将腾讯 IMA 知识库集成到 AOS 技能系统，支持检索 / 浏览 / 笔记读写。
    未配置 API Key 时诚实返回失败，不伪造知识结果。
    """

    NAME = "ima"
    DESCRIPTION = "腾讯 IMA 知识库 — 知识检索 / 知识库浏览 / 笔记读写"
    VERSION = "1.0.0"
    AUTHOR = "Tencent"
    LICENSE = "Proprietary (IMA OpenAPI)"
    CATEGORY = "knowledge"
    TAGS = ["knowledge", "rag", "memory", "tencent", "ima", "handoff"]
    CAPABILITIES = [
        "knowledge_search",
        "knowledge_base",
        "note_management",
        "rag",
        "memory",
        "structured_handoff",
    ]

    def __init__(self):
        super().__init__()
        self._client: Optional["_IMAClient"] = None
        self._api_configured = False
        self._op_status: Dict[str, Dict] = {}

        self._check_creds()

    def _check_creds(self):
        """检查并初始化 IMA 凭证（环境变量优先）"""
        client_id = os.environ.get("IMA_OPENAPI_CLIENTID") or DEFAULT_CLIENT_ID
        api_key = os.environ.get("IMA_OPENAPI_APIKEY", "")

        if client_id and api_key:
            self._client = _IMAClient(client_id, api_key)
            self._api_configured = True
            logger.info("IMA 凭证已配置（Client ID + API Key 齐备）")
        elif client_id:
            logger.warning("IMA 仅配置了 Client ID，缺少 IMA_OPENAPI_APIKEY，无法真实调用")
        else:
            logger.warning("IMA 未配置凭证")

    def is_configured(self) -> bool:
        """是否已配置可真实调用"""
        return self._api_configured

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行 IMA 操作

        Args:
            context: 执行上下文
                - operation: 操作类型（见 IMA_OPERATIONS）
                - query/input: 检索关键词
                - knowledge_base_id / folder_id / ids / title / content / limit / cursor 等视操作而定

        Returns:
            Dict: 执行结果
        """
        operation = (context.get("operation") or context.get("mode") or "search_knowledge").lower()

        if operation not in IMA_OPERATIONS:
            return {
                "success": False,
                "error": f"未知操作 '{operation}'，可用: {list(IMA_OPERATIONS.keys())}",
                "available_operations": list(IMA_OPERATIONS.keys()),
            }

        if not self._api_configured or self._client is None:
            return {
                "success": False,
                "operation": operation,
                "configured": False,
                "error": (
                    "IMA 未配置 API Key：请在 .env 设置 IMA_OPENAPI_APIKEY 后重启。"
                    "未配置时不返回伪造的知识库结果。"
                ),
            }

        task_id = str(uuid.uuid4())[:8]
        try:
            if operation == "search_knowledge":
                result = self._client.search_knowledge(context)
            elif operation == "search_knowledge_base":
                result = self._client.search_knowledge_base(context)
            elif operation == "get_knowledge_base":
                result = self._client.get_knowledge_base(context)
            elif operation == "list_knowledge":
                result = self._client.list_knowledge(context)
            elif operation == "create_note":
                result = self._client.create_note(context)
            elif operation == "store_handoff":
                return self._handle_store_handoff(context)
            elif operation == "get_handoff":
                return self._handle_get_handoff(context)
            elif operation == "search_handoffs":
                return self._handle_search_handoffs(context)
            else:
                return {"success": False, "operation": operation, "error": f"不支持的操作: {operation}"}

            self._op_status[task_id] = {
                "status": "completed" if result.get("success") else "failed",
                "operation": operation,
            }
            return {
                "success": result.get("success", False),
                "operation": operation,
                "task_id": task_id,
                "result": result.get("data"),
                "error": result.get("error"),
                "status": self._op_status[task_id]["status"],
            }

        except Exception as e:
            logger.error(f"IMA 执行失败: {e}", exc_info=True)
            self._op_status[task_id] = {"status": "failed", "operation": operation, "error": str(e)}
            return {
                "success": False,
                "operation": operation,
                "task_id": task_id,
                "error": str(e),
                "status": "failed",
            }

    def _handle_store_handoff(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """结构化交接：构造信封 → 只读审查（不通过则拒存）→ 存 IMA"""
        def _as_list(v):
            if v is None:
                return []
            if isinstance(v, list):
                return v
            if isinstance(v, str):
                return [v] if v.strip() else []
            return [v]

        try:
            envelope = HandoffEnvelope(
                task_id=context.get("task_id", str(uuid.uuid4())[:8]),
                title=context.get("title", "未命名交接"),
                summary=context.get("summary", ""),
                confirmed_facts=_as_list(context.get("confirmed_facts")),
                assumptions=_as_list(context.get("assumptions")),
                risk_boundary=_as_list(context.get("risk_boundary")),
                open_questions=_as_list(context.get("open_questions")),
                handoff_to=context.get("handoff_to", ""),
                source=context.get("source", ""),
                tags=_as_list(context.get("tags")),
            )
        except Exception as e:
            return {"success": False, "operation": "store_handoff", "error": f"信封构造失败: {e}"}

        review = review_handoff(envelope)
        if not review["ready"]:
            return {
                "success": False,
                "operation": "store_handoff",
                "review": review,
                "error": "交接信封未通过只读审查（见 gaps），拒绝存储以防丢上下文",
            }
        store_res = store_handoff(envelope, skill=self)
        return {
            "success": store_res.get("success", False),
            "operation": "store_handoff",
            "review": review,
            "result": store_res.get("result"),
            "error": store_res.get("error"),
        }

    def _handle_get_handoff(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """读回交接：取 IMA 笔记正文 → 解析回 HandoffEnvelope → 审查（不写任何东西）"""
        doc_id = context.get("doc_id") or context.get("note_id")
        if not doc_id:
            return {"success": False, "operation": "get_handoff",
                    "error": "缺少 doc_id / note_id（store_handoff 返回的 note_id）"}
        raw = self._client.get_note(doc_id)
        if not raw.get("success"):
            return {"success": False, "operation": "get_handoff", "error": raw.get("error")}
        # get_doc_content 返回形态兼容多种：裸字符串 / {content:"..."} / {data:{content:"..."}}
        data = raw.get("data")
        if isinstance(data, str):
            text = data
        elif isinstance(data, dict):
            inner = data.get("content")
            if isinstance(inner, str):
                text = inner
            elif isinstance(inner, dict):
                text = inner.get("content") or ""
            else:
                deep = data.get("data")
                text = deep.get("content") if isinstance(deep, dict) else (deep or "")
        else:
            text = str(data) if data is not None else ""
        if not text:
            return {"success": False, "operation": "get_handoff",
                    "error": "IMA 返回笔记内容为空（可能 doc_id 无效或内容格式不支持）"}
        envelope = HandoffEnvelope.from_markdown(text)
        review = review_handoff(envelope)
        return {
            "success": True,
            "operation": "get_handoff",
            "doc_id": doc_id,
            "envelope": envelope.to_dict(),
            "review": review,
            "raw": text,
        }

    def _handle_search_handoffs(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """检索历史交接笔记：按关键词搜 IMA 笔记正文"""
        raw = self._client.search_handoffs(context.get("query", "交接"),
                                           context.get("limit", 20))
        if not raw.get("success"):
            return {"success": False, "operation": "search_handoffs", "error": raw.get("error")}
        return {
            "success": True,
            "operation": "search_handoffs",
            "result": raw.get("data"),
        }

    def get_status(self, task_id: str) -> Dict[str, Any]:
        """获取任务状态"""
        return self._op_status.get(task_id, {"status": "unknown"})

    def list_operations(self) -> Dict[str, Any]:
        """列出所有可用操作"""
        return IMA_OPERATIONS


class _IMAClient:
    """IMA OpenAPI 薄客户端（纯标准库 urllib，无第三方依赖）"""

    def __init__(self, client_id: str, api_key: str):
        self.client_id = client_id
        self.api_key = api_key
        self.base = IMA_BASE_URL

    def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """POST 到 IMA OpenAPI，返回 {success, data|error}"""
        url = f"{self.base}/{path}"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("ima-openapi-clientid", self.client_id)
        req.add_header("ima-openapi-apikey", self.api_key)
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                body = resp.read().decode("utf-8")
            return {"success": True, "data": json.loads(body)}
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "ignore")
            return {"success": False, "error": f"HTTP {e.code}: {detail[:300]}"}
        except Exception as e:  # 网络/超时/解析等
            return {"success": False, "error": str(e)}

    def search_knowledge(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        return self._post("openapi/wiki/v1/search_knowledge", {
            "query": ctx.get("query", ctx.get("input", "")),
            "knowledge_base_id": ctx.get("knowledge_base_id", ""),
            "cursor": ctx.get("cursor", ""),
        })

    def search_knowledge_base(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        return self._post("openapi/wiki/v1/search_knowledge_base", {
            "query": ctx.get("query", ctx.get("input", "")),
            "cursor": ctx.get("cursor", ""),
            "limit": ctx.get("limit", 20),
        })

    def get_knowledge_base(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        ids = ctx.get("ids") or []
        if isinstance(ids, str):
            ids = [ids]
        return self._post("openapi/wiki/v1/get_knowledge_base", {"ids": ids})

    def list_knowledge(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        return self._post("openapi/wiki/v1/get_knowledge_list", {
            "knowledge_base_id": ctx.get("knowledge_base_id", ""),
            "folder_id": ctx.get("folder_id", ""),
            "cursor": ctx.get("cursor", ""),
            "limit": ctx.get("limit", 20),
        })

    def create_note(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        # 笔记创建：官方笔记模块路径为 openapi/note/v1/import_doc（全小写，已联网搜证核实）
        # 重要：IMA 笔记无独立 title 字段，标题即正文首个 '# 标题' 行；
        # payload = {content_format:1(固定Markdown), content: "# 标题\n\n正文", 可选 folder_id}
        # 防重复标题：若正文已以 '# ' 开头（如结构化交接的 to_markdown），不再叠加 '# {title}'。
        title = ctx.get("title", "AOS 笔记")
        body = ctx.get("content", ctx.get("input", ""))
        if body.startswith("# "):
            md = body
        else:
            md = f"# {title}\n\n{body}" if body else f"# {title}"
        return self._post("openapi/note/v1/import_doc", {
            "content": md,
            "content_format": ctx.get("content_format", 1),
            "folder_id": ctx.get("folder_id", ""),
        })

    def get_note(self, doc_id: str) -> Dict[str, Any]:
        # 读取单条笔记正文：openapi/note/v1/get_doc_content（已联网搜证核实）
        # target_content_format=1 返回 Markdown（保留 #/## 结构与换行，便于解析回信封）；
        # format=0 会把 Markdown 去格式化成纯文本、换行塌缩，无法还原结构。
        return self._post("openapi/note/v1/get_doc_content", {
            "doc_id": doc_id,
            "target_content_format": 1,
        })

    def search_handoffs(self, query: str, limit: int = 20) -> Dict[str, Any]:
        # 按关键词搜笔记正文：openapi/note/v1/search_note_book（已联网搜证核实）
        # search_type=1 按内容搜；query_info.content 为关键词
        return self._post("openapi/note/v1/search_note_book", {
            "search_type": 1,
            "query_info": {"content": query or "交接"},
            "start": 0,
            "end": limit,
        })


def get_ima_skill() -> IMASkill:
    """获取或创建 IMA 技能实例"""
    return IMASkill()


def register_ima_skill(registry=None):
    """注册 IMA 技能到技能注册表（与 ViMax 同形）"""
    if registry is None:
        from .base import SkillRegistry
        registry = SkillRegistry()

    skill = IMASkill()
    registry.register(skill)
    logger.info("IMA 技能已注册")
    return skill
