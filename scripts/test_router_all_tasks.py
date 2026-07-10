"""AOS LLMRouter 端到端路由验证：用户一句话 -> 按任务类型自动选 mistralrs 本地模型。
实时写入 D:\\AOS\\logs\\mistralrs\\router_test.log（每次 flush），方便外部观察进度。
"""
import sys, os, json, time
sys.path.insert(0, r"D:\AOS\src")
LOG = r"D:\AOS\logs\mistralrs\router_test.log"

def log(msg):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(msg + "\n")
        f.flush()
    print(msg, flush=True)

from router.llm_router import LLMRouter, TaskType

router = LLMRouter()

CASES = [
    # (task_type, 期望命中端口/模型, ASCII 提示)
    (TaskType.GENERAL,        "1234 / MiniCPM5",        "Introduce yourself in one sentence."),
    (TaskType.CODING,         "1235 / Qwen-Coder",       "Write a one-line Python function to reverse a string."),
    (TaskType.LONG_CONTEXT,   "1236 / DeepSeek-R1",      "What is 15 * 17? Answer briefly."),
]

log("=" * 70)
log(f"开始路由测试 @ {time.strftime('%H:%M:%S')}")
log(f"ROUTER_PREFER_LOCAL = {getattr(router.__class__.__module__, 'config', None)}")
try:
    import utils.config as cfg
    log(f"config.ROUTER_CODING_PRIMARY   = {cfg.ROUTER_CODING_PRIMARY}")
    log(f"config.ROUTER_LONG_CONTEXT_PRIMARY = {cfg.ROUTER_LONG_CONTEXT_PRIMARY}")
    log(f"config.ROUTER_FALLBACK        = {cfg.ROUTER_FALLBACK}")
except Exception as e:
    log(f"(config 读取失败: {e})")

for tt, expect, prompt in CASES:
    log("-" * 70)
    log(f"任务类型: {tt.value}  (期望命中 {expect})")
    t0 = time.time()
    try:
        res = router.chat(
            messages=[{"role": "user", "content": prompt}],
            task_type=tt,
            max_tokens=80,
            temperature=0.2,
        )
    except Exception as e:
        log(f"  !! 异常: {type(e).__name__}: {e}")
        continue
    dt = time.time() - t0
    ok = res.get("success")
    prov = res.get("provider")
    model = res.get("model")
    content = (res.get("content") or "").strip().replace("\n", " ")
    log(f"  成功={ok}  实际provider={prov}  实际model={model}  耗时={dt:.1f}s")
    log(f"  回复: {content[:200]}")
    if ok and "mistralrs" in str(prov).lower():
        log(f"  [OK] 命中 mistralrs 本地模型 ✓")
    elif ok:
        log(f"  [注意] 命中了 {prov}（非 mistralrs）——可能本地模型名不匹配被跳过")
    else:
        log(f"  [FAIL] 全部不可用: {content[:160]}")

log("=" * 70)
log("测试结束")
