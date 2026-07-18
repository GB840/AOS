"""
ViMax Subagent - 多智能体视频生成子智能体

将 ViMax 作为 DeerFlow 子智能体集成，提供专业级视频生成能力。
可通过 DeerFlow 调度执行，支持异步任务和进度追踪。
"""

import os
import logging
import uuid
import asyncio
from typing import Dict, Any, Optional
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
            # 结构化交接（opt-in）：跑完自动存 IMA。仅真实执行路径到达此处——
            # 模拟模式已在 handle 前置分支直接返回，不会把模拟结果当真交接（不弄虚）。
            self._maybe_store_handoff(input_data, result)
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
    
    def _maybe_store_handoff(self, input_data: Dict[str, Any], result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """opt-in 结构化交接：ViMax 任务跑完自动把执行事实存 IMA 知识库。

        仅在 input_data 显式带 auto_handoff=True 且任务成功时触发；IMA 未配置或
        写失败仅告警，绝不阻断主流程。模拟模式不会到达此处（handle 前置分支已
        拦截），故不会把模拟结果写成真交接（不弄虚）。
        """
        if not input_data.get("auto_handoff") or not result.get("success"):
            return None
        try:
            from core.fabric.handoff import HandoffEnvelope, store_handoff
            workflow = input_data.get("workflow", "unknown")
            task_id = (result.get("task_id") or input_data.get("task_id")
                       or f"vimax-{uuid.uuid4().hex[:8]}")
            res = result.get("result") or {}
            envelope = HandoffEnvelope(
                task_id=str(task_id),
                title=f"ViMax {workflow}",
                summary=f"ViMax 工作流 {workflow} 执行完成，状态 {result.get('status')}。",
                confirmed_facts=[
                    f"workflow={workflow}",
                    f"task_id={task_id}",
                    f"status={result.get('status')}",
                    f"video_url={result.get('video_url') or res.get('video_url') or 'N/A'}",
                ],
                assumptions=["ViMax SDK 已安装并真实执行（非模拟模式）"],
                risk_boundary=["交接仅记录执行事实，不保证成片质量",
                               "video_url 有效性需下游核验"],
                open_questions=["是否需要后续剪辑/发布步骤"],
                handoff_to=input_data.get("handoff_to", "下一手会话/人"),
                source=f"ViMaxSubagent.handle({workflow})",
                tags=["handoff", "vimax", workflow],
            )
            store_res = store_handoff(envelope)
            if store_res.get("success"):
                logger.info("ViMax 自动交接已存 IMA: %s", store_res.get("result"))
            else:
                logger.warning("ViMax 自动交接存 IMA 失败: %s", store_res.get("error"))
            return store_res
        except Exception as e:
            logger.warning("ViMax 自动交接异常（不影响主流程）: %s", e)
            return None

    def _handle_mock(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """SDK 未安装时的诚实降级 —— 修复 P0-4 假成功问题。

        默认返回 success=False（诚实：SDK 没装就是没装，不伪装完成）。
        如需演示/开发用途，显式设置环境变量 AOS_ALLOW_MOCK=1，此时返回
        原 mock 结构但顶层强标 mock=True，绝不混入真实成功路径。
        """
        workflow = input_data.get("workflow", "idea2video")
        input_content = input_data.get("input", input_data.get("message", ""))
        workflow_name = self.WORKFLOWS.get(workflow, {}).get("name", workflow)

        # 默认：诚实失败（修复 P0-4：禁止伪装成功）
        if os.environ.get("AOS_ALLOW_MOCK", "0") != "1":
            logger.warning(
                "ViMax SDK 未初始化，拒绝伪装成功（AOS_ALLOW_MOCK!=1）。workflow=%s", workflow)
            return {
                "success": False,
                "available": False,
                "error": "ViMax SDK 未安装或未初始化",
                "install_hint": "pip install vimax 或参考 tools/fetch-vimax.ps1；"
                                "演示用途可设 AOS_ALLOW_MOCK=1",
                "workflow": workflow,
                "workflow_name": workflow_name,
                "input_length": len(input_content),
            }

        # 显式演示模式：返回 mock 但顶层强标 mock=True（不污染真实成功路径）
        task_id = str(uuid.uuid4())[:8]
        mock_result = {
            "success": True,
            "mock": True,  # 顶层强标，调用方必须区分（修复 P0-4）
            "available": False,
            "task_id": task_id,
            "workflow": workflow,
            "workflow_name": workflow_name,
            "status": "mock_completed",
            "started_at": datetime.now().isoformat(),
            "completed_at": datetime.now().isoformat(),
            "result": {
                "mock": True,
                "workflow": workflow,
                "input_length": len(input_content),
                "params": input_data.get("params", {}),
                "message": "ViMax SDK 未安装，演示模式返回模拟结果（AOS_ALLOW_MOCK=1）。",
                "video_url": f"https://vimax.example.com/video/{task_id}",
                "preview_url": f"https://vimax.example.com/preview/{task_id}.jpg",
            },
            "video_url": f"https://vimax.example.com/video/{task_id}",
        }

        logger.info("ViMax 演示模式（mock）: %s -> %s", workflow, task_id)
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
        from subagents.registry import SubAgentRegistry
        registry = SubAgentRegistry()
    
    agent = ViMaxSubagent()
    registry.register(agent.NAME, agent.DESCRIPTION, agent.CAPABILITIES, agent.handle)
    logger.info("ViMax 子智能体已注册")
    return agent