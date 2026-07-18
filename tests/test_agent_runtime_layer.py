"""验证 agent_runtime_layer 修复（双轨债 ⑥）：stop_agent 不得误清全局记忆。

核心理念：故障隔离——停一个 agent 只清它命名空间下的记忆，
绝不能把其他 agent 的全局记忆一并清空（旧实现循环调 clear() 即此 bug）。
"""
import pytest

from kernel.layers.agent_runtime_layer import (
    AgentRuntimeLayer,
    InMemoryMemoryManager,
    FileMemoryManager,
)


class _FakeRuntime:
    def run_agent(self, *a, **k):
        return None


class _FakeKernel:
    def __init__(self):
        self.stopped = []

    def stop_agent(self, agent_id):
        self.stopped.append(agent_id)


def test_inmemory_keys_and_remove():
    m = InMemoryMemoryManager()
    m.set("a:1", 1)
    m.set("a:2", 2)
    m.set("b:1", 3)
    assert set(m.keys()) == {"a:1", "a:2", "b:1"}
    m.remove("a:1")
    assert m.get("a:1") is None
    assert m.get("a:2") == 2


def test_stop_agent_only_clears_that_agent():
    kernel = _FakeKernel()
    mem = InMemoryMemoryManager()
    mem.set("agent_x:task", "X")
    mem.set("agent_x:ctx", "X2")
    mem.set("agent_y:task", "Y")
    layer = AgentRuntimeLayer(_FakeRuntime(), kernel, mem)

    layer.stop_agent("agent_x")

    # agent_x 的记忆被清，agent_y 的记忆毫发无损（旧实现会全清）
    assert mem.get("agent_x:task") is None
    assert mem.get("agent_x:ctx") is None
    assert mem.get("agent_y:task") == "Y"
    assert kernel.stopped == ["agent_x"]


def test_file_memory_remove_persists(tmp_path):
    fp = str(tmp_path / "mem.jsonl")
    m = FileMemoryManager(fp)
    m.set("a:1", 1)
    m.set("b:1", 2)
    assert m.get("a:1") == 1

    m.remove("a:1")
    assert m.get("a:1") is None
    assert m.get("b:1") == 2

    # 重新加载确认删除已持久化（重写整个文件）
    m2 = FileMemoryManager(fp)
    assert m2.get("a:1") is None
    assert m2.get("b:1") == 2
