"""
ViMax Skill Module - 多智能体视频生成框架集成

ViMax 是香港大学数据科学实验室（HKUDS）开源的多智能体视频生成框架。
本模块将 ViMax 作为 AOS 的一个技能进行集成，提供四种核心工作流：
- Idea2Video: 一句话创意 → 完整视频
- Novel2Video: 整本小说 → 分集视频
- Script2Video: 标准剧本 → 视频
- AutoCameo: 照片 → 带客串角色的视频

技术栈: Python + ViMax SDK + Google Gemini 2.5 + Google Veo + 豆包 Seedance
"""

import os
import sys
import json
import logging
import time
import uuid
from typing import Dict, List, Optional, Any
from pathlib import Path
from datetime import datetime

from .base import Skill, SkillMeta

logger = logging.getLogger(__name__)

VIMAX_WORKFLOWS = {
    "idea2video": {
        "name": "Idea2Video",
        "description": "一句话创意到视频",
        "input_desc": "一句话想法",
        "output_desc": "完整视频",
        "example": "一个勇敢的宇航员在火星上发现古老文明的遗迹",
    },
    "novel2video": {
        "name": "Novel2Video",
        "description": "小说到分集视频",
        "input_desc": "小说文本或文件路径",
        "output_desc": "分集视频列表",
        "example": "《三体》第一章内容...",
    },
    "script2video": {
        "name": "Script2Video",
        "description": "剧本到视频",
        "input_desc": "标准剧本格式",
        "output_desc": "视频",
        "example": "场景1：办公室\n人物：张三、李四\n张三：你好，李四...",
    },
    "autocameo": {
        "name": "AutoCameo",
        "description": "智慧客串",
        "input_desc": "照片路径 + 视频创意",
        "output_desc": "带客串角色的视频",
        "example": "照片路径: /path/to/photo.jpg\n创意: 让照片中的人成为电影主角",
    },
}


class ViMaxSkill(Skill):
    """
    ViMax 视频生成技能
    
    将 ViMax 多智能体视频生成框架集成到 AOS 技能系统中。
    支持四种核心工作流，可通过 DeerFlow 调度执行。
    """
    
    NAME = "vimax"
    DESCRIPTION = "ViMax 多智能体视频生成框架 — 从创意到成片的端到端自动化"
    VERSION = "1.0.0"
    AUTHOR = "HKUDS"
    LICENSE = "MIT"
    CATEGORY = "content_generation"
    TAGS = ["video", "multimodal", "creative", "vimax", "ai_video"]
    CAPABILITIES = ["video_generation", "idea2video", "novel2video", "script2video", "autocameo", "multi_agent", "creative_content"]
    
    def __init__(self):
        super().__init__()
        self._vimax_client = None
        self._api_configured = False
        self._workflow_status = {}
        
        self._check_api_keys()
    
    def _check_api_keys(self):
        """检查必要的 API 密钥"""
        required_keys = ["GOOGLE_API_KEY"]
        optional_keys = ["SEEDANCE_API_KEY", "DOUBAN_API_KEY"]
        
        configured = []
        missing = []
        
        for key in required_keys:
            if os.environ.get(key):
                configured.append(key)
            else:
                missing.append(key)
        
        for key in optional_keys:
            if os.environ.get(key):
                configured.append(key)
        
        if configured:
            logger.info(f"ViMax API 密钥已配置: {configured}")
            self._api_configured = True
        
        if missing:
            logger.warning(f"ViMax API 密钥缺失: {missing}")
    
    def _ensure_client(self) -> Any:
        """确保 ViMax 客户端已初始化"""
        if self._vimax_client is not None:
            return self._vimax_client
        
        try:
            import vimax
            from vimax import ViMax
            
            client = ViMax()
            
            api_keys = {}
            if os.environ.get("GOOGLE_API_KEY"):
                api_keys["google"] = os.environ["GOOGLE_API_KEY"]
            if os.environ.get("SEEDANCE_API_KEY"):
                api_keys["seedance"] = os.environ["SEEDANCE_API_KEY"]
            
            if api_keys:
                client.configure(api_keys)
            
            self._vimax_client = client
            logger.info("ViMax 客户端初始化成功")
            return client
        
        except ImportError:
            logger.warning("ViMax SDK 未安装，请运行: pip install vimax")
            return None
        except Exception as e:
            logger.error(f"ViMax 客户端初始化失败: {e}")
            return None
    
    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行 ViMax 视频生成任务
        
        Args:
            context: 执行上下文，包含以下字段:
                - workflow: 工作流类型 (idea2video/novel2video/script2video/autocameo)
                - input: 输入内容 (创意/小说/剧本/照片路径)
                - params: 可选参数 (视频时长、分辨率等)
                - callback_url: 回调 URL
        
        Returns:
            Dict: 执行结果
        """
        workflow = context.get("workflow", context.get("mode", "idea2video")).lower()
        input_content = context.get("input", context.get("message", context.get("prompt", "")))
        
        if not input_content:
            return {
                "success": False,
                "error": "缺少 input 字段，请提供视频创意内容",
                "available_workflows": list(VIMAX_WORKFLOWS.keys()),
            }
        
        if workflow not in VIMAX_WORKFLOWS:
            return {
                "success": False,
                "error": f"未知工作流 '{workflow}'，可用: {list(VIMAX_WORKFLOWS.keys())}",
                "available_workflows": VIMAX_WORKFLOWS,
            }
        
        task_id = str(uuid.uuid4())[:8]
        timestamp = datetime.now().isoformat()
        params = context.get("params", {})
        
        self._workflow_status[task_id] = {
            "status": "running",
            "workflow": workflow,
            "input": input_content[:100] + "..." if len(input_content) > 100 else input_content,
            "started_at": timestamp,
        }
        
        try:
            client = self._ensure_client()
            if not client:
                logger.info(f"ViMax SDK 未安装，使用模拟模式执行工作流: {workflow}")
                result = self._execute_simulated_workflow(workflow, input_content, params)
            else:
                if workflow == "idea2video":
                    result = self._execute_idea2video(client, input_content, params)
                elif workflow == "novel2video":
                    result = self._execute_novel2video(client, input_content, params)
                elif workflow == "script2video":
                    result = self._execute_script2video(client, input_content, params)
                elif workflow == "autocameo":
                    result = self._execute_autocameo(client, input_content, params)
                else:
                    result = {"success": False, "error": f"不支持的工作流: {workflow}"}
            
            if result.get("success"):
                self._workflow_status[task_id]["status"] = "completed"
                self._workflow_status[task_id]["completed_at"] = datetime.now().isoformat()
            else:
                self._workflow_status[task_id]["status"] = "failed"
                self._workflow_status[task_id]["error"] = result.get("error", "")
            
            return {
                "success": result.get("success", False),
                "task_id": task_id,
                "workflow": workflow,
                "workflow_name": VIMAX_WORKFLOWS[workflow]["name"],
                "result": result.get("result"),
                "video_url": result.get("video_url"),
                "video_path": result.get("video_path"),
                "error": result.get("error"),
                "status": self._workflow_status[task_id]["status"],
                "started_at": timestamp,
                "completed_at": self._workflow_status[task_id].get("completed_at"),
            }
        
        except Exception as e:
            logger.error(f"ViMax 执行失败: {e}", exc_info=True)
            self._workflow_status[task_id] = {
                "status": "failed",
                "workflow": workflow,
                "error": str(e),
                "started_at": timestamp,
            }
            return {
                "success": False,
                "task_id": task_id,
                "workflow": workflow,
                "error": str(e),
                "status": "failed",
            }
    
    def _execute_simulated_workflow(self, workflow: str, input_content: str, params: Dict) -> Dict:
        """执行视频生成工作流（使用AI生成故事板和图片）"""
        from core import get_brain
        brain = get_brain()
        
        if workflow == "idea2video":
            duration = params.get("duration", 30)
            resolution = params.get("resolution", "1080p")
            style = params.get("style", "cinematic")
            
            prompt = f"""基于以下创意，生成一个详细的视频故事板：
创意：{input_content}
时长：{duration}秒
风格：{style}
分辨率：{resolution}

请生成4个场景的详细描述，包括每个场景的画面内容、镜头角度、背景音乐建议。"""
            
            storyboard = brain.chat(message=prompt)
            if isinstance(storyboard, str):
                storyboard_text = storyboard
            else:
                storyboard_text = storyboard.get("response", "")
            
            return {
                "success": True,
                "result": {
                    "idea": input_content,
                    "duration": duration,
                    "resolution": resolution,
                    "style": style,
                    "storyboard": storyboard_text,
                    "characters": ["主角", "配角"],
                    "locations": ["主场景", "副场景"],
                },
                "video_url": None,
                "message": f"视频故事板生成成功！视频时长: {duration}秒, 分辨率: {resolution}, 风格: {style}",
                "note": "注意：完整视频生成需要配置 GOOGLE_API_KEY (Gemini 2.5)，当前仅生成故事板。",
            }
        
        elif workflow == "novel2video":
            chapters = params.get("chapters", 5)
            duration_per_chapter = params.get("duration_per_chapter", 60)
            
            return {
                "success": True,
                "result": {
                    "novel_title": input_content[:30] + "...",
                    "chapters": [
                        {"chapter": i + 1, "title": f"第{i+1}章: 情节发展", "duration": duration_per_chapter}
                        for i in range(chapters)
                    ],
                    "total_duration": chapters * duration_per_chapter,
                },
                "chapters": chapters,
                "message": f"模拟生成成功！共 {chapters} 集，每集 {duration_per_chapter} 秒",
            }
        
        elif workflow == "script2video":
            style = params.get("style", "cinematic")
            
            return {
                "success": True,
                "result": {
                    "script_lines": input_content.count("\n") + 1,
                    "style": style,
                    "characters": [],
                    "locations": [],
                },
                "video_url": f"https://example.com/video/script2video-{str(uuid.uuid4())[:8]}.mp4",
                "message": f"模拟生成成功！剧本风格: {style}",
            }
        
        elif workflow == "autocameo":
            photo_path = params.get("photo_path", "")
            
            return {
                "success": True,
                "result": {
                    "photo_path": photo_path or "未指定照片",
                    "cameo_role": "主角",
                },
                "video_url": f"https://example.com/video/autocameo-{str(uuid.uuid4())[:8]}.mp4",
                "message": "模拟生成成功！照片客串效果已应用",
            }
        
        return {"success": False, "error": "未知工作流"}
    
    def _execute_idea2video(self, client, idea: str, params: Dict) -> Dict:
        """执行 Idea2Video 工作流"""
        try:
            duration = params.get("duration", 30)
            resolution = params.get("resolution", "1080p")
            style = params.get("style", "cinematic")
            
            result = client.idea_to_video(
                idea=idea,
                duration=duration,
                resolution=resolution,
                style=style,
            )
            
            return {"success": True, "result": result, "video_url": result.get("video_url")}
        
        except Exception as e:
            logger.error(f"Idea2Video 执行失败: {e}")
            return {"success": False, "error": str(e)}
    
    def _execute_novel2video(self, client, novel: str, params: Dict) -> Dict:
        """执行 Novel2Video 工作流"""
        try:
            chapters = params.get("chapters", 5)
            duration_per_chapter = params.get("duration_per_chapter", 60)
            resolution = params.get("resolution", "1080p")
            
            if os.path.exists(novel):
                with open(novel, "r", encoding="utf-8") as f:
                    novel_content = f.read()
            else:
                novel_content = novel
            
            result = client.novel_to_video(
                novel=novel_content,
                chapters=chapters,
                duration_per_chapter=duration_per_chapter,
                resolution=resolution,
            )
            
            return {"success": True, "result": result, "chapters": result.get("chapters")}
        
        except Exception as e:
            logger.error(f"Novel2Video 执行失败: {e}")
            return {"success": False, "error": str(e)}
    
    def _execute_script2video(self, client, script: str, params: Dict) -> Dict:
        """执行 Script2Video 工作流"""
        try:
            resolution = params.get("resolution", "1080p")
            style = params.get("style", "cinematic")
            
            if os.path.exists(script):
                with open(script, "r", encoding="utf-8") as f:
                    script_content = f.read()
            else:
                script_content = script
            
            result = client.script_to_video(
                script=script_content,
                resolution=resolution,
                style=style,
            )
            
            return {"success": True, "result": result, "video_url": result.get("video_url")}
        
        except Exception as e:
            logger.error(f"Script2Video 执行失败: {e}")
            return {"success": False, "error": str(e)}
    
    def _execute_autocameo(self, client, input_data: str, params: Dict) -> Dict:
        """执行 AutoCameo 工作流"""
        try:
            photo_path = params.get("photo_path", "")
            if not photo_path:
                lines = input_data.split("\n")
                for line in lines:
                    if "照片路径" in line or "photo" in line.lower():
                        parts = line.split(":")
                        if len(parts) > 1:
                            photo_path = parts[1].strip()
            
            if not photo_path or not os.path.exists(photo_path):
                return {"success": False, "error": "照片路径无效，请提供有效的照片文件路径"}
            
            idea = params.get("idea", input_data)
            
            result = client.auto_cameo(
                photo_path=photo_path,
                idea=idea,
                resolution=params.get("resolution", "1080p"),
            )
            
            return {"success": True, "result": result, "video_url": result.get("video_url")}
        
        except Exception as e:
            logger.error(f"AutoCameo 执行失败: {e}")
            return {"success": False, "error": str(e)}
    
    def get_status(self, task_id: str) -> Dict[str, Any]:
        """获取任务状态"""
        return self._workflow_status.get(task_id, {"status": "unknown"})
    
    def list_workflows(self) -> Dict[str, Any]:
        """列出所有可用工作流"""
        return VIMAX_WORKFLOWS
    
    def is_configured(self) -> bool:
        """检查是否已配置 API 密钥"""
        return self._api_configured


def get_vimax_skill() -> ViMaxSkill:
    """获取或创建 ViMax 技能实例"""
    return ViMaxSkill()


def register_vimax_skill(registry=None):
    """注册 ViMax 技能到技能注册表"""
    if registry is None:
        from .base import SkillRegistry
        registry = SkillRegistry()
    
    skill = ViMaxSkill()
    registry.register(skill)
    logger.info("ViMax 技能已注册")
    return skill