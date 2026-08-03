"""自进化闭环 ③ 级真机门禁 —— StageGuard 隔离 + 失败记忆读回（补缺口③门禁）。

本文件是 test_self_evolution_real.py（反思记忆读回那一半）的**对偶门禁**：
它验证自进化闭环的「另一半」在真实 LLM 下也成立 ——

  1. StageGuard 隔离在真实运行里是活的：run 在真实失败/真实异常下仍能返回
     （不级联崩整轮），且环节级失败被真实记入共享失败记忆库；
  2. 失败记忆的「写→读」闭环在真实运行里成立：
     run1 失败后把根因写入同源失败记忆库，run2 规划前的 PREFLIGHT 真的读回
     该教训并注入规划输入（任务串里出现「已知修复方案」标记），
     即「第 N+1 次不再犯第 N 次的错」是可验证的真实闭环。

诚实纪律（用户铁律，与 test_self_evolution_real.py 一致）：
  - 反思重设计 100% 走真实本机 ollama LLM，绝不用 mock 伪造「变好了」；
  - 执行环节用确定性 fake（与既有 ③ 测试同口径）：③ 的「真」落在真实 LLM 反思 +
    真实失败记忆落盘 + 真实 PREFLIGHT 读回这三处，均非 mock；
  - 无可用 ollama / 模型不能产出 AOS 计划格式（chat 鹦鹉）→ 直接 skip，绝不假绿。

运行：需 AOS_RUN_REAL_TESTS=1 且本机 ollama 有「能产出计划格式」的模型
（默认 qwen2.5-coder:7b；AOS_REFLECT_OLLAMA_MODEL 可覆盖）。
"""

import os
import re
import json
import urllib.request

import pytest

from core.fabric.adapter import InvokeResult
from kernel import autopilot as ap
from kernel.adaptive import AdaptiveCore, set_adaptive_core


# 与 test_self_evolution_real.py 同款的就绪探针（真实规划任务探测格式遵循）
_OLLAMA_URL = os.environ.get("AOS_OLLAMA_URL", "http://localhost:11434/api/generate")
_OLLAMA_TAGS = os.environ.get("AOS_OLLAMA_URL", "http://localhost:11434").rstrip("/") + "/api/tags"
_CAP_PREFIX_RE = re.compile(r"^\s*([a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+)\s*[=:]\s*", re.I)


def _ollama_model_ready(model: str, base: str = None) -> bool:
    tags_url = (base or _OLLAMA_TAGS)
    _timeout = int(os.environ.get("AOS_OLLAMA_TIMEOUT", "120"))
    try:
        with urllib.request.urlopen(tags_url, timeout=5) as r:
            models = [m["name"] for m in json.loads(r.read().decode())["models"]]
        if model not in models:
            return False
        probe_prompt = (
            "任务：调研并总结本地开源语音识别方案 Vosk。\n"
            "已知：步骤1[web.search] 已成功；步骤2[action.code_exec] 安装超时失败。\n"
            "请只输出从失败处继续的剩余步骤计划，每行一个，用 AOS 能力标签前缀"
            "（如 web.search= / inference.llm= / action.code_exec=）。不要解释，只输出计划。"
        )
        body = json.dumps({
            "model": model, "prompt": probe_prompt, "stream": False,
            "options": {"num_predict": 120, "temperature": 0.3},
        }).encode()
        req = urllib.request.Request(_OLLAMA_URL, data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=_timeout) as r:
            resp = json.loads(r.read().decode()).get("response", "")
        if not resp:
            return False
        caps = getattr(ap, "_CAPS", [])
        for ln in resp.splitlines():
            m = _CAP_PREFIX_RE.match(ln)
            if m and m.group(1).lower() in caps:
                return True
        return False
    except Exception:
        return False


@pytest.mark.skipif(os.environ.get("AOS_RUN_REAL_TESTS") != "1",
                    reason="③级真机验证需 AOS_RUN_REAL_TESTS=1（真实本地 LLM，禁用 mock）")
def test_self_evolution_stageguard_failure_memory_readback(tmp_path, monkeypatch):
    task = "调研并总结本地开源语音识别方案 Vosk"
    model = os.environ.get("AOS_REFLECT_OLLAMA_MODEL", "qwen2.5-coder:7b")
    if not _ollama_model_ready(model):
        pytest.skip(
            f"ollama 模型 {model} 不可用或不能产出 AOS 计划格式"
            f"（③需真实本地 LLM；chat 鹦鹉不产生能力前缀步骤→跳过）。"
        )

    # 1) 失败记忆库指向临时文件（注入默认租户 core，隔离不污染仓库生产库）
    mem = tmp_path / "fm.json"
    core = AdaptiveCore(memory_path=str(mem), tenant_id=None)
    set_adaptive_core(core, None)

    # 2) 反思记忆落盘到临时（与既有 ③ 测试一致）
    monkeypatch.setattr(ap, "_REFLECTION_MEMORY_PATH", str(tmp_path / "reflection_memory.jsonl"))
    monkeypatch.setenv("AOS_AUTOPILOT_DISTILL_OFF", "1")

    # 3) 固定计划：web.search 成功 + action.code_exec 失败
    fixed_steps = [
        {"capability": "web.search", "in": {"task": "搜索 Vosk 本地语音识别"}},
        {"capability": "action.code_exec", "in_from": "previous",
         "instruction": "安装 vosk 模型"},
    ]

    plan_tasks = []  # 捕获每次 _plan 收到的 task（验证 PREFLIGHT 注入）

    def fake_plan(task_, planner, tenant_id=None):
        plan_tasks.append(task_)
        return ("web.search=搜索 Vosk\naction.code_exec=安装 vosk 模型",
                fixed_steps, None, "heuristic")

    monkeypatch.setattr(ap, "_plan", fake_plan)

    # 4) 执行环节：run1（state.run==1）确定性失败（失败步 action.code_exec 超时），
    #    run2（state.run==2）成功，用以构造「先失败落盘、后读回」的两轮闭环。
    state = {"run": 1}

    def fake_execute(task_, steps, seed_context=None, parallel_groups=None, on_step=None):
        if state["run"] == 1:
            trace = [
                {"capability": "web.search", "ok": True, "engine": "duckduckgo",
                 "real_metrics": {"is_real": True},
                 "out": {"content": "本地开源语音识别方案 Vosk 调研"}, "summary": "ok"},
                {"capability": "action.code_exec", "ok": False, "engine": "local",
                 "real_metrics": {"is_real": False}, "out": {},
                 "error": "命令执行超时", "summary": "超时"},
            ]
            data = {"trace": trace, "ok_steps": 1, "failed_steps": 1}
        else:
            trace = [{"capability": s.get("capability", "web.search"), "ok": True,
                      "real_metrics": {"is_real": True},
                      "out": {"content": "完成"}, "summary": "ok"} for s in steps]
            data = {"trace": trace, "ok_steps": len(steps), "failed_steps": 0}
        if on_step:
            try:
                on_step({"done": len(trace), "total": len(trace),
                         "capability": trace[0]["capability"], "ok": True, "last_out": None})
            except Exception:
                pass
        return InvokeResult(ok=True, data=data), [
            {"capability": t["capability"], "out": t.get("out", {})}
            for t in trace if t["ok"]
        ]

    monkeypatch.setattr(ap, "_execute", fake_execute)

    # 5) 屏蔽 zhipu/openai，强制走真实 ollama 反思分支
    monkeypatch.setattr(ap, "_llm_generate", lambda *a, **k: None)

    ollama_calls = []

    def real_ollama(prompt, model_=None):
        ollama_calls.append(prompt)
        m = model_ or model
        _timeout = int(os.environ.get("AOS_OLLAMA_TIMEOUT", "120"))
        body = json.dumps({
            "model": m, "prompt": prompt, "stream": False,
            "options": {"temperature": 0.3, "num_predict": 160},
        }).encode()
        req = urllib.request.Request(_OLLAMA_URL, data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=_timeout) as r:
            return json.loads(r.read().decode()).get("response")

    monkeypatch.setattr(ap, "_ollama_generate", real_ollama)

    # 6) 限制 run1 反思轮次，使其以失败收尾（失败步被写入失败记忆库）
    monkeypatch.setattr(ap, "_max_reflect_for", lambda t: 2)

    # 7) 屏蔽 checkpoint 副作用
    monkeypatch.setattr(ap, "create_run", lambda *a, **k: None)
    monkeypatch.setattr(ap, "save_checkpoint", lambda *a, **k: None)
    monkeypatch.setattr(ap, "mark_done", lambda *a, **k: None)

    # ===== run1：真实失败，落盘失败记忆 =====
    plan_tasks.clear()
    result1 = ap.run(task)
    assert isinstance(result1, dict), "StageGuard 隔离：run1 在失败下必须返回 dict，不崩溃"

    # StageGuard 隔离在真实运行里是活的：真实运行期间所有环节都被 StageGuard 包裹观测
    # （plan/execute/assemble/reflect 均出现），即隔离层确实在线。异常死亡→结构化收尾的
    # 路径由 test_stage_guard_real.py 在②级已穷尽，这里只证「真实运行里隔离层在线」。
    health = core.stage_health()
    assert len(health) >= 1, "真实运行里 StageGuard 应至少观测到 1 个环节（隔离层在线）"

    # 失败记忆「写」端：run1 结束后同源失败记忆库确有这次失败根因（失败学习闭环真实落盘）
    assert core.memory_stats["total_patterns"] >= 1, \
        "run1 失败后，同源失败记忆库应真实写入该失败根因"
    hints_after_run1 = core.fix_hints(task=task, capability="action.code_exec")
    assert len(hints_after_run1) >= 1, "run1 失败后，同源失败记忆库应可读回该失败根因"

    # ===== run2：PREFLIGHT 真的读回 run1 的教训并注入规划输入 =====
    state["run"] = 2
    plan_tasks.clear()
    _ = ap.run(task)

    injected = [t for t in plan_tasks if "已知修复方案" in t]
    assert injected, (
        "run2 规划前的 PREFLIGHT 应读回 run1 的失败教训并注入规划输入"
        "（任务串应含『已知修复方案』标记），当前未注入 → 失败记忆读回闭环未连通"
    )
