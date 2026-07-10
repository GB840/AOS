#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验证 AOS LLMRouter 是否按任务类型正确路由到 mistralrs 本地端点。"""
import sys, traceback, importlib.util as u
sys.path.insert(0, r"D:\AOS\src")

print("openai available:", u.find_spec("openai") is not None)
try:
    from utils.config import config
    from router.llm_router import LLMRouter, TaskType
except Exception as e:
    print("IMPORT ERROR:", e)
    traceback.print_exc()
    sys.exit(1)

print("\n=== config 关键项 ===")
for k in ["MISTRALRS_ENABLED", "MISTRALRS_HOST", "MISTRALRS_PORT_GENERAL",
          "MISTRALRS_PORT_CODING", "MISTRALRS_PORT_REASONING",
          "MISTRALRS_MODEL_GENERAL", "MISTRALRS_MODEL_CODING", "MISTRALRS_MODEL_REASONING",
          "ROUTER_CODING_PRIMARY", "ROUTER_HIGH_CONCURRENCY_PRIMARY",
          "ROUTER_LONG_CONTEXT_PRIMARY", "ROUTER_EXPERIMENT_PRIMARY", "ROUTER_FALLBACK"]:
    print(f"  {k} = {getattr(config, k, 'MISSING')}")

print("\n=== 初始化 LLMRouter ===")
r = LLMRouter()
print("Providers (available):")
for p, info in r.providers.items():
    print(f"  {p.value}: available={info.get('available')} model={info.get('model')}")

print("\n=== 路由测试 (GENERAL -> 期望 mistralrs_general / minicpm5-1b) ===")
try:
    res = r.chat([{"role": "user", "content": "Say hi in one sentence."}],
                 task_type=TaskType.GENERAL)
    print(f"  provider = {res.get('provider')}")
    print(f"  model    = {res.get('model')}")
    print(f"  success  = {res.get('success')}")
    print(f"  content  = {(res.get('content') or '')[:240]}")
except Exception as e:
    print("  EXCEPTION:", e)
    traceback.print_exc()
