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
        title = ctx.get("title", "AOS 笔记")
        body = ctx.get("content", ctx.get("input", ""))
        md = f"# {title}\n\n{body}" if body else f"# {title}"
        return self._post("openapi/note/v1/import_doc", {
            "content": md,
            "content_format": ctx.get("content_format", 1),
            "folder_id": ctx.get("folder_id", ""),
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
