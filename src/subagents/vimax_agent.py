"""
ViMax Subagent - 多智能体视频生成子智能体

将 ViMax 作为 DeerFlow 子智能体集成，提供专业级视频生成能力。
可通过 DeerFlow 调度执行，支持异步任务和进度追踪。
"""

import os
import logging
import uuid
import asyncio
from typing import Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class ViMaxSubagent:
    """
    ViMax 视频生成子智能体
    
    通过 DeerFlow 调度，执行端到端的视频生成任务。
    支持四种工作流：Idea2Video、Novel2Video、Script2Video、AutoCameo。
    """
    
    NAME = "vimax"
    DESCRIPTION = "ViMax 多智能体视频生成框架 — 从创意到成片的端到端自动化"
    CAPABILITIES = [
        "video_generation",
        "content_production",
        "multimodal",
        "creative",
        "idea_to_video",
        "novel_to_video",
        "script_to_video",
        "auto_cameo",
    ]
    
    WORKFLOWS = {
        "idea2video": {
            "name": "Idea2Video",
            "description": "一句话创意 → 完整视频",
            "params": ["duration", "resolution", "style"],
        },
        "novel2video": {
            "name": "Novel2Video",
            "description": "小说文本 → 分集视频",
            "params": ["chapters", "duration_per_chapter", "resolution"],
        },
        "script2video": {
            "name": "Script2Video",
            "description": "标准剧本 → 视频",
            "params": ["resolution", "style"],
        },
        "autocameo": {
            "name": "AutoCameo",
            "description": "照片客串 → 视频",
            "params": ["photo_path", "resolution"],
        },
    }
    
    def __init__(self):
        self._skill = None
        self._initialized = False
        self._tasks: Dict[str, Dict] = {}
        
        self._init_skill()
    
    def _init_skill(self):
        """初始化 ViMax 技能"""
        try:
            from skills.vimax import get_vimax_skill
            self._skill = get_vimax_skill()
            self._initialized = True
            logger.info("ViMax 子智能体初始化成功")
        except Exception as e:
            logger.warning(f"ViMax 技能初始化失败: {e}")
            logger.info("ViMax SDK 未安装，将使用模拟模式")
    
    def handle(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        同步调用入口 — 供 SubAgentRegistry.invoke() 使用
        
        Args:
            input_data: 输入数据
                - workflow: 工作流类型
                - input/message/prompt: 输入内容
                - params: 可选参数
        
        Returns:
            Dict: 执行结果
        """
        if not self._initialized:
            return self._handle_mock(input_data)
        
        try:
            result = self._skill.execute(input_data)
            if result.get("success"):
                logger.info(f"ViMax 任务执行成功: {result.get('task_id')}")
            else:
                logger.warning(f"ViMax 任务执行失败: {result.get('error')}")
            return result
        except Exception as e:
            logger.error(f"ViMax 子智能体执行失败: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    async def async_handle(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        异步调用入口
        
        Args:
            input_data: 输入数据
        
        Returns:
            Dict: 执行结果
        """
        if not self._initialized:
            return self._handle_mock(input_data)
        
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self._skill.execute, input_data)
        return result
    
    def _handle_mock(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        模拟模式处理 — 当 ViMax SDK 未安装时返回模拟结果
        
        用于演示和开发目的，不实际调用视频生成 API。
        """
        task_id = str(uuid.uuid4())[:8]
        workflow = input_data.get("workflow", "idea2video")
        input_content = input_data.get("input", input_data.get("message", ""))
        
        mock_result = {
            "success": True,
            "task_id": task_id,
            "workflow": workflow,
            "workflow_name": self.WORKFLOWS.get(workflow, {}).get("name", workflow),
            "status": "completed",
            "started_at": datetime.now().isoformat(),
            "completed_at": datetime.now().isoformat(),
            "result": {
                "mock": True,
                "workflow": workflow,
                "input_length": len(input_content),
                "params": input_data.get("params", {}),
                "message": "ViMax SDK 未安装，返回模拟结果。实际使用请安装 vimax SDK 并配置 API 密钥。",
                "video_url": f"https://vimax.example.com/video/{task_id}",
                "preview_url": f"https://vimax.example.com/preview/{task_id}.jpg",
            },
            "video_url": f"https://vimax.example.com/video/{task_id}",
        }
        
        logger.info(f"ViMax 模拟模式: {workflow} -> {task_id}")
        return mock_result
    
    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """
        获取任务状态
        
        Args:
            task_id: 任务 ID
        
        Returns:
            Dict: 任务状态信息
        """
        if self._skill:
            return self._skill.get_status(task_id)
        
        return self._tasks.get(task_id, {"status": "unknown"})
    
    def list_workflows(self) -> Dict[str, Any]:
        """
        列出所有可用工作流
        
        Returns:
            Dict: 工作流列表
        """
        return self.WORKFLOWS
    
    def is_ready(self) -> bool:
        """
        检查子智能体是否就绪
        
        Returns:
            bool: 是否就绪
        """
        return self._initialized
    
    def configure(self, api_keys: Dict[str, str]) -> bool:
        """
        配置 API 密钥
        
        Args:
            api_keys: API 密钥字典
                - GOOGLE_API_KEY: Google API 密钥
                - SEEDANCE_API_KEY: 豆包 Seedance API 密钥
        
        Returns:
            bool: 是否配置成功
        """
        for key, value in api_keys.items():
            os.environ[key] = value
        
        if self._skill:
            self._skill._check_api_keys()
        
        logger.info(f"ViMax 已配置 API 密钥: {list(api_keys.keys())}")
        return True


def get_vimax_subagent() -> ViMaxSubagent:
    """获取或创建 ViMax 子智能体实例"""
    return ViMaxSubagent()


def register_vimax_subagent(registry=None):
    """注册 ViMax 子智能体到 SubAgentRegistry"""
    if registry is None:
        from subagents.base import SubAgentRegistry
        registry = SubAgentRegistry()
    
    agent = ViMaxSubagent()
    registry.register(agent.NAME, agent.DESCRIPTION, agent.CAPABILITIES, agent.handle)
    logger.info("ViMax 子智能体已注册")
    return agent