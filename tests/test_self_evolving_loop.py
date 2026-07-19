"""诚实自进化闭环离线验证（任务270 / 白皮书 3.1）。

验证核心差异化链路：失败 → 反思重设计（诚实 heuristic 兜底）→ Meta-Trace 教训沉淀
→ 相似任务跨任务注入。全程不依赖外部 LLM / API key，可在 CI 离线真跑。
"""
import json

import pytest

from kernel import autopilot as ap


@pytest.fixture
def offline_reflect(monkeypatch, tmp_path):
    """强制走诚实 heuristic 兜底（无 ag2 / 无 ollama），并把反思记忆指向 tmp。"""
    def _raise(*a, **k):
        raise RuntimeError("offline: no ag2 / ollama")
    monkeypatch.setattr(ap, "_get_ag2", _raise)
    monkeypatch.setattr(ap, "_ollama_generate", _raise)
    mem = tmp_path / "reflection_memory.jsonl"
    monkeypatch.setattr(ap, "_REFLECTION_MEMORY_PATH", str(mem))
    return mem


def _failed_trace(cap="web.search", summary="0 results"):
    return {"execution": {"trace": [
        {"capability": cap, "ok": False, "summary": summary,
         "real_metrics": {"is_real": False}},
    ]}}


def test_reflect_produces_redesign_and_saves_lesson(offline_reflect):
    mem = offline_reflect
    r = _failed_trace()
    out = ap._reflect_and_redesign("搜索某不存在的关键词并生成报告", r, 1)
    assert out is not None
    assert out["engine"] == "heuristic"
    assert isinstance(out["steps"], list) and out["steps"]
    # 教训沉淀到磁盘（失败即训练数据真实落盘）
    assert mem.exists()
    lines = [l for l in mem.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert "lesson" in rec and len(rec["lesson"]) >= 10
    assert rec["failed_cap"] == "web.search"


def test_lesson_injected_into_similar_task(offline_reflect):
    mem = offline_reflect
    # 第一次：沉淀教训
    ap._reflect_and_redesign("搜索某不存在的关键词并生成报告", _failed_trace(), 1)
    # 第二次：相似任务应注入历史教训（Meta-Trace 跨任务）
    lessons = ap._load_lessons("搜索另一个不存在的关键词写总结")
    assert lessons, "相似任务的 Meta-Trace 教训应被注入"
    assert any("web.search" in L.get("failed_cap", "") for L in lessons)


def test_reflection_memory_bounded_rotation(offline_reflect):
    mem = offline_reflect
    for i in range(ap._REFLECTION_MEMORY_MAX + 50):
        ap._save_lesson(
            f"task-{i}", "web.search", f"err-{i}",
            f"已知失败做法{i}，应在第{i}步规避重做已成功步。",
        )
    lines = [l for l in mem.read_text(encoding="utf-8").splitlines() if l.strip()]
    # 轮转生效：没有无限增长到 250，而是有界保留（删最旧 20% 后接近上限）
    assert len(lines) < 250
    assert ap._REFLECTION_MEMORY_MAX - 40 <= len(lines) <= ap._REFLECTION_MEMORY_MAX + 10
