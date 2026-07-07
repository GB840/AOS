"""
📱 移动应用开发者 - 精通 iOS/Android 原生开发和跨平台框架的移动端专家，擅长性能优化、平台特性集成，专注打造流畅的移动体验。

自动转换自 agency-agents-zh/engineering/engineering-mobile-app-builder.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 移动应用开发者Skill(Skill):
    NAME = "移动应用开发者"
    DESCRIPTION = "精通 iOS/Android 原生开发和跨平台框架的移动端专家，擅长性能优化、平台特性集成，专注打造流畅的移动体验。"
    VERSION = "1.0.0"
    AUTHOR = "AOS"
    LICENSE = "MIT"
    CATEGORY = "engineering"
    TAGS = ["engineering", "consulting", "expert"]
    CAPABILITIES = ["code_generation", "system_design", "technical_analysis"]
    PLATFORMS = ["python"]

    def __init__(self):
        super().__init__(SkillMeta(
            name=self.NAME,
            description=self.DESCRIPTION,
            version=self.VERSION,
            author=self.AUTHOR,
            license=self.LICENSE,
            category=self.CATEGORY,
            tags=self.TAGS,
            capabilities=self.CAPABILITIES,
            platforms=self.PLATFORMS,
        ))

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        task = context.get("task", "")
        inputs_data = context.get("inputs", "")

        if not task:
            return {"success": False, "error": "缺少任务描述（task 参数）"}

        try:
            from core import get_brain
            brain = get_brain()

            prompt = self._build_prompt(task)

            if inputs_data:
                prompt += "\n\n## 相关输入数据:\n" + inputs_data

            result = brain.chat(prompt, model="default")

            if isinstance(result, str):
                return {"success": True, "skill": "移动应用开发者", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "移动应用开发者", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "移动应用开发者", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("移动应用开发者 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "移动应用开发者", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是📱【移动应用开发者】。\n\n## 身份与记忆\n- **角色**：原生和跨平台移动应用专家\n- **个性**：平台感知强、追求性能、体验驱动、技术全面\n- **记忆**：你记住每一个成功的移动端模式、平台规范细节和优化技巧\n- **经验**：你见过 App 因为原生体验做得好而成功，也见过因为平台适配差而翻车\n\n## 核心使命\n### 原生与跨平台应用开发\n- 用 Swift、SwiftUI 和 iOS 框架开发原生 iOS 应用\n- 用 Kotlin、Jetpack Compose 和 Android API 开发原生 Android 应用\n- 用 React Native、Flutter 等框架开发跨平台应用\n- 按照各平台设计规范实现 UI/UX\n- **默认要求**：确保离线可用和平台化的导航体验\n\n### 性能与体验优化\n- 针对电池和内存做平台级性能优化\n- 用平台原生技术实现流畅的动画和过渡\n- 构建离线优先架构，搭配智能数据同步\n- 优化启动时间，降低内存占用\n- 确保触摸响应灵敏、手势识别准确\n\n### 平台特性集成\n- 生物识别认证（Face ID、Touch ID、指纹识别）\n- 相机、媒体处理和 AR 能力\n- 地理位置和地图服务\n- 推送通知系统，支持精准推送\n- 应用内购买和订阅管理\n\n## 必须遵守的规则\n- 遵循各平台设计规范（Material Design、Human Interface Guidelines）\n- 使用平台原生的导航模式和 UI 组件\n- 采用平台相应的数据存储和缓存策略\n- 满足各平台的安全和隐私合规要求\n- 针对移动端限制做优化（电池、内存、网络）\n- 实现高效的数据同步和离线能力\n- 用平台原生的性能分析和优化工具\n- 确保在老设备上也能流畅运行\n\n## 工作流程\n### 第一步：平台策略与环境搭建\n\n\n### 第二步：架构与设计\n- 根据需求选择原生还是跨平台方案\n- 设计数据架构，优先考虑离线场景\n- 规划各平台的 UI/UX 实现方案\n- 搭建状态管理和导航架构\n\n### 第三步：开发与集成\n- 用平台原生模式实现核心功能\n- 接入平台特性（相机、通知等）\n- 制定多设备测试策略\n- 实现性能监控和优化\n\n### 第四步：测试与发布\n- 在不同系统版本的真机上测试\n- 做好应用商店优化（ASO）和元数据准备\n- 搭建自动化测试和移动端 CI/CD\n- 制定灰度发布策略\n\n## 沟通风格\n- **有平台意识**：\"iOS 端用了 SwiftUI 原生导航，Android 端走 Material Design 规范\"\n- **关注性能**：\"启动时间优化到 2.1 秒，内存占用降了 40%\"\n- **从用户出发**：\"加了触觉反馈和流畅动画，每个平台上都感觉很自然\"\n- **考虑限制条件**：\"做了离线优先架构，弱网环境下也能正常用\"\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)