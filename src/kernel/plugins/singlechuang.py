"""单创OS 编排层：把 OPC 5 岗位注册表 + 报表芯粒 + 统一扩展点 组合成可直接调用的「活」入口。

本文件是被 autopilot（opc.orchestrate）/ API（/api/opc/plan）实际调用的，
避免 opc_roles / report_agent / extension 成为无人引用的死代码。
设计原则（用户铁律）：现有复用不重造、缺的用开源补、所有扩展留 opt-in 接口。
"""
from typing import Any, Dict, List, Optional

from .opc_roles import get_role, list_roles
from .report_agent import bom_cost, generate_report, profit_estimate
from .extension import get_extension

# 岗位固定顺序（OPC 数字组织内核的 5 大标准化岗位）
_ROLE_ORDER = ("product_rd", "market_research", "content_marketing",
               "customer_service", "finance")


def plan_company(goal: str, industry: str = "default") -> Dict[str, Any]:
    """把一句创业目标映射到 OPC 5 岗位的工作分解（复用注册表，不重造岗位逻辑）。

    返回结构可直接被前端「单创OS 工作台」渲染为五个岗位卡片 + 各自能力清单。
    """
    roles: List[Dict[str, Any]] = []
    for key in _ROLE_ORDER:
        role = get_role(key)
        if not role:
            continue
        roles.append({
            "role": role.id,
            "name": role.name,
            "capabilities": role.capabilities,
            "knowledge_base": role.knowledge_base or "",
            "dev_env": resolve_dev_env() if key == "product_rd" else None,
        })
    return {
        "goal": goal,
        "industry": industry,
        "roles": roles,
        "role_count": len(roles),
    }


def build_financial_report(
    rows: List[Dict[str, Any]],
    path: Optional[str] = None,
    title: str = "财务核算报表",
) -> Dict[str, Any]:
    """财务核算岗位调用报表芯粒产出 xlsx/csv（开源 openpyxl，无闭源依赖）。"""
    return generate_report(rows, fmt="xlsx", path=path)


def resolve_content_tools() -> List[str]:
    """内容营销岗位的工具集：默认走开源 media 栈；WorkRally 仅当授权账号存在时 opt-in 追加。

    这是 extension 扩展点的真实消费处——没账号 get_extension 返回 None，自动静默跳过，
    零腾讯依赖，不锁死核心。
    """
    tools = ["content.media_gen", "content.video_maker", "content.tts"]
    wr = get_extension("workrally")
    if wr is not None:
        tools.append("content.workrally")
    return tools


def bom_summary(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """产品研发岗位：BOM 成本汇总（开源，无闭源依赖）。"""
    return bom_cost(items)


def resolve_dev_env() -> Dict[str, Any]:
    """产品研发岗位的终端开发环境：默认无；Terax 仅当本机安装时 opt-in 提供。

    这是 extension 扩展点的真实消费处——未安装 get_extension 返回 None，自动静默跳过，
    零外部依赖，不锁死核心。与 WorkRally 的云端 opt-in 不同，Terax 是本地开源应用，
    红线 local_only=True（绝不触外部网络）。
    """
    t = get_extension("terax")
    if t is not None:
        return {"available": True, **t}
    return {"available": False, "name": "terax",
            "note": "未安装；装后自动启用（Apache-2.0 本地开源，无 token）"}


def resolve_course_tools() -> Dict[str, Any]:
    """内容营销岗位的课程/教育素材工具：OpenMAIC 仅当配置并可达时 opt-in 提供。

    这是 extension 扩展点的真实消费处——未配置 AOS_OPENMAIC_URL 或不可达时
    get_extension 返回 None，自动静默跳过，零 OpenMAIC 依赖，不锁死核心。
    与 Terax 的本地隔离不同，OpenMAIC 是独立 HTTP 服务（MIT 开源、自管 LLM）。
    """
    om = get_extension("openmaic")
    if om is not None:
        return {"available": True, **om}
    return {"available": False, "name": "openmaic",
            "note": "未配置 AOS_OPENMAIC_URL 或 OpenMAIC 未启动；配置后自动启用（MIT 开源，自管 LLM）"}


def profit_summary(revenue: float, cost: float) -> Dict[str, Any]:
    """财务岗位：利润预估（开源，无闭源依赖）。"""
    return profit_estimate(revenue, cost)


__all__ = [
    "plan_company",
    "build_financial_report",
    "resolve_content_tools",
    "resolve_dev_env",
    "resolve_course_tools",
    "bom_summary",
    "profit_summary",
    "list_roles",
]
