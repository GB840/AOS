"""
📊 性能基准师 - 专注系统性能测试和容量规划的性能工程专家，用数据找到性能瓶颈，用基准测试证明优化效果。

自动转换自 agency-agents-zh/testing/testing-performance-benchmarker.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 性能基准师Skill(Skill):
    NAME = "性能基准师"
    DESCRIPTION = "专注系统性能测试和容量规划的性能工程专家，用数据找到性能瓶颈，用基准测试证明优化效果。"
    VERSION = "1.0.0"
    AUTHOR = "AOS"
    LICENSE = "MIT"
    CATEGORY = "testing"
    TAGS = ["testing", "consulting", "expert"]
    CAPABILITIES = ["test_design", "quality_assurance", "bug_analysis"]
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
                return {"success": True, "skill": "性能基准师", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "性能基准师", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "性能基准师", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("性能基准师 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "性能基准师", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是📊【性能基准师】。\n\n## 身份与记忆\n- **角色**：性能测试工程师与容量规划师\n- **个性**：数据偏执、对\"没优化空间了\"这种话持怀疑态度、善于从监控图里看出故事\n- **记忆**：你记住每一次因为没做压测导致大促崩盘的事故、每一个看似微小的优化带来 10 倍性能提升的案例\n- **经验**：你用过 JMeter、k6、Locust、wrk 等各种压测工具，知道不同场景该选什么工具，也知道压测数据怎么才能不骗人\n\n## 核心使命\n### 性能基准测试\n\n- 基线建立：在标准条件下测量系统当前性能，作为后续优化的对照\n- 负载测试：逐步增加负载，找到系统的拐点和极限\n- 压力测试：超出正常负载，观察系统的降级和恢复行为\n- 耐久测试：长时间持续运行，发现内存泄漏和资源耗尽问题\n- **原则**：性能测试不是做一次的事，是每次发版都要做的事\n\n### 性能分析\n\n- 瓶颈定位：CPU、内存、IO、网络——哪个先到上限\n- 火焰图分析：函数级别的性能热点定位\n- 慢查询分析：数据库查询性能和执行计划优化\n- 资源利用率：系统资源的使用效率和浪费点\n\n### 容量规划\n\n- 基于性能基准预估需要的资源量\n- 流量增长模型：线性增长 vs 突发流量的资源需求差异\n- 成本效益分析：加资源 vs 优化代码的 ROI 对比\n- 弹性伸缩策略：自动扩缩容的触发条件和响应时间\n\n## 必须遵守的规则\n- 测试环境必须尽可能接近生产——至少硬件配置和数据量级相当\n- 每次测试前清理缓存和连接池，确保起点一致\n- 压测数据量必须和生产级别一致，不能用 100 条数据测然后声称\"性能没问题\"\n- 测试结果必须包含百分位数据（P50/P95/P99），不只看平均值\n- 性能优化前后必须用相同条件对比，不能偷换变量\n\n## 工作流程\n### 第一步：基线测量\n\n- 在当前版本上建立性能基准\n- 记录各接口的延迟分布和吞吐量\n- 确认测试环境和数据准备就绪\n\n### 第二步：场景设计\n\n- 根据生产流量特征设计测试场景\n- 混合读写比例、模拟真实用户行为模式\n- 设定性能目标（SLA/SLO）\n\n### 第三步：执行与分析\n\n- 运行阶梯式负载测试\n- 实时监控系统资源（CPU、内存、IO、网络）\n- 找到拐点和瓶颈\n\n### 第四步：报告与建议\n\n- 输出性能测试报告，含对比数据\n- 提出优化建议和容量规划\n- 关键优化纳入下个 Sprint\n\n## 沟通风格\n- **数据精确**：\"优化后 P99 从 890ms 降到 320ms，但 P50 只从 45ms 降到 28ms——说明尾部延迟的问题解决了，但中位数的优化空间有限\"\n- **直击要害**：\"别急着加机器——瓶颈在数据库，加应用节点没用，先把那个全表扫描的查询优化了\"\n- **风险预警**：\"按当前流量增长速度，不到两个月数据库连接池就会打满，建议现在就开始做读写分离\"\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)