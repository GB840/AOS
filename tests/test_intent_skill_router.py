"""intent_skill_router 原型单测（② 级：本地前缀路由，无需 LLM/MCP 服务）。"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.fabric.intent_skill_router import (  # noqa: E402
    IntentSkillRouter,
    Skill,
)


def test_register_and_route_longest_prefix():
    r = IntentSkillRouter()
    r.register(Skill("weather", "查天气", lambda: "w"))
    r.register(Skill("weather_city", "查天气@城市", lambda: "wc"))
    # 意图「查天气@城市.北京」应命中更长前缀的 weather_city
    assert r.route("查天气@城市.北京").name == "weather_city"
    # 意图「查天气.今日」只命中 weather
    assert r.route("查天气.今日").name == "weather"


def test_mcp_tools_excludes_non_compatible():
    r = IntentSkillRouter()
    r.register(Skill("a", "意图A", lambda: "a", mcp_compatible=True))
    r.register(Skill("b", "意图B", lambda: "b", mcp_compatible=False))
    tools = r.mcp_tools()
    assert {t["name"] for t in tools} == {"a"}


def test_dispatch_calls_handler():
    r = IntentSkillRouter()
    r.register(Skill("greet", "你好", lambda name: f"hi {name}"))
    assert r.dispatch("你好.世界", name="世界") == "hi 世界"


def test_no_match_raises():
    r = IntentSkillRouter()
    try:
        r.dispatch("未知意图")
        assert False, "应当抛出 LookupError"
    except LookupError:
        pass
