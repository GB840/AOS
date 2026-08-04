"""Offline logic tests for src/core/brain.py -- pure functions / thin seams.

These tests exercise the *pure-logic* and *thin-seam* methods of UnifiedBrain and
DeerFlowGatewayClient WITHOUT any network, real LLM, or subprocess. They skip
__init__ via object.__new__ and inject MagicMock dependencies, so they are
deterministic, fast, and coverage-meaningful (no flaky I/O).

Coverage targets (all offline, ②-level empirical):
- Fabric routing: route_via_fabric / route_capability / resolve_engine / _fabric_stats
- Role routing: _find_best_single_role / _find_main_and_support_roles / _synthesize_results / _synthesize_project_results
- DeerFlow skill: _match_deerflow_skill / refresh_deerflow_skills
- Meta/evolution: _route_l3_5
- Memory bridge: semantic_memory_add / semantic_memory_search / get_task_classification / add_memory / export_memory
- Stats & sessions: get_full_stats / list_sessions / get_session / list_threads / get_thread
- L1 direct channel: _route_l1 / _route_l2 / _route_l3
- Gateway housekeeping: DeerFlowGatewayClient._evict_terminal_tasks
- Singleton: get_brain

Run: python -m pytest tests/test_brain_logic.py -v
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

for var in ["API_KEY_HASH", "ADMIN_USERNAME", "ADMIN_PASSWORD", "POSTGRES_PASSWORD", "AOS_TOKEN_SECRET"]:
    os.environ.setdefault(var, "test-placeholder")

from unittest.mock import MagicMock, patch

from core.brain import UnifiedBrain, DeerFlowGatewayClient


def _fresh_brain():
    """Skip __init__ (no network/subprocess) and return a bare UnifiedBrain."""
    return object.__new__(UnifiedBrain)


# ---------------------------------------------------------------------------
# Fabric routing -- the #9 dual-track convergence surface
# ---------------------------------------------------------------------------

class TestFabricRouting:
    def test_route_capability_delegates(self):
        b = _fresh_brain()
        b.route_via_fabric = MagicMock(return_value="RES")
        assert b.route_capability("web.search", {"q": 1}) == "RES"
        b.route_via_fabric.assert_called_once()

    def test_route_via_fabric_hub_ok(self):
        b = _fresh_brain()
        hub = MagicMock()
        ok_res = MagicMock(); ok_res.ok = True
        hub.route.return_value = ok_res
        reg = MagicMock()
        b._fabric_hub = MagicMock(return_value=hub)
        b._fabric_registry = MagicMock(return_value=reg)
        assert b.route_via_fabric("cap", {"x": 1}) is ok_res
        reg.route.assert_not_called()

    def test_route_via_fabric_hub_not_ok_returns_none(self):
        """hub 返回 ok=False 时直接返回 None（不降级 reg），让调用方回退内部路由。"""
        b = _fresh_brain()
        hub = MagicMock()
        bad = MagicMock(); bad.ok = False
        hub.route.return_value = bad
        b._fabric_hub = MagicMock(return_value=hub)
        reg = MagicMock()
        b._fabric_registry = MagicMock(return_value=reg)
        assert b.route_via_fabric("cap", {"x": 1}) is None
        # 不降级到裸 registry 轨（仅 hub 抛异常才降级）
        reg.route.assert_not_called()

    def test_route_via_fabric_hub_exception_falls_to_registry(self):
        b = _fresh_brain()
        hub = MagicMock()
        hub.route.side_effect = RuntimeError("boom")
        reg = MagicMock()
        reg_res = MagicMock(); reg_res.ok = True
        reg.route.return_value = reg_res
        b._fabric_hub = MagicMock(return_value=hub)
        b._fabric_registry = MagicMock(return_value=reg)
        assert b.route_via_fabric("cap", {}) is reg_res

    def test_route_via_fabric_no_hub_no_reg(self):
        b = _fresh_brain()
        b._fabric_hub = MagicMock(return_value=None)
        b._fabric_registry = MagicMock(return_value=None)
        assert b.route_via_fabric("cap", {}) is None

    def test_route_via_fabric_reg_only(self):
        b = _fresh_brain()
        b._fabric_hub = MagicMock(return_value=None)
        reg = MagicMock()
        reg_res = MagicMock(); reg_res.ok = True
        reg.route.return_value = reg_res
        b._fabric_registry = MagicMock(return_value=reg)
        assert b.route_via_fabric("cap", {}) is reg_res

    def test_resolve_engine_none_when_no_registry(self):
        b = _fresh_brain()
        b._fabric_registry = MagicMock(return_value=None)
        assert b.resolve_engine("web.search") is None

    def test_resolve_engine_matches_live(self):
        b = _fresh_brain()
        ad = MagicMock()
        ad.advertise_capabilities.return_value = ["web.search", "chat"]
        ad.health.return_value = True
        reg = MagicMock()
        reg._adapters = {"eng-1": ad}
        b._fabric_registry = MagicMock(return_value=reg)
        assert b.resolve_engine("web.search") == "eng-1"

    def test_resolve_engine_capability_object_with_value(self):
        b = _fresh_brain()

        class Cap:
            def __init__(self, v):
                self.value = v
        ad = MagicMock()
        ad.advertise_capabilities.return_value = [Cap("chat")]
        ad.health.return_value = True
        reg = MagicMock()
        reg._adapters = {"eng-x": ad}
        b._fabric_registry = MagicMock(return_value=reg)
        assert b.resolve_engine("chat") == "eng-x"

    def test_resolve_engine_unhealthy_not_returned(self):
        b = _fresh_brain()
        ad = MagicMock()
        ad.advertise_capabilities.return_value = ["web.search"]
        ad.health.return_value = False
        reg = MagicMock()
        reg._adapters = {"eng-1": ad}
        b._fabric_registry = MagicMock(return_value=reg)
        assert b.resolve_engine("web.search") is None

    def test_resolve_engine_exception_returns_none(self):
        b = _fresh_brain()
        reg = MagicMock()
        reg._adapters = MagicMock(side_effect=RuntimeError("x"))
        def boom():
            raise RuntimeError("x")
        reg._adapters.items.side_effect = boom
        b._fabric_registry = MagicMock(return_value=reg)
        assert b.resolve_engine("web.search") is None

    def test_fabric_stats_lazy_hub_mode(self):
        b = _fresh_brain()
        b._fabric_direct = False
        b._fabric_registry = MagicMock(return_value=None)
        out = b._fabric_stats()
        assert out == {"status": "lazy", "mode": "hub"}

    def test_fabric_stats_disabled_direct_mode(self):
        b = _fresh_brain()
        b._fabric_direct = True
        b._fabric_registry = MagicMock(return_value=None)
        out = b._fabric_stats()
        assert out["mode"] == "direct-registry"
        assert out["status"] == "disabled"

    def test_fabric_stats_with_live_probe(self):
        b = _fresh_brain()
        b._fabric_direct = False
        a1 = MagicMock(); a1.health.return_value = True
        a2 = MagicMock(); a2.health.return_value = False
        reg = MagicMock()
        reg._adapters = {"live-eng": a1, "dead-eng": a2}
        b._fabric_registry = MagicMock(return_value=reg)
        out = b._fabric_stats(probe_health=True)
        assert out["adapters"] == 2
        assert out["live"] == ["live-eng"]

    def test_fabric_stats_no_probe(self):
        b = _fresh_brain()
        b._fabric_direct = False
        reg = MagicMock()
        reg._adapters = {"e": MagicMock()}
        b._fabric_registry = MagicMock(return_value=reg)
        out = b._fabric_stats(probe_health=False)
        assert "live" not in out


# ---------------------------------------------------------------------------
# Role routing -- pure logic
# ---------------------------------------------------------------------------

class TestRoleRouting:
    def test_find_best_single_role_found(self):
        b = _fresh_brain()
        b.skill_registry = MagicMock()
        b.skill_registry.search.return_value = [{"name": "coder"}, {"name": "writer"}]
        assert b._find_best_single_role("do something") == "coder"

    def test_find_best_single_role_none(self):
        b = _fresh_brain()
        b.skill_registry = MagicMock()
        b.skill_registry.search.return_value = []
        assert b._find_best_single_role("x") is None

    def test_find_main_and_support_zero(self):
        b = _fresh_brain()
        b.skill_registry = MagicMock()
        b.skill_registry.search.return_value = []
        assert b._find_main_and_support_roles("x") == []

    def test_find_main_and_support_one(self):
        b = _fresh_brain()
        b.skill_registry = MagicMock()
        b.skill_registry.search.return_value = [{"name": "a"}]
        assert b._find_main_and_support_roles("x") == ["a"]

    def test_find_main_and_support_two(self):
        b = _fresh_brain()
        b.skill_registry = MagicMock()
        b.skill_registry.search.return_value = [{"name": "a"}, {"name": "b"}, {"name": "c"}]
        assert b._find_main_and_support_roles("x") == ["a", "b"]

    def test_synthesize_results_all_success(self):
        b = _fresh_brain()
        results = [
            {"role": "a", "result": {"success": True, "data": {"response": "ra"}}},
            {"role": "b", "result": {"success": True, "data": "rb"}},
        ]
        out = b._synthesize_results(results)
        assert "a: ra" in out and "b: rb" in out

    def test_synthesize_results_skips_failure(self):
        b = _fresh_brain()
        results = [
            {"role": "a", "result": {"success": False, "data": {"response": "ra"}}},
            {"role": "b", "result": {"success": True, "data": {"response": "rb"}}},
        ]
        out = b._synthesize_results(results)
        assert "rb" in out and "ra" not in out

    def test_synthesize_results_empty(self):
        b = _fresh_brain()
        assert b._synthesize_results([]) == "任务执行完成"

    def test_synthesize_project_results(self):
        b = _fresh_brain()
        results = [
            {"subtask": "s1", "level": "L2", "result": {"response": "r1"}},
            {"subtask": "s2", "level": "L3", "result": {"response": "", "data": {"response": "r2"}}},
        ]
        out = b._synthesize_project_results(results)
        assert "s1" in out and "r1" in out and "s2" in out and "r2" in out

    def test_synthesize_project_results_empty(self):
        b = _fresh_brain()
        assert b._synthesize_project_results([]) == "项目执行完成"


# ---------------------------------------------------------------------------
# DeerFlow skill routing (thin seam)
# ---------------------------------------------------------------------------

class TestDeerFlowSkillRouting:
    def test_match_skill_found(self):
        b = _fresh_brain()
        b._skill_provider = MagicMock()
        b.deerflow_skill_provider.match.return_value = "skill-x"
        assert b._match_deerflow_skill("do x") == "skill-x"

    def test_match_skill_none(self):
        b = _fresh_brain()
        b._skill_provider = MagicMock()
        b.deerflow_skill_provider.match.return_value = None
        assert b._match_deerflow_skill("x") is None

    def test_match_skill_exception_returns_none(self):
        b = _fresh_brain()
        b._skill_provider = MagicMock()
        b.deerflow_skill_provider.match.side_effect = RuntimeError("boom")
        assert b._match_deerflow_skill("x") is None

    def test_refresh_skills_count(self):
        b = _fresh_brain()
        b._skill_provider = MagicMock()
        b.deerflow_skill_provider.refresh.return_value = ["a", "b", "c"]
        assert b.refresh_deerflow_skills() == 3

    def test_refresh_skills_exception_returns_zero(self):
        b = _fresh_brain()
        b._skill_provider = MagicMock()
        b.deerflow_skill_provider.refresh.side_effect = RuntimeError("x")
        assert b.refresh_deerflow_skills() == 0


# ---------------------------------------------------------------------------
# Meta / evolution channel
# ---------------------------------------------------------------------------

class TestMetaEvolution:
    def test_route_l3_5_with_orchestrator(self):
        b = _fresh_brain()
        mo = MagicMock()
        mo.propose_self_modification.return_value = {"plan": "p"}
        b.meta_orchestrator = mo
        out = b._route_l3_5("evolve", meta_decision={"workflow_id": "wf1", "priority": 3})
        assert out["level"] == "L3.5"
        assert out["requires_human_approval"] is True
        assert out["proposal"] == {"plan": "p"}
        assert out["workflow_id"] == "wf1"
        assert out["priority"] == 3

    def test_route_l3_5_no_orchestrator(self):
        b = _fresh_brain()
        b.meta_orchestrator = None
        out = b._route_l3_5("evolve")
        assert out["proposal"] == {}

    def test_route_l3_5_orchestrator_exception(self):
        b = _fresh_brain()
        mo = MagicMock()
        mo.propose_self_modification.side_effect = RuntimeError("x")
        b.meta_orchestrator = mo
        out = b._route_l3_5("evolve")
        assert out["proposal"] == {}


# ---------------------------------------------------------------------------
# Memory bridge (offline)
# ---------------------------------------------------------------------------

class TestMemoryBridge:
    def test_semantic_add_no_store(self):
        b = _fresh_brain()
        b.mem0_store = None
        out = b.semantic_memory_add("hello")
        assert out == {"ok": False, "backend": "none", "result": None}

    def test_semantic_add_with_store(self):
        b = _fresh_brain()
        store = MagicMock()
        store.add.return_value = {"id": 1}
        b.mem0_store = store
        out = b.semantic_memory_add("hello", user_id="u1")
        assert out == {"id": 1}
        store.add.assert_called_once_with("hello", user_id="u1")

    def test_semantic_search_no_store(self):
        b = _fresh_brain()
        b.mem0_store = None
        out = b.semantic_memory_search("q")
        assert out == {"ok": False, "backend": "none", "results": []}

    def test_semantic_search_with_store(self):
        b = _fresh_brain()
        store = MagicMock()
        store.search.return_value = {"hits": 2}
        b.mem0_store = store
        out = b.semantic_memory_search("q", limit=3)
        assert out == {"hits": 2}

    def test_get_task_classification(self):
        b = _fresh_brain()
        cls = MagicMock()
        cls.to_dict.return_value = {"level": "L2", "confidence": 0.8}
        b.task_classifier = MagicMock()
        b.task_classifier.classify.return_value = cls
        out = b.get_task_classification("build a website")
        assert out == {"level": "L2", "confidence": 0.8}

    def test_add_memory(self):
        b = _fresh_brain()
        b.hermes = MagicMock()
        b.hermes.add_knowledge.return_value = {"ok": True}
        b.deerflow = MagicMock()
        out = b.add_memory("content-here", category="fact", confidence=0.9)
        assert out == {"ok": True}
        b.hermes.add_knowledge.assert_called_once()
        b.deerflow.create_memory_fact.assert_called_once()

    def test_export_memory(self):
        b = _fresh_brain()
        b.memory = MagicMock()
        b.memory.list_knowledge.return_value = [1, 2]
        b.memory.list_tasks.return_value = [1]
        b.deerflow = MagicMock()
        b.deerflow.export_memory.return_value = {"status": "ok"}
        out = b.export_memory()
        assert out["aos"]["knowledge"] == 2
        assert out["aos"]["conversations"] == 1
        assert out["deerflow"] == {"status": "ok"}


# ---------------------------------------------------------------------------
# Stats & sessions (thin seams)
# ---------------------------------------------------------------------------

class TestStatsAndSessions:
    def test_get_full_stats_all_none(self):
        b = _fresh_brain()
        b.identity = MagicMock(); b.identity.aid = "aid-1"
        b.hermes = None
        b.deerflow = None
        b.subagents = None
        b.audit = None
        b.aid_gen = None
        b.hermes = None
        # reset: set everything to None explicitly
        for attr in ("hermes", "deerflow", "subagents", "audit", "aid_gen", "tracer", "persistence"):
            setattr(b, attr, None)
        out = b.get_full_stats()
        assert out["app"]["aid"] == "aid-1"
        assert out["hermes"] == {"status": "unavailable"}
        assert out["fabric"]["mode"] == "hub"
        assert out["deerflow_deep"] == {"status": "unavailable"}
        assert out["deep_hermes"] == {"status": "unavailable"}

    def test_get_full_stats_with_components(self):
        b = _fresh_brain()
        b.identity = MagicMock(); b.identity.aid = "aid-9"
        h = MagicMock(); h.get_stats.return_value = {"status": "ok"}
        h.list_skills.return_value = ["s1"]
        b.hermes = h
        b.deerflow = None
        b.subagents = MagicMock(); b.subagents.get_stats.return_value = {"count": 1}
        b.audit = MagicMock(); b.audit.get_stats.return_value = {"c": 2}
        b.aid_gen = MagicMock(); b.aid_gen.get_stats.return_value = {"ok": 1}
        b.tracer = MagicMock(); b.tracer.get_stats.return_value = {"t": 1}
        b.persistence = MagicMock(); b.persistence.get_stats.return_value = {"p": 1}
        b._fabric_registry = MagicMock(return_value=None)
        out = b.get_full_stats()
        assert out["hermes"]["status"] == "ok"
        assert out["skills"] == ["s1"]
        assert out["subagents"]["count"] == 1

    def test_list_sessions(self):
        b = _fresh_brain()
        b.hermes = MagicMock()
        b.hermes.list_sessions.return_value = [{"id": 1}]
        assert b.list_sessions() == [{"id": 1}]

    def test_get_session(self):
        b = _fresh_brain()
        b.hermes = MagicMock()
        b.hermes.get_session_info.return_value = {"id": "s1"}
        assert b.get_session("s1") == {"id": "s1"}

    def test_list_threads(self):
        b = _fresh_brain()
        b.deerflow = MagicMock()
        b.deerflow.list_threads.return_value = {"threads": []}
        assert b.list_threads(limit=5) == {"threads": []}

    def test_get_thread(self):
        b = _fresh_brain()
        b.deerflow = MagicMock()
        b.deerflow.get_thread.return_value = {"id": "t1"}
        assert b.get_thread("t1") == {"id": "t1"}


# ---------------------------------------------------------------------------
# _route_l1 / l2 / l3 -- direct channels (mocked hermes/registry)
# ---------------------------------------------------------------------------

class TestRouteChannels:
    def test_route_l1_hermes_str(self):
        b = _fresh_brain()
        b.hermes = MagicMock()
        b.hermes.chat.return_value = "hi there"
        out = b._route_l1("hello")
        assert out["success"] is True
        assert out["response"] == "hi there"
        assert out["level"] == "L1"

    def test_route_l1_hermes_empty_falls_back(self):
        b = _fresh_brain()
        b.hermes = MagicMock()
        b.hermes.chat.return_value = ""
        b._llm_cloud_fallback = MagicMock(return_value={"success": True, "response": "cloud"})
        out = b._route_l1("hello")
        assert out["response"] == "cloud"

    def test_route_l1_hermes_dict_error_falls_back(self):
        b = _fresh_brain()
        b.hermes = MagicMock()
        b.hermes.chat.return_value = {"error": "boom"}
        b._llm_cloud_fallback = MagicMock(return_value={"success": True, "response": "cloud"})
        out = b._route_l1("hello")
        assert out["response"] == "cloud"

    def test_route_l1_hermes_exception_falls_back(self):
        b = _fresh_brain()
        b.hermes = MagicMock()
        b.hermes.chat.side_effect = RuntimeError("x")
        b._llm_cloud_fallback = MagicMock(return_value={"success": True, "response": "cloud"})
        out = b._route_l1("x")
        assert out["response"] == "cloud"

    def test_route_l2_role_found(self):
        b = _fresh_brain()
        b.task_fingerprint = MagicMock()
        b.task_fingerprint.search_similar.return_value = []
        b.skill_registry = MagicMock()
        b.skill_registry.search.return_value = [{"name": "coder"}]
        b.skill_registry.execute.return_value = {"success": True, "data": {"response": "done"}}
        out = b._route_l2("write code")
        assert out["level"] == "L2"
        assert out["role"] == "coder"
        assert out["data"]["response"] == "done"

    def test_route_l2_template_reuse(self):
        b = _fresh_brain()
        fp = MagicMock()
        fp.search_similar.return_value = [MagicMock(role_whitelist=["reused-role"], fingerprint="fp1")]
        b.task_fingerprint = fp
        b.skill_registry = MagicMock()
        b.skill_registry.execute.return_value = {"success": True, "data": {"response": "r"}}
        out = b._route_l2("task")
        assert out["role"] == "reused-role"
        # search for best role should NOT have been called (template used)
        b.skill_registry.search.assert_not_called()

    def test_route_l2_no_role_falls_back_l1(self):
        b = _fresh_brain()
        b.task_fingerprint = MagicMock()
        b.task_fingerprint.search_similar.return_value = []
        b.skill_registry = MagicMock()
        b.skill_registry.search.return_value = []
        b._route_l1 = MagicMock(return_value={"level": "L1", "response": "fallback"})
        out = b._route_l2("x")
        assert out["level"] == "L1"

    def test_route_l3_two_roles(self):
        b = _fresh_brain()
        b.task_fingerprint = MagicMock()
        b.task_fingerprint.search_similar.return_value = []
        b.skill_registry = MagicMock()
        b.skill_registry.search.return_value = [{"name": "a"}, {"name": "b"}]
        b.skill_registry.execute.return_value = {"success": True, "data": {"response": "ok"}}
        b._synthesize_results = MagicMock(return_value="synthesized")
        out = b._route_l3("complex task")
        assert out["level"] == "L3"
        assert out["roles"] == ["a", "b"]
        assert out["response"] == "synthesized"
        assert b.skill_registry.execute.call_count == 2

    def test_route_l3_no_role_falls_back_l1(self):
        b = _fresh_brain()
        b.task_fingerprint = MagicMock()
        b.task_fingerprint.search_similar.return_value = []
        b.skill_registry = MagicMock()
        b.skill_registry.search.return_value = []
        b._route_l1 = MagicMock(return_value={"level": "L1"})
        out = b._route_l3("x")
        assert out["level"] == "L1"


# ---------------------------------------------------------------------------
# DeerFlowGatewayClient housekeeping
# ---------------------------------------------------------------------------

class TestGatewayEviction:
    def test_evict_under_cap_noop(self):
        c = DeerFlowGatewayClient()
        c._tasks = {}
        c._evict_terminal_tasks()  # no crash with empty
        assert c._tasks == {}

    def test_evict_drops_terminal_oldest(self):
        c = DeerFlowGatewayClient()
        os.environ["AOS_TASK_RETENTION_MAX"] = "2"
        try:
            c._tasks = {
                "t1": {"status": "completed"},
                "t2": {"status": "running"},
                "t3": {"status": "failed"},
                "t4": {"status": "completed"},
            }
            c._evict_terminal_tasks()
            # running never dropped; only terminal ones dropped until <= cap(2)
            assert "t2" in c._tasks
            assert len(c._tasks) == 2
        finally:
            os.environ.pop("AOS_TASK_RETENTION_MAX", None)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

class TestGetBrain:
    def test_get_brain_returns_instance(self):
        import core.brain as brain_mod
        brain_mod._brain_instance = None
        try:
            inst = brain_mod.get_brain()
            assert isinstance(inst, UnifiedBrain)
            # second call returns same instance
            assert brain_mod.get_brain() is inst
        finally:
            brain_mod._brain_instance = None
