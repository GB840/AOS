"""OPC 5 岗位智能体注册表（单创OS 数字组织内核）。

设计原则（用户铁律）：
- 现有能力全部复用，不重造：每个岗位映射 autopilot/opc 已注册的 capability 标签。
- 比现有差的才优化，没有的才用开源补（财务岗的报表由 report_agent 开源补）。
- 可插拔：行业模板通过 knowledge_base 钩子扩展，不影响核心 5 岗。

能力标签来源（已在项目注册）：
- web.search       市场调研/客服检索
- media.image      图文/海报
- media.video      短视频
- media.audio      语音/配音
- action.code_exec 代码生成/固件
- action.repo      仓库提交沉淀
- inference.llm    推理/规划/反思
- memory.semantic  记忆检索
- finance.report   财务核算（report_agent 提供，开源 openpyxl）
- dev.terax        终端开发环境（Terax，opt-in 本地开源，产品研发岗主阵地；由 extension 注册，未安装静默跳过）
- media.3d.reconstruct 图片→程序化 Three.js 模型重建（img2threejs，vendored 纯 stdlib + divine_eye 零 token 评分）
- media.process      云端音视频后期处理（火山引擎 mediakit-cli，opt-in 借鉴，默认关闭）
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class OPCRole:
    """一个数字员工岗位。capabilities 全部复用现有已注册 capability。"""
    id: str
    name: str
    description: str
    capabilities: List[str]
    workflow: List[str]          # 对应 opc_loop.Stage.id 的工作流阶段
    knowledge_base: str = ""     # 行业知识库标识（预留，可插拔）


# ── 5 个标准岗位（所有租户/自用通用，行业差异走 knowledge_base 钩子）──
OPC_ROLES: Dict[str, OPCRole] = {
    "product_rd": OPCRole(
        id="product_rd",
        name="产品研发智能体",
        description="硬件选型、模型量化、嵌入式固件、代码生成、仓库沉淀；终端开发环境由 Terax(opt-in) 提供；产品外观/结构可由图片重建为 Three.js 模型(img2threejs)",
        capabilities=["action.code_exec", "inference.llm", "memory.semantic", "action.repo", "dev.terax", "media.3d.reconstruct"],
        workflow=["analyze", "deliver", "evolve"],
    ),
    "market_research": OPCRole(
        id="market_research",
        name="市场调研智能体",
        description="竞品抓取、用户痛点提取、调研报告生成",
        capabilities=["web.search", "inference.llm", "media.image"],
        workflow=["analyze", "acquire"],
    ),
    "content_marketing": OPCRole(
        id="content_marketing",
        name="内容营销智能体",
        description="短视频脚本、海报、图文笔记、分发（可选 WorkRally 增强）；音视频后期处理可由 mediakit-cli（火山引擎，opt-in）提供",
        capabilities=["media.image", "media.video", "media.audio", "inference.llm", "edu.course_gen", "media.process"],
        workflow=["promote"],
    ),
    "customer_service": OPCRole(
        id="customer_service",
        name="客户服务智能体",
        description="售前咨询、工单处理、用户回访",
        capabilities=["inference.llm", "web.search", "action.code_exec"],
        workflow=["maintain"],
    ),
    "finance": OPCRole(
        id="finance",
        name="财务核算智能体",
        description="BOM 成本、利润预估、收支报表（开源 openpyxl）",
        capabilities=["finance.report", "inference.llm", "action.repo"],
        workflow=["deliver", "evolve"],
    ),
}


def list_roles() -> List[OPCRole]:
    return list(OPC_ROLES.values())


def get_role(role_id: str) -> "OPCRole | None":
    return OPC_ROLES.get(role_id)


def roles_for_capability(cap: str) -> List[OPCRole]:
    """哪个岗位拥有某 capability（调度引擎派活用）。"""
    return [r for r in OPC_ROLES.values() if cap in r.capabilities]


def all_capabilities() -> List[str]:
    """5 岗位合并去重的能力清单（用于校验注册完整性）。"""
    out: List[str] = []
    for r in OPC_ROLES.values():
        for c in r.capabilities:
            if c not in out:
                out.append(c)
    return out
