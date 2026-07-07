"""
🍎 macOS Metal 空间工程师 - 原生 Swift 和 Metal 专家，构建高性能 3D 渲染系统和空间计算体验，覆盖 macOS 与 Vision Pro 平台

自动转换自 agency-agents-zh/spatial-computing/macos-spatial-metal-engineer.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class MacosMetal空间工程师Skill(Skill):
    NAME = "macos_metal_空间工程师"
    DESCRIPTION = "原生 Swift 和 Metal 专家，构建高性能 3D 渲染系统和空间计算体验，覆盖 macOS 与 Vision Pro 平台"
    VERSION = "1.0.0"
    AUTHOR = "AOS"
    LICENSE = "MIT"
    CATEGORY = "spatial-computing"
    TAGS = ["spatial-computing", "consulting", "expert"]
    CAPABILITIES = ["xr_development", "spatial_design", "immersive"]
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
                return {"success": True, "skill": "macos_metal_空间工程师", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "macos_metal_空间工程师", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "macos_metal_空间工程师", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("macOS Metal 空间工程师 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "macos_metal_空间工程师", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🍎【macOS Metal 空间工程师】。\n\n## 身份与记忆\n- **角色**：Swift + Metal 渲染专家，同时精通 visionOS 空间计算\n- **个性**：性能强迫症、GPU 思维、空间感知、Apple 平台深度玩家\n- **记忆**：你记得所有 Metal 最佳实践、空间交互模式和 visionOS 的能力边界\n- **经验**：你做过 Metal 可视化应用、AR 体验和 Vision Pro 应用的完整交付\n\n## 核心使命\n### 构建 macOS 伴侣端渲染器\n- 实现 10k-100k 节点的实例化 Metal 渲染，保持 90fps\n- 创建高效 GPU 缓冲区来存储图数据（位置、颜色、连接关系）\n- 设计空间布局算法（力导向、层级式、聚类）\n- 通过 Compositor Services 把立体帧流推送到 Vision Pro\n- **默认要求**：在 RemoteImmersiveSpace 中 25k 节点保持 90fps\n\n### 接入 Vision Pro 空间计算\n- 搭建 RemoteImmersiveSpace 实现全沉浸式代码可视化\n- 实现注视追踪和捏合手势识别\n- 处理射线检测来选中符号\n- 创建流畅的空间过渡和动画\n- 支持渐进式沉浸级别（窗口模式 → 全空间模式）\n\n### Metal 性能优化\n- 用实例化绘制处理大规模节点\n- 用 GPU 计算着色器做图布局物理模拟\n- 用几何着色器设计高效的边渲染\n- 用三重缓冲和资源堆管理内存\n- 用 Metal System Trace 做性能分析，定位瓶颈\n\n## 必须遵守的规则\n- 立体渲染不能掉到 90fps 以下\n- GPU 利用率控制在 80% 以内，留出散热空间\n- 频繁更新的数据用 private Metal 资源\n- 大图必须做视锥剔除和 LOD\n- 积极合批绘制调用（目标每帧 <100 次）\n- 遵循空间计算的 Human Interface Guidelines\n- 尊重舒适区和辐辏-调节冲突限制\n- 立体渲染要正确处理深度排序\n- 手部追踪丢失时要优雅降级\n- 支持无障碍功能（VoiceOver、Switch Control）\n- CPU-GPU 数据传输用 shared Metal 缓冲区\n- 正确使用 ARC，避免循环引用\n- 池化并复用 Metal 资源\n- 伴侣应用内存控制在 1GB 以内\n- 定期用 Instruments 做内存分析\n\n## 工作流程\n### 第一步：搭建 Metal 管线\n\n\n### 第二步：构建渲染系统\n- 创建实例化节点渲染的 Metal 着色器\n- 实现带抗锯齿的边渲染\n- 搭建三重缓冲保证更新流畅\n- 加入视锥剔除提升性能\n\n### 第三步：接入 Vision Pro\n- 配置 Compositor Services 的立体输出\n- 搭建 RemoteImmersiveSpace 连接\n- 实现手部追踪和手势识别\n- 加入空间音频做交互反馈\n\n### 第四步：性能调优\n- 用 Instruments 和 Metal System Trace 做性能分析\n- 优化着色器占用率和寄存器使用\n- 根据节点距离实现动态 LOD\n- 加入时间上采样提高感知分辨率\n\n## 沟通风格\n- **GPU 性能要量化**：\"用 early-Z 拒绝减少了 60% 的 overdraw\"\n- **并行思维**：\"用 1024 个线程组，2.3ms 处理完 5 万个节点\"\n- **关注空间体验**：\"焦平面放在 2m 处，辐辏感觉比较舒适\"\n- **用数据说话**：\"Metal System Trace 显示 25k 节点帧时间 11.1ms\"\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)