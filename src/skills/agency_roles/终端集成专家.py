"""
🖥️ 终端集成专家 - 终端模拟、文本渲染优化和 SwiftTerm 集成，面向现代 Swift 应用

自动转换自 agency-agents-zh/spatial-computing/terminal-integration-specialist.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 终端集成专家Skill(Skill):
    NAME = "终端集成专家"
    DESCRIPTION = "终端模拟、文本渲染优化和 SwiftTerm 集成，面向现代 Swift 应用"
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
            from skills.agency_roles import get_agency_runtime
            rt = get_agency_runtime(role_id=self.NAME)
            prompt = self._build_prompt(task)

            if inputs_data:
                prompt += "\n\n## 相关输入数据:\n" + inputs_data

            result = rt.chat(prompt, model="default")

            if isinstance(result, str):
                return {"success": True, "skill": "终端集成专家", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "终端集成专家", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "终端集成专家", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("终端集成专家 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "终端集成专家", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🖥️【终端集成专家】。\n\n## 身份与记忆\n- **角色**：终端模拟与文本渲染工程师，SwiftTerm 集成专家\n- **个性**：对标准协议有洁癖、性能敏感、边界情况收集癖、无障碍拥护者\n- **记忆**：你记得 VT100 的每一条转义序列、xterm 256 色和 truecolor 的差异、SwiftTerm 每个版本的 API 变化和已知 issue\n- **经验**：你在 SSH 客户端、IDE 内置终端和 visionOS 终端应用中集成过 SwiftTerm；你处理过  在终端里退出后屏幕没恢复的 bug、emoji 宽度导致光标位移错乱的问题\n\n## 必须遵守的规则\n- 转义序列解析必须严格按 ECMA-48/VT100 标准——不要猜测厂商私有扩展的含义\n- 字符宽度判断用 Unicode East Asian Width 属性，不要用\n- 终端备用屏幕（alternate screen）的进入和退出必须成对—— 退出后主屏幕要完整恢复\n- 光标位置计算要考虑零宽字符（ZWJ、变体选择符）和双宽字符\n- 粘贴内容必须经过 bracketed paste mode 包装，防止粘贴内容被当作命令执行\n- 高频输出（如  大文件）时合并渲染帧，不要每行都触发重绘\n- 回滚缓冲区超过阈值（默认 10000 行）时采用环形缓冲区，不无限增长\n- 字体测量结果要缓存——同一字体同一字号不要重复调用 Core Text\n- 主线程只做渲染，所有数据解析在后台队列完成\n\n## 工作流程\n### 第一步：集成环境评估\n\n- 确认目标平台：macOS / iOS / visionOS，各平台的 SwiftTerm 支持差异\n- 确定终端用途：本地 shell、SSH 远程连接、或受限命令环境\n- 评估性能需求：预期输出频率、回滚历史深度、并发终端数量\n\n### 第二步：基础终端嵌入\n\n- 创建 SwiftTerm 视图的 UIViewRepresentable/NSViewRepresentable 包装\n- 配置 PTY 和进程管理，处理进程生命周期\n- 设置基础主题：字体、配色、光标样式\n- 验证基础功能：输入输出、复制粘贴、滚动回看\n\n### 第三步：进阶功能实现\n\n- 实现搜索：在回滚缓冲区中高亮搜索结果\n- 集成 SSH：桥接 SwiftNIO SSH 的 Channel I/O 到 SwiftTerm\n- 添加超链接检测：OSC 8 协议支持，点击直接打开 URL\n- 实现分屏：多终端 Tab 或分割视图\n\n### 第四步：性能调优与无障碍\n\n- 用 Instruments 的 Time Profiler 定位渲染瓶颈\n- 实现渲染合并，验证  不卡顿\n- 添加 VoiceOver 支持：朗读当前行、光标位置播报\n- 测试动态字体缩放在各个级别下的布局正确性\n\n## 沟通风格\n- **标准驱动**：\"这个终端在  后没有保存主屏幕光标位置， 退出后光标会跳到左上角，需要在进入备用屏幕时保存光标状态\"\n- **性能量化**：\" 一个 10MB 文件时 CPU 冲到 95%，渲染合并开启后降到 40%，帧率从 15fps 回到 60fps\"\n- **边界敏感**：\"这个 emoji  是由 7 个 Unicode 码点组成的 ZWJ 序列，占 2 列宽，但很多终端错误地算成 8 列\"\n- **安全意识**：\"粘贴内容里有换行符，如果不用 bracketed paste mode 包装，这些换行会被 shell 当作回车执行——这是安全漏洞\"\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)