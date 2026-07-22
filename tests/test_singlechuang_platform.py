"""单创OS 平台层轻量测试（避开重型 kernel 链，沙箱可跑）。

覆盖：5岗位注册表、财务报表芯粒、opt-in 扩展注册(含 WorkRally 接口位)、Ollama 开源网关、
以及 singlechuang 编排层对三件套的「真实消费」（证明它们不是死代码）。
所有模块用 importlib 直接加载模块体，绕过 kernel.plugins.__init__ 的重型依赖。
"""
import importlib.util
import os
import sys
import types
import unittest
from unittest import mock

SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))


def _load(modname, relpath):
    spec = importlib.util.spec_from_file_location(modname, os.path.join(SRC, relpath))
    m = importlib.util.module_from_spec(spec)
    sys.modules[modname] = m
    spec.loader.exec_module(m)
    return m


opc_roles = _load("sc_opc_roles", "kernel/plugins/opc_roles.py")
report_agent = _load("sc_report_agent", "kernel/plugins/report_agent.py")
extension = _load("sc_extension", "kernel/plugins/extension.py")
ollama_gw = _load("sc_ollama_gw", "kernel/plugins/ollama_gateway.py")

# 让 singlechuang 的相对导入解析到已加载模块（验证编排层真的消费三件套）
sys.modules.setdefault("kernel", types.ModuleType("kernel"))
_kp = types.ModuleType("kernel.plugins")
_kp.__path__ = [os.path.join(SRC, "kernel", "plugins")]
sys.modules["kernel.plugins"] = _kp
sys.modules["kernel.plugins.opc_roles"] = opc_roles
sys.modules["kernel.plugins.report_agent"] = report_agent
sys.modules["kernel.plugins.extension"] = extension
singlechuang = _load("kernel.plugins.singlechuang", "kernel/plugins/singlechuang.py")


class TestOPCRoles(unittest.TestCase):
    def test_five_roles(self):
        roles = opc_roles.list_roles()
        self.assertEqual(len(roles), 5)
        self.assertEqual(
            {r.id for r in roles},
            {"product_rd", "market_research", "content_marketing",
             "customer_service", "finance"},
        )

    def test_finance_uses_report_cap(self):
        fin = opc_roles.get_role("finance")
        self.assertIn("finance.report", fin.capabilities)

    def test_all_capabilities_nonempty(self):
        caps = opc_roles.all_capabilities()
        self.assertIn("web.search", caps)
        self.assertIn("action.code_exec", caps)
        self.assertIn("finance.report", caps)

    def test_roles_for_capability(self):
        rs = opc_roles.roles_for_capability("web.search")
        self.assertTrue(any(r.id == "market_research" for r in rs))


class TestReportAgent(unittest.TestCase):
    def test_bom_cost(self):
        r = report_agent.bom_cost([
            {"name": "RK", "unit_price": 45, "qty": 1},
            {"name": "cam", "unit_price": 12, "qty": 2},
        ])
        self.assertEqual(r["total"], 69.0)

    def test_generate_csv_fallback(self):
        recs = [{"项目": "营收", "金额": 100}, {"项目": "成本", "金额": 60}]
        res = report_agent.generate_report(recs, fmt="csv")
        self.assertTrue(res["ok"])
        self.assertEqual(res["engine"], "csv")
        self.assertIn("营收", res["content"])

    def test_profit(self):
        p = report_agent.profit_estimate(100, 60)
        self.assertEqual(p["profit"], 40.0)
        self.assertEqual(p["margin_pct"], 40.0)


class TestExtension(unittest.TestCase):
    def test_workrally_optin_hidden_without_token(self):
        os.environ.pop("WORKRALLY_TOKEN", None)
        inst = extension.get_extension("workrally")
        self.assertIsNone(inst)  # 无 token 静默跳过
        exts = extension.list_extensions()
        self.assertIn("workrally", exts)
        self.assertFalse(exts["workrally"]["enabled"])

    def test_register_and_enable(self):
        os.environ["SC_TEST_TOKEN"] = "1"
        extension.register_extension("sc_test", lambda: "instance", env_gate="SC_TEST_TOKEN")
        self.assertTrue(extension.is_enabled("sc_test"))
        self.assertEqual(extension.get_extension("sc_test"), "instance")
        del os.environ["SC_TEST_TOKEN"]


class TestTeraxExtension(unittest.TestCase):
    """Terax 是本地开源应用（Apache-2.0，无需 token）：装了就在、没装静默跳过。"""

    def test_terax_registered_local_only(self):
        exts = extension.list_extensions()
        self.assertIn("terax", exts)
        self.assertTrue(exts["terax"]["local_only"])   # 安全红线：只本机
        self.assertTrue(exts["terax"]["enabled"])      # 无 env_gate -> 默认启用（但二进制未装则实例为 None）

    def test_terax_not_installed_returns_none(self):
        # 沙箱 PATH 上无 terax 二进制 -> factory 返回 None，静默跳过，不阻塞主链路
        inst = extension.get_extension("terax")
        self.assertIsNone(inst)

    def test_terax_detected_when_on_path(self):
        # 模拟本机已装 terax（PATH 命中）-> 返回描述符
        import shutil
        with mock.patch.object(shutil, "which", return_value="/usr/bin/terax"):
            inst = extension.get_extension("terax")
        self.assertIsNotNone(inst)
        self.assertEqual(inst["license"], "Apache-2.0")
        self.assertEqual(inst["fits"], "product_rd")


class TestOllamaGateway(unittest.TestCase):
    def _gw(self):
        return ollama_gw.OllamaModelGateway()

    def test_health_unreachable(self):
        gw = self._gw()
        gw.base_url = "http://localhost:9"  # 不存在端口
        h = gw.health()
        self.assertFalse(h.healthy)

    def test_list_models_mock(self):
        gw = self._gw()
        fake = {"models": [{"name": "qwen3:8b", "size": 100},
                           {"name": "llama3.1:8b", "size": 200}]}
        with mock.patch.object(gw, "_get", return_value=fake):
            models = gw.list_models()
        self.assertEqual(len(models), 2)
        self.assertEqual(models[0].model_id, "ollama/qwen3:8b")
        self.assertTrue(models[0].extra["opensource"])

    def test_chat_mock(self):
        gw = self._gw()
        fake = {"message": {"content": "你好"}}
        with mock.patch.object(gw, "_post", return_value=fake):
            resp = gw.chat("ollama/qwen3:8b", [])
        self.assertEqual(resp.content, "你好")


class TestSingleChuangWiring(unittest.TestCase):
    """证明 singlechuang 编排层真的消费了三件套（不是死代码）。"""

    def test_plan_company_returns_five_roles(self):
        out = singlechuang.plan_company("开发青少年护眼 AI 眼镜")
        self.assertEqual(out["role_count"], 5)
        self.assertEqual(out["roles"][0]["role"], "product_rd")
        for r in out["roles"]:
            self.assertTrue(r["capabilities"], "岗位能力清单不应为空")
        # 财务岗必须带报表能力（report_agent 开源补位）
        fin = [r for r in out["roles"] if r["role"] == "finance"][0]
        self.assertIn("finance.report", fin["capabilities"])

    def test_resolve_content_tools_no_workrally(self):
        os.environ.pop("WORKRALLY_TOKEN", None)
        tools = singlechuang.resolve_content_tools()
        self.assertIn("content.video_maker", tools)
        self.assertNotIn("content.workrally", tools)  # 无账号不暴露

    def test_resolve_content_tools_with_workrally(self):
        os.environ["WORKRALLY_TOKEN"] = "fake"
        try:
            extension.register_extension(
                "workrally", lambda: "wr_instance", env_gate="WORKRALLY_TOKEN")
            tools = singlechuang.resolve_content_tools()
            self.assertIn("content.workrally", tools)  # 有账号 opt-in 追加
        finally:
            os.environ.pop("WORKRALLY_TOKEN", None)

    def test_build_financial_report(self):
        recs = [{"项目": "营收", "金额": 100}, {"项目": "成本", "金额": 60}]
        res = singlechuang.build_financial_report(recs)
        self.assertTrue(res["ok"])

    def test_bom_and_profit_helpers(self):
        b = singlechuang.bom_summary([{"name": "RK", "unit_price": 45, "qty": 1}])
        self.assertEqual(b["total"], 45.0)
        p = singlechuang.profit_summary(100, 60)
        self.assertEqual(p["profit"], 40.0)

    def test_product_rd_has_terax_capability(self):
        role = opc_roles.get_role("product_rd")
        self.assertIn("dev.terax", role.capabilities)  # 产品研发岗映射终端开发环境

    def test_resolve_dev_env_not_installed(self):
        # 沙箱无 terax -> available=False，但结构完整、不崩
        env = singlechuang.resolve_dev_env()
        self.assertIn("available", env)
        self.assertFalse(env["available"])
        self.assertEqual(env["name"], "terax")

    def test_plan_company_exposes_dev_env(self):
        out = singlechuang.plan_company("开发青少年护眼 AI 眼镜")
        prd = [r for r in out["roles"] if r["role"] == "product_rd"][0]
        self.assertIsNotNone(prd["dev_env"])
        self.assertIn("available", prd["dev_env"])
        # 其它岗位不应带 dev_env
        others = [r for r in out["roles"] if r["role"] != "product_rd"]
        self.assertTrue(all(r["dev_env"] is None for r in others))


if __name__ == "__main__":
    unittest.main(verbosity=2)
