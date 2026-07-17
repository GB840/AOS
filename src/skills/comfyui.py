"""
ComfyUI Skill Module - 视觉内容生产引擎

ComfyUI 是一个强大的可视化节点编辑器，用于生成图像和视频。
作为 VisualWorker 嵌入 DeerFlow 调度体系，填补视觉内容生产空白。

核心价值:
- 文生图: 根据提示词生成高质量图像
- 图生视频: 将静态图片转换为动态视频
- 风格迁移: 将图片转换为指定风格
- 视频生视频: 对视频进行风格化处理
- 多工作流模式: 预置多个 workflow.json 模板

部署位置:
1. DeerFlow 调度引擎的"视觉执行节点" - VisualWorker
2. AI 工厂的"图像/视频生产流水线" - 自动化内容生成
3. Hermes 认知大脑的"视觉工具集" - 对话中调用

工作流模板:
- txt2img: 文生图工作流
- img2vid: 图生视频工作流
- style_transfer: 风格迁移工作流
- vid2vid: 视频生视频工作流
"""

import os
import json
import logging
import uuid
import time
import random
import requests
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path

from .base import Skill
from utils.config import config

logger = logging.getLogger(__name__)

COMFYUI_FEATURES = {
    "txt2img": {
        "name": "文生图",
        "description": "根据提示词生成高质量图像",
        "input": ["prompt", "negative_prompt", "width", "height"],
        "output": "image_path",
    },
    "img2vid": {
        "name": "图生视频",
        "description": "将静态图片转换为动态视频",
        "input": ["image_path", "prompt", "duration"],
        "output": "video_path",
    },
    "style_transfer": {
        "name": "风格迁移",
        "description": "将图片转换为指定风格",
        "input": ["image_path", "reference_image", "style_prompt"],
        "output": "image_path",
    },
    "vid2vid": {
        "name": "视频生视频",
        "description": "对视频进行风格化处理",
        "input": ["video_path", "prompt", "style"],
        "output": "video_path",
    },
    "generate": {
        "name": "通用生成",
        "description": "根据工作流模板生成内容",
        "input": ["workflow", "prompt"],
        "output": "file_path",
    },
    "list_workflows": {
        "name": "列出工作流",
        "description": "列出所有可用的工作流模板",
        "input": [],
        "output": "workflows",
    },
    "status": {
        "name": "状态检查",
        "description": "检查 ComfyUI 服务状态",
        "input": [],
        "output": "status",
    },
}

DEFAULT_WORKFLOWS_DIR = os.path.join(os.path.dirname(__file__), "workflows")


class ComfyUISkill(Skill):
    """
    ComfyUI 视觉内容生产技能
    
    提供图像和视频生成能力，支持多种工作流模式。
    通过 ComfyUI HTTP API 封装调用。
    """
    
    NAME = "comfyui"
    DESCRIPTION = "ComfyUI 视觉内容生产引擎 — 文生图、图生视频、风格迁移、视频生视频"
    VERSION = "1.0.0"
    AUTHOR = "ComfyUI"
    LICENSE = "MIT"
    CATEGORY = "content_generation"
    TAGS = ["comfyui", "image", "video", "generation", "visual", "stable-diffusion"]
    CAPABILITIES = ["txt2img", "img2vid", "style_transfer", "vid2vid", "content_generation", "visual_production"]
    
    def __init__(self):
        super().__init__()
        # env 优先于配置文件（更灵活：起服务时 export 一下即可，不必改 .env）。
        self._base_url = (
            os.environ.get("COMFYUI_BASE_URL")
            or getattr(config, "COMFYUI_BASE_URL", "http://localhost:8188")
        )
        # 模型名可配：ComfyUI 装什么 ckpt 各不相同，硬编码必踩。优先 env，
        # 否则常见默认；缺省留空串时 ComfyUI 会明确报「缺模型」而非静默失败。
        self._ckpt_name = (
            os.environ.get("COMFYUI_CKPT_NAME")
            or getattr(config, "COMFYUI_CKPT_NAME", "")
            or "v1-5-pruned-emaonly.ckpt"
        )
        self._client_id = str(uuid.uuid4())
        self._workflows_dir = getattr(config, "COMFYUI_WORKFLOWS_DIR", DEFAULT_WORKFLOWS_DIR)
        self._output_dir = getattr(config, "COMFYUI_OUTPUT_DIR", "./outputs/comfyui")
        self._enabled = getattr(config, "COMFYUI_ENABLED", True)
        self._available = False
        
        Path(self._output_dir).mkdir(parents=True, exist_ok=True)
        Path(self._workflows_dir).mkdir(parents=True, exist_ok=True)
        
        self._check_comfyui()
    
    def _check_comfyui(self):
        """检查 ComfyUI 是否可用"""
        try:
            resp = requests.get(f"{self._base_url}/system_info", timeout=5)
            if resp.status_code == 200:
                self._available = True
                logger.info(f"ComfyUI 可用: {self._base_url}")
            else:
                logger.warning(f"ComfyUI 状态异常: {resp.status_code}")
        except Exception as e:
            logger.warning(f"ComfyUI 不可用: {e}")
    
    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行 ComfyUI 视觉生成任务
        
        Args:
            context: 执行上下文
                - action: 操作类型 (txt2img/img2vid/style_transfer/vid2vid/generate/list_workflows/status)
                - prompt: 提示词
                - negative_prompt: 负向提示词
                - width: 图像宽度
                - height: 图像高度
                - image_path: 输入图像路径
                - video_path: 输入视频路径
                - reference_image: 参考图像路径
                - duration: 视频时长
                - style: 风格类型
                - workflow: 工作流名称
        
        Returns:
            Dict: 执行结果
        """
        action = context.get("action", "txt2img")
        
        if action not in COMFYUI_FEATURES:
            return {
                "success": False,
                "error": f"未知操作: {action}，可用操作: {list(COMFYUI_FEATURES.keys())}",
                "available_actions": COMFYUI_FEATURES,
            }
        
        task_id = str(uuid.uuid4())[:8]
        
        if action == "list_workflows":
            return self._list_workflows(task_id)
        
        if action == "status":
            return self._get_status(task_id)
        
        if not self._available:
            return self._execute_fallback(action, task_id, context)
        
        result = self._execute_enhanced(action, task_id, context)
        
        return {
            "success": result.get("success", False),
            "task_id": task_id,
            "action": action,
            "action_name": COMFYUI_FEATURES[action]["name"],
            "result": result.get("result"),
            "error": result.get("error"),
            "mode": "comfyui" if self._available else "fallback",
            "comfyui_available": self._available,
            "timestamp": datetime.now().isoformat(),
        }
    
    def _execute_enhanced(self, action: str, task_id: str, context: Dict) -> Dict[str, Any]:
        """增强模式执行 — 使用 ComfyUI API"""
        try:
            if action == "txt2img":
                return self._txt2img(context)
            elif action == "img2vid":
                return self._img2vid(context)
            elif action == "style_transfer":
                return self._style_transfer(context)
            elif action == "vid2vid":
                return self._vid2vid(context)
            elif action == "generate":
                return self._generate(context)
            else:
                return {"success": False, "error": f"未知操作: {action}"}
        except Exception as e:
            logger.error(f"ComfyUI 执行失败: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    def _execute_fallback(self, action: str, task_id: str, context: Dict) -> Dict[str, Any]:
        """降级模式执行 — 模拟生成结果"""
        try:
            result_path = os.path.join(self._output_dir, f"{action}_{task_id}_{int(time.time())}.txt")
            
            with open(result_path, "w", encoding="utf-8") as f:
                f.write(f"任务类型: {action}\n")
                f.write(f"提示词: {context.get('prompt', '')}\n")
                f.write(f"时间: {datetime.now().isoformat()}\n")
                f.write("模式: 降级模式 (ComfyUI 不可用)\n")
                f.write("说明: 需要启动 ComfyUI 服务才能生成真实图像/视频\n")
            
            return {
                "success": True,
                "result": {
                    "output_path": result_path,
                    "mode": "fallback",
                    "message": f"已记录任务到 {result_path}",
                    "instructions": self._get_install_instructions(),
                },
            }
        except Exception as e:
            logger.error(f"降级模式执行失败: {e}")
            return {"success": False, "error": str(e)}
    
    def _txt2img(self, context: Dict) -> Dict[str, Any]:
        """文生图"""
        workflow_path = os.path.join(self._workflows_dir, "txt2img.json")
        
        workflow = self._load_workflow(workflow_path)
        if not workflow:
            workflow = self._generate_txt2img_workflow()
        
        prompt = context.get("prompt", "")
        negative_prompt = context.get("negative_prompt", "low quality, blurry, distorted")
        width = context.get("width", 1024)
        height = context.get("height", 768)
        steps = context.get("steps", 20)
        cfg_scale = context.get("cfg_scale", 7)
        
        workflow = self._inject_params(workflow, {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "width": width,
            "height": height,
            "steps": steps,
            "cfg_scale": cfg_scale,
        })
        
        prompt_id = self._submit_prompt(workflow)
        if not prompt_id:
            return {"success": False, "error": "提交任务失败"}
        
        output_path = self._wait_for_result(prompt_id)
        if output_path:
            return {"success": True, "result": {"output_path": output_path}}
        else:
            return {"success": False, "error": "生成超时"}
    
    def _img2vid(self, context: Dict) -> Dict[str, Any]:
        """图生视频"""
        workflow_path = os.path.join(self._workflows_dir, "img2vid.json")
        
        workflow = self._load_workflow(workflow_path)
        if not workflow:
            workflow = self._generate_img2vid_workflow()
        
        image_path = context.get("image_path", "")
        prompt = context.get("prompt", "")
        duration = context.get("duration", 5)
        
        if not image_path:
            return {"success": False, "error": "缺少 image_path 参数"}
        
        workflow = self._inject_params(workflow, {
            "image_path": image_path,
            "prompt": prompt,
            "duration": duration,
        })
        
        prompt_id = self._submit_prompt(workflow)
        if not prompt_id:
            return {"success": False, "error": "提交任务失败"}
        
        output_path = self._wait_for_result(prompt_id)
        if output_path:
            return {"success": True, "result": {"output_path": output_path}}
        else:
            return {"success": False, "error": "生成超时"}
    
    def _style_transfer(self, context: Dict) -> Dict[str, Any]:
        """风格迁移"""
        workflow_path = os.path.join(self._workflows_dir, "style_transfer.json")
        
        workflow = self._load_workflow(workflow_path)
        if not workflow:
            workflow = self._generate_style_transfer_workflow()
        
        image_path = context.get("image_path", "")
        reference_image = context.get("reference_image", "")
        style_prompt = context.get("style_prompt", "")
        
        if not image_path:
            return {"success": False, "error": "缺少 image_path 参数"}
        
        workflow = self._inject_params(workflow, {
            "image_path": image_path,
            "reference_image": reference_image,
            "style_prompt": style_prompt,
        })
        
        prompt_id = self._submit_prompt(workflow)
        if not prompt_id:
            return {"success": False, "error": "提交任务失败"}
        
        output_path = self._wait_for_result(prompt_id)
        if output_path:
            return {"success": True, "result": {"output_path": output_path}}
        else:
            return {"success": False, "error": "生成超时"}
    
    def _vid2vid(self, context: Dict) -> Dict[str, Any]:
        """视频生视频"""
        workflow_path = os.path.join(self._workflows_dir, "vid2vid.json")
        
        workflow = self._load_workflow(workflow_path)
        if not workflow:
            workflow = self._generate_vid2vid_workflow()
        
        video_path = context.get("video_path", "")
        prompt = context.get("prompt", "")
        style = context.get("style", "")
        
        if not video_path:
            return {"success": False, "error": "缺少 video_path 参数"}
        
        workflow = self._inject_params(workflow, {
            "video_path": video_path,
            "prompt": prompt,
            "style": style,
        })
        
        prompt_id = self._submit_prompt(workflow)
        if not prompt_id:
            return {"success": False, "error": "提交任务失败"}
        
        output_path = self._wait_for_result(prompt_id)
        if output_path:
            return {"success": True, "result": {"output_path": output_path}}
        else:
            return {"success": False, "error": "生成超时"}
    
    def _generate(self, context: Dict) -> Dict[str, Any]:
        """通用生成"""
        workflow_name = context.get("workflow", "txt2img")
        workflow_path = os.path.join(self._workflows_dir, f"{workflow_name}.json")
        
        workflow = self._load_workflow(workflow_path)
        if not workflow:
            return {"success": False, "error": f"工作流模板不存在: {workflow_name}"}
        
        workflow = self._inject_params(workflow, context)
        
        prompt_id = self._submit_prompt(workflow)
        if not prompt_id:
            return {"success": False, "error": "提交任务失败"}
        
        output_path = self._wait_for_result(prompt_id)
        if output_path:
            return {"success": True, "result": {"output_path": output_path}}
        else:
            return {"success": False, "error": "生成超时"}
    
    def _load_workflow(self, path: str) -> Optional[Dict]:
        """加载工作流模板"""
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"加载工作流失败: {e}")
        return None
    
    def _generate_txt2img_workflow(self) -> Dict:
        """生成文生图工作流"""
        return {
            "3": {"class_type": "KSampler", "inputs": {"cfg": 7, "denoise": 1, "latent_image": ["5", 0], "model": ["4", 0], "negative": ["7", 0], "positive": ["6", 0], "sampler_name": "euler", "scheduler": "normal", "seed": random.randint(0, 2**32 - 1), "steps": 20}},
            "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": self._ckpt_name}},
            "5": {"class_type": "EmptyLatentImage", "inputs": {"batch_size": 1, "height": 768, "width": 1024}},
            "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "{{prompt}}", "clip": ["4", 1]}},
            "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "{{negative_prompt}}", "clip": ["4", 1]}},
            "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
            "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "aos_txt2img", "images": ["8", 0]}},
        }
    
    def _generate_img2vid_workflow(self) -> Dict:
        """生成图生视频工作流"""
        return {
            "1": {"class_type": "LoadImage", "inputs": {"image": "{{image_path}}"}},
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "{{prompt}}", "clip": ["3", 1]}},
            "3": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": self._ckpt_name}},
            "4": {"class_type": "SaveVideo", "inputs": {"filename_prefix": "aos_img2vid", "frames": ["5", 0]}},
        }
    
    def _generate_style_transfer_workflow(self) -> Dict:
        """生成风格迁移工作流"""
        return {
            "1": {"class_type": "LoadImage", "inputs": {"image": "{{image_path}}"}},
            "2": {"class_type": "LoadImage", "inputs": {"image": "{{reference_image}}"}},
            "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "{{style_prompt}}", "clip": ["4", 1]}},
            "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": self._ckpt_name}},
            "5": {"class_type": "SaveImage", "inputs": {"filename_prefix": "aos_style_transfer", "images": ["6", 0]}},
        }
    
    def _generate_vid2vid_workflow(self) -> Dict:
        """生成视频生视频工作流"""
        return {
            "1": {"class_type": "LoadVideo", "inputs": {"video": "{{video_path}}"}},
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "{{prompt}}", "clip": ["3", 1]}},
            "3": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": self._ckpt_name}},
            "4": {"class_type": "SaveVideo", "inputs": {"filename_prefix": "aos_vid2vid", "frames": ["5", 0]}},
        }
    
    def _inject_params(self, workflow: Dict, params: Dict) -> Dict:
        """注入参数到工作流模板"""
        workflow_str = json.dumps(workflow)
        for key, value in params.items():
            workflow_str = workflow_str.replace(f"{{{{{key}}}}}", str(value))
        wf = json.loads(workflow_str)
        # 兜底：无论走文件模板还是内置生成，都强制合法 seed + 可配 ckpt。
        # （模板文件里写死 seed:-1 / 硬编码 ckpt 都会在此被修正，避免真发请求踩坑）
        return self._fix_seed(self._fix_ckpt(wf))

    def _fix_seed(self, workflow: Dict) -> Dict:
        """把所有 KSampler 的负数 seed 替换为随机非负整数（ComfyUI 不接受 -1）。"""
        for node in workflow.values():
            inp = (node or {}).get("inputs") or {}
            if isinstance(inp.get("seed"), int) and inp["seed"] < 0:
                inp["seed"] = random.randint(0, 2**32 - 1)
        return workflow

    def _fix_ckpt(self, workflow: Dict) -> Dict:
        """CheckpointLoaderSimple 的 ckpt_name 统一改为可配置模型（env 优先）。"""
        for node in workflow.values():
            if (node or {}).get("class_type") == "CheckpointLoaderSimple":
                (node.setdefault("inputs", {}))["ckpt_name"] = self._ckpt_name
        return workflow
    
    def _submit_prompt(self, workflow: Dict) -> Optional[str]:
        """提交任务到 ComfyUI"""
        try:
            resp = requests.post(
                f"{self._base_url}/prompt",
                json={"prompt": workflow, "client_id": self._client_id},
                timeout=30,
            )
            if resp.status_code == 200:
                return resp.json().get("prompt_id")
            else:
                logger.warning(f"提交任务失败: {resp.status_code}")
                return None
        except Exception as e:
            logger.error(f"提交任务异常: {e}")
            return None
    
    def _wait_for_result(self, prompt_id: str, timeout=300) -> Optional[str]:
        """等待生成结果"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                resp = requests.get(f"{self._base_url}/history/{prompt_id}", timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    if prompt_id in data:
                        outputs = data[prompt_id].get("outputs", {})
                        return self._extract_output_path(outputs)
            except Exception as e:
                logger.debug(f"轮询结果异常: {e}")
            
            time.sleep(2)
        
        logger.warning(f"生成超时: {timeout}秒")
        return None
    
    def _extract_output_path(self, outputs: Dict) -> Optional[str]:
        """提取输出文件路径"""
        for node_id, node_outputs in outputs.items():
            for output_name, values in node_outputs.items():
                if isinstance(values, list):
                    for value in values:
                        if isinstance(value, dict) and "filename" in value:
                            return os.path.join(self._get_output_dir(), value["filename"])
                elif isinstance(values, dict) and "filename" in values:
                    return os.path.join(self._get_output_dir(), values["filename"])
        return None
    
    def _get_output_dir(self) -> str:
        """获取 ComfyUI 输出目录"""
        try:
            resp = requests.get(f"{self._base_url}/config", timeout=5)
            if resp.status_code == 200:
                config = resp.json()
                return config.get("output_dir", "./output")
        except Exception as e:
            logger.warning("获取 ComfyUI 输出目录失败: %s", e)
        return "./output"

    def _list_workflows(self, task_id: str) -> Dict[str, Any]:
        """列出所有可用工作流"""
        workflows = {}
        
        for filename in os.listdir(self._workflows_dir):
            if filename.endswith(".json"):
                name = filename[:-5]
                workflows[name] = {
                    "name": name,
                    "file": filename,
                    "description": COMFYUI_FEATURES.get(name, {}).get("description", "自定义工作流"),
                    "input": COMFYUI_FEATURES.get(name, {}).get("input", []),
                }
        
        return {
            "success": True,
            "result": {
                "workflows": workflows,
                "count": len(workflows),
                "workflows_dir": self._workflows_dir,
            },
        }
    
    def _get_status(self, task_id: str) -> Dict[str, Any]:
        """获取 ComfyUI 状态"""
        try:
            resp = requests.get(f"{self._base_url}/system_info", timeout=5)
            if resp.status_code == 200:
                return {
                    "success": True,
                    "result": {
                        "running": True,
                        "url": self._base_url,
                        "system_info": resp.json(),
                    },
                }
            else:
                return {
                    "success": True,
                    "result": {
                        "running": False,
                        "url": self._base_url,
                        "error": f"HTTP {resp.status_code}",
                    },
                }
        except Exception as e:
            return {
                "success": True,
                "result": {
                    "running": False,
                    "url": self._base_url,
                    "error": str(e),
                },
            }
    
    def _get_install_instructions(self) -> List[str]:
        """获取安装说明"""
        return [
            "1. 下载秋叶整合包: https://github.com/AUTOMATIC1111/stable-diffusion-webui",
            "2. 启动 ComfyUI: python main.py --listen --lowvram",
            "3. 配置环境变量: COMFYUI_BASE_URL=http://localhost:8188",
            "4. 预置工作流模板到: src/skills/workflows/",
        ]
    
    def list_features(self) -> Dict[str, Any]:
        """列出所有可用功能"""
        return COMFYUI_FEATURES
    
    def is_available(self) -> bool:
        """检查 ComfyUI 是否可用"""
        return self._available


def get_comfyui_skill() -> ComfyUISkill:
    """获取或创建 ComfyUI 技能实例"""
    return ComfyUISkill()


def register_comfyui_skill(registry=None):
    """注册 ComfyUI 技能到技能注册表"""
    if registry is None:
        from .base import SkillRegistry
        registry = SkillRegistry()
    
    skill = ComfyUISkill()
    registry.register(skill)
    logger.info("ComfyUI 技能已注册")
    return skill