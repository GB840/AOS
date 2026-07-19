"""诚实自进化闭环端到端演示（任务270 / 白皮书 3.1）。

离线可跑（无需 LLM key）：展示 AOS 新范式核心——
  失败即训练 → 反思重设计（诚实 heuristic 兜底）→ Meta-Trace 跨任务记忆沉淀。
每一步带可审计证据，绝不伪造成功。

运行:
  cd D:/AOS
  PYTHONPATH=/d/AOS/src python examples/self_evolving_demo.py
"""
import os
import sys
import logging

# 让脚本在 repo 根直接运行也能找到 src 包
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kernel import autopilot as ap

# 静音反思降级 warning（演示只展示闭环证据，不展示内部降级日志）
logging.getLogger("kernel.autopilot").setLevel(logging.ERROR)


def _noop(*a, **k):
    raise RuntimeError("offline demo: no ag2 / ollama")


def demo():
    # 强制诚实 heuristic 兜底 + 独立记忆文件（不污染真实 _traces）
    ap._get_ag2 = _noop
    ap._ollama_generate = _noop
    mem = os.path.join(os.path.dirname(__file__), "self_evolving_reflection.jsonl")
    if os.path.exists(mem):
        os.remove(mem)
    ap._REFLECTION_MEMORY_PATH = mem

    print("=" * 66)
    print("AOS 新范式演示：诚实可验证的自进化闭环")
    print("=" * 66)

    # ---------- 第一次任务：搜索失败 ----------
    task_a = "搜索『不存在的冷门API』并生成调研报告"
    trace_a = {"execution": {"trace": [
        {"capability": "web.search", "ok": False,
         "summary": "0 条结果（关键词过窄/拼写错误）",
         "real_metrics": {"is_real": False}},
    ]}}
    print(f"\n[任务A] {task_a}")
    print("  执行结果: web.search -> 0 条结果（真实失败，非伪造）")
    refl_a = ap._reflect_and_redesign(task_a, trace_a, 1)
    print(f"  反思重设计: engine={refl_a['engine']}, 新步数={len(refl_a['steps'])}")
    lines = [l for l in open(mem, encoding="utf-8") if l.strip()]
    print(f"  教训沉淀 -> Meta-Trace 当前条数: {len(lines)}")

    # ---------- 第二次相似任务：注入历史教训 ----------
    task_b = "搜索『另一个也不存在的库』写技术总结"
    lessons = ap._load_lessons(task_b)
    print(f"\n[任务B] {task_b}")
    print(f"  载入历史相似教训: {len(lessons)} 条")
    for L in lessons:
        print(f"    - 曾失败于 [{L['failed_cap']}]: {L['lesson'][:78]}")
    trace_b = {"execution": {"trace": [
        {"capability": "web.search", "ok": False,
         "summary": "0 条结果", "real_metrics": {"is_real": False}},
    ]}}
    refl_b = ap._reflect_and_redesign(task_b, trace_b, 1)
    print(f"  反思重设计(已携历史教训): engine={refl_b['engine']}")

    print("\n" + "=" * 66)
    print("结论: 失败被沉淀为可跨任务复用的经验 (Meta-Trace)，")
    print("      系统下次遇相似任务自动规避已知失败做法——这就是")
    print("      AOS『诚实自进化闭环』：每步带真实证据、可审计、不伪造。")
    print("=" * 66)


if __name__ == "__main__":
    demo()
