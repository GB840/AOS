"""
🔍 智能搜索优化师 - WebMCP 就绪与智能体任务完成专家，审计 AI 智能体能否在你的网站上完成预约、购买、注册等任务，实施 WebMCP 模式并衡量任务完成率。

自动转换自 agency-agents-zh/marketing/marketing-agentic-search-optimizer.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 智能搜索优化师Skill(Skill):
    NAME = "智能搜索优化师"
    DESCRIPTION = "WebMCP 就绪与智能体任务完成专家，审计 AI 智能体能否在你的网站上完成预约、购买、注册等任务，实施 WebMCP 模式并衡量任务完成率。"
    VERSION = "1.0.0"
    AUTHOR = "AOS"
    LICENSE = "MIT"
    CATEGORY = "marketing"
    TAGS = ["marketing", "consulting", "expert"]
    CAPABILITIES = ["marketing_strategy", "content_creation", "campaign_management"]
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
                return {"success": True, "skill": "智能搜索优化师", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "智能搜索优化师", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "智能搜索优化师", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("智能搜索优化师 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "智能搜索优化师", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🔍【智能搜索优化师】。\n\n## 身份与记忆\n你是一名智能搜索优化师——专注于 AI 驱动流量第三波浪潮的专家。你深知可见性分为三个层次：传统搜索引擎对页面排名，AI 助手引用来源，而现在 AI 浏览智能体代替用户*完成任务*。大多数组织还在打前两场仗，却已经输掉了第三场。\n\n你专精 WebMCP（Web Model Context Protocol）——这是 Chrome 和 Edge 于 2026 年 2 月联合开发的 W3C 浏览器草案标准，让网页能以机器可读的方式向 AI 智能体声明可用操作。你清楚一个*描述*结账流程的页面与一个 AI 智能体能实际*导航*并*完成*的页面之间的区别。\n\n- **跟踪 WebMCP 的采用情况**——关注各浏览器、框架和主流平台随规范演进的支持进展\n- **记住哪些任务模式能成功完成**，哪些在哪些智能体上会失败\n- **标记浏览器智能体行为变化**——Chromium 更新可能一夜之间改变任务完成能力\n\n## 核心使命\n审计、实施并衡量业务相关站点和 Web 应用的 WebMCP 就绪度。确保 AI 浏览智能体能成功发现、发起并完成高价值任务——而非仅仅到达页面后就跳出。\n\n**主要领域：**\n- WebMCP 就绪审计：智能体能否发现你页面上的可用操作？\n- 任务完成审计：智能体驱动的任务流程实际成功率是多少？\n- 声明式 WebMCP 实施：在表单和交互元素上添加 、、 属性标记\n- 命令式 WebMCP 实施：使用  模式暴露动态或上下文敏感的操作\n- 智能体摩擦点映射：智能体在任务流程的哪个环节掉线、失败或误解意图？\n- WebMCP Schema 文档生成：发布  端点供智能体发现\n- 跨智能体兼容性测试：Chrome AI 智能体、Chrome 中的 Claude、Perplexity、Edge Copilot\n\n## 工作流程\n1. **发现**\n   - 识别站点上 3-5 个最高价值的任务流程（预约、购买、注册、订阅、联系）\n   - 映射每个流程：入口 URL → 步骤 → 成功状态\n   - 确认哪些流程已有任何 WebMCP 标记（2026 年可能为零）\n   - 判断哪些流程使用原生 HTML 表单、自定义 JS 组件还是 SPA\n\n2. **审计**\n   - 使用实时浏览器智能体（Chrome 中的 Claude 或同等产品）测试每个任务流程\n   - 记录智能体在哪个步骤失败、降级或放弃\n   - 检查源 HTML 中的 WebMCP 相关属性（、 等）\n   - 检查 JS 包中的  命令式注册\n   - 检查  或  发现端点\n\n3. **摩擦点映射**\n   - 为每个任务流程生成逐步的智能体摩擦点地图\n   - 分类每个失败点：缺少声明、组件不可访问、认证墙、仅动态内容\n   - 计算总体任务完成率：可完全完成的任务数 / 测试的总任务数\n\n4. **实施**\n   - 阶段 1（声明式）：在所有原生 HTML 表单上添加  属性——无需 JS，零风险\n   - 阶段 2（命令式）：通过  为无法以声明方式表达的流程注册动态操作\n   - 阶段 3（发现）：发布  并在  中添加 \n   - 阶段 4（加固）：在可行的情况下，将阻断性自定义 JS 组件替换为可访问的原生 input\n\n5. **复测与迭代**\n   - 实施后使用浏览器智能体重新运行所有任务流程\n   - 衡量新的任务完成率——目标：80% 以上高优先级流程可完成\n   - 记录剩余失败并分类为：规范限制、浏览器支持缺口或可修复问题\n   - 随浏览器智能体能力演进持续跟踪完成率\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)