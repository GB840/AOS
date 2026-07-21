"""FabricHub 真实通电自检测试（MASTER_PLAN 阶段 1.2）。

不依赖具体环境是否通电：只验证「诚实」这一核心不变量——
resolve_engine 绝不返回未通电的引擎；dead 引擎如实写出；无 live 提供者时
优雅失败（带原因，不静默）。
"""
from __future__ import annotations

import sys

from kernel.kernel import AOSKernel
from kernel.plugins.fabric_hub import FabricHub

_KNOWN_CAPS = (
    "inference.llm",
    "system.observability",
    "memory.semantic",
    "group.orchestration",
    "action.aci",
    "channel.access",
    "media.image",
    "media.video",
)
# 枢纽当前注册的全部引擎（单一真相源；新增引擎在此追加一行即可，
# total 断言自动从本集合推导，避免计数与集合再漂移）。
# 前 8 个为原始通电引擎；code-exec/file-io/web-fetch 为本特性新增的零依赖
# 适配器；orchestrator 为默认通电编排芯粒；codebase-memory-mcp 为 stdio MCP。
_EXPECTED_ENGINES = {
    "openclaw",
    "ag2",
    "litellm",
    "mem0",
    "browser-use",
    "langfuse",
    "web-search",
    "agnes",
    "code-exec",
    "file-io",
    "web-fetch",
    "web-crawl",       # crawl4ai 网页转 LLM 友好 Markdown（需 pip install crawl4ai）
    "media-gen",      # 国产智谱文生图/文生视频（零依赖 urllib）
    "orchestrator",
    "codebase-memory-mcp",
    "threejs",
    "stt",
    "tts",
    "lnn",
    "lfm2",
    "scripts",
    "minicpm_o",
    "vlm",
    "desktop-touch",
    "omni-video",
    "video-use",
    "cast",
    "code-team",
    "comfyui",
    "content-director",
    "content-marketer",
    "echo",
    "refine",
    "remotion",
    "security-audit",
    "video-maker",
}


def test_registers_all_six_and_reports_total():
    hub = FabricHub()
    rep = hub.health_report()
    assert rep["total"] == len(_EXPECTED_ENGINES)
    assert set(rep["adapters"].keys()) == _EXPECTED_ENGINES
    # health_report 的字段是条件性的：核心字段恒在，隔离引擎额外带 isolation，
    # 支持 health_detail 的适配器额外带 health_detail。只校验「核心必在 + 无未知字段」。
    _CORE = {"live", "capabilities", "error", "isolated"}
    _OPTIONAL = {"isolation", "health_detail"}
    for info in rep["adapters"].values():
        assert _CORE <= set(info.keys())
        assert set(info.keys()) <= (_CORE | _OPTIONAL)


def test_resolve_never_returns_dead_engine():
    """核心诚实不变量：返回的引擎一定 live；绝不谎报。"""
    hub = FabricHub()
    rep = hub.health_report()
    for cap in _KNOWN_CAPS:
        eng = hub.resolve_engine(cap)
        if eng is None:
            continue
        assert eng in rep["adapters"]
        assert rep["adapters"][eng]["live"] is True


def test_route_to_unpowered_capability_fails_gracefully():
    hub = FabricHub()
    res = hub.route("memory.semantic", {"prompt": "x"})
    assert hasattr(res, "ok")
    if not res.ok:
        # 失败必须给出原因，绝不静默回退假装成功
        assert res.error


def test_hub_import_does_not_pull_brain():
    """内核零依赖接缝不被破坏：构造 Hub 不应拉起重型 brain 栈。"""
    before = set(sys.modules)
    FabricHub()
    pulled = set(sys.modules) - before
    assert "core.brain" not in pulled


def test_kernel_delegates_resolve_engine_to_hub():
    """内核级单一可信源：resolve_engine / fabric_health 正确委派给 Hub。"""
    k = AOSKernel()
    assert k.resolve_engine("inference.llm") is None  # 尚未登记枢纽
    assert k.fabric_health() is None

    k.set_fabric_hub(FabricHub())
    rep = k.fabric_health()
    assert rep is not None and rep["total"] == len(_EXPECTED_ENGINES)


def test_session_lru_eviction_on_capacity_limit():
    """验证会话 LRU 淘汰：超出 SESSION_MAX_COUNT 时自动淘汰最旧会话。"""
    from kernel.plugins.fabric_hub import _SESSIONS, _SESSION_MAX_COUNT, _save_session

    # 清空现有会话
    _SESSIONS.clear()

    # 填充到容量上限
    for i in range(_SESSION_MAX_COUNT):
        _save_session(f"session_{i}", [{"task": f"task_{i}", "response": f"response_{i}"}])

    # 验证容量已达上限
    assert len(_SESSIONS) == _SESSION_MAX_COUNT

    # 添加新会话，应触发 LRU 淘汰
    _save_session(f"session_{_SESSION_MAX_COUNT}", [{"task": "new", "response": "new"}])

    # 验证：总数仍为上限，且最旧的会话被淘汰
    assert len(_SESSIONS) == _SESSION_MAX_COUNT
    assert "session_0" not in _SESSIONS, "最旧会话应被淘汰"
    assert f"session_{_SESSION_MAX_COUNT}" in _SESSIONS, "新会话应被添加"


def test_session_max_turns_limit():
    """验证 SESSION_MAX_TURNS=5：每个会话最多保留5轮历史。"""
    from kernel.plugins.fabric_hub import _save_session, _load_session

    # 创建超过5轮的会话历史
    history = [{"task": f"task_{i}", "response": f"response_{i}"} for i in range(10)]
    _save_session("test_session", history)

    # 验证：只保留最近5轮
    loaded = _load_session("test_session")
    assert len(loaded) == 5, f"预期5轮，实际{len(loaded)}轮"
    assert loaded[0]["task"] == "task_5", "应保留最近5轮"
    assert loaded[-1]["task"] == "task_9", "应保留最近5轮"

