#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
③级真 LLM 端到端验证：生命体层(life_state)真驱动运行时模型选择。

直接用生产统一入口 autopilot._llm_generate 跑真实 ollama 生成：
- 高能量(energy>=0.3)时，生产 picker 选重模型 qwen3:8b，ollama 真实生成；
- 多次真实推理回写 life_state（生产反馈 on_run_finished），energy 衰减过 0.3；
- 低能量时，picker 自动降档到轻模型 qwen2.5:3b，ollama 真实生成；
- 清空进程内单例、从磁盘重载，确认 energy 真落盘、降档状态持续。

全程不 mock 任何生成逻辑：只在 _ollama_generate 外包一层「记录 model 参数」的
spy，真实生成仍走 ollama。这是真 ③（真 LLM + 真磁盘 + 真生产装配）。
"""
import os
import sys

# 沙箱内存受限，跑不了 5.2GB 的 qwen3:8b；用两个已装的小模型做等价替身证明机制：
# 重模型 = qwen2.5:1.5b，轻模型 = minicpm5-1b。主机上把这两项换成
# qwen3:8b / qwen2.5:3b 即为白皮书原文路径，代码完全一致。
os.environ.setdefault("AOS_LLM_MODEL", "qwen2.5:1.5b")
os.environ.setdefault("AOS_LLM_LIGHT_MODEL", "minicpm5-1b")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

import kernel.lifeform_runtime as lr
import kernel.autopilot as ap
from kernel.life_state import LifeState

UID = "default"
HEAVY = os.environ["AOS_LLM_MODEL"]
LIGHT_EXPECT = os.environ["AOS_LLM_LIGHT_MODEL"]

rt = lr.get_lifeform_runtime()
store = rt.components["life_state"]

# 重置探针用户体征到满能量，避免历史落盘污染
store.save(UID, LifeState())
assert store.load(UID).energy == 1.0, "reset failed"

# spy：记录每次真实生成时 ollama 实际收到的 model + 当时 energy（不替换真实生成）
recorded = []
_orig_ollama = ap._ollama_generate


def _spy(prompt, model=None):
    e = store.load(UID).energy
    recorded.append((model, round(e, 3)))
    return _orig_ollama(prompt, model)


ap._ollama_generate = _spy

PROMPT = "用一句话介绍人工智能。"


def _phase(label):
    out = ap._llm_generate(PROMPT)
    model_used, energy_at = recorded[-1]
    ok = bool(out) and out.strip() != ""
    print(f"[{label}] energy={energy_at} model={model_used} gen_ok={ok} "
          f"out={repr((out or '')[:24])}")
    return ok, model_used


print("=== ③级真 LLM 端到端验证开始 ===")
print(f"重模型={HEAVY} 轻模型(预期)={LIGHT_EXPECT}")

# Phase 1: 高能量
ok1, m1 = _phase("P1-高能量")

# 真实衰减：用生产反馈函数把 energy 推过阈值（真实连续跑也是这条路）
for _ in range(20):
    rt.on_run_finished(cost=0.05, failed=False, user_id=UID)
e_low = store.load(UID).energy
print(f"衰减后 energy={round(e_low, 3)} (<0.3={e_low < 0.3})")

# Phase 2: 低能量
ok2, m2 = _phase("P2-低能量")

# 持久化验证：清空单例缓存，从磁盘重载
delattr(lr.get_lifeform_runtime, "_inst")
rt2 = lr.get_lifeform_runtime()
e_reload = rt2.components["life_state"].load(UID).energy
pick_reload = rt2.pick_model(HEAVY, LIGHT_EXPECT, user_id=UID)
print(f"重载后 energy={round(e_reload, 3)} 重载后 picker={pick_reload}")

# 断言
assert ok1 and ok2, "两次真实 ollama 生成都必须成功"
assert m1 == HEAVY, f"高能量应走重模型 {HEAVY}，实际 {m1}"
assert m2 == LIGHT_EXPECT, f"低能量应降档到轻模型 {LIGHT_EXPECT}，实际 {m2}"
assert e_low < 0.3, "energy 必须衰减过阈值"
assert e_reload < 0.3, "energy 必须真落盘（重载后仍 <0.3）"
assert pick_reload == LIGHT_EXPECT, "重载后 picker 仍须返回轻模型（真落盘非内存）"

print("\n✅ ③级真 LLM 端到端闭环验证通过："
      f"life_state(energy {round(e_low,3)}→{round(e_reload,3)}) "
      f"真实驱动 autopilot 模型选择 {HEAVY}→{LIGHT_EXPECT}，"
      "且两次均为 ollama 真实生成、状态真落盘。")
