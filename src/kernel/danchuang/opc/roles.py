"""OPC 岗位智能体定义 —— 5大标准岗位的能力与工作流。

岗位体系：
┌─────────────────────────────────────────────────────────────────────┐
│                        OPC 数字组织内核                              │
│  ┌──────────┐ ┌────────────┐ ┌────────────┐ ┌──────────┐ ┌──────┐ │
│  │ 产品研发  │ │  市场调研   │ │  内容营销   │ │ 客户服务  │ │ 财务 │ │
│  └──────────┘ └────────────┘ └────────────┘ └──────────┘ └──────┘ │
└─────────────────────────────────────────────────────────────────────┘
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional


logger = logging.getLogger(__name__)


class OPCRole(Enum):
    """OPC 岗位类型枚举。"""

    PRODUCT_RD = "product_rd"               # 产品研发
    MARKET_RESEARCH = "market_research"     # 市场调研
    CONTENT_MARKETING = "content_marketing" # 内容营销
    CUSTOMER_SERVICE = "customer_service"   # 客户服务
    FINANCE = "finance"                     # 财务核算


@dataclass
class OPCAgentRole:
    """岗位智能体基类。

    每个岗位智能体封装：
    - 身份信息：岗位类型、名称、职责描述
    - 能力清单：具体可执行的能力项
    - 工具集：可调用的 FabricHub 能力
    - 工作流模板：标准化的业务流程模板
    """

    role: OPCRole = OPCRole.PRODUCT_RD
    name: str = ""
    description: str = ""
    capabilities: List[str] = field(default_factory=list)
    tools: List[str] = field(default_factory=list)
    workflow_templates: Dict[str, dict] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。"""
        data = asdict(self)
        data["role"] = self.role.value
        return data

    def has_capability(self, capability: str) -> bool:
        """检查是否具备指定能力。"""
        return capability in self.capabilities

    def has_tool(self, tool: str) -> bool:
        """检查是否可调用指定工具。"""
        return tool in self.tools

    def get_workflow(self, workflow_name: str) -> Optional[dict]:
        """获取指定工作流模板。"""
        return self.workflow_templates.get(workflow_name)

    def list_workflows(self) -> List[str]:
        """列出所有可用工作流名称。"""
        return list(self.workflow_templates.keys())


@dataclass
class ProductRDAgent(OPCAgentRole):
    """产品研发智能体。

    负责从需求分析到产品上线的完整产品研发闭环，
    涵盖需求、设计、开发、测试、部署全流程。
    """

    role: OPCRole = OPCRole.PRODUCT_RD
    name: str = "产品研发智能体"
    description: str = (
        "负责产品从0到1的研发全流程：需求分析、原型设计、技术选型、"
        "代码生成、测试验证、部署上线，保障产品高质量交付。"
    )
    capabilities: List[str] = field(default_factory=lambda: [
        "需求分析",
        "原型设计",
        "技术选型",
        "代码生成",
        "测试验证",
        "部署上线",
    ])
    tools: List[str] = field(default_factory=lambda: [
        "code.generate",
        "code.understanding",
        "action.code_exec",
        "media.image",
    ])
    workflow_templates: Dict[str, dict] = field(default_factory=lambda: {
        "新产品开发流程": {
            "name": "新产品开发流程",
            "description": "从需求到上线的完整产品开发流程",
            "stages": [
                {
                    "stage": "需求分析",
                    "tasks": ["需求收集", "需求梳理", "优先级排序", "需求文档输出"],
                    "output": "产品需求文档（PRD）",
                },
                {
                    "stage": "原型设计",
                    "tasks": ["信息架构设计", "交互流程设计", "原型图绘制", "原型评审"],
                    "output": "产品原型与交互设计稿",
                },
                {
                    "stage": "技术选型",
                    "tasks": ["架构设计", "技术栈评估", "数据库设计", "API设计"],
                    "output": "技术方案文档",
                },
                {
                    "stage": "代码生成",
                    "tasks": ["项目脚手架", "核心模块开发", "接口联调", "代码审查"],
                    "output": "可运行的代码库",
                },
                {
                    "stage": "测试验证",
                    "tasks": ["单元测试", "集成测试", "功能测试", "Bug修复"],
                    "output": "测试报告与质量评估",
                },
                {
                    "stage": "部署上线",
                    "tasks": ["环境配置", "部署脚本", "灰度发布", "上线验证"],
                    "output": "线上可用版本",
                },
            ],
        },
        "迭代优化流程": {
            "name": "迭代优化流程",
            "description": "基于用户反馈和数据的产品迭代优化",
            "stages": [
                {
                    "stage": "问题收集",
                    "tasks": ["用户反馈整理", "数据分析", "问题归类", "优先级评估"],
                    "output": "迭代需求清单",
                },
                {
                    "stage": "方案设计",
                    "tasks": ["优化方案设计", "影响评估", "技术方案", "排期计划"],
                    "output": "迭代方案文档",
                },
                {
                    "stage": "开发实现",
                    "tasks": ["代码开发", "单元测试", "代码审查", "功能联调"],
                    "output": "迭代版本代码",
                },
                {
                    "stage": "测试发布",
                    "tasks": ["回归测试", "灰度发布", "效果验证", "全量上线"],
                    "output": "上线版本与效果报告",
                },
            ],
        },
    })


@dataclass
class MarketResearchAgent(OPCAgentRole):
    """市场调研智能体。

    负责市场情报收集与分析，通过竞品分析、用户调研、
    趋势洞察为产品决策提供数据支撑。
    """

    role: OPCRole = OPCRole.MARKET_RESEARCH
    name: str = "市场调研智能体"
    description: str = (
        "负责市场情报与用户洞察：竞品分析、用户调研、痛点挖掘、"
        "市场规模测算、行业趋势分析，为决策提供数据支撑。"
    )
    capabilities: List[str] = field(default_factory=lambda: [
        "竞品分析",
        "用户调研",
        "痛点挖掘",
        "市场规模",
        "趋势分析",
    ])
    tools: List[str] = field(default_factory=lambda: [
        "web.search",
        "web.fetch",
        "web.crawl",
        "data.query",
    ])
    workflow_templates: Dict[str, dict] = field(default_factory=lambda: {
        "竞品调研流程": {
            "name": "竞品调研流程",
            "description": "系统性的竞品分析与情报收集",
            "stages": [
                {
                    "stage": "竞品锁定",
                    "tasks": ["确定竞品范围", "直接竞品识别", "间接竞品识别", "标杆产品筛选"],
                    "output": "竞品清单",
                },
                {
                    "stage": "信息收集",
                    "tasks": ["产品功能调研", "定价策略分析", "用户评价采集", "市场表现数据"],
                    "output": "竞品信息库",
                },
                {
                    "stage": "深度分析",
                    "tasks": ["功能对比矩阵", "优劣势分析", "差异化定位", "商业模式拆解"],
                    "output": "竞品分析报告",
                },
                {
                    "stage": "洞察输出",
                    "tasks": ["机会点识别", "风险预警", "策略建议", "行动清单"],
                    "output": "竞品洞察与策略建议",
                },
            ],
        },
        "用户痛点分析流程": {
            "name": "用户痛点分析流程",
            "description": "深度挖掘用户真实需求与痛点",
            "stages": [
                {
                    "stage": "用户画像",
                    "tasks": ["目标用户定义", "用户分层", "典型角色建模", "使用场景梳理"],
                    "output": "用户画像与场景地图",
                },
                {
                    "stage": "痛点收集",
                    "tasks": ["评论挖掘", "社群调研", "访谈记录整理", "问卷数据分析"],
                    "output": "用户痛点清单",
                },
                {
                    "stage": "痛点分析",
                    "tasks": ["痛点归类", "影响度评估", "频率分析", "未被满足需求识别"],
                    "output": "痛点优先级矩阵",
                },
                {
                    "stage": "机会转化",
                    "tasks": ["痛点-需求映射", "解决方案构思", "价值评估", "MVP方向建议"],
                    "output": "用户痛点转化报告",
                },
            ],
        },
    })


@dataclass
class ContentMarketingAgent(OPCAgentRole):
    """内容营销智能体。

    负责全链路内容生产与社媒运营，从文案撰写到视频策划，
    从海报设计到矩阵发布，打造品牌影响力。
    """

    role: OPCRole = OPCRole.CONTENT_MARKETING
    name: str = "内容营销智能体"
    description: str = (
        "负责全链路内容生产与社媒运营：文案撰写、脚本生成、"
        "海报设计、短视频策划、社媒矩阵运营，打造品牌影响力。"
    )
    capabilities: List[str] = field(default_factory=lambda: [
        "文案撰写",
        "脚本生成",
        "海报设计",
        "短视频策划",
        "社媒运营",
    ])
    tools: List[str] = field(default_factory=lambda: [
        "media.image",
        "media.video",
        "content.produce",
    ])
    workflow_templates: Dict[str, dict] = field(default_factory=lambda: {
        "内容生产流程": {
            "name": "内容生产流程",
            "description": "从选题到成品的标准化内容生产",
            "stages": [
                {
                    "stage": "选题策划",
                    "tasks": ["热点追踪", "用户需求分析", "选题 brainstorm", "选题评估"],
                    "output": "内容选题清单",
                },
                {
                    "stage": "内容创作",
                    "tasks": ["文案撰写", "脚本生成", "视觉设计", "素材准备"],
                    "output": "内容初稿",
                },
                {
                    "stage": "优化打磨",
                    "tasks": ["标题优化", "结构调整", "视觉优化", "审核校对"],
                    "output": "最终内容成品",
                },
                {
                    "stage": "效果复盘",
                    "tasks": ["发布数据追踪", "互动数据分析", "转化效果评估", "经验沉淀"],
                    "output": "内容效果报告",
                },
            ],
        },
        "社媒矩阵发布流程": {
            "name": "社媒矩阵发布流程",
            "description": "多平台内容适配与矩阵式发布",
            "stages": [
                {
                    "stage": "平台策略",
                    "tasks": ["平台特性分析", "受众画像匹配", "内容形式规划", "发布节奏制定"],
                    "output": "社媒矩阵策略",
                },
                {
                    "stage": "内容适配",
                    "tasks": ["平台调性适配", "内容格式转换", "素材尺寸调整", "本地化优化"],
                    "output": "各平台适配内容",
                },
                {
                    "stage": "排期发布",
                    "tasks": ["发布排期表", "定时发布", "互动维护", "评论管理"],
                    "output": "发布执行记录",
                },
                {
                    "stage": "数据整合",
                    "tasks": ["多平台数据汇总", "跨平台对比分析", "ROI评估", "策略迭代"],
                    "output": "矩阵运营周报",
                },
            ],
        },
    })


@dataclass
class CustomerServiceAgent(OPCAgentRole):
    """客户服务智能体。

    负责全渠道客户服务与关系管理，从咨询接待到售后处理，
    从客户反馈到工单管理，提升客户满意度与忠诚度。
    """

    role: OPCRole = OPCRole.CUSTOMER_SERVICE
    name: str = "客户服务智能体"
    description: str = (
        "负责全渠道客户服务与关系管理：咨询接待、问题解答、"
        "售后处理、客户反馈收集、工单管理，提升客户满意度。"
    )
    capabilities: List[str] = field(default_factory=lambda: [
        "咨询接待",
        "问题解答",
        "售后处理",
        "客户反馈",
        "工单管理",
    ])
    tools: List[str] = field(default_factory=lambda: [
        "channel.send",
        "channel.access",
        "memory.persistent",
    ])
    workflow_templates: Dict[str, dict] = field(default_factory=lambda: {
        "客户咨询流程": {
            "name": "客户咨询流程",
            "description": "标准化的客户咨询接待与解答",
            "stages": [
                {
                    "stage": "接待分流",
                    "tasks": ["客户问候", "意图识别", "咨询分类", "优先级判断"],
                    "output": "咨询工单",
                },
                {
                    "stage": "问题解答",
                    "tasks": ["知识库检索", "答案生成", "多轮对话澄清", "解决方案提供"],
                    "output": "咨询答复",
                },
                {
                    "stage": "确认跟进",
                    "tasks": ["满意度确认", "问题是否解决", "补充说明", "转人工判断"],
                    "output": "咨询处理结果",
                },
                {
                    "stage": "记录沉淀",
                    "tasks": ["对话记录归档", "FAQ更新", "知识库优化", "服务质量评估"],
                    "output": "服务记录与优化建议",
                },
            ],
        },
        "售后处理流程": {
            "name": "售后处理流程",
            "description": "售后问题的标准化处理与闭环",
            "stages": [
                {
                    "stage": "问题受理",
                    "tasks": ["售后申请接收", "问题类型判定", "订单信息核实", "客户情绪安抚"],
                    "output": "售后工单",
                },
                {
                    "stage": "方案制定",
                    "tasks": ["责任判定", "解决方案拟定", "赔偿/退换方案", "客户沟通确认"],
                    "output": "售后处理方案",
                },
                {
                    "stage": "执行处理",
                    "tasks": ["退款/换货操作", "补偿执行", "物流跟进", "进度同步"],
                    "output": "售后执行记录",
                },
                {
                    "stage": "闭环回访",
                    "tasks": ["处理结果确认", "满意度回访", "问题原因分析", "流程优化建议"],
                    "output": "售后闭环报告",
                },
            ],
        },
    })


@dataclass
class FinanceAgent(OPCAgentRole):
    """财务核算智能体。

    负责公司财务管理与核算，从成本核算到营收预估，
    从利润测税务规划，从报表生成到财务分析。
    """

    role: OPCRole = OPCRole.FINANCE
    name: str = "财务核算智能体"
    description: str = (
        "负责财务管理与核算：成本核算、营收预估、利润测算、"
        "税务规划、财务报表生成，保障财务健康与合规。"
    )
    capabilities: List[str] = field(default_factory=lambda: [
        "成本核算",
        "营收预估",
        "利润测算",
        "税务规划",
        "报表生成",
    ])
    tools: List[str] = field(default_factory=lambda: [
        "data.query",
        "action.code_exec",
    ])
    workflow_templates: Dict[str, dict] = field(default_factory=lambda: {
        "月度财务结算流程": {
            "name": "月度财务结算流程",
            "description": "月度财务结账与报表生成",
            "stages": [
                {
                    "stage": "数据收集",
                    "tasks": ["收入数据汇总", "支出凭证整理", "银行流水核对", "发票管理"],
                    "output": "月度财务数据",
                },
                {
                    "stage": "账务处理",
                    "tasks": ["凭证录入", "科目归类", "成本分摊", "折旧计提"],
                    "output": "记账凭证与账簿",
                },
                {
                    "stage": "报表生成",
                    "tasks": ["利润表编制", "资产负债表", "现金流量表", "财务指标计算"],
                    "output": "月度财务报表",
                },
                {
                    "stage": "分析报告",
                    "tasks": ["同比环比分析", "预算执行对比", "异常项说明", "经营建议"],
                    "output": "月度财务分析报告",
                },
            ],
        },
        "项目成本核算流程": {
            "name": "项目成本核算流程",
            "description": "单项目的成本归集与利润核算",
            "stages": [
                {
                    "stage": "成本归集",
                    "tasks": ["直接成本统计", "间接成本分摊", "人力成本核算", "费用归类"],
                    "output": "项目成本明细",
                },
                {
                    "stage": "收入确认",
                    "tasks": ["项目收入统计", "回款进度追踪", "应收款管理", "收入确认"],
                    "output": "项目收入明细",
                },
                {
                    "stage": "利润测算",
                    "tasks": ["毛利计算", "净利测算", "ROI分析", "敏感性分析"],
                    "output": "项目利润测算表",
                },
                {
                    "stage": "项目复盘",
                    "tasks": ["成本偏差分析", "预算执行评估", "经验总结", "优化建议"],
                    "output": "项目财务复盘报告",
                },
            ],
        },
    })


# ─────────────────────────────────────────────────────────────
# 工厂函数
# ─────────────────────────────────────────────────────────────

_AGENT_MAP: Dict[OPCRole, type] = {
    OPCRole.PRODUCT_RD: ProductRDAgent,
    OPCRole.MARKET_RESEARCH: MarketResearchAgent,
    OPCRole.CONTENT_MARKETING: ContentMarketingAgent,
    OPCRole.CUSTOMER_SERVICE: CustomerServiceAgent,
    OPCRole.FINANCE: FinanceAgent,
}


def create_agent(role: OPCRole) -> OPCAgentRole:
    """根据岗位类型创建对应智能体实例。

    Args:
        role: 岗位类型枚举值

    Returns:
        对应岗位的智能体实例

    Raises:
        ValueError: 当岗位类型不支持时抛出
    """
    agent_cls = _AGENT_MAP.get(role)
    if agent_cls is None:
        raise ValueError(f"不支持的岗位类型: {role}")
    logger.debug("创建岗位智能体: %s", role.value)
    return agent_cls()


def get_all_roles() -> List[OPCAgentRole]:
    """获取所有岗位智能体列表。

    Returns:
        所有岗位智能体实例列表
    """
    return [create_agent(role) for role in OPCRole]
