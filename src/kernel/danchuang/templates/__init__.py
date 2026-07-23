"""行业模板系统（Industry Templates）。"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class IndustryType(str, Enum):
    HARDWARE = "hardware"
    ECOMMERCE = "ecommerce"
    CONTENT = "content"
    SERVICE = "service"
    GENERAL = "general"


@dataclass
class IndustryTemplate:
    industry: IndustryType
    name: str
    description: str
    role_config: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    workflow_templates: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    knowledge_seeds: List[Dict[str, str]] = field(default_factory=list)
    recommended_tools: List[str] = field(default_factory=list)
    kpi_examples: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "industry": self.industry.value,
            "name": self.name,
            "description": self.description,
            "role_config": self.role_config,
            "workflow_templates": self.workflow_templates,
            "knowledge_seeds": self.knowledge_seeds,
            "recommended_tools": self.recommended_tools,
            "kpi_examples": self.kpi_examples,
        }


_TEMPLATES: Dict[IndustryType, IndustryTemplate] = {}


def _init_templates() -> None:
    if _TEMPLATES:
        return
    _TEMPLATES[IndustryType.GENERAL] = IndustryTemplate(
        industry=IndustryType.GENERAL,
        name="通用创业模板",
        description="通用型一人公司模板，5个岗位均衡配置",
        role_config={
            "product_rd": {"weight": 0.25},
            "market_research": {"weight": 0.20},
            "content_marketing": {"weight": 0.20},
            "customer_service": {"weight": 0.20},
            "finance": {"weight": 0.15},
        },
        kpi_examples=[
            {"name": "月营收", "target": ">1万", "unit": "元", "description": "月度营业收入"},
            {"name": "利润率", "target": ">30%", "unit": "%", "description": "净利润率"},
        ],
    )
    _TEMPLATES[IndustryType.HARDWARE] = IndustryTemplate(
        industry=IndustryType.HARDWARE,
        name="硬件创业模板",
        description="面向智能硬件、消费电子、IoT设备创业者，含护眼眼镜行业专属配置",
        role_config={
            "product_rd": {"weight": 0.35, "additional_capabilities": [
                "硬件选型", "PCB设计", "固件开发", "结构设计",
                "BOM成本核算", "样品验证", "量产准备",
            ]},
            "market_research": {"weight": 0.20, "additional_capabilities": [
                "供应链调研", "元器件价格趋势", "代工厂评估",
            ]},
            "content_marketing": {"weight": 0.20, "additional_capabilities": [
                "产品视频制作", "开箱评测脚本", "众筹文案",
            ]},
            "finance": {"weight": 0.15, "additional_capabilities": [
                "BOM成本核算", "开模费用评估", "量产成本测算",
            ]},
            "customer_service": {"weight": 0.10, "additional_capabilities": [
                "售后维修流程", "质保政策", "固件升级指导",
            ]},
        },
        workflow_templates={
            "eyewear_product_development": {
                "name": "青少年护眼眼镜开发流程",
                "description": "从需求定义到量产出货的完整硬件开发流程",
                "stages": [
                    {"name": "需求定义", "duration_weeks": 2, "deliverables": ["PRD需求文档", "目标用户画像"], "assigned_role": "product_rd"},
                    {"name": "方案设计", "duration_weeks": 3, "deliverables": ["硬件方案选型", "结构设计图", "BOM清单"], "assigned_role": "product_rd"},
                    {"name": "原型开发", "duration_weeks": 4, "deliverables": ["PCB打样", "固件初版", "原型机3D打印"], "assigned_role": "product_rd"},
                    {"name": "测试验证", "duration_weeks": 2, "deliverables": ["功能测试报告", "可靠性测试", "用户试用反馈"], "assigned_role": "product_rd"},
                    {"name": "量产准备", "duration_weeks": 3, "deliverables": ["模具开发", "小批量试产", "供应链确认"], "assigned_role": "product_rd"},
                    {"name": "上市推广", "duration_weeks": 4, "deliverables": ["营销素材", "众筹/电商上架", "用户运营"], "assigned_role": "content_marketing"},
                ],
            },
        },
        knowledge_seeds=[
            {"category": "护眼眼镜", "topic": "坐姿检测技术方案", "content": "主流方案：YOLOv8姿态估计、MediaPipe Face Mesh、深度摄像头、陀螺仪加速度计"},
            {"category": "护眼眼镜", "topic": "主控芯片选型", "content": "全志V853、瑞芯微RK3566、ESP32-S3、nRF52832"},
            {"category": "护眼眼镜", "topic": "电池续航方案", "content": "聚合物锂电池、Type-C充电、低功耗模式、续航目标8小时以上"},
            {"category": "硬件创业", "topic": "BOM构成", "content": "主控、传感器、电池、结构件、包装、物流、税费"},
            {"category": "硬件创业", "topic": "开发流程", "content": "ID设计→MD设计→EVT→DVT→PVT→MP"},
        ],
        recommended_tools=["KiCad", "立创EDA", "SolidWorks", "嘉立创打样", "PCBWay"],
        kpi_examples=[
            {"name": "BOM成本", "target": "<50元", "unit": "元", "description": "单台物料成本"},
            {"name": "续航时间", "target": ">8小时", "unit": "小时", "description": "单次充电使用时长"},
            {"name": "检测准确率", "target": ">95%", "unit": "%", "description": "坐姿检测准确率"},
        ],
    )
    _TEMPLATES[IndustryType.ECOMMERCE] = IndustryTemplate(
        industry=IndustryType.ECOMMERCE,
        name="电商创业模板",
        description="面向淘宝/抖店/拼多多等电商平台创业者",
        role_config={
            "content_marketing": {"weight": 0.30, "additional_capabilities": ["主图设计", "详情页文案", "短视频脚本", "直播脚本"]},
            "market_research": {"weight": 0.25, "additional_capabilities": ["选品分析", "竞品监控", "关键词研究"]},
            "customer_service": {"weight": 0.20, "additional_capabilities": ["售前咨询", "售后处理", "差评处理"]},
            "product_rd": {"weight": 0.10, "additional_capabilities": ["产品摄影", "上架维护", "库存管理"]},
            "finance": {"weight": 0.15, "additional_capabilities": ["利润核算", "推广ROI计算"]},
        },
        kpi_examples=[
            {"name": "点击率", "target": ">5%", "unit": "%", "description": "主图点击率"},
            {"name": "转化率", "target": ">3%", "unit": "%", "description": "访客转化率"},
        ],
    )
    _TEMPLATES[IndustryType.CONTENT] = IndustryTemplate(
        industry=IndustryType.CONTENT,
        name="自媒体/内容创作模板",
        description="面向短视频、图文、自媒体创业者",
        role_config={
            "content_marketing": {"weight": 0.40, "additional_capabilities": ["选题策划", "脚本撰写", "剪辑指导", "矩阵运营"]},
            "market_research": {"weight": 0.20, "additional_capabilities": ["热点追踪", "竞品账号分析", "爆款拆解"]},
            "finance": {"weight": 0.15, "additional_capabilities": ["广告收益核算", "商单报价"]},
            "customer_service": {"weight": 0.15, "additional_capabilities": ["评论回复", "粉丝互动", "私域运营"]},
            "product_rd": {"weight": 0.10, "additional_capabilities": ["工具使用", "效率优化"]},
        },
        kpi_examples=[
            {"name": "完播率", "target": ">30%", "unit": "%", "description": "视频完播率"},
            {"name": "互动率", "target": ">5%", "unit": "%", "description": "点赞评论转发/播放"},
        ],
    )
    _TEMPLATES[IndustryType.SERVICE] = IndustryTemplate(
        industry=IndustryType.SERVICE,
        name="服务/咨询模板",
        description="面向设计、咨询、开发等服务类创业者",
        role_config={
            "product_rd": {"weight": 0.30, "additional_capabilities": ["服务产品化", "SOP标准化", "质量把控"]},
            "customer_service": {"weight": 0.25, "additional_capabilities": ["客户对接", "需求沟通", "项目跟进"]},
            "content_marketing": {"weight": 0.20, "additional_capabilities": ["案例包装", "获客内容", "个人品牌"]},
            "market_research": {"weight": 0.15, "additional_capabilities": ["行业研究", "客户画像"]},
            "finance": {"weight": 0.10, "additional_capabilities": ["报价方案", "合同管理"]},
        },
        kpi_examples=[
            {"name": "客单价", "target": ">5000元", "unit": "元", "description": "单项目客单价"},
            {"name": "复购率", "target": ">30%", "unit": "%", "description": "客户复购率"},
        ],
    )


def get_template(industry: str | IndustryType) -> Optional[IndustryTemplate]:
    _init_templates()
    if isinstance(industry, str):
        try:
            industry = IndustryType(industry)
        except ValueError:
            industry = IndustryType.GENERAL
    return _TEMPLATES.get(industry)


def list_templates() -> List[IndustryTemplate]:
    _init_templates()
    return list(_TEMPLATES.values())
