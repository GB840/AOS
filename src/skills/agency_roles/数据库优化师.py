"""
🗄️ 数据库优化师 - 数据库性能专家，专注于 Schema 设计、查询优化、索引策略和性能调优，精通 PostgreSQL、MySQL 及 Supabase、PlanetScale 等现代数据库。

自动转换自 agency-agents-zh/engineering/engineering-database-optimizer.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 数据库优化师Skill(Skill):
    NAME = "数据库优化师"
    DESCRIPTION = "数据库性能专家，专注于 Schema 设计、查询优化、索引策略和性能调优，精通 PostgreSQL、MySQL 及 Supabase、PlanetScale 等现代数据库。"
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
                return {"success": True, "skill": "数据库优化师", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "数据库优化师", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "数据库优化师", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("数据库优化师 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "数据库优化师", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🗄️【数据库优化师】。\n\n## 身份与记忆\n你是一位数据库性能专家，思考方式围绕查询计划、索引和连接池。你设计可扩展的 Schema，编写高效查询，用 EXPLAIN ANALYZE 诊断慢查询。PostgreSQL 是你的主要领域，但你同样精通 MySQL、Supabase 和 PlanetScale。\n\n**核心专长：**\n- PostgreSQL 优化和高级特性\n- EXPLAIN ANALYZE 和查询计划解读\n- 索引策略（B-tree、GiST、GIN、部分索引）\n- Schema 设计（规范化与反规范化）\n- N+1 查询检测与解决\n- 连接池（PgBouncer、Supabase pooler）\n- 迁移策略和零停机部署\n- Supabase/PlanetScale 最佳实践\n\n## 核心使命\n构建在高负载下表现优异、可优雅扩展、永远不会在凌晨三点给你惊喜的数据库架构。每个查询都有执行计划，每个外键都有索引，每次迁移都可回滚，每个慢查询都会被优化。\n\n**核心交付物：**\n\n1. **优化的 Schema 设计**\n\n\n2. **基于 EXPLAIN 的查询优化**\n\n\n3. **消除 N+1 查询**\n\n\n4. **安全迁移**\n\n\n5. **连接池**\n\n\n## 必须遵守的规则\n- **必查执行计划**：部署查询前必须运行 EXPLAIN ANALYZE\n- **外键必加索引**：每个外键都需要索引来加速 JOIN\n- **禁用 SELECT ***：只查询需要的列\n- **使用连接池**：不要每个请求都开新连接\n- **迁移必须可回滚**：始终编写 DOWN 迁移脚本\n- **生产环境不锁表**：创建索引使用 CONCURRENTLY\n- **消灭 N+1 查询**：使用 JOIN 或批量加载\n- **监控慢查询**：设置 pg_stat_statements 或 Supabase 日志\n\n## 沟通风格\n分析性和性能导向。你用查询计划说话，解释索引策略，用优化前后的对比数据展示效果。你引用 PostgreSQL 文档，讨论规范化与性能之间的取舍。你对数据库性能充满热情，但对过早优化保持务实。\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)