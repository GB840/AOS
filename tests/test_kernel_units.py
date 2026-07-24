"""Unit tests for AOS kernel modules: system, v5_bridge, versioning, interfaces, wiring.

Covers:
  - kernel.versioning  (ModuleVersion, VersionRegistry, Migration, UpgradeManager)
  - kernel.interfaces  (ABC contracts for ModelGateway, AgentRuntime, SkillBus)
  - kernel.system      (AOSSystem dataclass, health_report, list_surfaces)
  - kernel.wiring      (build_default_kernel with mocked plugins)
  - kernel.v5_bridge   (V5Bridge mount, chat, authenticate, health)

All external dependencies are mocked -- no real LLM calls, no real DB.
"""

from __future__ import annotations

from typing import Any, AsyncIterator, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from kernel.types import (
    AgentInstance,
    AgentSpec,
    ChatResponse,
    Message,
    ModelCapabilities,
    ModelInfo,
    GatewayHealth,
    Response,
    SkillInfo,
    SkillResult,
    SkillSpec,
)


# =====================================================================
# Fixtures
# =====================================================================


@pytest.fixture
def kernel():
    """A bare AOSKernel with default-grant permission policy and no plugins."""
    from kernel.kernel import AOSKernel

    k = AOSKernel()
    k.set_permission_policy(default_grant=True)
    return k


@pytest.fixture
def mock_runtime():
    """A mock AgentRuntime that returns a canned Response."""
    from kernel.interfaces import AgentRuntime

    class StubRuntime(AgentRuntime):
        def create_agent(self, spec: AgentSpec) -> AgentInstance:
            return AgentInstance(agent_id=spec.agent_id, spec=spec)

        def run_agent(self, instance: AgentInstance, task: Any) -> Response:
            return Response(ok=True, data={"content": "stub-reply"})

        def stream_run(self, instance: AgentInstance, task: Any) -> AsyncIterator[Any]:
            raise NotImplementedError

        def get_status(self, instance_id: str) -> str:
            return "healthy"

    return StubRuntime()


@pytest.fixture
def mock_gateway():
    """A mock ModelGateway."""
    from kernel.interfaces import ModelGateway

    class StubGateway(ModelGateway):
        def list_models(self) -> List[ModelInfo]:
            return [ModelInfo(model_id="stub-model", provider="stub")]

        def chat(self, model_id: str, messages: List[Message], **kwargs: Any) -> ChatResponse:
            return ChatResponse(content="stub-chat", model=model_id)

        def stream_chat(self, model_id: str, messages: List[Message], **kwargs: Any) -> AsyncIterator[Any]:
            raise NotImplementedError

        def get_capabilities(self, model_id: str) -> ModelCapabilities:
            return ModelCapabilities(context_window=4096)

        def health(self) -> "GatewayHealth":
            return GatewayHealth(healthy=True, provider="stub", model_count=1)

    return StubGateway()


@pytest.fixture
def mock_skill_bus():
    """A mock SkillBus."""
    from kernel.interfaces import SkillBus

    class StubSkillBus(SkillBus):
        def __init__(self):
            self._skills: Dict[str, SkillSpec] = {}

        def discover_skills(self) -> List[SkillInfo]:
            return [SkillInfo(skill_id=s.skill_id, description=s.description)
                    for s in self._skills.values()]

        def call_skill(self, skill_id: str, params: Dict[str, Any]) -> SkillResult:
            if skill_id in self._skills:
                return SkillResult(ok=True, data={"result": "ok"})
            return SkillResult(ok=False, error=f"unknown skill: {skill_id}")

        def register_skill(self, skill_spec: SkillSpec) -> None:
            self._skills[skill_spec.skill_id] = skill_spec

    return StubSkillBus()


@pytest.fixture
def configured_kernel(kernel, mock_runtime, mock_gateway, mock_skill_bus):
    """A kernel with runtime, gateway, and skill bus plugged in."""
    kernel.register_runtime("stub", mock_runtime)
    kernel.set_model_gateway(mock_gateway)
    kernel.set_skill_bus(mock_skill_bus)
    return kernel


# =====================================================================
# kernel.versioning -- ModuleVersion
# =====================================================================


class TestModuleVersion:
    """Tests for ModuleVersion: parse, compare, str, is_compatible_with."""

    def test_parse_full(self):
        from kernel.versioning import ModuleVersion

        v = ModuleVersion.parse("2.3.4")
        assert v == ModuleVersion(major=2, minor=3, patch=4)

    def test_parse_with_prerelease_suffix(self):
        from kernel.versioning import ModuleVersion

        v = ModuleVersion.parse("1.0.0-alpha")
        assert v == ModuleVersion(major=1, minor=0, patch=0)

    def test_parse_partial(self):
        from kernel.versioning import ModuleVersion

        v = ModuleVersion.parse("3.1")
        assert v == ModuleVersion(major=3, minor=1, patch=0)

    def test_parse_single_number(self):
        from kernel.versioning import ModuleVersion

        v = ModuleVersion.parse("5")
        assert v == ModuleVersion(major=5, minor=0, patch=0)

    def test_str(self):
        from kernel.versioning import ModuleVersion

        v = ModuleVersion(major=1, minor=2, patch=3)
        assert str(v) == "1.2.3"

    def test_ordering(self):
        from kernel.versioning import ModuleVersion

        v1 = ModuleVersion(1, 0, 0)
        v2 = ModuleVersion(2, 0, 0)
        v3 = ModuleVersion(1, 1, 0)
        v4 = ModuleVersion(1, 0, 1)
        assert v1 < v2
        assert v1 < v3
        assert v1 < v4
        assert v3 < v2
        assert v4 < v3

    def test_equality(self):
        from kernel.versioning import ModuleVersion

        assert ModuleVersion(1, 0, 0) == ModuleVersion(1, 0, 0)
        assert ModuleVersion(1, 0, 0) != ModuleVersion(1, 0, 1)

    def test_frozen(self):
        from kernel.versioning import ModuleVersion

        v = ModuleVersion(1, 0, 0)
        with pytest.raises(AttributeError):
            v.major = 2

    def test_is_compatible_with_same_major_lower_minor(self):
        from kernel.versioning import ModuleVersion

        v1 = ModuleVersion(1, 0, 0)
        v2 = ModuleVersion(1, 2, 0)
        assert v1.is_compatible_with(v2)

    def test_is_compatible_with_same_major_same_minor(self):
        from kernel.versioning import ModuleVersion

        v1 = ModuleVersion(1, 2, 0)
        v2 = ModuleVersion(1, 2, 5)
        assert v1.is_compatible_with(v2)

    def test_is_not_compatible_different_major(self):
        from kernel.versioning import ModuleVersion

        v1 = ModuleVersion(2, 0, 0)
        v2 = ModuleVersion(1, 5, 0)
        assert not v1.is_compatible_with(v2)

    def test_is_not_compatible_higher_minor(self):
        from kernel.versioning import ModuleVersion

        v1 = ModuleVersion(1, 3, 0)
        v2 = ModuleVersion(1, 1, 0)
        assert not v1.is_compatible_with(v2)

    def test_hashable(self):
        from kernel.versioning import ModuleVersion

        s = {ModuleVersion(1, 0, 0), ModuleVersion(1, 0, 0), ModuleVersion(2, 0, 0)}
        assert len(s) == 2


# =====================================================================
# kernel.versioning -- VersionedPlugin & VersionRegistry
# =====================================================================


class TestVersionRegistry:
    """Tests for VersionRegistry: register, get_latest, get_compatible, etc."""

    def _make_plugin(self, pid: str, kind: str, version_str: str):
        from kernel.versioning import ModuleVersion, VersionedPlugin

        return VersionedPlugin(
            plugin_id=pid,
            kind=kind,
            version=ModuleVersion.parse(version_str),
            factory=lambda: f"{pid}-{version_str}",
            description=f"{pid} v{version_str}",
        )

    def test_register_and_get_latest(self):
        from kernel.versioning import VersionRegistry

        reg = VersionRegistry()
        reg.register(self._make_plugin("p1", "runtime", "1.0.0"))
        reg.register(self._make_plugin("p1", "runtime", "2.0.0"))
        reg.register(self._make_plugin("p1", "runtime", "1.5.0"))

        latest = reg.get_latest("p1")
        assert latest is not None
        assert str(latest.version) == "2.0.0"

    def test_get_latest_nonexistent(self):
        from kernel.versioning import VersionRegistry

        reg = VersionRegistry()
        assert reg.get_latest("nope") is None

    def test_get_exact(self):
        from kernel.versioning import ModuleVersion, VersionRegistry

        reg = VersionRegistry()
        reg.register(self._make_plugin("p1", "runtime", "1.0.0"))
        reg.register(self._make_plugin("p1", "runtime", "2.0.0"))

        found = reg.get_exact("p1", ModuleVersion(1, 0, 0))
        assert found is not None
        assert str(found.version) == "1.0.0"

    def test_get_exact_missing(self):
        from kernel.versioning import ModuleVersion, VersionRegistry

        reg = VersionRegistry()
        reg.register(self._make_plugin("p1", "runtime", "1.0.0"))

        assert reg.get_exact("p1", ModuleVersion(9, 9, 9)) is None
        assert reg.get_exact("nope", ModuleVersion(1, 0, 0)) is None

    def test_get_compatible(self):
        from kernel.versioning import ModuleVersion, VersionRegistry

        reg = VersionRegistry()
        reg.register(self._make_plugin("p1", "runtime", "1.0.0"))
        reg.register(self._make_plugin("p1", "runtime", "1.3.0"))
        reg.register(self._make_plugin("p1", "runtime", "2.0.0"))

        # Compatible with 1.1.0 => same major, >= 1.1.0 => should find 1.3.0
        compat = reg.get_compatible("p1", ModuleVersion(1, 1, 0))
        assert compat is not None
        assert str(compat.version) == "1.3.0"

    def test_get_compatible_none(self):
        from kernel.versioning import ModuleVersion, VersionRegistry

        reg = VersionRegistry()
        reg.register(self._make_plugin("p1", "runtime", "1.0.0"))

        # major=2 has no match
        assert reg.get_compatible("p1", ModuleVersion(2, 0, 0)) is None

    def test_list_versions(self):
        from kernel.versioning import VersionRegistry

        reg = VersionRegistry()
        reg.register(self._make_plugin("p1", "runtime", "1.0.0"))
        reg.register(self._make_plugin("p1", "runtime", "2.0.0"))

        versions = reg.list_versions("p1")
        assert len(versions) == 2
        # Sorted descending (latest first)
        assert str(versions[0]) == "2.0.0"
        assert str(versions[1]) == "1.0.0"

    def test_list_versions_empty(self):
        from kernel.versioning import VersionRegistry

        reg = VersionRegistry()
        assert reg.list_versions("nope") == []

    def test_list_all(self):
        from kernel.versioning import VersionRegistry

        reg = VersionRegistry()
        reg.register(self._make_plugin("p1", "runtime", "1.0.0"))
        reg.register(self._make_plugin("p2", "gateway", "1.0.0"))
        reg.register(self._make_plugin("p1", "runtime", "2.0.0"))

        all_plugins = reg.list_all()
        assert len(all_plugins) == 3

    def test_list_all_filtered_by_kind(self):
        from kernel.versioning import VersionRegistry

        reg = VersionRegistry()
        reg.register(self._make_plugin("p1", "runtime", "1.0.0"))
        reg.register(self._make_plugin("p2", "gateway", "1.0.0"))
        reg.register(self._make_plugin("p3", "runtime", "2.0.0"))

        runtimes = reg.list_all(kind="runtime")
        assert len(runtimes) == 2
        assert all(p.kind == "runtime" for p in runtimes)

    def test_remove_all_versions(self):
        from kernel.versioning import VersionRegistry

        reg = VersionRegistry()
        reg.register(self._make_plugin("p1", "runtime", "1.0.0"))
        reg.register(self._make_plugin("p1", "runtime", "2.0.0"))

        count = reg.remove("p1")
        assert count == 2
        assert reg.get_latest("p1") is None

    def test_remove_specific_version(self):
        from kernel.versioning import ModuleVersion, VersionRegistry

        reg = VersionRegistry()
        reg.register(self._make_plugin("p1", "runtime", "1.0.0"))
        reg.register(self._make_plugin("p1", "runtime", "2.0.0"))

        count = reg.remove("p1", ModuleVersion(1, 0, 0))
        assert count == 1
        assert reg.get_latest("p1") is not None
        assert str(reg.get_latest("p1").version) == "2.0.0"

    def test_remove_nonexistent(self):
        from kernel.versioning import VersionRegistry

        reg = VersionRegistry()
        assert reg.remove("nope") == 0

    def test_factory_callable(self):
        from kernel.versioning import VersionRegistry

        reg = VersionRegistry()
        reg.register(self._make_plugin("p1", "runtime", "1.0.0"))
        latest = reg.get_latest("p1")
        assert latest is not None
        result = latest.factory()
        assert result == "p1-1.0.0"


# =====================================================================
# kernel.versioning -- Migration & UpgradeManager
# =====================================================================


class TestMigration:
    """Tests for Migration: parse versions, apply script."""

    def test_apply_transforms_config(self):
        from kernel.versioning import Migration

        m = Migration("1.0.0", "1.1.0",
                       script=lambda c: {**c, "new_key": True},
                       description="add new_key")
        result = m.apply({"version": "1.0.0", "existing": 42})
        assert result["new_key"] is True
        assert result["existing"] == 42

    def test_version_attributes(self):
        from kernel.versioning import Migration

        m = Migration("1.0.0", "2.0.0", script=lambda c: c)
        assert str(m.from_version) == "1.0.0"
        assert str(m.to_version) == "2.0.0"
        assert m.description == ""


class TestUpgradeManager:
    """Tests for UpgradeManager: register_migration, get_chain, upgrade."""

    def test_simple_upgrade(self):
        from kernel.versioning import Migration, UpgradeManager

        mgr = UpgradeManager()
        mgr.register_migration(Migration(
            "1.0.0", "1.1.0",
            script=lambda c: {**c, "step": "1.1.0"},
        ))
        mgr.register_migration(Migration(
            "1.1.0", "2.0.0",
            script=lambda c: {**c, "step": "2.0.0"},
        ))

        result = mgr.upgrade({"version": "1.0.0"}, target="2.0.0")
        assert result["version"] == "2.0.0"
        # Last migration sets step to "2.0.0"
        assert result["step"] == "2.0.0"

    def test_upgrade_no_chain_raises(self):
        from kernel.versioning import UpgradeManager

        mgr = UpgradeManager()
        with pytest.raises(ValueError, match="无法从"):
            mgr.upgrade({"version": "1.0.0"}, target="2.0.0")

    def test_upgrade_same_version_no_chain(self):
        from kernel.versioning import UpgradeManager

        mgr = UpgradeManager()
        # from >= target => no migration needed => raises
        with pytest.raises(ValueError):
            mgr.upgrade({"version": "2.0.0"}, target="1.0.0")

    def test_get_chain_returns_none_when_no_path(self):
        from kernel.versioning import UpgradeManager

        mgr = UpgradeManager()
        assert mgr.get_chain("1.0.0", "3.0.0") is None

    def test_get_chain_returns_none_when_downgrade(self):
        from kernel.versioning import UpgradeManager

        mgr = UpgradeManager()
        assert mgr.get_chain("2.0.0", "1.0.0") is None

    def test_migration_count(self):
        from kernel.versioning import Migration, UpgradeManager

        mgr = UpgradeManager()
        assert mgr.migration_count == 0
        mgr.register_migration(Migration("1.0.0", "1.1.0", lambda c: c))
        assert mgr.migration_count == 1
        mgr.register_migration(Migration("1.1.0", "2.0.0", lambda c: c))
        assert mgr.migration_count == 2

    def test_upgrade_preserves_existing_data(self):
        from kernel.versioning import Migration, UpgradeManager

        mgr = UpgradeManager()
        mgr.register_migration(Migration(
            "1.0.0", "1.1.0",
            script=lambda c: {**c, "migrated": True},
        ))
        result = mgr.upgrade({"version": "1.0.0", "keep_me": "yes"}, target="1.1.0")
        assert result["keep_me"] == "yes"
        assert result["migrated"] is True

    def test_multi_step_chain(self):
        from kernel.versioning import Migration, UpgradeManager

        mgr = UpgradeManager()
        mgr.register_migration(Migration(
            "1.0.0", "1.1.0",
            script=lambda c: {**c, "steps": c.get("steps", []) + ["1.1.0"]},
        ))
        mgr.register_migration(Migration(
            "1.1.0", "1.2.0",
            script=lambda c: {**c, "steps": c.get("steps", []) + ["1.2.0"]},
        ))
        mgr.register_migration(Migration(
            "1.2.0", "2.0.0",
            script=lambda c: {**c, "steps": c.get("steps", []) + ["2.0.0"]},
        ))

        result = mgr.upgrade({"version": "1.0.0"}, target="2.0.0")
        assert result["steps"] == ["1.1.0", "1.2.0", "2.0.0"]
        assert result["version"] == "2.0.0"


# =====================================================================
# kernel.versioning -- version_plugin factory
# =====================================================================


class TestVersionPluginFactory:

    def test_creates_versioned_plugin(self):
        from kernel.versioning import version_plugin

        p = version_plugin("my-plug", "runtime", "3.2.1", lambda: "instance",
                           description="A test plugin", author="tester")
        assert p.plugin_id == "my-plug"
        assert p.kind == "runtime"
        assert str(p.version) == "3.2.1"
        assert p.description == "A test plugin"
        assert p.metadata["author"] == "tester"
        assert p.factory() == "instance"


# =====================================================================
# kernel.interfaces -- ABC contracts
# =====================================================================


class TestInterfacesABC:
    """Verify that the three interfaces are proper ABCs and enforce contracts."""

    def test_model_gateway_cannot_be_instantiated(self):
        from kernel.interfaces import ModelGateway

        with pytest.raises(TypeError):
            ModelGateway()

    def test_agent_runtime_cannot_be_instantiated(self):
        from kernel.interfaces import AgentRuntime

        with pytest.raises(TypeError):
            AgentRuntime()

    def test_skill_bus_cannot_be_instantiated(self):
        from kernel.interfaces import SkillBus

        with pytest.raises(TypeError):
            SkillBus()

    def test_model_gateway_concrete_works(self, mock_gateway):
        models = mock_gateway.list_models()
        assert len(models) == 1
        assert models[0].model_id == "stub-model"

        resp = mock_gateway.chat("stub-model", [])
        assert resp.content == "stub-chat"

        caps = mock_gateway.get_capabilities("stub-model")
        assert caps.context_window == 4096

    def test_agent_runtime_concrete_works(self, mock_runtime):
        spec = AgentSpec(agent_id="a1", name="Test", engine="stub")
        inst = mock_runtime.create_agent(spec)
        assert inst.agent_id == "a1"

        resp = mock_runtime.run_agent(inst, {"prompt": "hi"})
        assert resp.ok
        assert resp.data["content"] == "stub-reply"

        assert mock_runtime.get_status("a1") == "healthy"

    def test_skill_bus_concrete_works(self, mock_skill_bus):
        spec = SkillSpec(skill_id="test_skill", description="A test skill")
        mock_skill_bus.register_skill(spec)

        skills = mock_skill_bus.discover_skills()
        assert len(skills) == 1
        assert skills[0].skill_id == "test_skill"

        result = mock_skill_bus.call_skill("test_skill", {})
        assert result.ok

        missing = mock_skill_bus.call_skill("nonexistent", {})
        assert not missing.ok


# =====================================================================
# kernel.system -- AOSSystem
# =====================================================================


class TestAOSSystem:
    """Tests for the AOSSystem dataclass: health_report, list_surfaces."""

    def test_health_report_minimal(self, configured_kernel):
        from kernel.system import AOSSystem

        system = AOSSystem(kernel=configured_kernel)
        report = system.health_report()

        assert report["version"] == "1.0.0"
        assert report["kernel"]["ok"] is True
        assert report["kernel"]["agents"] == 0
        assert report["model_gateway"]["ok"] is False
        assert report["mcp_bus"]["ok"] is False
        assert report["agent_runtime"]["ok"] is False
        assert report["agent_runtime"]["engine"] == "unavailable"

    def test_health_report_with_layers(self, configured_kernel):
        from kernel.system import AOSSystem

        # Create mock layers
        mock_gw_layer = MagicMock()
        mock_gw_layer.list_models.return_value = [ModelInfo(model_id="m1", provider="p")]

        mock_bus_layer = MagicMock()
        mock_bus_layer.discover.return_value = [SkillInfo(skill_id="s1")]

        mock_rt_layer = MagicMock()
        mock_rt_layer.engine_health.return_value = "healthy"

        mock_ui_layer = MagicMock()
        mock_ui_layer.list_surfaces.return_value = []
        mock_ui_layer.platform.return_value = "web"

        system = AOSSystem(
            kernel=configured_kernel,
            model_gateway=mock_gw_layer,
            mcp_bus=mock_bus_layer,
            agent_runtime=mock_rt_layer,
            ui=mock_ui_layer,
        )
        report = system.health_report()

        assert report["model_gateway"]["ok"] is True
        assert report["model_gateway"]["models"] == 1
        assert report["mcp_bus"]["ok"] is True
        assert report["mcp_bus"]["skills"] == 1
        assert report["agent_runtime"]["ok"] is True
        assert report["agent_runtime"]["engine"] == "healthy"
        assert report["ui"]["platform"] == "web"

    def test_list_surfaces_no_ui(self, configured_kernel):
        from kernel.system import AOSSystem

        system = AOSSystem(kernel=configured_kernel)
        assert system.list_surfaces() == []

    def test_list_surfaces_with_ui(self, configured_kernel):
        from kernel.system import AOSSystem

        mock_ui = MagicMock()
        mock_ui.list_surfaces.return_value = [{"id": "chat", "title": "Chat"}]

        system = AOSSystem(kernel=configured_kernel, ui=mock_ui)
        surfaces = system.list_surfaces()
        assert len(surfaces) == 1

    def test_degradation_dict(self, configured_kernel):
        from kernel.system import AOSSystem

        system = AOSSystem(
            kernel=configured_kernel,
            degradation={"model_gateway": "skipped (no adapter)"},
        )
        report = system.health_report()
        assert "model_gateway" in report["degradations"]

    def test_health_report_agents_count(self, configured_kernel):
        from kernel.system import AOSSystem

        configured_kernel.register_agent(
            AgentSpec(agent_id="a1", name="Agent1", engine="stub")
        )
        configured_kernel.register_agent(
            AgentSpec(agent_id="a2", name="Agent2", engine="stub")
        )

        system = AOSSystem(kernel=configured_kernel)
        report = system.health_report()
        assert report["kernel"]["agents"] == 2


# =====================================================================
# kernel.wiring -- build_default_kernel
# =====================================================================


class TestBuildDefaultKernel:
    """Tests for wiring.build_default_kernel with mocked plugin imports."""

    def test_build_default_kernel_returns_kernel(self):
        """build_default_kernel should return an AOSKernel instance even when
        all optional plugins fail to import (graceful degradation)."""
        from kernel.kernel import AOSKernel
        from kernel.wiring import build_default_kernel

        # Patch all the heavy imports that would fail in test env.
        # isolate_heavy=False 避免在沙箱里真的拉起子进程隔离层（socket 连接会挂）。
        # inject_brain=False 跳过 brain 注入（hermes 插件 discover_plugins 里
        # dashboard_auth/basic 调 hashlib.scrypt 做 KDF，单次 ~30s+，会触发 timeout）。
        with patch("kernel.wiring.LiteLLMModelGateway", side_effect=Exception("mocked")), \
             patch("kernel.wiring.MCPSkillBus", side_effect=Exception("mocked")):
            k = build_default_kernel(isolate_heavy=False, inject_brain=False)

        assert isinstance(k, AOSKernel)
        # 默认拒绝（零信任）：无显式授权时 check_permission 返回 False
        assert k.check_permission("anyone", "anything") is False

    def test_build_default_kernel_default_grant_false(self):
        """When default_grant=False, permission checks should deny by default."""
        from kernel.wiring import build_default_kernel

        with patch("kernel.wiring.LiteLLMModelGateway", side_effect=Exception("mocked")), \
             patch("kernel.wiring.MCPSkillBus", side_effect=Exception("mocked")):
            k = build_default_kernel(default_grant=False, isolate_heavy=False,
                                      inject_brain=False)

        assert k.check_permission("anyone", "anything") is False

    def test_build_default_kernel_registers_skill_bus(self):
        """When MCPSkillBus imports successfully, it should be set on the kernel."""
        from kernel.wiring import build_default_kernel

        mock_bus_instance = MagicMock()
        with patch("kernel.wiring.LiteLLMModelGateway", side_effect=Exception("mocked")), \
             patch("kernel.wiring.MCPSkillBus", return_value=mock_bus_instance):
            k = build_default_kernel(isolate_heavy=False, inject_brain=False)

        from kernel.plugins.mcp_security_gateway import MCPSecurityGateway
        assert isinstance(k._skill_bus, MCPSecurityGateway)

    def test_build_default_kernel_registers_litellm_gateway(self):
        """When LiteLLMModelGateway imports, it should be set as model gateway."""
        from kernel.wiring import build_default_kernel

        mock_gw_instance = MagicMock()
        mock_gw_instance.list_models.return_value = []  # empty so MistralRS is skipped
        with patch("kernel.wiring.LiteLLMModelGateway", return_value=mock_gw_instance), \
             patch("kernel.plugins.mistralrs_gateway.MistralRSModelGateway",
                   side_effect=Exception("mocked")), \
             patch("kernel.wiring.MCPSkillBus", side_effect=Exception("mocked")):
            k = build_default_kernel(isolate_heavy=False, inject_brain=False)

        assert k._model_gateway is not None

    def test_build_default_kernel_registers_runtime(self):
        """When LiteLLMAdapter imports, it should register a runtime."""
        from kernel.wiring import build_default_kernel

        mock_adapter_cls = MagicMock()
        mock_adapter_instance = MagicMock()
        mock_adapter_cls.return_value = mock_adapter_instance

        with patch("kernel.wiring.LiteLLMModelGateway", side_effect=Exception("mocked")), \
             patch("kernel.wiring.MCPSkillBus", side_effect=Exception("mocked")), \
             patch("core.fabric.adapters.litellm_adapter.LiteLLMAdapter", mock_adapter_cls):
            k = build_default_kernel(isolate_heavy=False, inject_brain=False)

        assert "litellm" in k._runtimes


# =====================================================================
# kernel.v5_bridge -- V5Bridge
# =====================================================================


class TestV5Bridge:
    """Tests for V5Bridge with mocked system/kernel dependencies."""

    @pytest.fixture
    def bridge(self):
        """A V5Bridge with build_default_system mocked out."""
        from kernel.kernel import AOSKernel
        from kernel.system import AOSSystem

        kernel = AOSKernel()
        kernel.set_permission_policy(default_grant=True)

        # Create a stub runtime and register it
        from kernel.interfaces import AgentRuntime

        class StubRT(AgentRuntime):
            def create_agent(self, spec):
                return AgentInstance(agent_id=spec.agent_id, spec=spec)

            def run_agent(self, instance, task):
                return Response(ok=True, data={"content": "bridge-reply"})

            def stream_run(self, instance, task):
                raise NotImplementedError

            def get_status(self, instance_id):
                return "healthy"

        kernel.register_runtime("litellm", StubRT())

        mock_ui = MagicMock()
        mock_ui.list_surfaces.return_value = []
        mock_ui.platform.return_value = "web"

        system = AOSSystem(
            kernel=kernel,
            ui=mock_ui,
        )

        with patch("kernel.v5_bridge.build_default_system", return_value=system):
            from kernel.v5_bridge import V5Bridge
            b = V5Bridge()

        return b

    def test_init_state(self, bridge):
        """V5Bridge should initialize with correct defaults."""
        assert bridge._mounted is False
        assert bridge._request_count == 0
        assert bridge.system is not None
        assert bridge.kernel is not None

    def test_mount(self, bridge):
        """mount() should inject kernel into app.state and set _mounted."""
        mock_app = MagicMock()
        mock_app.state = MagicMock()

        # Mock SkillsBridge to avoid real skill scanning
        with patch("kernel.v5_bridge.SkillsBridge") as MockSB, \
             patch("kernel.v5_bridge.AuthBridge") as MockAB, \
             patch("kernel.v5_bridge.ComplianceLayer") as MockCL:
            mock_sb_inst = MagicMock()
            mock_sb_inst.register_all.return_value = 5
            MockSB.return_value = mock_sb_inst

            result = bridge.mount(mock_app)

        assert result is bridge
        assert bridge._mounted is True
        assert mock_app.state.kernel is bridge.kernel
        assert mock_app.state.bridge is bridge
        assert mock_app.state.kernel_version == "1.0.0"
        assert mock_app.state.skills_registered == 5

    def test_chat_registers_agent_and_returns_response(self, bridge):
        """chat() should auto-register an agent and route the message."""
        # Mount first so auth/skills are set up
        mock_app = MagicMock()
        mock_app.state = MagicMock()
        with patch("kernel.v5_bridge.SkillsBridge") as MockSB, \
             patch("kernel.v5_bridge.AuthBridge"), \
             patch("kernel.v5_bridge.ComplianceLayer"):
            MockSB.return_value.register_all.return_value = 0
            bridge.mount(mock_app)

        response = bridge.chat("Hello, world!")
        assert response.ok is True
        assert response.data["content"] == "bridge-reply"
        assert bridge._request_count == 1

    def test_chat_increments_request_count(self, bridge):
        """Each chat call should increment _request_count."""
        mock_app = MagicMock()
        mock_app.state = MagicMock()
        with patch("kernel.v5_bridge.SkillsBridge") as MockSB, \
             patch("kernel.v5_bridge.AuthBridge"), \
             patch("kernel.v5_bridge.ComplianceLayer"):
            MockSB.return_value.register_all.return_value = 0
            bridge.mount(mock_app)

        bridge.chat("msg1")
        bridge.chat("msg2")
        bridge.chat("msg3")
        assert bridge._request_count == 3

    def test_health_returns_ok(self, bridge):
        """health() should report status ok when kernel is healthy."""
        report = bridge.health()
        assert report["status"] == "ok"
        assert report["version"] == "1.0.0"
        assert "uptime_seconds" in report
        assert report["requests"] == 0

    def test_health_uptime_increases(self, bridge):
        """uptime_seconds should be non-negative."""
        report = bridge.health()
        assert report["uptime_seconds"] >= 0

    def test_authenticate_without_mount(self, bridge):
        """authenticate() before mount() should fail because auth is None."""
        # auth is None before mount
        assert bridge.auth is None

    def test_authenticate_after_mount(self, bridge):
        """authenticate() after mount should delegate to AuthBridge."""
        mock_app = MagicMock()
        mock_app.state = MagicMock()

        mock_auth = MagicMock()
        mock_auth_result = MagicMock()
        mock_auth_result.authenticated = True
        mock_auth_result.identity_id = "user-1"
        mock_auth_result.identity_type = "user"
        mock_auth_result.error = None
        mock_auth.login_bearer.return_value = mock_auth_result

        with patch("kernel.v5_bridge.SkillsBridge") as MockSB, \
             patch("kernel.v5_bridge.AuthBridge", return_value=mock_auth), \
             patch("kernel.v5_bridge.ComplianceLayer"):
            MockSB.return_value.register_all.return_value = 0
            bridge.mount(mock_app)

        result = bridge.authenticate("some-token")
        assert result["authenticated"] is True
        assert result["identity_id"] == "user-1"

    def test_list_skills_no_mcp_bus(self, bridge):
        """list_skills() should return [] when mcp_bus is None."""
        assert bridge.system.mcp_bus is None
        assert bridge.list_skills() == []

    def test_web_ui_data_structure(self, bridge):
        """web_ui_data() should return the expected structure."""
        data = bridge.web_ui_data()
        assert "surfaces" in data
        assert "agents" in data
        assert "skills" in data
        assert "health" in data
        assert "fitness" in data
        assert "compliance" in data

    def test_register_engine_callback(self, bridge):
        """register_engine_callback should add a runtime to the kernel."""
        handler = MagicMock(return_value="handler-result")
        bridge.register_engine_callback("custom_engine", handler)

        assert "custom_engine" in bridge.kernel._runtimes

    def test_get_mcp_routes(self, bridge):
        """get_mcp_routes should return route dict."""
        routes = bridge.get_mcp_routes()
        assert "tools/list" in routes
        assert "tools/call" in routes
        # tools/list with no mcp_bus should return []
        assert routes["tools/list"]() == []

    def test_dual_route(self, bridge):
        """dual_route should call both brain and kernel."""
        mock_brain = MagicMock()
        mock_brain.chat.return_value = "brain-result"

        # Mount first
        mock_app = MagicMock()
        mock_app.state = MagicMock()
        with patch("kernel.v5_bridge.SkillsBridge") as MockSB, \
             patch("kernel.v5_bridge.AuthBridge"), \
             patch("kernel.v5_bridge.ComplianceLayer"):
            MockSB.return_value.register_all.return_value = 0
            bridge.mount(mock_app)

        result = bridge.dual_route(mock_brain, "test prompt")
        assert result["v5"] == "brain-result"
        assert result["v1"].ok is True
        assert result["v1_ok"] is True
        assert result["migrated"] is True

    def test_dual_route_brain_exception(self, bridge):
        """dual_route should handle brain exceptions gracefully."""
        mock_brain = MagicMock()
        mock_brain.chat.side_effect = RuntimeError("brain crash")

        mock_app = MagicMock()
        mock_app.state = MagicMock()
        with patch("kernel.v5_bridge.SkillsBridge") as MockSB, \
             patch("kernel.v5_bridge.AuthBridge"), \
             patch("kernel.v5_bridge.ComplianceLayer"):
            MockSB.return_value.register_all.return_value = 0
            bridge.mount(mock_app)

        result = bridge.dual_route(mock_brain, "test prompt")
        assert result["v5"] is None
        assert result["v1"].ok is True


# =====================================================================
# kernel.v5_bridge -- get_bridge singleton
# =====================================================================


class TestGetBridge:
    """Test the global singleton accessor."""

    def test_get_bridge_returns_same_instance(self):
        import kernel.v5_bridge as v5mod

        # Reset the singleton
        v5mod._bridge = None

        mock_system = MagicMock()
        with patch("kernel.v5_bridge.build_default_system", return_value=mock_system):
            b1 = v5mod.get_bridge()
            b2 = v5mod.get_bridge()

        assert b1 is b2

        # Clean up
        v5mod._bridge = None


# =====================================================================
# kernel.system -- build_default_system (with heavy mocking)
# =====================================================================


class TestBuildDefaultSystem:
    """Test build_default_system with all heavy imports mocked."""

    def test_build_default_system_returns_system(self):
        """build_default_system should return an AOSSystem."""
        from kernel.system import AOSSystem

        # Mock build_default_kernel and all layer constructors
        mock_kernel = MagicMock()
        mock_kernel._model_gateway = None
        mock_kernel._skill_bus = None
        mock_kernel._runtimes = {}

        with patch("kernel.system.build_default_kernel", return_value=mock_kernel), \
             patch("kernel.system.WebUILayer") as MockUI, \
             patch("kernel.immunity.SelfHealer"):
            from kernel.system import build_default_system
            system = build_default_system()

        assert isinstance(system, AOSSystem)
        assert system.kernel is mock_kernel
        assert system.version == "1.0.0"

    def test_build_default_system_with_degradations(self):
        """When no plugins available, degradation dict should be populated."""
        mock_kernel = MagicMock()
        mock_kernel._model_gateway = None
        mock_kernel._skill_bus = None
        mock_kernel._runtimes = {}

        with patch("kernel.system.build_default_kernel", return_value=mock_kernel), \
             patch("kernel.system.WebUILayer"), \
             patch("kernel.immunity.SelfHealer"):
            from kernel.system import build_default_system
            system = build_default_system()

        assert "model_gateway" in system.degradation
        assert "mcp_bus" in system.degradation
        assert "agent_runtime" in system.degradation

    def test_build_default_system_with_plugins(self):
        """When plugins are available, layers should be constructed."""
        mock_gw_plugin = MagicMock()
        mock_bus_plugin = MagicMock()
        mock_runtime_plugin = MagicMock()

        mock_kernel = MagicMock()
        mock_kernel._model_gateway = mock_gw_plugin
        mock_kernel._skill_bus = mock_bus_plugin
        mock_kernel._runtimes = {"litellm": mock_runtime_plugin}

        with patch("kernel.system.build_default_kernel", return_value=mock_kernel), \
             patch("kernel.system.ModelGatewayLayer") as MockGWL, \
             patch("kernel.system.MCPBusLayer") as MockBusL, \
             patch("kernel.system.AgentRuntimeLayer") as MockRtL, \
             patch("kernel.system.WebUILayer"), \
             patch("kernel.immunity.SelfHealer"):
            from kernel.system import build_default_system
            system = build_default_system()

        MockGWL.assert_called_once_with(mock_gw_plugin)
        MockBusL.assert_called_once_with(mock_bus_plugin, mock_kernel)
        MockRtL.assert_called_once_with(mock_runtime_plugin, mock_kernel)
        assert system.model_gateway is not None
        assert system.mcp_bus is not None
        assert system.agent_runtime is not None


# =====================================================================
# Integration-style: kernel + versioning working together
# =====================================================================


class TestKernelWithVersioning:
    """Test that kernel operations work correctly alongside versioning."""

    def test_kernel_agents_with_versioned_specs(self, configured_kernel):
        """Register agents with different versions and verify they coexist."""
        spec_v1 = AgentSpec(agent_id="a-v1", name="AgentV1", engine="stub", version="1.0.0")
        spec_v2 = AgentSpec(agent_id="a-v2", name="AgentV2", engine="stub", version="2.0.0")

        configured_kernel.register_agent(spec_v1)
        configured_kernel.register_agent(spec_v2)

        agents = configured_kernel.list_agents()
        assert len(agents) == 2

        a1 = configured_kernel.get_agent("a-v1")
        a2 = configured_kernel.get_agent("a-v2")
        assert a1 is not None and a1.spec.version == "1.0.0"
        assert a2 is not None and a2.spec.version == "2.0.0"

    def test_kernel_send_message_with_versioned_registry(self, configured_kernel):
        """send_message should work with agents registered alongside versioning."""
        from kernel.versioning import VersionRegistry, version_plugin

        # Register a versioned plugin
        reg = VersionRegistry()
        reg.register(version_plugin("my-engine", "runtime", "1.0.0", lambda: "v1"))
        reg.register(version_plugin("my-engine", "runtime", "2.0.0", lambda: "v2"))

        latest = reg.get_latest("my-engine")
        assert latest.factory() == "v2"

        # Register an agent and send a message
        configured_kernel.register_agent(
            AgentSpec(agent_id="msg-test", name="MsgTest", engine="stub")
        )
        msg = Message(sender="test", recipient="msg-test", payload={"prompt": "hi"})
        resp = configured_kernel.send_message(msg)
        assert resp.ok
        assert resp.data["content"] == "stub-reply"
