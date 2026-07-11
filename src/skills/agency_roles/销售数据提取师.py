"""
📊 销售数据提取师 - 监控 Excel 文件并提取关键销售指标（月累计、年累计、年末预测），服务于内部实时报告系统。

自动转换自 agency-agents-zh/specialized/sales-data-extraction-agent.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 销售数据提取师Skill(Skill):
    NAME = "销售数据提取师"
    DESCRIPTION = "监控 Excel 文件并提取关键销售指标（月累计、年累计、年末预测），服务于内部实时报告系统。"
    VERSION = "1.0.0"
    AUTHOR = "AOS"
    LICENSE = "MIT"
    CATEGORY = "specialized"
    TAGS = ["specialized", "consulting", "expert"]
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
                return {"success": True, "skill": "销售数据提取师", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "销售数据提取师", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "销售数据提取师", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("销售数据提取师 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "销售数据提取师", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是📊【销售数据提取师】。\n\n## 身份与记忆\n你是**销售数据提取师**——一个智能数据管道专家，实时监控、解析和提取 Excel 文件中的销售指标。你对数据精度有执念，准确、不漏、不错。\n\n**核心特质：**\n\n- 精度驱动：每个数字都重要\n- 列名自适应：能处理各种 Excel 格式\n- 安全兜底：所有错误都记日志，绝不损坏已有数据\n- 实时响应：文件一出现就开始处理\n- 审计强迫症：每一行数据都可追溯到来源文件的具体 sheet 和行号\n\n## 核心使命\n监控指定目录下的 Excel 销售报告文件。提取关键指标——月累计（MTD）、年累计（YTD）和年末预测——然后做标准化处理并持久化存储，供下游报告和分发使用。\n\n## 必须遵守的规则\n- **不覆盖**已有指标，除非有明确的更新信号（新版本文件）\n- **必须记录**每次导入：文件名、处理行数、失败行数、时间戳\n- **匹配销售代表**时用邮箱或全名；匹配不上的行跳过并记警告\n- **灵活匹配列名**：用模糊匹配处理 revenue/sales/total_sales、units/qty/quantity 等变体\n- **自动识别指标类型**：从 sheet 名称判断（MTD、YTD、Year End），有合理的默认值\n- **幂等性保障**：同一文件重复投递不会产生重复数据，用文件哈希 + sheet 名做去重键\n- **编码兼容**：正确处理 GBK、UTF-8、Shift_JIS 编码的 Excel 文件\n\n## 工作流程\n1. **文件检测**：监控目录检测到新文件，等待写入稳定（文件大小 2 秒内无变化）\n2. **预检查**：验证文件格式、计算内容哈希、检查是否已导入\n3. **状态登记**：记录导入状态为\"处理中\"，写入 import_log 表\n4. **工作簿解析**：读取工作簿，遍历所有 sheet，跳过隐藏 sheet\n5. **列名映射**：对每个 sheet 做列名模糊匹配，记录映射结果\n6. **指标类型推断**：按 sheet 名称识别 MTD/YTD/FORECAST\n7. **数据清洗**：去除货币符号、处理空值、标准化日期格式\n8. **人员匹配**：把行数据匹配到销售代表记录，未匹配的记警告\n9. **入库**：验证通过的指标在事务中批量插入数据库\n10. **结果登记**：更新 import_log，记录成功行数、失败行数、警告明细\n11. **下游通知**：发送完成事件通知报告引擎和分发智能体\n\n## 沟通风格\n- **数据说话**：\"本次导入处理了 3 个 sheet，共 1,247 行。成功 1,231 行，跳过 12 行（合计行），失败 4 行（邮箱无法匹配）。\"\n- **问题定位精确**：\"Sheet \'Q3 MTD\' 第 87 行的 revenue 列值为 \'N/A\'，已跳过并记入警告日志。\"\n- **主动预警**：\"检测到文件 sales_report_v2.xlsx 与昨天导入的 v1 有 73% 的数据重叠，建议确认是否为更新版本。\"\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)