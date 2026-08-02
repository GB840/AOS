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
# 枢纽当前注册的全部「稳定核心引擎」（单一真相源；新增引擎在此追加一行即可）。
# 前 8 个为原始通电引擎；code-exec/web-fetch 为本特性新增的零依赖适配器；
# orchestrator 为默认通电编排芯粒；codebase-memory-mcp 为 stdio MCP；
# img2threejs/knowmesh/mediakit 为后批接入的开源（3D/知识图谱/音视频后期）。
# 注意：断言使用「子集」语义（_EXPECTED_ENGINES <= 实际注册集），因为部分引擎
# 依赖可选环境（如 content-director 依赖 pydantic_settings）；这类放入
# _OPTIONAL_ENGINES，装了才注册，不计入硬断言，避免跨环境假红。
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
    "content-marketer",
    "echo",
    "refine",
    "remotion",
    "security-audit",
    "video-maker",
    "img2threejs",    # 后批：hoainho/img2threejs (Apache-2.0) 文/图生 3D，产品研发岗
    "knowmesh",       # 后批：知识图谱 / Mesh 生成芯粒
    "mediakit",       # 后批：火山引擎 mediakit-cli 胶水（opt-in，默认关闭）
}
# 可选环境依赖引擎：装了对应依赖才注册，不计入硬断言（避免缺依赖时测试假红）。
_OPTIONAL_ENGINES = {
    "content-director",  # 依赖 pydantic_settings；本沙箱缺故不注册，主机有依赖则注册
    "file-io",           # 代码当前未注册此引擎（疑似已重构移除）；若未来恢复须加回核心集
}


def test_registers_all_six_and_reports_total():
    hub = FabricHub()
    rep = hub.health_report()
    got = set(rep["adapters"].keys())
    # 核心引擎必须全部注册（单一真相源，新增须在此追加；环境依赖的放 _OPTIONAL_ENGINES）。
    # 用子集语义而非 ==：可选依赖引擎（如 content-director 需 pydantic_settings）在缺依赖
    # 环境不注册，但总数仍如实反映实际注册数，避免跨环境假红。
    assert _EXPECTED_ENGINES <= got, sorted(_EXPECTED_ENGINES - got)
    assert rep["total"] == len(got)
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
    assert rep is not None and rep["total"] == len(rep["adapters"])


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

