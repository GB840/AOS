"""
本地小模型路由自检脚本
=======================
验证三个本地模型是否按任务类型被 LLMRouter 正确选中并真实应答：
  GENERAL / HIGH_CONCURRENCY -> MiniCPM5-1B   (轻量全能)
  CODING                     -> Qwen2.5-Coder-3B (写代码)
  LONG_CONTEXT / EXPERIMENT  -> DeepSeek-R1-1.5B  (推理逻辑)

用法：
  set PYTHONPATH=D:\\AOS\\src
  python scripts\\verify_local_models.py
"""
import os
import sys

# 确保能 import src 包
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from router.llm_router import LLMRouter, TaskType  # noqa: E402

CASES = [
    (TaskType.GENERAL, "用一句话介绍你自己。"),
    (TaskType.CODING, "用 Python 写一个判断素数的函数，只给代码。"),
    (TaskType.LONG_CONTEXT, "小明比小红大3岁，小红比小刚大2岁，小刚10岁，小明几岁？给出推理。"),
]


def main() -> int:
    router = LLMRouter()

    print("=" * 60)
    print("已初始化的 provider：")
    for p in router.get_available_providers():
        print(f"  - {p['id']:12s} model={p['model']:20s} available={p['available']}")
    print("本地任务映射：")
    for tt, m in router.ollama_task_model.items():
        print(f"  - {tt.value:16s} -> {m}")
    print("=" * 60)

    ok = 0
    for task_type, prompt in CASES:
        print(f"\n[{task_type.value}] 提问: {prompt}")
        res = router.chat(
            [{"role": "user", "content": prompt}],
            task_type=task_type,
            max_tokens=256,
        )
        provider = res.get("provider")
        model = res.get("model")
        success = res.get("success")
        content = (res.get("content") or "").strip().replace("\n", " ")
        print(f"  -> provider={provider}  model={model}  success={success}")
        print(f"  -> 回答: {content[:160]}")
        if success:
            ok += 1

    print("\n" + "=" * 60)
    print(f"结果: {ok}/{len(CASES)} 条任务成功路由并应答")
    print("=" * 60)
    return 0 if ok == len(CASES) else 1


if __name__ == "__main__":
    sys.exit(main())
