"""
UI-TARS 技能模块 - 字节跳动 GUI 自动化 Agent

UI-TARS 是字节跳动开源的多模态 AI Agent，主打桌面/浏览器自动化。
核心价值：给 AI 装上眼睛和手，看懂屏幕、操控鼠标键盘。

技术特点:
- 多模态视觉理解：能识别屏幕内容、截图、视觉元素
- 精准操控：支持鼠标点击、键盘输入、滚动等操作
- 跨平台：支持 Windows、macOS、浏览器
- 原生 MCP 协议：与 AOS 无缝集成
- 浏览器自动化：GUI Agent + DOM 混合策略

部署方式:
- 源码：external/UI-TARS-desktop (可配置)
- CLI: npx @agent-tars/cli@latest
- Desktop: UI-TARS-desktop 应用
"""

import os
import sys
import json
import logging
import uuid
import subprocess
from typing import Dict, List, Any
from datetime import datetime

from .base import Skill
from deerflow.path_detect import detect_uitars_path

logger = logging.getLogger(__name__)

UITARS_PATH = detect_uitars_path()

if UITARS_PATH:
    logger.info(f"UI-TARS: 源码路径已检测到: {UITARS_PATH}")
else:
    logger.warning("UI-TARS: 源码路径未检测到，将使用 CLI 模式或模拟实现")

UITARS_FEATURES = {
    "desktop_automation": {
        "name": "桌面自动化",
        "description": "自动操控桌面应用，完成点击、输入、拖拽等操作",
    },
    "browser_automation": {
        "name": "浏览器自动化",
        "description": "自动操作浏览器，网页搜索、表单填写、数据抓取",
    },
    "screen_capture": {
        "name": "截屏识别",
        "description": "截取屏幕并识别内容，支持视觉问答",
    },
    "visual_qa": {
        "name": "视觉问答",
        "description": "基于截图回答问题，理解屏幕内容",
    },
    "task_execution": {
        "name": "任务执行",
        "description": "执行复杂的多步骤自动化任务",
    },
}

UITARS_PRESETS = {
    "search_web": {
        "name": "网页搜索",
        "description": "打开浏览器搜索指定内容",
        "example": "搜索 AI Agent 最新动态",
    },
    "fill_form": {
        "name": "填写表单",
        "description": "自动填写网页表单",
        "example": "在注册页面填写用户名和密码",
    },
    "open_app": {
        "name": "打开应用",
        "description": "打开指定的桌面应用",
        "example": "打开计算器",
    },
    "data_extract": {
        "name": "数据提取",
        "description": "从网页或应用中提取数据",
        "example": "提取淘宝商品价格信息",
    },
    "file_operation": {
        "name": "文件操作",
        "description": "自动化文件管理操作",
        "example": "整理下载文件夹",
    },
}


class UITarsSkill(Skill):
    """
    UI-TARS 桌面自动化技能
    
    提供 GUI 桌面自动化能力，支持桌面和浏览器操作。
    基于字节跳动 UI-TARS (Agent TARS) 项目。
    """
    
    NAME = "uitars"
    DESCRIPTION = "UI-TARS 桌面自动化 — 字节跳动开源GUI Agent，看懂屏幕、操控鼠标键盘"
    VERSION = "1.0.0"
    AUTHOR = "ByteDance"
    LICENSE = "MIT"
    CATEGORY = "automation"
    TAGS = ["ui-tars", "agent-tars", "gui", "automation", "desktop", "browser", "byteDance"]
    CAPABILITIES = [
        "desktop_automation",
        "browser_automation", 
        "screen_capture",
        "mouse_keyboard_control",
        "visual_qa",
        "task_execution",
        "multi_modal",
    ]
    
    def __init__(self):
        super().__init__()
        self._uitars_path = UITARS_PATH
        self._cli_command = "node"
        self._cli_args = [os.path.join(UITARS_PATH, "packages", "ui-tars", "cli", "bin", "index.js")]
        self._available = False
        self._node_available = False
        self._enhanced_mode = True
        self._check_uitars()
    
    def _check_uitars(self):
        """检查 UI-TARS 是否可用"""
        try:
            if os.path.exists(self._uitars_path):
                self._available = True
                logger.info("UI-TARS 源码目录存在: %s", self._uitars_path)
            
            try:
                subprocess.run(
                    ["where.exe" if sys.platform == "win32" else "which", "node"],
                    capture_output=True, timeout=5,
                )
                self._node_available = True
            except Exception:
                self._node_available = False
                logger.warning("Node.js 未安装，CLI 模式不可用")
        except Exception as e:
            logger.warning("UI-TARS 检查失败: %s", e)
    
    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行 UI-TARS 任务
        
        Args:
            context: 执行上下文
                - action: 操作类型
                - task: 任务描述
                - max_steps: 最大步骤数（默认 20）
                - timeout: 超时时间（秒）
        
        Returns:
            Dict: 执行结果
        """
        action = context.get("action", "task_execution")
        task = context.get("task", context.get("message", ""))
        
        if action not in UITARS_FEATURES:
            return {
                "success": False,
                "error": f"未知操作: {action}，可用操作: {list(UITARS_FEATURES.keys())}",
                "available_actions": UITARS_FEATURES,
            }
        
        if not task:
            return {
                "success": False,
                "error": "请提供任务描述 (task/message)",
            }
        
        task_id = str(uuid.uuid4())[:8]
        
        if self._enhanced_mode:
            result = self._execute_enhanced(action, task, context)
        else:
            result = self._execute_cli(action, task, context)
        
        return {
            "success": result.get("success", False),
            "task_id": task_id,
            "action": action,
            "action_name": UITARS_FEATURES[action]["name"],
            "task": task,
            "result": result.get("result"),
            "error": result.get("error"),
            "mode": "enhanced" if self._enhanced_mode else "cli",
            "uitars_available": self._available,
            "timestamp": datetime.now().isoformat(),
        }
    
    def _execute_enhanced(self, action: str, task: str, context: Dict) -> Dict[str, Any]:
        """增强模式执行 — 优先 CLI，失败降级到模拟"""
        try:
            if self._available and self._node_available:
                cli_result = self._execute_cli(action, task, context)
                if cli_result.get("success"):
                    return cli_result
                logger.info("CLI 模式执行失败，降级到模拟模式: %s", cli_result.get("error"))
            
            return self._execute_simulation(action, task, context)
        except Exception as e:
            logger.error(f"增强模式执行失败: {e}", exc_info=True)
            try:
                return self._execute_simulation(action, task, context)
            except Exception as e2:
                return {"success": False, "error": str(e), "simulation_error": str(e2)}
    
    def _execute_cli(self, action: str, task: str, context: Dict) -> Dict[str, Any]:
        """通过 CLI 调用 UI-TARS"""
        timeout = context.get("timeout", 300)
        max_steps = context.get("max_steps", 20)
        
        cmd_args = {
            "task": task,
            "maxSteps": max_steps,
            "action": action,
        }
        
        cmd = [self._cli_command] + self._cli_args + [
            "--json", json.dumps(cmd_args, ensure_ascii=False)
        ]
        
        logger.info("UI-TARS CLI 调用: %s", " ".join(cmd[:4]))
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=self._uitars_path,
                encoding="utf-8",
                errors="replace",
            )
            
            output = result.stdout.strip()
            
            try:
                parsed = json.loads(output) if output else {}
            except json.JSONDecodeError:
                parsed = {"raw_output": output}
            
            if result.returncode != 0:
                logger.warning("UI-TARS CLI 退出码: %d", result.returncode)
                return {
                    "success": False,
                    "result": {
                        "exit_code": result.returncode,
                        "stdout": output[:2000],
                        "stderr": result.stderr[:2000] if result.stderr else "",
                    },
                    "error": f"CLI 执行失败 (退出码 {result.returncode})",
                }
            
            return {
                "success": True,
                "result:": parsed,
            }
        
        except subprocess.TimeoutExpired:
            return {"success": False, "error": f"执行超时 ({timeout}s)"}
        except FileNotFoundError:
            return {"success": False, "error": "CLI 命令不可用，请确保 Node.js 已安装"}
        except Exception as e:
            logger.error(f"UI-TARS CLI 调用失败: {e}")
            return {"success": False, "error": str(e)}
    
    def _execute_simulation(self, action: str, task: str, context: Dict) -> Dict[str, Any]:
        """模拟执行模式 — 生成执行计划和步骤"""
        try:
            steps = self._generate_task_steps(action, task)
            
            return {
                "success": True,
                "result": {
                    "mode": "simulation",
                    "task": task,
                    "action": action,
                    "steps": steps,
                    "step_count": len(steps),
                    "estimated_time": f"{len(steps) * 5} 秒",
                    "note": "模拟模式：生成执行计划，实际执行需启动 UI-TARS 服务",
                    "instructions": self._get_start_instructions(),
                },
            }
        except Exception as e:
            logger.error(f"模拟执行失败: {e}")
            return {"success": False, "error": str(e)}
    
    def _generate_task_steps(self, action: str, task: str) -> List[Dict[str, Any]]:
        """生成任务执行步骤"""
        steps = []
        
        if action == "browser_automation" or "浏览" in task or "搜索" in task or "网页" in task:
            steps = [
                {"step": 1, "action": "open_browser", "description": "打开浏览器", "status": "pending"},
                {"step": 2, "action": "navigate", "description": f"导航到目标页面: {task[:30]}...", "status": "pending"},
                {"step": 3, "action": "interact", "description": "执行页面交互操作", "status": "pending"},
                {"step": 4, "action": "extract", "description": "提取结果信息", "status": "pending"},
                {"step": 5, "action": "complete", "description": "任务完成，返回结果", "status": "pending"},
            ]
        elif action == "desktop_automation" or "桌面" in task or "应用" in task:
            steps = [
                {"step": 1, "action": "find_app", "description": "定位目标应用程序", "status": "pending"},
                {"step": 2, "action": "launch_app", "description": "启动应用程序", "status": "pending"},
                {"step": 3, "action": "interact", "description": f"执行操作: {task[:30]}...", "status": "pending"},
                {"step": 4, "action": "verify", "description": "验证操作结果", "status": "pending"},
                {"step": 5, "action": "complete", "description": "任务完成", "status": "pending"},
            ]
        elif action == "screen_capture" or action == "visual_qa":
            steps = [
                {"step": 1, "action": "capture", "description": "截取屏幕/窗口图像", "status": "pending"},
                {"step": 2, "action": "analyze", "description": "使用视觉模型分析图像", "status": "pending"},
                {"step": 3, "action": "answer", "description": f"回答问题: {task[:30]}...", "status": "pending"},
                {"step": 4, "action": "complete", "description": "返回分析结果", "status": "pending"},
            ]
        else:
            steps = [
                {"step": 1, "action": "understand", "description": "理解任务需求", "status": "pending"},
                {"step": 2, "action": "plan", "description": "制定执行计划", "status": "pending"},
                {"step": 3, "action": "execute", "description": f"执行: {task[:30]}...", "status": "pending"},
                {"step": 4, "action": "verify", "description": "验证执行结果", "status": "pending"},
                {"step": 5, "action": "complete", "description": "任务完成", "status": "pending"},
            ]
        
        return steps
    
    def _get_start_instructions(self) -> List[str]:
        """获取启动 UI-TARS 的说明"""
        path_display = UITARS_PATH or "external/UI-TARS-desktop"
        return [
            "1. 确保已安装 Node.js (>= 18)",
            f"2. 进入 UI-TARS 目录: cd {path_display}",
            "3. 安装依赖: pnpm install (或 npm install)",
            "4. 启动 CLI: npx @agent-tars/cli@latest",
            "5. 或启动 Desktop 应用: cd apps/ui-tars && npm run dev",
        ]
    
    def list_features(self) -> Dict[str, Any]:
        """列出所有可用功能"""
        return UITARS_FEATURES
    
    def list_presets(self) -> Dict[str, Any]:
        """列出预设任务"""
        return UITARS_PRESETS
    
    def is_available(self) -> bool:
        """检查 UI-TARS 是否可用"""
        return self._available


def get_uitars_skill() -> UITarsSkill:
    """获取或创建 UI-TARS 技能实例"""
    return UITarsSkill()


def register_uitars_skill(registry=None):
    """注册 UI-TARS 技能到技能注册表"""
    if registry is None:
        from .base import SkillRegistry
        registry = SkillRegistry()
    
    skill = UITarsSkill()
    registry.register(skill)
    logger.info("UI-TARS 技能已注册")
    return skill
