"""单创OS（DanchuangOS）系统测试。"""
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


class TestOPCRoles:
    """OPC岗位智能体测试。"""

    def test_import(self):
        from kernel.danchuang.opc.roles import OPCRole, OPCAgentRole, get_all_roles, create_agent
        assert OPCRole is not None
        assert OPCAgentRole is not None

    def test_all_five_roles(self):
        from kernel.danchuang.opc.roles import get_all_roles
        roles = get_all_roles()
        assert len(roles) == 5
        role_names = [r.name for r in roles]
        assert any("产品研发" in n for n in role_names)
        assert any("市场调研" in n for n in role_names)
        assert any("内容营销" in n for n in role_names)
        assert any("客户服务" in n for n in role_names)
        assert any("财务核算" in n for n in role_names)

    def test_create_agent_by_role(self):
        from kernel.danchuang.opc.roles import create_agent, OPCRole
        for role in OPCRole:
            agent = create_agent(role)
            assert agent is not None
            assert agent.role == role
            assert hasattr(agent, "capabilities")
            assert hasattr(agent, "tools")
            assert hasattr(agent, "workflow_templates")

    def test_to_dict(self):
        from kernel.danchuang.opc.roles import create_agent, OPCRole
        agent = create_agent(OPCRole.PRODUCT_RD)
        d = agent.to_dict()
        assert "role" in d
        assert "name" in d
        assert "capabilities" in d
        assert "tools" in d

    def test_has_capability(self):
        from kernel.danchuang.opc.roles import create_agent, OPCRole
        agent = create_agent(OPCRole.PRODUCT_RD)
        assert agent.has_capability("代码生成") or agent.has_capability("需求分析")


class TestTenantManager:
    """多租户管理测试。"""

    @pytest.fixture
    def tm(self, tmp_path):
        from kernel.danchuang.tenant.tenant_manager import TenantManager
        db_path = str(tmp_path / "test_tenants.db")
        return TenantManager(db_path=db_path)

    def test_create_tenant(self, tm):
        tenant = tm.create_tenant("测试公司", "test@example.com", "standard", "hardware")
        assert tenant is not None
        assert tenant.tenant_id.startswith("tnt_")
        assert tenant.name == "测试公司"
        assert tenant.email == "test@example.com"
        assert tenant.status == "active"
        assert tenant.industry == "hardware"

    def test_get_tenant(self, tm):
        t = tm.create_tenant("A", "a@a.com", "free", "general")
        found = tm.get_tenant(t.tenant_id)
        assert found is not None
        assert found.tenant_id == t.tenant_id
        assert found.name == "A"

    def test_list_tenants(self, tm):
        tm.create_tenant("A", "a@a.com", "free", "general")
        tm.create_tenant("B", "b@b.com", "standard", "hardware")
        all_tenants = tm.list_tenants()
        assert len(all_tenants) == 2
        active = tm.list_tenants(status="active")
        assert len(active) == 2

    def test_suspend_and_activate(self, tm):
        t = tm.create_tenant("A", "a@a.com", "free", "general")
        assert tm.suspend_tenant(t.tenant_id) is True
        found = tm.get_tenant(t.tenant_id)
        assert found.status == "suspended"
        assert tm.activate_tenant(t.tenant_id) is True
        found2 = tm.get_tenant(t.tenant_id)
        assert found2.status == "active"

    def test_api_key_management(self, tm):
        t = tm.create_tenant("A", "a@a.com", "free", "general")
        key = tm.generate_api_key(t.tenant_id)
        assert key.startswith("sk-")
        validated = tm.validate_api_key(key)
        assert validated is not None
        assert validated.tenant_id == t.tenant_id
        assert tm.validate_api_key("sk-invalid") is None

    def test_update_plan(self, tm):
        t = tm.create_tenant("A", "a@a.com", "free", "general")
        assert tm.update_plan(t.tenant_id, "professional") is True
        found = tm.get_tenant(t.tenant_id)
        assert found.plan.value == "professional"


class TestTenantIsolation:
    """租户数据隔离测试。"""

    @pytest.fixture
    def iso(self, tmp_path):
        from kernel.danchuang.tenant.isolation import TenantDataIsolation
        return TenantDataIsolation(tenants_root=str(tmp_path / "tenants"))

    def test_ensure_tenant_space(self, iso):
        iso.ensure_tenant_space("test_tenant")
        ws = iso.get_tenant_workspace("test_tenant")
        assert ws.exists()
        assert ws.is_dir()
        kb = iso.get_tenant_kb_dir("test_tenant")
        assert kb.exists()

    def test_config_management(self, iso):
        iso.ensure_tenant_space("test_tenant")
        cfg = iso.get_tenant_config("test_tenant")
        assert isinstance(cfg, dict)
        iso.update_tenant_config("test_tenant", {"theme": "dark", "lang": "zh"})
        cfg2 = iso.get_tenant_config("test_tenant")
        assert cfg2.get("theme") == "dark"
        assert cfg2.get("lang") == "zh"

    def test_isolate_sandbox(self, iso):
        iso.ensure_tenant_space("test_tenant")
        sandbox = iso.isolate_sandbox("test_tenant", "my_sandbox")
        assert "test_tenant" in sandbox
        assert Path(sandbox).exists()

    def test_cleanup_tenant_space(self, iso):
        iso.ensure_tenant_space("test_tenant")
        ws = iso.get_tenant_workspace("test_tenant")
        assert ws.exists()
        iso.cleanup_tenant_space("test_tenant")
        assert not Path(iso.tenants_root / "test_tenant").exists()


class TestIndustryTemplates:
    """行业模板系统测试。"""

    def test_list_templates(self):
        from kernel.danchuang.templates import list_templates
        templates = list_templates()
        assert len(templates) >= 5
        names = [t.name for t in templates]
        assert any("硬件" in n for n in names)
        assert any("电商" in n for n in names)
        assert any("内容" in n or "自媒体" in n for n in names)
        assert any("服务" in n or "咨询" in n for n in names)
        assert any("通用" in n for n in names)

    def test_hardware_template_eyewear(self):
        from kernel.danchuang.templates import get_template, IndustryType
        t = get_template(IndustryType.HARDWARE)
        assert t is not None
        assert "eyewear_product_development" in t.workflow_templates
        wf = t.workflow_templates["eyewear_product_development"]
        assert "stages" in wf
        assert len(wf["stages"]) >= 5

    def test_get_template_by_string(self):
        from kernel.danchuang.templates import get_template
        t = get_template("hardware")
        assert t is not None
        assert t.industry.value == "hardware"

    def test_invalid_industry_fallback(self):
        from kernel.danchuang.templates import get_template
        t = get_template("nonexistent_industry")
        assert t is not None
        assert t.industry.value == "general"

    def test_knowledge_seeds(self):
        from kernel.danchuang.templates import get_template, IndustryType
        t = get_template(IndustryType.HARDWARE)
        assert len(t.knowledge_seeds) > 0
        topics = [k["topic"] for k in t.knowledge_seeds]
        assert any("坐姿" in t or "芯片" in t or "BOM" in t for t in topics)

    def test_kpi_examples(self):
        from kernel.danchuang.templates import get_template, IndustryType
        t = get_template(IndustryType.HARDWARE)
        assert len(t.kpi_examples) > 0


class TestGoalDecomposer:
    """目标拆解引擎测试。"""

    def test_import(self):
        from kernel.danchuang.engine.goal_decomposer import GoalDecomposer
        assert GoalDecomposer is not None

    def test_decompose_general(self):
        from kernel.danchuang.engine.goal_decomposer import GoalDecomposer
        gd = GoalDecomposer()
        result = gd.decompose("做一个个人博客网站", "general")
        assert result is not None
        assert hasattr(result, "projects") or "projects" in (result.to_dict() if hasattr(result, "to_dict") else result)

    def test_decompose_hardware(self):
        from kernel.danchuang.engine.goal_decomposer import GoalDecomposer
        gd = GoalDecomposer()
        result = gd.decompose("开发青少年坐姿矫正AI眼镜", "hardware")
        d = result.to_dict() if hasattr(result, "to_dict") else result
        assert "projects" in d or "goal" in d


class TestDanchuangOS:
    """单创OS总入口测试。"""

    @pytest.fixture
    def dcos(self, tmp_path):
        from kernel.danchuang.core import DanchuangOS
        data_dir = str(tmp_path / "danchuang_data")
        return DanchuangOS(data_dir=data_dir)

    def test_system_init(self, dcos):
        status = dcos.system_status()
        assert status.tenant_count == 0
        assert len(status.supported_industries) >= 5

    def test_full_workflow(self, dcos):
        """完整工作流：创建租户→设定目标→每日运行→状态查询→复盘。"""
        # 创建租户
        tenant = dcos.create_tenant(
            "测试创业者", "founder@test.com", "standard", "hardware"
        )
        assert tenant.get("tenant_id") is not None
        assert "api_key" in tenant

        tid = tenant["tenant_id"]

        # 行业模板
        industries = dcos.list_industries()
        assert len(industries) >= 5

        # OPC岗位
        roles = dcos.get_opc_roles()
        assert len(roles) == 5

        # 租户专属岗位（含行业增强）
        tenant_roles = dcos.get_tenant_roles(tid)
        assert len(tenant_roles) == 5

        # 设定创业目标
        result = dcos.set_goal(tid, "开发青少年坐姿矫正AI眼镜并上架抖音售卖")
        assert result is not None

        # 获取状态
        status = dcos.get_status(tid)
        assert status is not None

        # 复盘
        review = dcos.review_iteration(tid, "weekly")
        assert review is not None

    def test_validate_api_key(self, dcos):
        tenant = dcos.create_tenant("A", "a@a.com", "free", "general")
        key = tenant["api_key"]
        validated = dcos.validate_api_key(key)
        assert validated is not None
        assert validated["tenant_id"] == tenant["tenant_id"]

    def test_suspend_and_delete(self, dcos):
        tenant = dcos.create_tenant("A", "a@a.com", "free", "general")
        tid = tenant["tenant_id"]
        assert dcos.suspend_tenant(tid) is True
        t = dcos.get_tenant(tid)
        assert t["status"] == "suspended"
        assert dcos.activate_tenant(tid) is True
        assert dcos.delete_tenant(tid) is True
        assert dcos.get_tenant(tid) is None
