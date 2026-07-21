"""FabricHub.chat 通电逻辑：智谱直连优先，路由不可用时不阻塞。

用 __new__ 跳过重型 __init__（避免 prewarm 子进程），仅验证 chat 方法的
「智谱优先 / 路由兜底」分支正确性，不依赖网络与外部引擎。
"""
import sys
from unittest.mock import patch

sys.path.insert(0, "src")
import kernel.plugins.fabric_hub as fh
from kernel.plugins.fabric_hub import FabricHub, InvokeResult


def test_chat_prefers_zhipu_when_route_unavailable():
    hub = FabricHub.__new__(FabricHub)  # 跳过重型 __init__
    with patch.object(fh, "_load_session", return_value=[]), \
         patch.object(fh, "_save_session", return_value=None), \
         patch.object(fh, "zhipu_chat", return_value="你好，我是 AOS"):
        r = hub.chat("你好")
    assert r["ok"] is True
    assert r["engine"] == "zhipu-direct"
    assert r["response"] == "你好，我是 AOS"


def test_chat_falls_back_to_route_when_zhipu_none():
    hub = FabricHub.__new__(FabricHub)

    res = InvokeResult(ok=True, engine_id="lfm", data={"content": "来自本地模型"}, error=None)

    with patch.object(fh, "_load_session", return_value=[]), \
         patch.object(fh, "_save_session", return_value=None), \
         patch.object(fh, "zhipu_chat", return_value=None), \
         patch.object(hub, "route", return_value=res):
        r = hub.chat("你好")
    assert r["ok"] is True
    assert r["response"] == "来自本地模型"
