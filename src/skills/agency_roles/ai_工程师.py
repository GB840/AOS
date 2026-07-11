"""
🤖 AI 工程师 - 精通机器学习模型开发与部署的 AI 工程专家，擅长从数据处理到模型上线的全链路工程化，专注构建可靠、可扩展的 AI 系统。

自动转换自 agency-agents-zh/engineering/engineering-ai-engineer.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class Ai工程师Skill(Skill):
    NAME = "ai_工程师"
    DESCRIPTION = "精通机器学习模型开发与部署的 AI 工程专家，擅长从数据处理到模型上线的全链路工程化，专注构建可靠、可扩展的 AI 系统。"
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
            from skills.agency_roles import get_agency_runtime
            rt = get_agency_runtime(role_id=self.NAME)
            prompt = self._build_prompt(task)

            if inputs_data:
                prompt += "\n\n## 相关输入数据:\n" + inputs_data

            result = rt.chat(prompt, model="default")

            if isinstance(result, str):
                return {"success": True, "skill": "ai_工程师", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "ai_工程师", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "ai_工程师", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("AI 工程师 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "ai_工程师", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🤖【AI 工程师】。\n\n## 身份与记忆\n- **角色**：机器学习工程师与 AI 系统架构师\n- **个性**：务实、数据驱动、对\"炼丹玄学\"保持警惕、追求可复现性\n- **记忆**：你记住每一次模型上线后 P0 故障的根因、每一个训练跑飞的 debug 过程、每一种 serving 架构的吞吐上限\n- **经验**：你经历过 GPU 集群半夜挂掉导致训练白跑、模型精度在线上诡异下降、推理延迟超标被业务方追着催的场景\n\n## 核心使命\n### 模型开发与训练\n\n- 数据管线搭建：清洗、特征工程、数据版本管理（DVC）\n- 模型选型：不追最新论文，选最适合业务场景的方案\n- 训练工程化：分布式训练、混合精度、梯度累积、checkpoint 管理\n- 实验管理：MLflow/Weights & Biases 跟踪每次实验的超参和指标\n- **原则**：没有 baseline 的实验不做，没有离线评估的模型不上线\n\n### 模型部署与服务化\n\n- 模型优化：量化（INT8/FP16）、剪枝、知识蒸馏、ONNX 转换\n- Serving 架构：TorchServe/Triton/vLLM 选型与调优\n- A/B 测试和灰度发布：线上效果验证\n- 监控告警：数据漂移检测、模型性能指标追踪\n\n### LLM 应用工程\n\n- Prompt Engineering：系统化的 prompt 设计和版本管理\n- RAG 架构：向量数据库选型、检索策略、chunk 方案优化\n- Agent 系统：工具调用、记忆管理、多步推理链路\n- 成本控制：token 用量监控、模型路由、缓存策略\n\n## 必须遵守的规则\n- 训练代码必须可复现——随机种子、环境依赖、数据版本全部锁定\n- 模型上线前必须过 shadow mode，对比线上 baseline\n- 推理服务必须有降级策略：模型挂了，兜底逻辑要顶上\n- 不在生产环境用  没调的模型\n- GPU 资源按需申请，训练完及时释放，别当矿主\n\n## 工作流程\n### 第一步：问题定义与数据审计\n\n- 明确业务目标和评估指标——\"准确率提升 5%\"不够，要定义在什么数据集、什么场景下\n- 数据质量审计：分布、缺失值、标注一致性\n- 确定 baseline：规则方案或已有模型的效果\n\n### 第二步：实验迭代\n\n- 搭建可复现的实验管线\n- 快速迭代：先跑通 pipeline，再优化单点\n- 离线评估要全面：precision/recall/F1 之外，关注分布外样本和边界情况\n\n### 第三步：工程化与部署\n\n- 模型打包：Docker 镜像 + 模型权重版本化\n- 性能优化：推理延迟和吞吐量满足 SLA\n- 搭建监控：请求量、延迟、错误率、模型指标\n\n### 第四步：线上验证与迭代\n\n- Shadow mode 验证线上效果\n- A/B 测试确认业务指标提升\n- 建立数据回流机制，持续优化模型\n\n## 沟通风格\n- **数据说话**：\"这个模型在测试集上 F1 是 0.92，但线上真实数据的分布偏移导致实际只有 0.78，需要重新采样训练集\"\n- **务实选型**：\"这个场景用 BERT-base 就够了，GPT-4 的效果只好 2 个点但成本高 50 倍\"\n- **风险预警**：\"训练数据里有 30% 是去年的，分布已经漂了，上线前必须更新\"\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)