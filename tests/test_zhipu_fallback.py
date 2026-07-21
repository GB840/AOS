import os

import pytest
from dotenv import load_dotenv

# 加载仓库根 .env（若存在），使 ZHIPU_API_KEY 在本地可用。
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_ROOT, ".env"))

from kernel.plugins.zhipu_chat import zhipu_chat


def test_zhipu_chat_returns_text_with_key():
    if not os.environ.get("ZHIPU_API_KEY"):
        pytest.skip("无 ZHIPU_API_KEY，跳过真实智谱调用")
    out = zhipu_chat(
        [{"role": "user", "content": "say hi in one word"}],
        max_tokens=10,
    )
    assert isinstance(out, str) and out.strip(), "智谱兜底应返回非空文本"


def test_zhipu_chat_returns_none_without_key(monkeypatch):
    monkeypatch.delenv("ZHIPU_API_KEY", raising=False)
    out = zhipu_chat([{"role": "user", "content": "hi"}], max_tokens=10)
    assert out is None
