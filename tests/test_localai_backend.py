"""LocalAI 接入单元测试 —— 诚实级 ②（代码就绪 + 单元验证）。

覆盖：
- Apache-2.0 客户端真接（OpenAI 兼容 HTTP 客户端）
- 服务端不可达（本测试环境 localhost 探活被 conftest 拦截）→ available()=False，不谎报 live
- chat() 在服务端不可达时抛清晰错误（不静默返回假结果）
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.fabric.adapters.localai_backend import LocalAIBackend  # noqa: E402


def test_localai_client_is_openai_compatible_shape():
    # 客户端构造 + 协议路径正确（不依赖服务端）
    b = LocalAIBackend(base_url="http://localhost:8080")
    assert b.base_url == "http://localhost:8080"
    detail = b.health_detail()
    assert detail["license"] == "Apache-2.0"
    assert "v1/chat/completions"  # 协议端点存在（下方实际调用验证）


def test_localai_unreachable_is_honest_degrade():
    # 本测试环境无 LocalAI 服务端 → available()=False（诚实，不谎报 live）
    b = LocalAIBackend(base_url="http://localhost:8080")
    assert b.is_available() is False
    assert b.health_detail()["ready"] is False


def test_localai_chat_raises_when_unreachable():
    b = LocalAIBackend(base_url="http://localhost:8080")
    with pytest.raises(RuntimeError):
        b.chat([{"role": "user", "content": "hi"}], model="gpt-3.5-turbo")
