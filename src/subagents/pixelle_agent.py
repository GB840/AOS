"""
Pixelle-Video Subagent - 短视频自动化生产线子智能体

将 Pixelle-Video 作为 DeerFlow 子智能体集成，提供一键短视频生成能力。

核心特点:
- 文案+配图+配音+合成，一键出片
- 1分钟左右短视频，适合抖音/快手
- 支持Ollama完全离线运行
- Apache-2.0 开源协议（可商用）

技术架构: ComfyUI 流水线模式
本质是一条 "工作流管道"，适合批量生产标准化内容
"""

import logging
import uuid
import asyncio
from typing import Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class PixelleVideoSubagent:
    """
    Pixelle-Video 短视频生成子智能体
    
    通过 DeerFlow 调度，执行短视频自动化生产任务。
    支持完整的工作流：文案生成 → 配图生成 → 语音合成 → 背景音乐 → 视频合成
    
    支持的风格:
    - douyin: 抖音风格（竖屏9:16，快节奏）
    - kuaishou: 快手风格（竖屏9:16，生活化）
    - youtube: YouTube风格（横屏16:9，专业感）
    - weibo: 微博风格（方形1:1，社交分享）
    
    支持的配音:
    - female: 女声（温柔甜美）
    - male: 男声（稳重磁性）
    - child: 童声（活泼可爱）
    - robot: 机器人（科技感）
    """
    
    NAME = "pixelle_video"
    DESCRIPTION = "Pixelle-Video 短视频自动化生产线 — 文案+配图+配音+合成，一键出片"
    CAPABILITIES = [
        "short_video_generation",
        "content_production",
        "video_automation",
        "script_writing",
        "image_generation",
        "text_to_speech",
        "video_synthesis",
        "batch_processing",
    ]
    
    STYLES = {
        "douyin": {"name": "抖音风格", "description": "竖屏9:16，快节奏", "ratio": "9:16"},
        "kuaishou": {"name": "快手风格", "description": "竖屏9:16，生活化", "ratio": "9:16"},
        "youtube": {"name": "YouTube风格", "description": "横屏16:9，专业感", "ratio": "16:9"},
        "weibo": {"name": "微博风格", "description": "方形1:1，社交分享", "ratio": "1:1"},
    }
    
    VOICES = {
        "female": {"name": "女声", "description": "温柔甜美"},
        "male": {"name": "男声", "description": "稳重磁性"},
        "child": {"name": "童声", "description": "活泼可爱"},
        "robot": {"name": "机器人", "description": "科技感"},
    }
    
    STEPS = {
        "script": {"name": "文案生成", "description": "使用LLM生成视频文案"},
        "image": {"name": "配图生成", "description": "根据文案生成配图或视频素材"},
        "audio": {"name": "语音合成", "description": "TTS配音，生成语音解说"},
        "bgm": {"name": "背景音乐", "description": "添加背景音乐"},
        "merge": {"name": "视频合成", "description": "将素材合成为最终视频"},
    }
    
    def __init__(self):
        self._skill = None
        self._initialized = False
        self._tasks: Dict[str, Dict] = {}
        
        self._init_skill()
    
    def _init_skill(self):
        """初始化 Pixelle-Video 技能"""
        try:
            from skills.pixelle_video import get_pixelle_skill
            self._skill = get_pixelle_skill()
            self._initialized = True
            logger.info("Pixelle-Video 子智能体初始化成功")
        except Exception as e:
            logger.warning(f"Pixelle-Video 技能初始化失败: {e}")
            logger.info("将使用内置能力执行短视频生成")
    
    def handle(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        同步调用入口 — 供 SubAgentRegistry.invoke() 使用
        
        Args:
            input_data: 输入数据
                - topic: 视频主题（必填）
                - style: 视频风格（可选，默认douyin）
                - duration: 视频时长（可选，默认60秒）
                - voice: 配音类型（可选，默认female）
        
        Returns:
            Dict: 执行结果
        """
        if not self._initialized:
            return self._handle_fallback(input_data)
        
        try:
            result = self._skill.execute(input_data)
            if result.get("success"):
                logger.info(f"Pixelle-Video 任务执行成功: {result.get('task_id')}")
            else:
                logger.warning(f"Pixelle-Video 任务执行失败: {result.get('error')}")
            return result
        except Exception as e:
            logger.error(f"Pixelle-Video 子智能体执行失败: {e}", exc_info=True)
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
            return self._handle_fallback(input_data)
        
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self._skill.execute, input_data)
        return result
    
    def _handle_fallback(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        降级处理 — 当技能未初始化时使用内置能力
        
        使用 AOS 内置能力执行短视频生成流程。
        """
        task_id = str(uuid.uuid4())[:8]
        topic = input_data.get("topic", input_data.get("input", input_data.get("message", "")))
        style = input_data.get("style", "douyin")
        duration = input_data.get("duration", 60)
        voice = input_data.get("voice", "female")
        
        try:
            from core import get_brain
            
            brain = get_brain()
            
            steps = []
            
            steps.append({"step": "script", "name": "文案生成", "status": "running"})
            
            script_prompt = f"""你是一名专业的短视频文案策划师。请根据以下主题生成一份完整的短视频文案。

主题: {topic}
风格: {self.STYLES[style]['description']}

要求:
1. 文案时长约{duration}秒（约{duration*3}字）
2. 包含吸引人的开头、核心内容和收尾
3. 语言口语化，适合口播
4. 标注出需要配图的场景（用【】标出）

请直接返回文案内容。"""
            
            script_result = brain.chat(message=script_prompt, session_id=f"pixelle-fallback-{task_id}")
            script = script_result.get("response", "")
            
            steps[-1]["status"] = "completed"
            
            import re
            scenes = re.findall(r'【(.*?)】', script)[:5]
            
            steps.append({"step": "image", "name": "配图生成", "status": "running"})
            
            images = []
            for i, scene in enumerate(scenes[:3], 1):
                image_prompt = f"""根据场景生成AI图像提示词：{scene}，主题：{topic}，风格：{self.STYLES[style]['name']}"""
                img_result = brain.chat(message=image_prompt, session_id=f"pixelle-image-{task_id}-{i}")
                images.append({
                    "id": i,
                    "scene": scene,
                    "prompt": img_result.get("response", ""),
                })
            
            steps[-1]["status"] = "completed"
            
            # 诚实降级：audio/bgm/merge 三步未真实执行（fallback 模式无 TTS/BGM/视频合成后端）→
            # 标 skipped 而非 completed，避免假成功（修复 P0-4）
            steps.append({"step": "audio", "name": "语音合成", "status": "skipped", "reason": "fallback 模式无 TTS 后端"})
            steps.append({"step": "bgm", "name": "背景音乐", "status": "skipped", "reason": "fallback 模式无 BGM 库"})
            steps.append({"step": "merge", "name": "视频合成", "status": "skipped", "reason": "fallback 模式无视频合成后端"})
            
            result = {
                "success": True,           # 文案与配图提示词真实生成了
                "partial": True,           # 但音频/BGM/合成未做（修复 P0-4：诚实标识）
                "mock": True,              # 顶层强标 mock，调用方必须区分
                "task_id": task_id,
                "topic": topic,
                "style": self.STYLES[style]["name"],
                "duration": duration,
                "voice": self.VOICES[voice]["name"],
                "status": "partial",       # 修复 P0-4：原为 completed，实际未合成音视频
                "started_at": datetime.now().isoformat(),
                "completed_at": datetime.now().isoformat(),
                "steps": steps,
                "result": {
                    "script": {"full_text": script, "word_count": len(script), "scenes": scenes},
                    "images": images,
                    "audio": None,           # 修复 P0-4：原造假的 segments 数，现诚实为 None
                    "video_url": None,       # 修复 P0-4：原造 example.com 假 URL，现诚实为 None
                    "preview_url": None,
                },
                "message": "降级模式：文案与配图提示词已用 AOS 内置能力生成；"
                           "语音/BGM/视频合成未执行（需安装 Pixelle-Video SDK 或接入真实 TTS/合成后端）",
            }
            
            logger.info("Pixelle-Video 降级模式（partial，未合成音视频）: %s", task_id)
            return result
        
        except Exception as e:
            logger.error(f"Pixelle-Video 降级模式执行失败: {e}")
            return {
                "success": False,
                "task_id": task_id,
                "topic": topic,
                "error": str(e),
                "status": "failed",
            }
    
    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """获取任务状态"""
        if self._skill:
            return self._skill.get_task_status(task_id)
        return self._tasks.get(task_id, {"status": "unknown"})
    
    def list_styles(self) -> Dict[str, Any]:
        """列出所有可用风格"""
        return self.STYLES
    
    def list_voices(self) -> Dict[str, Any]:
        """列出所有可用配音"""
        return self.VOICES
    
    def list_steps(self) -> Dict[str, Any]:
        """列出所有步骤"""
        return self.STEPS
    
    def is_ready(self) -> bool:
        """检查子智能体是否就绪"""
        return self._initialized


def get_pixelle_subagent() -> PixelleVideoSubagent:
    """获取或创建 Pixelle-Video 子智能体实例"""
    return PixelleVideoSubagent()


def register_pixelle_subagent(registry=None):
    """注册 Pixelle-Video 子智能体到 SubAgentRegistry"""
    if registry is None:
        from subagents.registry import SubAgentRegistry
        registry = SubAgentRegistry()
    
    agent = PixelleVideoSubagent()
    registry.register(agent.NAME, agent.DESCRIPTION, agent.CAPABILITIES, agent.handle)
    logger.info("Pixelle-Video 子智能体已注册")
    return agent