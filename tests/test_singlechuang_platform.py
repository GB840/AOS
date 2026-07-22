"""单创OS 平台层轻量测试（避开重型 kernel 链，沙箱可跑）。

覆盖：5岗位注册表、财务报表芯粒、opt-in 扩展注册(含 WorkRally 接口位)、Ollama 开源网关。
所有模块用 importlib 直接加载模块体，绕过 kernel.plugins.__init__ 的重型依赖。
"""
import importlib.util
import os
import sys
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
