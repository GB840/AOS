"""Fix B + Fix A 回归：mem0 2.0 schema 正确性，以及 FabricHub 自动加载 .env 通电 agnes。

背景（用户主机真机暴露的两个真 bug，非环境降级）：
- Bug A：FabricHub() 构造没加载 .env → AGNES_API_KEY 不在 env → AgnesAdapter.health()
  返回 False → media.image / media.video 没有 live provider（route 报 "no live provider"）。
  修复：FabricHub.__init__ best-effort 加载仓库根 .env。
- Bug B：mem0 升级到 2.0.11，config schema 全变（llm/embedder 字段名 api_key 而非
  openai_api_key；vector_store 不再支持 "memory"；LlmConfig 不接受 openai_base_url
  参数）。旧代码 Memory(**config) 展开传参直接抛 unexpected keyword argument。
  修复：build_mem0_config 用 2.0 schema + chroma 真实路径；invoke 用 from_config。
"""
from __future__ import annotations

import os
import sys

# 与现有测试一致：让 `import kernel` / `import core` 可用。
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (_ROOT, os.path.join(_ROOT, "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def test_build_mem0_config_uses_v2_schema():
    from core.fabric.adapters.mem0_adapter import build_mem0_config

    cfg = build_mem0_config()
    assert cfg is not None, "FabricHub 应已自动加载 .env，存在可用 key（SILICONFLOW/ZHIPU/UNIFIED）"

    # mem0 2.0 schema：llm/embedder 用 api_key（旧版 openai_api_key 已弃用）
    assert "openai_api_key" not in cfg["llm"]["config"], "旧版字段已弃用"
    assert cfg["llm"]["config"]["api_key"]
    assert cfg["embedder"]["config"]["api_key"]

    # vector_store 用 chroma 真实路径（Windows 不支持 ":memory:"）
    assert cfg["vector_store"]["provider"] == "chroma"
    assert ":memory:" not in cfg["vector_store"]["config"]["path"]


def test_mem0_from_config_initializes_without_kwarg_error():
    from mem0 import Memory
    from core.fabric.adapters.mem0_adapter import build_mem0_config, _build_memory

    cfg = build_mem0_config()
    # 旧版 Memory(**cfg) 会抛 `unexpected keyword argument 'llm'`；from_config 应 OK
    mem = _build_memory(Memory, cfg)
    assert isinstance(mem, Memory)


def test_fabric_hub_autoloads_env_resolves_agnes():
    from kernel.plugins.fabric_hub import FabricHub

    # 不手动 load_dotenv：验证 hub 自身构造时 best-effort 加载仓库根 .env，
    # 让依赖 key 的 agnes 通电，media.image 因此有 live provider。
    h = FabricHub()
    assert h.resolve_engine("media.image") == "agnes", \
        "agnes 应因 .env 被自动加载而通电，advertise media.image"
    assert h.resolve_engine("media.video") == "agnes"
