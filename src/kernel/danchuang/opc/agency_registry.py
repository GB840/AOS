"""Agency 角色注册中心 — 把 147+ 个专业角色挂到 OPC 5 大岗位下。

融合 The Agency 的 12 部门 147+ 专业角色到 OPC 数字组织内核，
形成「5 大一级岗位 + N 个二级专业角色」的两级角色体系。

角色来源：agency-agents-zh/ （The Agency 中文翻译版）
映射策略：按专业领域归类到 OPC 5 大岗位
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .roles import OPCRole

logger = logging.getLogger(__name__)


@dataclass
class AgencyAgentSpec:
    """Agency 专业角色定义。

    封装从 agency-agents-zh 加载的角色信息，
    包含身份、能力、工作流、所属 OPC 岗位等。
    """

    agent_id: str
    name: str
    description: str
    emoji: str = ""
    color: str = ""
    department: str = ""
    opc_role: OPCRole = OPCRole.PRODUCT_RD
    capabilities: List[str] = field(default_factory=list)
    workflow_steps: List[str] = field(default_factory=list)
    success_metrics: List[str] = field(default_factory=list)
    file_path: str = ""
    raw_content: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "description": self.description,
            "emoji": self.emoji,
            "color": self.color,
            "department": self.department,
            "opc_role": self.opc_role.value,
            "capabilities": self.capabilities,
            "workflow_steps": self.workflow_steps,
            "success_metrics": self.success_metrics,
            "file_path": self.file_path,
        }


# ── OPC 岗位 → Agency 部门/角色映射 ─────────────────────────
# 定义哪些 agency 部门/角色归属到哪个 OPC 一级岗位

_OPC_ROLE_MAPPING: Dict[OPCRole, Dict[str, Any]] = {
    OPCRole.PRODUCT_RD: {
        "departments": [
            "engineering",
            "design",
            "product",
            "game-development",
            "gis",
            "spatial-computing",
            "testing",
        ],
        "specialized_agents": [
            "specialized/specialized-workflow-architect",
            "specialized/specialized-mcp-builder",
            "specialized/specialized-model-qa",
        ],
        "description": "产品研发群：含工程、设计、产品、测试等 41+9+4+10+12+6+8 = 90+ 专业角色",
    },
    OPCRole.MARKET_RESEARCH: {
        "departments": [
            "academic",
            "strategy",
            "security",
        ],
        "specialized_agents": [
            "specialized/business-strategist",
            "specialized/specialized-risk-assessor",
            "specialized/specialized-pricing-analyst",
            "specialized/specialized-cultural-intelligence-strategist",
        ],
        "description": "市场调研群：含学术研究、战略、安全分析等 6+1+19 = 26 专业角色",
    },
    OPCRole.CONTENT_MARKETING: {
        "departments": [
            "marketing",
        ],
        "specialized_agents": [
            "specialized/specialized-chief-of-staff",
            "specialized/specialized-document-generator",
            "specialized/technical-translator-agent",
            "specialized/language-translator",
            "specialized/specialized-developer-advocate",
            "specialized/grant-writer",
            "specialized/specialized-salesforce-architect",
        ],
        "description": "内容营销群：含全平台营销、社媒运营、内容创作等 50+ 专业角色",
    },
    OPCRole.CUSTOMER_SERVICE: {
        "departments": [
            "support",
            "hr",
            "legal",
        ],
        "specialized_agents": [
            "specialized/customer-success-manager",
            "specialized/healthcare-customer-service",
            "specialized/hospitality-guest-services",
            "specialized/retail-customer-returns",
            "specialized/hr-onboarding",
            "specialized/legal-client-intake",
        ],
        "description": "客户服务群：含支持、HR、法务客户对接等 7+2+2 = 11 专业角色",
    },
    OPCRole.FINANCE: {
        "departments": [
            "finance",
            "sales",
            "supply-chain",
            "paid-media",
            "project-management",
        ],
        "specialized_agents": [
            "specialized/chief-financial-officer",
            "specialized/bookkeeper-controller",
            "specialized/accounts-payable-agent",
            "specialized/sales-data-extraction-agent",
            "specialized/report-distribution-agent",
            "specialized/data-consolidation-agent",
            "specialized/specialized-french-consulting-market",
            "specialized/specialized-korean-business-navigator",
            "specialized/recruitment-specialist",
            "specialized/real-estate-buyer-seller",
            "specialized/study-abroad-advisor",
            "specialized/gaokao-college-advisor",
            "specialized/personal-growth-mentor",
            "specialized/operations-manager",
            "specialized/organizational-psychologist",
            "specialized/change-management-consultant",
            "specialized/specialized-civil-engineer",
            "specialized/specialized-government-digital-presales-consultant",
            "specialized/specialized-ai-policy-writer",
            "specialized/automation-governance-architect",
            "specialized/agentic-identity-trust",
            "specialized/identity-graph-operator",
            "specialized/zk-steward",
            "specialized/data-privacy-officer",
            "specialized/esg-sustainability-officer",
            "specialized/livestock-archive-auditor",
            "specialized/loan-officer-assistant",
            "specialized/lsp-index-engineer",
            "specialized/ma-integration-manager",
            "specialized/medical-billing-coding-specialist",
            "specialized/specialized-pricing-optimizer",
            "specialized/specialized-strategy-duel-agent",
        ],
        "description": "财务核算群：含财务、销售、供应链、付费媒体、项目管理等 8+12+5+6+6 = 37 专业角色",
    },
}

# 部门中文名映射
_DEPT_NAME_MAP: Dict[str, str] = {
    "engineering": "工程部",
    "design": "设计部",
    "product": "产品部",
    "marketing": "营销部",
    "finance": "金融部",
    "sales": "销售部",
    "support": "支持部",
    "hr": "人力资源部",
    "legal": "法务部",
    "academic": "学术部",
    "strategy": "战略部",
    "security": "安全部",
    "gis": "GIS部",
    "game-development": "游戏开发部",
    "spatial-computing": "空间计算部",
    "testing": "测试部",
    "supply-chain": "供应链部",
    "paid-media": "付费媒体部",
    "project-management": "项目管理部",
    "specialized": "专家团",
}


class AgencyRegistry:
    """Agency 角色注册中心。

    管理 147+ 专业角色的加载、查询、按 OPC 岗位归类等。
    支持从 agency-agents-zh 目录动态加载，也支持内置静态索引。
    """

    def __init__(self, agency_dir: str = None):
        """
        Args:
            agency_dir: agency-agents-zh 目录路径（默认自动探测）
        """
        if agency_dir is None:
            agency_dir = str(
                Path(__file__).resolve().parents[4] / "agency-agents-zh"
            )
        self._agency_dir = Path(agency_dir)
        self._agents: Dict[str, AgencyAgentSpec] = {}
        self._by_opc_role: Dict[OPCRole, List[AgencyAgentSpec]] = {
            role: [] for role in OPCRole
        }
        self._loaded = False
        self._load_agents()

    def _load_agents(self) -> None:
        """加载所有 agency 角色。

        优先从文件系统加载 agency-agents-zh 目录，
        若目录不存在则使用内置的核心角色索引（保证系统可用）。
        """
        if self._loaded:
            return

        if self._agency_dir.exists():
            self._load_from_filesystem()
        else:
            logger.warning(
                "agency-agents-zh 目录不存在: %s，使用内置核心角色索引",
                self._agency_dir,
            )
            self._load_builtin_index()

        self._loaded = True
        logger.info(
            "Agency 角色注册完成: 共 %d 个角色",
            len(self._agents),
        )

    def _load_from_filesystem(self) -> None:
        """从文件系统加载 agency 角色。"""
        import re

        md_files = list(self._agency_dir.rglob("*.md"))
        for md_file in md_files:
            rel_path = md_file.relative_to(self._agency_dir)
            rel_str = str(rel_path).replace("\\", "/")

            if rel_str.startswith(("strategy/", "scripts/", "examples/", ".")):
                if not rel_str.startswith("strategy/coordination/") and \
                   not rel_str.startswith("strategy/playbooks/") and \
                   not rel_str.startswith("strategy/runbooks/"):
                    continue
            if md_file.name in (
                "README.md", "CATALOG.md", "AGENT-LIST.md", "UPSTREAM.md",
                "CONTRIBUTING.md", "README.zh-TW.md", "QUICKSTART.md",
                "EXECUTIVE-BRIEF.md", "nexus-strategy.md",
            ):
                continue
            if md_file.suffix != ".md":
                continue

            try:
                content = md_file.read_text(encoding="utf-8")
                spec = self._parse_agent_md(rel_str, content)
                if spec is not None:
                    self._register_agent(spec)
            except Exception as e:
                logger.debug("解析角色文件失败 %s: %s", rel_str, e)

    def _parse_agent_md(
        self, rel_path: str, content: str
    ) -> Optional[AgencyAgentSpec]:
        """解析单个 agency 角色 markdown 文件。

        Args:
            rel_path: 相对路径，如 engineering/engineering-software-architect.md
            content: 文件内容

        Returns:
            AgencyAgentSpec 或 None
        """
        import re

        frontmatter_match = re.match(
            r"^---\n(.*?)\n---", content, re.DOTALL
        )
        if not frontmatter_match:
            return None

        frontmatter = frontmatter_match.group(1)

        def extract_field(name: str) -> str:
            m = re.search(rf"^{name}:\s*(.+)$", frontmatter, re.MULTILINE)
            return m.group(1).strip().strip('"').strip("'") if m else ""

        name = extract_field("name")
        description = extract_field("description")
        emoji = extract_field("emoji")
        color = extract_field("color")

        if not name:
            return None

        parts = rel_path.split("/")
        department = parts[0] if len(parts) > 1 else "unknown"

        agent_id = Path(rel_path).stem
        if agent_id.startswith(f"{department}-"):
            agent_id = agent_id[len(department) + 1:]

        full_agent_id = f"{department}.{agent_id}"

        opc_role = self._map_department_to_opc(department, full_agent_id)

        body = content[frontmatter_match.end():].strip()

        capabilities = self._extract_capabilities(body)
        workflow_steps = self._extract_workflow_steps(body)
        success_metrics = self._extract_success_metrics(body)

        return AgencyAgentSpec(
            agent_id=full_agent_id,
            name=name,
            description=description,
            emoji=emoji,
            color=color,
            department=department,
            opc_role=opc_role,
            capabilities=capabilities,
            workflow_steps=workflow_steps,
            success_metrics=success_metrics,
            file_path=rel_path,
            raw_content=content,
        )

    def _map_department_to_opc(
        self, department: str, agent_id: str
    ) -> OPCRole:
        """根据部门和角色ID映射到 OPC 岗位。"""
        for opc_role, mapping in _OPC_ROLE_MAPPING.items():
            if department in mapping.get("departments", []):
                return opc_role
            for special in mapping.get("specialized_agents", []):
                if agent_id.endswith(Path(special).stem):
                    return opc_role

        if department == "specialized":
            return OPCRole.PRODUCT_RD

        return OPCRole.PRODUCT_RD

    def _extract_capabilities(self, body: str) -> List[str]:
        """从正文中提取能力列表。"""
        import re

        capabilities = []
        patterns = [
            r"##\s*(?:核心使命|主要职责|你的职责|负责什么)[^\n]*\n(.*?)(?=\n##|\Z)",
            r"###\s*(?:核心功能|关键能力|主要能力)[^\n]*\n(.*?)(?=\n###|\n##|\Z)",
        ]

        for pattern in patterns:
            match = re.search(pattern, body, re.DOTALL)
            if match:
                section = match.group(1)
                items = re.findall(r"^\s*[-*]\s*(.+)$", section, re.MULTILINE)
                if items:
                    capabilities = [
                        re.sub(r"\*\*(.+?)\*\*", r"\1", item).strip(" -")
                        for item in items
                        if len(item.strip()) > 2
                    ][:10]
                    break

        return capabilities

    def _extract_workflow_steps(self, body: str) -> List[str]:
        """从正文中提取工作流步骤。"""
        import re

        steps = []
        patterns = [
            r"##\s*(?:工作流程|工作流|执行流程|开发流程)[^\n]*\n(.*?)(?=\n##|\Z)",
            r"###\s*(?:第.*?步|流程|步骤)[^\n]*\n(.*?)(?=\n###|\n##|\Z)",
        ]

        for pattern in patterns:
            match = re.search(pattern, body, re.DOTALL)
            if match:
                section = match.group(1)
                items = re.findall(
                    r"^\s*###\s*(?:第\s*\d+\s*步[：: ]*)?(.+)$",
                    section,
                    re.MULTILINE,
                )
                if not items:
                    items = re.findall(
                        r"^\s*[-*]\s*(?:\*\*)?(.+?)(?:\*\*)?[：:]?",
                        section,
                        re.MULTILINE,
                    )
                if items:
                    steps = [item.strip() for item in items if len(item.strip()) > 2][:8]
                    break

        return steps

    def _extract_success_metrics(self, body: str) -> List[str]:
        """从正文中提取成功指标。"""
        import re

        metrics = []
        patterns = [
            r"##\s*(?:成功指标|衡量标准|KPI|关键指标)[^\n]*\n(.*?)(?=\n##|\Z)",
        ]

        for pattern in patterns:
            match = re.search(pattern, body, re.DOTALL)
            if match:
                section = match.group(1)
                items = re.findall(r"^\s*[-*]\s*(.+)$", section, re.MULTILINE)
                if items:
                    metrics = [item.strip() for item in items if len(item.strip()) > 2][:8]
                    break

        return metrics

    def _register_agent(self, spec: AgencyAgentSpec) -> None:
        """注册一个角色。"""
        self._agents[spec.agent_id] = spec
        self._by_opc_role[spec.opc_role].append(spec)

    def _load_builtin_index(self) -> None:
        """加载内置核心角色索引（当 agency-agents-zh 目录不存在时的降级方案）。"""
        _builtin = [
            (OPCRole.PRODUCT_RD, "engineering.software-architect", "软件架构师",
             "系统设计、领域驱动设计、架构模式和技术决策专家"),
            (OPCRole.PRODUCT_RD, "engineering.frontend-developer", "前端开发者",
             "专注于构建高质量、可维护的用户界面和前端应用"),
            (OPCRole.PRODUCT_RD, "engineering.senior-developer", "高级开发者",
             "资深全栈工程师，精通多种技术栈和最佳实践"),
            (OPCRole.PRODUCT_RD, "design.ui-designer", "UI设计师",
             "用户界面设计专家，打造美观且易用的产品视觉"),
            (OPCRole.PRODUCT_RD, "product.product-manager", "产品经理",
             "产品规划与设计专家，从用户需求到产品交付全流程"),
            (OPCRole.MARKET_RESEARCH, "academic.anthropologist", "人类学家",
             "用户研究与文化分析专家，深度洞察用户行为"),
            (OPCRole.MARKET_RESEARCH, "business.strategist", "商业战略家",
             "商业战略与市场分析专家，制定企业发展方向"),
            (OPCRole.CONTENT_MARKETING, "marketing.xiaohongshu-operator", "小红书运营专家",
             "小红书平台内容运营与种草策略专家"),
            (OPCRole.CONTENT_MARKETING, "marketing.douyin-strategist", "抖音策略师",
             "抖音短视频平台内容策略与增长专家"),
            (OPCRole.CONTENT_MARKETING, "marketing.content-creator", "内容创作者",
             "全平台内容创作与文案撰写专家"),
            (OPCRole.CUSTOMER_SERVICE, "support.support-responder", "客服响应者",
             "客户服务与问题解答专家，提升客户满意度"),
            (OPCRole.FINANCE, "finance.financial-analyst", "财务分析师",
             "财务分析与报表专家，企业财务健康度评估"),
            (OPCRole.FINANCE, "sales.deal-strategist", "赢单策略师",
             "销售策略与谈判专家，提升成交转化率"),
        ]

        for opc_role, agent_id, name, desc in _builtin:
            parts = agent_id.split(".")
            dept = parts[0] if len(parts) > 1 else "general"
            spec = AgencyAgentSpec(
                agent_id=agent_id,
                name=name,
                description=desc,
                department=dept,
                opc_role=opc_role,
                capabilities=[desc],
            )
            self._register_agent(spec)

    # ── 查询 API ──────────────────────────────────────────────

    def get_agent(self, agent_id: str) -> Optional[AgencyAgentSpec]:
        """根据ID获取角色。

        Args:
            agent_id: 角色ID，如 engineering.software-architect

        Returns:
            AgencyAgentSpec 或 None
        """
        return self._agents.get(agent_id)

    def list_agents(
        self,
        opc_role: OPCRole = None,
        department: str = None,
        limit: int = None,
    ) -> List[AgencyAgentSpec]:
        """列出角色，可按OPC岗位或部门筛选。

        Args:
            opc_role: 按 OPC 岗位筛选
            department: 按部门筛选
            limit: 返回数量限制

        Returns:
            角色列表
        """
        result = list(self._agents.values())

        if opc_role is not None:
            result = [a for a in result if a.opc_role == opc_role]

        if department is not None:
            result = [a for a in result if a.department == department]

        if limit is not None:
            result = result[:limit]

        return result

    def get_role_summary(self, opc_role: OPCRole) -> Dict[str, Any]:
        """获取某个 OPC 岗位下的角色汇总。

        Args:
            opc_role: OPC 岗位

        Returns:
            汇总信息
        """
        agents = self._by_opc_role.get(opc_role, [])
        departments = {}
        for agent in agents:
            dept_name = _DEPT_NAME_MAP.get(agent.department, agent.department)
            if dept_name not in departments:
                departments[dept_name] = []
            departments[dept_name].append({
                "agent_id": agent.agent_id,
                "name": agent.name,
                "emoji": agent.emoji,
                "description": agent.description[:50] + "..."
                if len(agent.description) > 50
                else agent.description,
            })

        mapping = _OPC_ROLE_MAPPING.get(opc_role, {})

        return {
            "opc_role": opc_role.value,
            "agent_count": len(agents),
            "departments": departments,
            "description": mapping.get("description", ""),
        }

    def get_full_hierarchy(self) -> Dict[str, Any]:
        """获取完整的两级角色体系。

        Returns:
            {
              "product_rd": { ... 岗位汇总 + 角色列表 ... },
              ...
            }
        """
        result = {}
        for role in OPCRole:
            result[role.value] = self.get_role_summary(role)
        return result

    def search_agents(self, keyword: str, limit: int = 10) -> List[AgencyAgentSpec]:
        """搜索角色。

        Args:
            keyword: 搜索关键词
            limit: 返回数量限制

        Returns:
            匹配的角色列表
        """
        keyword_lower = keyword.lower()
        scored = []

        for agent in self._agents.values():
            score = 0
            if keyword_lower in agent.name.lower():
                score += 10
            if keyword_lower in agent.description.lower():
                score += 5
            if keyword_lower in agent.agent_id.lower():
                score += 3
            for cap in agent.capabilities:
                if keyword_lower in cap.lower():
                    score += 2
                    break

            if score > 0:
                scored.append((score, agent))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [a for _, a in scored[:limit]]

    def get_agent_prompt(self, agent_id: str) -> Optional[str]:
        """获取角色的完整 prompt（原始 markdown 内容）。

        Args:
            agent_id: 角色ID

        Returns:
            角色完整定义（可直接用作 system prompt）
        """
        agent = self._agents.get(agent_id)
        if not agent:
            return None
        if agent.raw_content:
            return agent.raw_content
        return self._build_prompt_from_spec(agent)

    def _build_prompt_from_spec(self, spec: AgencyAgentSpec) -> str:
        """从 spec 构建 prompt。"""
        lines = [
            f"# {spec.name}",
            "",
            f"你是**{spec.name}**。{spec.description}",
            "",
        ]
        if spec.capabilities:
            lines.append("## 核心能力")
            for cap in spec.capabilities:
                lines.append(f"- {cap}")
            lines.append("")
        if spec.workflow_steps:
            lines.append("## 工作流程")
            for i, step in enumerate(spec.workflow_steps, 1):
                lines.append(f"{i}. {step}")
            lines.append("")
        return "\n".join(lines)

    def total_count(self) -> int:
        """角色总数。"""
        return len(self._agents)


# ── 单例 ────────────────────────────────────────────────────────

_registry: Optional[AgencyRegistry] = None


def get_agency_registry() -> AgencyRegistry:
    """获取 Agency 角色注册中心单例。"""
    global _registry
    if _registry is None:
        _registry = AgencyRegistry()
    return _registry


def reload_agency_registry() -> AgencyRegistry:
    """重新加载 Agency 角色注册中心。"""
    global _registry
    _registry = AgencyRegistry()
    return _registry
