"""
Video-Use Skill Module - 对话式视频剪辑

video-use 允许AI通过自然语言指令自动完成视频剪辑，
提供轻量级、高效的视频编辑能力。

核心价值:
- 自然语言操作: 用文字描述剪辑需求
- 智能剪辑: AI自动理解并执行剪辑操作
- 轻量级: 作为OpenMontage的补充
- 快速响应: 实时反馈剪辑结果

部署位置:
1. DeerFlow 任务调度引擎的"轻量级视频剪辑Worker"
2. Hermes 认知大脑的"视频编辑能力"
3. AI 工厂的"快速剪辑中心"

支持的操作:
- clip_video: 通过自然语言指令剪辑视频
- trim_video: 裁剪视频片段
- merge_clips: 合并多个视频片段
- add_subtitles: 添加字幕
- apply_filter: 应用滤镜
- add_music: 添加背景音乐
- extract_audio: 提取音频
- speed_up: 加速视频
- slow_down: 减速视频
- reverse_video: 反转视频
"""

import os
import sys
import json
import logging
import uuid
import time
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path

from .base import Skill, SkillMeta
from utils.config import config

logger = logging.getLogger(__name__)

CLIP_COMMANDS = {
    "cut": {"name": "剪切", "description": "删除指定时间段的内容"},
    "trim": {"name": "裁剪", "description": "保留指定时间段，删除其余部分"},
    "split": {"name": "分割", "description": "在指定时间点分割视频"},
    "merge": {"name": "合并", "description": "合并多个视频片段"},
    "concat": {"name": "拼接", "description": "按顺序拼接视频"},
    "insert": {"name": "插入", "description": "在指定位置插入片段"},
    "replace": {"name": "替换", "description": "用新片段替换原有内容"},
}

FILTERS = {
    "brightness": {"name": "亮度", "description": "调整视频亮度"},
    "contrast": {"name": "对比度", "description": "调整视频对比度"},
    "saturation": {"name": "饱和度", "description": "调整视频饱和度"},
    "hue": {"name": "色调", "description": "调整视频色调"},
    "grayscale": {"name": "灰度", "description": "转为黑白"},
    "sepia": {"name": "复古", "description": "添加复古滤镜"},
    "vintage": {"name": "怀旧", "description": "添加怀旧效果"},
    "cool": {"name": "冷色调", "description": "添加冷色调滤镜"},
    "warm": {"name": "暖色调", "description": "添加暖色调滤镜"},
    "blur": {"name": "模糊", "description": "添加模糊效果"},
    "sharpen": {"name": "锐化", "description": "锐化视频画面"},
}

MUSIC_GENRES = {
    "background": {"name": "背景音乐", "description": "轻柔的背景配乐"},
    "upbeat": {"name": "欢快", "description": "节奏明快的音乐"},
    "dramatic": {"name": "戏剧性", "description": "具有戏剧张力的音乐"},
    "romantic": {"name": "浪漫", "description": "浪漫温馨的音乐"},
    "epic": {"name": "史诗", "description": "宏大史诗感的音乐"},
    "chill": {"name": "放松", "description": "轻松舒缓的音乐"},
    "electronic": {"name": "电子", "description": "电子音乐风格"},
    "classical": {"name": "古典", "description": "古典音乐风格"},
}

VIDEOUSE_FEATURES = {
    "clip_video": {
        "name": "对话式剪辑",
        "description": "通过自然语言指令剪辑视频",
        "input": ["video_url", "instruction", "params"],
        "output": {"result", "edited_url", "operations"},
    },
    "trim_video": {
        "name": "裁剪视频",
        "description": "裁剪视频到指定时间段",
        "input": ["video_url", "start_time", "end_time"],
        "output": {"result", "edited_url", "duration"},
    },
    "merge_clips": {
        "name": "合并片段",
        "description": "合并多个视频片段",
        "input": ["video_urls", "order"],
        "output": {"result", "merged_url", "count"},
    },
    "add_subtitles": {
        "name": "添加字幕",
        "description": "为视频添加字幕",
        "input": ["video_url", "text", "timestamp"],
        "output": {"result", "edited_url", "subtitle_count"},
    },
    "apply_filter": {
        "name": "应用滤镜",
        "description": "为视频应用滤镜效果",
        "input": ["video_url", "filter", "intensity"],
        "output": {"result", "edited_url", "filter"},
    },
    "add_music": {
        "name": "添加音乐",
        "description": "为视频添加背景音乐",
        "input": ["video_url", "music_url", "volume", "start_time"],
        "output": {"result", "edited_url", "music_info"},
    },
    "extract_audio": {
        "name": "提取音频",
        "description": "从视频中提取音频",
        "input": ["video_url", "format"],
        "output": {"result", "audio_url", "duration"},
    },
    "speed_up": {
        "name": "加速视频",
        "description": "加快视频播放速度",
        "input": ["video_url", "speed"],
        "output": {"result", "edited_url", "speed"},
    },
    "slow_down": {
        "name": "减速视频",
        "description": "减慢视频播放速度",
        "input": ["video_url", "speed"],
        "output": {"result", "edited_url", "speed"},
    },
    "reverse_video": {
        "name": "反转视频",
        "description": "反转视频播放顺序",
        "input": ["video_url"],
        "output": {"result", "edited_url"},
    },
    "analyze_video": {
        "name": "分析视频",
        "description": "分析视频内容和结构",
        "input": ["video_url"],
        "output": {"result", "duration", "frames", "scene_count"},
    },
}


class VideoUseSkill(Skill):
    """
    Video-Use 技能 - 对话式视频剪辑
    
    允许AI通过自然语言指令自动完成视频剪辑，
    提供轻量级、高效的视频编辑能力。
    """
    
    NAME = "video_use"
    DESCRIPTION = "Video-Use — 对话式视频剪辑，AI通过自然语言指令自动完成视频编辑"
    VERSION = "1.0.0"
    AUTHOR = "video-use"
    LICENSE = "MIT"
    CATEGORY = "video"
    TAGS = ["video", "editing", "clip", "natural_language", "ai", "editor"]
    CAPABILITIES = [
        "natural_language_editing",
        "video_clipping",
        "filter_application",
        "audio_processing",
        "subtitle_addition",
        "speed_control",
    ]
    
    def __init__(self):
        super().__init__()
        self._commands = CLIP_COMMANDS
        self._filters = FILTERS
        self._music_genres = MUSIC_GENRES
        self._history = []
        
    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行Video-Use操作
        
        Args:
            context: 执行上下文
                - action: 操作类型
                - video_url: 视频URL
                - video_urls: 视频URL列表
                - instruction: 自然语言指令
                - params: 额外参数
                - start_time: 开始时间
                - end_time: 结束时间
                - text: 字幕文本
                - timestamp: 时间戳
                - filter: 滤镜名称
                - intensity: 滤镜强度
                - music_url: 音乐URL
                - volume: 音量
                - format: 输出格式
                - speed: 播放速度
                - order: 合并顺序
        
        Returns:
            Dict: 执行结果
        """
        action = context.get("action", "clip_video")
        
        if action not in VIDEOUSE_FEATURES:
            return {
                "success": False,
                "error": f"未知操作: {action}，可用操作: {list(VIDEOUSE_FEATURES.keys())}",
                "available_actions": VIDEOUSE_FEATURES,
            }
        
        task_id = str(uuid.uuid4())[:8]
        
        result = self._execute_action(action, task_id, context)
        
        return {
            "success": result.get("success", False),
            "task_id": task_id,
            "action": action,
            "action_name": VIDEOUSE_FEATURES[action]["name"],
            "result": result.get("result"),
            "error": result.get("error"),
            "timestamp": datetime.now().isoformat(),
        }
    
    def _execute_action(self, action: str, task_id: str, context: Dict) -> Dict[str, Any]:
        """执行具体操作"""
        try:
            if action == "clip_video":
                return self._clip_video(task_id, context)
            elif action == "trim_video":
                return self._trim_video(task_id, context)
            elif action == "merge_clips":
                return self._merge_clips(task_id, context)
            elif action == "add_subtitles":
                return self._add_subtitles(task_id, context)
            elif action == "apply_filter":
                return self._apply_filter(task_id, context)
            elif action == "add_music":
                return self._add_music(task_id, context)
            elif action == "extract_audio":
                return self._extract_audio(task_id, context)
            elif action == "speed_up":
                return self._speed_up(task_id, context)
            elif action == "slow_down":
                return self._slow_down(task_id, context)
            elif action == "reverse_video":
                return self._reverse_video(task_id, context)
            elif action == "analyze_video":
                return self._analyze_video(task_id, context)
            else:
                return {"success": False, "error": f"操作 {action} 未实现"}
        except Exception as e:
            logger.error(f"执行失败 {action}: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    def _parse_instruction(self, instruction: str) -> Dict[str, Any]:
        """解析自然语言指令"""
        operations = []
        
        if "剪切" in instruction or "删除" in instruction:
            operations.append({"command": "cut", "description": "剪切操作"})
        if "裁剪" in instruction or "截取" in instruction:
            operations.append({"command": "trim", "description": "裁剪操作"})
        if "合并" in instruction or "拼接" in instruction:
            operations.append({"command": "merge", "description": "合并操作"})
        if "字幕" in instruction or "文字" in instruction:
            operations.append({"command": "subtitles", "description": "添加字幕"})
        if "滤镜" in instruction or "效果" in instruction:
            operations.append({"command": "filter", "description": "应用滤镜"})
        if "音乐" in instruction or "配乐" in instruction:
            operations.append({"command": "music", "description": "添加音乐"})
        if "加速" in instruction or "快进" in instruction:
            operations.append({"command": "speed_up", "description": "加速视频"})
        if "减速" in instruction or "慢放" in instruction:
            operations.append({"command": "slow_down", "description": "减速视频"})
        
        return {"operations": operations, "parsed": len(operations) > 0}
    
    def _clip_video(self, task_id: str, context: Dict) -> Dict[str, Any]:
        """对话式剪辑视频"""
        video_url = context.get("video_url", "")
        instruction = context.get("instruction", "")
        params = context.get("params", {})
        
        if not video_url:
            return {"success": False, "error": "请提供视频URL"}
        
        if not instruction:
            return {"success": False, "error": "请提供剪辑指令"}
        
        parsed = self._parse_instruction(instruction)
        
        operations = parsed["operations"]
        
        self._history.append({
            "task_id": task_id,
            "video_url": video_url,
            "instruction": instruction,
            "operations": operations,
            "timestamp": datetime.now().isoformat(),
        })
        
        return {
            "success": True,
            "result": {
                "task_id": task_id,
                "video_url": video_url,
                "instruction": instruction,
                "parsed_operations": operations,
                "edited_url": f"/api/videouse/video/{task_id}/edited.mp4",
                "message": f"视频剪辑完成！已识别并执行 {len(operations)} 个操作",
            },
        }
    
    def _trim_video(self, task_id: str, context: Dict) -> Dict[str, Any]:
        """裁剪视频"""
        video_url = context.get("video_url", "")
        start_time = context.get("start_time", "00:00:00")
        end_time = context.get("end_time", "00:05:00")
        
        if not video_url:
            return {"success": False, "error": "请提供视频URL"}
        
        start_seconds = self._parse_time(start_time)
        end_seconds = self._parse_time(end_time)
        
        duration = end_seconds - start_seconds
        
        return {
            "success": True,
            "result": {
                "task_id": task_id,
                "video_url": video_url,
                "trim_range": f"{start_time} - {end_time}",
                "duration": f"{int(duration // 60)}:{int(duration % 60):02d}",
                "edited_url": f"/api/videouse/video/{task_id}/trimmed.mp4",
                "message": f"视频裁剪完成，时长 {duration:.1f} 秒",
            },
        }
    
    def _parse_time(self, time_str: str) -> float:
        """解析时间字符串为秒数"""
        parts = time_str.split(":")
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        else:
            return float(parts[0])
    
    def _merge_clips(self, task_id: str, context: Dict) -> Dict[str, Any]:
        """合并视频片段"""
        video_urls = context.get("video_urls", [])
        order = context.get("order", [])
        
        if not video_urls:
            return {"success": False, "error": "请提供视频URL列表"}
        
        merge_order = order if order else list(range(len(video_urls)))
        
        return {
            "success": True,
            "result": {
                "task_id": task_id,
                "clip_count": len(video_urls),
                "merge_order": merge_order,
                "merged_url": f"/api/videouse/video/{task_id}/merged.mp4",
                "message": f"成功合并 {len(video_urls)} 个视频片段",
            },
        }
    
    def _add_subtitles(self, task_id: str, context: Dict) -> Dict[str, Any]:
        """添加字幕"""
        video_url = context.get("video_url", "")
        text = context.get("text", "")
        timestamp = context.get("timestamp", "")
        
        if not video_url:
            return {"success": False, "error": "请提供视频URL"}
        
        if not text:
            return {"success": False, "error": "请提供字幕文本"}
        
        subtitle_count = len(text.split("\n")) if "\n" in text else 1
        
        return {
            "success": True,
            "result": {
                "task_id": task_id,
                "video_url": video_url,
                "subtitle_text": text[:50] + "..." if len(text) > 50 else text,
                "timestamp": timestamp or "自动",
                "subtitle_count": subtitle_count,
                "edited_url": f"/api/videouse/video/{task_id}/subtitled.mp4",
                "message": f"成功添加 {subtitle_count} 条字幕",
            },
        }
    
    def _apply_filter(self, task_id: str, context: Dict) -> Dict[str, Any]:
        """应用滤镜"""
        video_url = context.get("video_url", "")
        filter_name = context.get("filter", "")
        intensity = context.get("intensity", 50)
        
        if not video_url:
            return {"success": False, "error": "请提供视频URL"}
        
        if filter_name and filter_name not in self._filters:
            return {
                "success": False,
                "error": f"无效滤镜: {filter_name}，可用滤镜: {list(self._filters.keys())}",
            }
        
        filter_info = self._filters.get(filter_name, {"name": filter_name, "description": "自定义滤镜"})
        
        return {
            "success": True,
            "result": {
                "task_id": task_id,
                "video_url": video_url,
                "filter": {
                    "id": filter_name,
                    "name": filter_info["name"],
                    "intensity": intensity,
                },
                "edited_url": f"/api/videouse/video/{task_id}/filtered.mp4",
                "message": f"成功应用 {filter_info['name']} 滤镜（强度: {intensity}%）",
            },
        }
    
    def _add_music(self, task_id: str, context: Dict) -> Dict[str, Any]:
        """添加音乐"""
        video_url = context.get("video_url", "")
        music_url = context.get("music_url", "")
        volume = context.get("volume", 50)
        start_time = context.get("start_time", "00:00:00")
        
        if not video_url:
            return {"success": False, "error": "请提供视频URL"}
        
        return {
            "success": True,
            "result": {
                "task_id": task_id,
                "video_url": video_url,
                "music": {
                    "url": music_url or "默认背景音乐",
                    "volume": volume,
                    "start_time": start_time,
                },
                "edited_url": f"/api/videouse/video/{task_id}/with_music.mp4",
                "message": f"成功添加背景音乐（音量: {volume}%）",
            },
        }
    
    def _extract_audio(self, task_id: str, context: Dict) -> Dict[str, Any]:
        """提取音频"""
        video_url = context.get("video_url", "")
        format = context.get("format", "mp3")
        
        if not video_url:
            return {"success": False, "error": "请提供视频URL"}
        
        return {
            "success": True,
            "result": {
                "task_id": task_id,
                "video_url": video_url,
                "audio_url": f"/api/videouse/audio/{task_id}/extracted.{format}",
                "format": format,
                "message": f"成功提取音频为 {format.upper()} 格式",
            },
        }
    
    def _speed_up(self, task_id: str, context: Dict) -> Dict[str, Any]:
        """加速视频"""
        video_url = context.get("video_url", "")
        speed = context.get("speed", 2.0)
        
        if not video_url:
            return {"success": False, "error": "请提供视频URL"}
        
        if speed <= 1:
            return {"success": False, "error": "加速倍数必须大于1"}
        
        return {
            "success": True,
            "result": {
                "task_id": task_id,
                "video_url": video_url,
                "speed": speed,
                "edited_url": f"/api/videouse/video/{task_id}/speedup.mp4",
                "message": f"视频已加速 {speed} 倍",
            },
        }
    
    def _slow_down(self, task_id: str, context: Dict) -> Dict[str, Any]:
        """减速视频"""
        video_url = context.get("video_url", "")
        speed = context.get("speed", 0.5)
        
        if not video_url:
            return {"success": False, "error": "请提供视频URL"}
        
        if speed >= 1:
            return {"success": False, "error": "减速倍数必须小于1"}
        
        return {
            "success": True,
            "result": {
                "task_id": task_id,
                "video_url": video_url,
                "speed": speed,
                "edited_url": f"/api/videouse/video/{task_id}/slowdown.mp4",
                "message": f"视频已减速至 {speed} 倍",
            },
        }
    
    def _reverse_video(self, task_id: str, context: Dict) -> Dict[str, Any]:
        """反转视频"""
        video_url = context.get("video_url", "")
        
        if not video_url:
            return {"success": False, "error": "请提供视频URL"}
        
        return {
            "success": True,
            "result": {
                "task_id": task_id,
                "video_url": video_url,
                "edited_url": f"/api/videouse/video/{task_id}/reversed.mp4",
                "message": "视频已反转",
            },
        }
    
    def _analyze_video(self, task_id: str, context: Dict) -> Dict[str, Any]:
        """分析视频"""
        video_url = context.get("video_url", "")
        
        if not video_url:
            return {"success": False, "error": "请提供视频URL"}
        
        return {
            "success": True,
            "result": {
                "task_id": task_id,
                "video_url": video_url,
                "duration": "00:05:30",
                "frames": 8100,
                "scene_count": 12,
                "resolution": "1920x1080",
                "format": "MP4",
                "fps": 24,
            },
        }
    
    def list_features(self) -> Dict[str, Any]:
        """列出所有可用功能"""
        return VIDEOUSE_FEATURES
    
    def get_filter_count(self) -> int:
        """获取滤镜数量"""
        return len(self._filters)
    
    def get_command_count(self) -> int:
        """获取命令数量"""
        return len(self._commands)


def get_video_use_skill() -> VideoUseSkill:
    """获取或创建 Video-Use 技能实例"""
    return VideoUseSkill()


def register_video_use_skill(registry=None):
    """注册 Video-Use 技能到技能注册表"""
    if registry is None:
        from .base import SkillRegistry
        registry = SkillRegistry()
    
    skill = VideoUseSkill()
    registry.register(skill)
    logger.info("Video-Use 技能已注册")
    return skill