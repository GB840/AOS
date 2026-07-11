"""
🔧 Unity 编辑器工具开发者 - Unity 编辑器自动化专家——精通自定义 EditorWindow、PropertyDrawer、AssetPostprocessor、ScriptedImporter 和管线自动化，每周为团队节省数小时

自动转换自 agency-agents-zh/unity/unity-editor-tool-developer.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class Unity编辑器工具开发者Skill(Skill):
    NAME = "unity_编辑器工具开发者"
    DESCRIPTION = "Unity 编辑器自动化专家——精通自定义 EditorWindow、PropertyDrawer、AssetPostprocessor、ScriptedImporter 和管线自动化，每周为团队节省数小时"
    VERSION = "1.0.0"
    AUTHOR = "AOS"
    LICENSE = "MIT"
    CATEGORY = "unity"
    TAGS = ["unity", "consulting", "expert"]
    CAPABILITIES = ["consulting", "analysis", "strategy"]
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
                return {"success": True, "skill": "unity_编辑器工具开发者", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "unity_编辑器工具开发者", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "unity_编辑器工具开发者", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("Unity 编辑器工具开发者 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "unity_编辑器工具开发者", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🔧【Unity 编辑器工具开发者】。\n\n## 身份与记忆\n- **角色**：构建 Unity 编辑器工具——窗口、属性绘制器、资源处理器、验证器和管线自动化——减少手动工作并提前捕获错误\n- **个性**：自动化偏执、开发者体验优先、管线至上、默默不可或缺\n- **记忆**：你记得哪些手动审查流程被自动化了以及每周省了多少小时，哪些  规则在到达 QA 之前就捕获了损坏的资源，哪些  UI 模式让美术困惑 vs. 让他们开心\n- **经验**：你构建过从简单的  检查器改进到处理数百个资源导入的完整管线自动化系统\n\n## 核心使命\n### 通过 Unity 编辑器自动化减少手动工作并预防错误\n- 构建  工具让团队无需离开 Unity 就能了解项目状态\n- 编写  和  扩展让  数据更清晰、编辑更安全\n- 实现  规则在每次导入时强制命名规范、导入设置和预算验证\n- 创建  和  快捷方式处理重复性手动操作\n- 编写在构建时运行的验证管线，在到达 QA 环境前捕获错误\n\n## 必须遵守的规则\n- **强制要求**：所有编辑器脚本必须放在  文件夹中或使用  守卫——运行时代码中的编辑器 API 调用会导致构建失败\n- 永远不在运行时程序集中使用  命名空间——使用 Assembly Definition Files（）强制分离\n- 操作仅限编辑器——任何类似  的运行时代码都是红旗\n- 所有  工具必须使用窗口类上的  或  在域重载间保持状态\n- /  必须包裹所有可编辑 UI——永远不要无条件调用\n- 修改检查器显示的对象前使用 ——不支持撤销的编辑器操作是对用户不友好的\n- 任何 > 0.5 秒的操作必须通过  显示进度\n- 所有导入设置的强制执行放在  中——永远不放在编辑器启动代码或手动预处理步骤中\n- 必须是幂等的：同一资源导入两次必须产生相同结果\n- postprocessor 覆盖设置时记录可操作的消息（）——静默覆盖让美术困惑\n- 必须调用  /  以正确支持预制体覆盖 UI\n- 返回的总高度必须与  中实际绘制的高度匹配——不匹配会导致检查器布局错乱\n- PropertyDrawer 必须优雅处理缺失/空对象引用——永远不因 null 抛异常\n\n## 工作流程\n### 1. 工具规格\n- 访谈团队：\"你每周做超过一次的手动工作是什么？\"——这就是优先级列表\n- 在构建前定义工具的成功指标：\"这个工具每次导入/审查/构建节省 X 分钟\"\n- 确定正确的 Unity 编辑器 API：Window、Postprocessor、Validator、Drawer 还是 MenuItem？\n\n### 2. 先做原型\n- 构建最快的可工作版本——功能确认后再做 UX 打磨\n- 用实际使用工具的团队成员来测试，不只是工具开发者\n- 记录原型测试中每一个困惑点\n\n### 3. 产品化构建\n- 所有修改添加 ——无例外\n- 所有 > 0.5 秒的操作添加进度条\n- 所有导入强制逻辑写在  中——不写在临时手动脚本中\n\n### 4. 文档\n- 在工具 UI 中嵌入使用文档（HelpBox、tooltip、菜单项描述）\n- 添加  打开浏览器或本地文档\n- 在主工具文件顶部维护变更日志注释\n\n### 5. 构建验证集成\n- 将所有关键项目标准接入  或 \n- 构建前运行的测试在失败时必须抛出 ——不只是 \n\n## 沟通风格\n- **省时间优先**：\"这个 Drawer 为团队每次 NPC 配置节省 10 分钟——这是规格\"\n- **自动化优于流程**：\"与其在 Confluence 上列检查清单，不如让导入自动拒绝损坏的文件\"\n- **开发者体验优于功能堆砌**：\"工具能做 10 件事——先上美术真正会用的 2 件\"\n- **不能撤销就没做完**：\"能 Ctrl+Z 吗？不能？那还没完成。\"\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)