"""mem0 本地零成本配置测试 —— 验证 AOS 记忆平面不依赖任何付费 API。

之前 mem0 被锁死在三个远程付费 key（SILICONFLOW/ZHIPU/UNIFIED），导致
「无余额即全废」的虚假死局。现改为默认本地优先（ollama / sentence-transformers
+ 本地 chroma），本测试锚定这一零成本契约：
  - force_local 时 embedder/llm 走 ollama，配置里绝不含 api_key；
  - AOS_MEM0_EMBEDDER=huggingface 时走本机已装的 sentence-transformers；
  - 关本地且无远程 key 时返回 None（优雅降级，不崩）。
且 from_config 能干净构造（不联网、不下载模型）。
"""
import os

import pytest

pytest.importorskip("mem0")  # 缺 mem0 包（本地零成本记忆依赖）；装齐后自动跑

from core.fabric.adapters.mem0_adapter import build_mem0_config


def test_local_ollama_zero_cost(monkeypatch):
    monkeypatch.setenv("AOS_MEM0_LOCAL", "1")
    cfg = build_mem0_config(force_local=True)
    assert cfg["llm"]["provider"] == "ollama"
    assert cfg["embedder"]["provider"] == "ollama"
    assert "api_key" not in str(cfg), "本地模式不应出现付费 key"
    # 能从配置构造 Memory（不联网、不下载模型，仅建本地客户端）
    from mem0 import Memory
    mem = Memory.from_config(cfg)
    assert mem is not None


def test_local_huggingface_embedder(monkeypatch):
    monkeypatch.setenv("AOS_MEM0_EMBEDDER", "huggingface")
    cfg = build_mem0_config(force_local=True)
    assert cfg["embedder"]["provider"] == "huggingface"
    assert cfg["embedder"]["config"]["model"] == "BAAI/bge-small-zh-v1.5"
    assert "api_key" not in str(cfg)


def test_remote_fallback_none_without_keys(monkeypatch):
    # 关掉本地、且清掉所有远程 key -> 返回 None（优雅降级）
    monkeypatch.setenv("AOS_MEM0_LOCAL", "0")
    for k in ("SILICONFLOW_API_KEY", "ZHIPU_API_KEY", "UNIFIED_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    assert build_mem0_config() is None
