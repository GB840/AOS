"""
IMA Subagent - 腾讯 IMA 知识库子智能体

将腾讯 IMA Copilot 知识库作为 AOS 子智能体集成，提供知识检索、知识库浏览、
笔记读写能力。可作为 AOS 的结构化交接链 / 长期知识后端。

接入方式：直连 IMA OpenAPI (ima.qq.com/openapi)，认证用
ima-openapi-clientid + ima-openapi-apikey 两个 Header。
完全对标 ViMax 的接法（subagent + skill + API 端点），都是腾讯系产品。
"""

import os
import logging
import uuid
import asyncio
from typing import Dict, Any

logger = logging.getLogger(__name__)


class IMASubagent:
    """
    IMA 知识库子智能体

    经 DeerFlow / SubAgentRegistry 调度，执行知识检索与笔记读写任务。
    支持五种操作：search_knowledge / search_knowledge_base /
    get_knowledge_base / list_knowledge / create_note。
    """

    NAME = "ima"
    DESCRIPTION = "腾讯 IMA 知识库 — 知识检索 / 知识库浏览 / 笔记读写（结构化交接后端）"
    CAPABILITIES = [
        "knowledge_search",
        "knowledge_base",
        "note_management",
        "rag",
        "memory",
        "structured_handoff",
        "tencent_ima",
    ]

    OPERATIONS = {
        "search_knowledge": {
            "name": "search_knowledge",
            "description": "在指定知识库内语义检索知识条目",
            "params": ["query", "knowledge_base_id", "cursor"],
        },
        "search_knowledge_base": {
            "name": "search_knowledge_base",
            "description": "搜索 / 列出可用知识库",
            "params": ["query", "cursor", "limit"],
        },
        "get_knowledge_base": {
            "name": "get_knowledge_base",
            "description": "获取知识库元信息",
            "params": ["ids"],
        },
        "list_knowledge": {
            "name": "list_knowledge",
            "description": "浏览知识库内容 / 文件夹",
            "params": ["knowledge_base_id", "folder_id", "cursor", "limit"],
        },
        "create_note": {
            "name": "create_note",
            "description": "创建笔记（用于结构化交接 / 长期记忆存储）",
            "params": ["title", "content", "content_format"],
        },
        "store_handoff": {
            "name": "store_handoff",
            "description": "结构化交接：构造信封 → 只读审查 → 存 IMA 知识库",
            "params": ["title", "summary", "confirmed_facts", "assumptions",
                       "risk_boundary", "open_questions", "handoff_to", "source", "tags"],
        },
    }

    def __init__(self):
        self._skill = None
        self._initialized = False
        self._tasks: Dict[str, Dict] = {}

        self._init_skill()

    def _init_skill(self):
        """初始化 IMA 技能"""
        try:
            from skills.ima import get_ima_skill
            self._skill = get_ima_skill()
            self._initialized = True
            logger.info("IMA 子智能体初始化成功")
        except Exception as e:
            logger.warning(f"IMA 技能初始化失败: {e}")

    def handle(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        同步调用入口 — 供 SubAgentRegistry.invoke() 使用

        Args:
            input_data: 输入数据
                - operation: 操作类型
                - query/input: 检索关键词
                - knowledge_base_id / folder_id / title / content 等视操作而定
                - params: 可选参数

        Returns:
            Dict: 执行结果
        """
        if not self._initialized or self._skill is None:
            return self._handle_unconfigured(input_data)

        try:
            result = self._skill.execute(input_data)
            if result.get("success"):
                logger.info(f"IMA 操作执行成功: {result.get('operation')} / {result.get('task_id')}")
            else:
                logger.warning(f"IMA 操作执行失败: {result.get('error')}")
            return result
        except Exception as e:
            logger.error(f"IMA 子智能体执行失败: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def async_handle(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """异步调用入口"""
        if not self._initialized or self._skill is None:
            return self._handle_unconfigured(input_data)

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self._skill.execute, input_data)
        return result

    def _handle_unconfigured(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        未配置处理 — 诚实返回，不伪造知识库结果。

        知识检索不同于视频生成：伪造的检索结果会直接误导下游决策，
        因此未配置 API Key 时明确报错，而非返回模拟数据。
        """
        return {
            "success": False,
            "operation": input_data.get("operation"),
            "configured": False,
            "error": (
                "IMA 未配置：请在 .env 设置 IMA_OPENAPI_APIKEY（Client ID 已有默认值 "
                "b1f8f7574dc75ac48e7bb0624ff72482）。未配置时不返回伪造的知识库结果。"
            ),
        }

    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """获取任务状态"""
        if self._skill:
            return self._skill.get_status(task_id)
        return self._tasks.get(task_id, {"status": "unknown"})

    def list_operations(self) -> Dict[str, Any]:
        """列出所有可用操作"""
        return self.OPERATIONS

    def is_ready(self) -> bool:
        """检查子智能体是否就绪（已配置凭证、可真实调用 IMA）"""
        return bool(self._initialized and self._skill and self._skill.is_configured())

    def configure(self, api_keys: Dict[str, str]) -> bool:
        """
        配置 API 密钥

        Args:
            api_keys: API 密钥字典
                - IMA_OPENAPI_CLIENTID: Client ID
                - IMA_OPENAPI_APIKEY: API Key

        Returns:
            bool: 是否配置成功
        """
        for key, value in api_keys.items():
            os.environ[key] = value

        # 重新初始化技能以加载新凭证
        self._init_skill()
        logger.info(f"IMA 已配置凭证: {list(api_keys.keys())}")
        return True


def get_ima_subagent() -> "IMASubagent":
    """获取或创建 IMA 子智能体实例"""
    return IMASubagent()


def register_ima_subagent(registry=None):
    """注册 IMA 子智能体到 SubAgentRegistry（与 ViMax 同形）"""
    if registry is None:
        from subagents.registry import SubAgentRegistry
        registry = SubAgentRegistry()

    agent = IMASubagent()
    registry.register(agent.NAME, agent.DESCRIPTION, agent.CAPABILITIES, agent.handle)
    logger.info("IMA 子智能体已注册")
    return agent
