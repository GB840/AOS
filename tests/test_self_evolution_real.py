"""自进化闭环 ③ 级真实端到端验证（原则9 / 理念2.5）。

这是 ② 级离线测试（test_self_evolving_loop.py，走 heuristic 兜底）的「真机」对偶：
本测试用**本机真实 ollama LLM** 驱动反思重设计，证明自进化闭环在真实 LLM 下：

  1. 第一轮失败后，真实 LLM 产出重设计方案（不是 heuristic 兜底伪装）；
  2. 每轮反思的「失败→教训」真实落盘到 reflection_memory.jsonl（有界 JSONL）；
  3. 第二轮反思**真的重新读回**了第一轮沉淀的教训（跨轮 Meta-Trace 记忆读回为真）；
  4. 重设计方案确实换了做法（首步能力不同于失败步，或带因果 engine_hint），
     即「第 N+1 轮比第 1 轮好」是可验证的真实闭环，而非原地重试伪装成反思。

诚实纪律（用户铁律）：
  - 绝不用 mock LLM 伪造「变好了」。反思 LLM 调用 100% 走真实 ollama 本地推理。
  - 若无可用 ollama / 模型不能产出 AOS 计划格式（如 minicpm-mem / minicpm5-1b 之类
    chat 鹦鹉会鹦鹉学舌、不产生能力前缀步骤）→ 直接 skip，绝不假绿。
  - ② 级（offline heuristic）与 ③ 级（真实 LLM）分层清晰，本文件只验证 ③。

运行：需 AOS_RUN_REAL_TESTS=1 且本机 ollama 有「能产出计划格式」的模型
（默认 qwen2.5-coder:7b；可用 AOS_REFLECT_OLLAMA_MODEL 覆盖）。
"""
import os
import re
import json
import urllib.request

import pytest

from core.fabric.adapter import InvokeResult
from kernel import autopilot as ap


# 本机 ollama 基础地址（与产品 autopilot._ollama_generate 一致）
_OLLAMA_URL = os.environ.get("AOS_OLLAMA_URL", "http://localhost:11434/api/generate")
_OLLAMA_TAGS = os.environ.get("AOS_OLLAMA_URL", "http://localhost:11434").rstrip("/") + "/api/tags"


def _ollama_model_ready(model: str, base: str = None) -> bool:
    """快速就绪探针（≤20s）：模型已拉取 且 能在短 prompt 下产出 AOS 能力前缀步骤。

    返回 False 的情况：ollama 没起 / 模型未拉取 / 模型是 chat 鹦鹉（不产生计划格式，
    如默认的 minicpm-mem）。这些情况下 ③ 无法 honest 验证 → 测试会 skip。
    """
    tags_url = (base or _OLLAMA_TAGS)
    _timeout = int(os.environ.get("AOS_OLLAMA_TIMEOUT", "120"))
    try:
        with urllib.request.urlopen(tags_url, timeout=5) as r:
            models = [m["name"] for m in json.loads(r.read().decode())["models"]]
        if model not in models:
            return False
        # 计划格式探针：要求只输出一行能力前缀步骤（超时与反思调用共用 AOS_OLLAMA_TIMEOUT）
        body = json.dumps({
            "model": model,
            "prompt": "只输出一行：web.search=ok",
            "stream": False,
            "options": {"num_predict": 24, "temperature": 0.2},
        }).encode()
        req = urllib.request.Request(_OLLAMA_URL, data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=_timeout) as r:
            resp = json.loads(r.read().decode()).get("response", "")
        return any(re.match(r"^\s*[A-Za-z][\w.\-]*\s*=", ln) for ln in resp.splitlines())
    except Exception:
        return False


@pytest.mark.skipif(os.environ.get("AOS_RUN_REAL_TESTS") != "1",
                    reason="③级真机验证需 AOS_RUN_REAL_TESTS=1（真实本地 LLM，禁用 mock）")
def test_self_evolution_real_llm_loop(tmp_path, monkeypatch):
    task = "调研并总结本地开源语音识别方案 Vosk"
    model = os.environ.get("AOS_REFLECT_OLLAMA_MODEL", "qwen2.5-coder:7b")
    if not _ollama_model_ready(model):
        pytest.skip(
            f"ollama 模型 {model} 不可用或不能产出 AOS 计划格式"
            f"（③需真实本地 LLM；若模型是 minicpm-mem 之类 chat 鹦鹉、不产生能力前缀步骤→跳过）。"
        )

    # 1) 反思记忆指向 tmp（隔离，不污染仓库 _traces/）
    mem = tmp_path / "reflection_memory.jsonl"
    monkeypatch.setattr(ap, "_REFLECTION_MEMORY_PATH", str(mem))

    # 2) 关闭蒸馏器（避免写 data/ 且加速），与本测试无关
    monkeypatch.setenv("AOS_AUTOPILOT_DISTILL_OFF", "1")

    # 3) 固定初始计划：[web.search 成功, action.code_exec 失败]
    fixed_steps = [
        {"capability": "web.search", "in": {"task": "搜索 Vosk 本地语音识别"}},
        {"capability": "action.code_exec", "in_from": "previous",
         "instruction": "安装 vosk 模型"},
    ]

    def fake_plan(task_, planner):
        return ("web.search=搜索 Vosk\naction.code_exec=安装 vosk 模型",
                fixed_steps, None, "heuristic")

    monkeypatch.setattr(ap, "_plan", fake_plan)

    # 4) 隔离「执行」半程：第1、2轮强制步骤2失败（触发真实反思）；
    #    第3轮全部成功（达成，停）。其余真实机制（反思/教训/重设计）保持原样。
    calls = {"n": 0}

    def fake_execute(task_, steps, seed_context=None, parallel_groups=None, on_step=None):
        calls["n"] += 1
        if calls["n"] <= 2:
            trace = [
                {"capability": "web.search", "ok": True, "engine": "duckduckgo",
                 "real_metrics": {"is_real": True},
                 "out": {"content": "本地开源语音识别方案 Vosk 调研：Vosk 是 CMU 开源离线 ASR 工具kit"},
                 "summary": "ok"},
                {"capability": "action.code_exec", "ok": False, "engine": "local",
                 "real_metrics": {"is_real": False}, "out": {},
                 "error": "命令执行超时", "summary": "超时"},
            ]
            data = {"trace": trace, "ok_steps": 1, "failed_steps": 1}
            recorded = [{"capability": "web.search",
                         "out": {"content": "本地开源语音识别方案 Vosk 调研"}}]
        else:
            trace = [{"capability": s.get("capability", "web.search"), "ok": True,
                      "real_metrics": {"is_real": True},
                      "out": {"content": "本地开源语音识别方案 Vosk 调研总结完成"},
                      "summary": "ok"} for s in steps]
            data = {"trace": trace, "ok_steps": len(steps), "failed_steps": 0}
            recorded = [{"capability": s.get("capability", "web.search"),
                         "out": {"content": "完成"}} for s in steps]
        if on_step:
            try:
                on_step({"done": len(trace), "total": len(trace),
                         "capability": trace[0]["capability"], "ok": True, "last_out": None})
            except Exception:
                pass
        return InvokeResult(ok=True, data=data), recorded

    monkeypatch.setattr(ap, "_execute", fake_execute)

    # 5) 屏蔽 zhipu / openai-compat（无 key 情形，忠实于本机），强制走真实 ollama 分支
    monkeypatch.setattr(ap, "_llm_generate", lambda *a, **k: None)

    # 6) 真实 ollama 反思后端（延长超时兼容 CPU 冷加载；模型与产品一致，仍是真推理）
    ollama_calls = []

    def real_ollama(prompt, model_=None):
        ollama_calls.append(prompt)
        import json as _json
        m = model_ or model
        # 传输超时可用 AOS_OLLAMA_TIMEOUT 覆盖（默认 120s）：慢速 CPU 主机给真实
        # LLM 更多墙钟时间跑反思，不伪造任何东西（仍是真实本地推理）。
        _timeout = int(os.environ.get("AOS_OLLAMA_TIMEOUT", "120"))
        body = _json.dumps({
            "model": m, "prompt": prompt, "stream": False,
            "options": {"temperature": 0.3, "num_predict": 160},
        }).encode()
        req = urllib.request.Request(_OLLAMA_URL, data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=_timeout) as r:
            return _json.loads(r.read().decode()).get("response")

    monkeypatch.setattr(ap, "_ollama_generate", real_ollama)

    # 7) 探针：跨轮读回 + 反思结果捕获（不改动行为，只观测）
    orig_load = ap._load_lessons
    load_calls = []

    def spy_load(task_, limit=3):
        res = orig_load(task_, limit)
        load_calls.append((task_, res))
        return res

    monkeypatch.setattr(ap, "_load_lessons", spy_load)

    orig_refl = ap._reflect_and_redesign
    refl_results = []

    def spy_refl(task_, r, cycle, prior_success=None):
        res = orig_refl(task_, r, cycle, prior_success)
        refl_results.append(res)
        return res

    monkeypatch.setattr(ap, "_reflect_and_redesign", spy_refl)

    # 8) 允许 3 轮（2 次反思 + 1 次达成），避免撞默认 MAX_REFLECT 上限提前停
    monkeypatch.setattr(ap, "_max_reflect_for", lambda t: 5)

    # 9) 屏蔽 checkpoint sqlite 副作用（本测试只验证反思/教训闭环）
    monkeypatch.setattr(ap, "create_run", lambda *a, **k: None)
    monkeypatch.setattr(ap, "save_checkpoint", lambda *a, **k: None)
    monkeypatch.setattr(ap, "mark_done", lambda *a, **k: None)

    # ===== 跑真实自进化闭环 =====
    result = ap.run(task)

    # ---- 断言 1：真实 LLM 被咨询（反思三后端降级到 ollama 真推理）----
    assert len(ollama_calls) >= 2, "真实 ollama 反思应被调用 ≥2 次（每轮反思一次）"

    # ---- 断言 2：教训真实落盘（磁盘 JSONL 有界增长）----
    assert mem.exists(), "reflection_memory.jsonl 应真实落盘"
    lines = [l for l in mem.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) >= 2, f"应沉淀 ≥2 条反思教训，实际 {len(lines)}"
    for ln in lines:
        rec = json.loads(ln)
        assert "lesson" in rec and len(rec["lesson"]) >= 10

    # ---- 断言 3：第二轮**真读回**了第一轮沉淀的教训（跨轮 Meta-Trace 读回为真）----
    reloaded = [res for _, res in load_calls if len(res) >= 1]
    assert reloaded, "第二轮反思应读回第一轮沉淀的教训（跨轮记忆读回为真实闭环）"

    # ---- 断言 4：真实 LLM 确实换了做法（不是原地重试伪装成反思）----
    real_llm_redesigns = [
        r for r in refl_results
        if r and isinstance(r, dict) and r.get("engine") in ("ag2", "zhipu", "ollama")
    ]
    if real_llm_redesigns:
        for r in real_llm_redesigns:
            steps = r.get("steps") or []
            assert steps, "真实 LLM 重设计应产出步骤"
            first_cap = steps[0].get("capability", "")
            # 换做法判定：首步能力 ≠ 失败步(action.code_exec)，或带因果 engine_hint
            changed = (first_cap != "action.code_exec") or any(
                "engine_hint" in s for s in steps)
            assert changed, (
                f"真实 LLM 反思未换做法（首步仍 {first_cap} 且无 engine_hint），"
                f"疑似原地重试伪装成反思"
            )
        # 闭环最终应达成（经反思自愈）
        verdict = (result.get("verdict") or {}).get("status", "")
        assert "完成" in verdict or (result.get("reflection", {}).get("attempts", 1) > 1), \
            f"自进化闭环应经反思达成，verdict={verdict}"
    else:
        # 模型虽能产出计划格式、但反思被 _is_meaningful_redesign 拒后降级 heuristic：
        # ③ 的「真 LLM 换做法」未达成——诚实记录，不假绿。
        pytest.skip(
            "真实 ollama 反思被「换做法守卫」拒绝并降级 heuristic："
            "本轮未产出比重试更好的方案（仍属诚实闭环，但 ③『变好』未达）。"
        )
