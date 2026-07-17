"""Tool-Call Repair 层验证（借鉴 DeepSeek Reasonix 的 Tool-Call Repair）。

覆盖：合法 JSON 直过、类型强制、枚举裁剪、未知字段剔除、单引号/损坏 JSON 容错、
必填缺失用 default、必填缺失推断填充、彻底不可解析、模块级直调。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from execution.tool_executor import ToolExecutor
from core.fabric.tool_call_repair import (  # noqa: E402
    ToolCallRepair,
    CLASS_TYPE,
    CLASS_ENUM,
    CLASS_UNKNOWN,
    CLASS_MISSING_REQUIRED,
    CLASS_JSON_DECODE,
)

SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "age": {"type": "integer"},
        "status": {"type": "string", "enum": ["open", "closed"]},
    },
    "required": ["name", "age"],
}


def _make_executor(schema=SCHEMA):
    ex = ToolExecutor()

    def handler(name, age, status="open"):
        if not isinstance(age, int):
            raise ValueError("age must be int")
        if not isinstance(name, str):
            raise ValueError("name must be str")
        return f"{name}:{age}:{status}"

    ex.register_tool("user.add", "add user", schema, handler)
    return ex


def _actions(r):
    return [s["action"] for s in r["repair"]["steps"]]


def test_strict_ok():
    ex = _make_executor()
    r = ex.execute_with_repair("user.add", '{"name":"a","age":30}')
    assert r["success"] is True
    assert r["result"] == "a:30:open"
    assert r["repair"]["ok"] is True


def test_type_coerce():
    ex = _make_executor()
    r = ex.execute_with_repair("user.add", '{"name":"a","age":"30"}')
    assert r["success"] is True
    assert r["result"] == "a:30:open"
    assert CLASS_TYPE in _actions(r)


def test_enum_clip():
    ex = _make_executor()
    r = ex.execute_with_repair("user.add", '{"name":"a","age":30,"status":"ope"}')
    assert r["success"] is True
    assert r["result"] == "a:30:open"
    assert CLASS_ENUM in _actions(r)


def test_unknown_dropped():
    ex = _make_executor()
    r = ex.execute_with_repair("user.add", '{"name":"a","age":30,"extra":1}')
    assert r["success"] is True
    assert r["result"] == "a:30:open"
    assert CLASS_UNKNOWN in _actions(r)


def test_single_quote_repaired():
    ex = _make_executor()
    r = ex.execute_with_repair("user.add", "{'name':'a','age':30}")
    assert r["success"] is True
    assert r["result"] == "a:30:open"
    assert CLASS_JSON_DECODE in _actions(r)


def test_missing_required_default():
    schema = dict(SCHEMA)
    schema["properties"] = dict(SCHEMA["properties"])
    schema["properties"]["name"] = {"type": "string", "default": "anon"}
    ex = _make_executor(schema)
    r = ex.execute_with_repair("user.add", '{"age":30}')
    assert r["success"] is True
    assert r["result"] == "anon:30:open"
    assert CLASS_MISSING_REQUIRED in _actions(r)


def test_missing_required_inferred():
    ex = _make_executor()  # name required, 无 default
    r = ex.execute_with_repair("user.add", '{"age":30}')
    assert r["success"] is True
    assert r["result"] == ":30:open"  # name 被推断填充为 ""
    assert CLASS_MISSING_REQUIRED in _actions(r)


def test_unrepairable():
    ex = _make_executor()
    r = ex.execute_with_repair("user.add", "{not valid json at all")
    assert r["success"] is False
    assert r["repair"]["classification"] == CLASS_JSON_DECODE
    assert r["repair"]["ok"] is False


def test_repair_module_direct():
    rep = ToolCallRepair()
    res = rep.repair('{"age":"30","status":"ope"}', SCHEMA, aggressiveness=0)
    assert res.fixed is not None
    assert res.fixed["age"] == 30
    assert res.fixed["status"] == "open"
    actions = [s.action for s in res.report.steps]
    assert CLASS_TYPE in actions and CLASS_ENUM in actions
