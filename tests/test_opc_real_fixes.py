"""OPC 真机验证暴露的三个 bug 修复守护测试（mock 模式，无真实 LLM，快速全绿）。

bug 1: verdict 文本型完成判定——inference.llm 产长文本+其他步空转 → 应判完成（非部分完成）
bug 2: _looks_like_markdown_text——Markdown 标题文本不被当 code 丢给 sandbox
bug 3: heuristic_plan 同能力合并——研报类任务被逗号过度拆分时合并为单步
"""

import pytest

import kernel.autopilot as ap
from kernel.plugins.plan_bridge import heuristic_plan


# ---------------------------------------------------------------------------
# bug 1: verdict 文本型完成判定
# ---------------------------------------------------------------------------
def test_verdict_text_complete_with_empty_step():
    """inference.llm 产长文本(>=200字) + 第2步空转 → verdict 应判完成，不触发反思。"""
    long_text = "# 研报标题\n" + ("这是研报内容。" * 30)  # >> 200 字
    trace = [
        {
            "capability": "inference.llm", "ok": True,
            "real_metrics": {"is_real": True, "char_count": len(long_text), "refusal": False},
            "out": {"content": long_text},
        },
        {
            "capability": "inference.llm", "ok": False,
            "real_metrics": {"is_real": False, "char_count": 0, "refusal": True},
        },
    ]
    data = {"ok_steps": 1, "failed_steps": 1}
    confidence = {"level": "medium", "label": "🟡 中置信"}
    v = ap._verdict("调研 AI Agent 框架", data, trace, confidence)
    assert v["status"].startswith("完成"), f"应判完成，实际: {v['status']}"
    assert "空转" in v["reason"]


def test_verdict_short_text_still_partial():
    """inference.llm 产出过短(<200字) + 有失败步 → 仍判部分完成（不误升完成）。"""
    trace = [
        {
            "capability": "inference.llm", "ok": True,
            "real_metrics": {"is_real": True, "char_count": 50, "refusal": False},
            "out": {"content": "短回答"},
        },
        {"capability": "inference.llm", "ok": False, "real_metrics": {"is_real": False}},
    ]
    data = {"ok_steps": 1, "failed_steps": 1}
    v = ap._verdict("任务", data, trace, {"level": "low"})
    assert "部分完成" in v["status"], f"短文本应判部分完成，实际: {v['status']}"


# ---------------------------------------------------------------------------
# bug 2: _looks_like_markdown_text 防御
# ---------------------------------------------------------------------------
def test_looks_like_markdown_text_title():
    """以 Markdown 标题开头的纯文档 → 判为非代码文本。"""
    assert ap._looks_like_markdown_text("# 2026年AI Agent框架研报\n## 一、架构差异\nLangGraph 是...")
    assert ap._looks_like_markdown_text("## 章节标题\n内容段落")


def test_not_markdown_when_has_code_syntax():
    """Markdown 标题但含代码语法 → 不拦（可能是带注释的代码）。"""
    assert not ap._looks_like_markdown_text("# 注释\nprint('hello')")
    assert not ap._looks_like_markdown_text("# 安装\npip install requests")


def test_not_markdown_plain_text():
    """非标题开头的纯文本 → 不拦（交给其他闸门）。"""
    assert not ap._looks_like_markdown_text("这是一段普通文本，没有标题")
    assert not ap._looks_like_markdown_text("winget install ffmpeg")


def test_extract_cmd_rejects_markdown_report():
    """反思产的 code_exec 步若 in 字段是研报 Markdown → _extract_cmd_from_text 返回空。"""
    report = (
        "# 2026年主流开源AI Agent框架深度研报\n\n"
        "## 一、核心架构与定位差异\n\n"
        "随着2026年AI Agent技术从概念验证全面转向工程化落地，"
        "LangGraph、AutoGen、CrewAI与Agno四大框架在底层逻辑上呈现出显著的分化。"
    )
    cmd = ap._extract_cmd_from_text(report)
    assert cmd == "", f"研报 Markdown 不应被当命令，实际: {cmd[:50]}"


# ---------------------------------------------------------------------------
# bug 3: heuristic_plan 同能力合并
# ---------------------------------------------------------------------------
def test_heuristic_plan_merges_same_cap_parts():
    """研报类任务被逗号拆成多段但全是 inference.llm → 合并为单步执行完整任务。"""
    task = "针对以下一人公司业务做市场/竞品/选题研报，输出结构化要点：调研 AI Agent 框架"
    steps = heuristic_plan(task, ap._CAPS)
    # 应合并为单步（不拆成"针对...研报" + "输出...要点"）
    assert len(steps) == 1, f"同能力多段应合并，实际 {len(steps)} 步"
    assert steps[0]["capability"] == "inference.llm"
    # in.task 应含完整业务描述（含"调研 AI Agent 框架"），不是只取前半段
    in_task = steps[0].get("in", {}).get("task", "")
    assert "调研 AI Agent" in in_task, f"in.task 应含完整业务描述，实际: {in_task[:80]}"


def test_heuristic_plan_keeps_multi_search():
    """两个不同搜索主题仍拆成多步（不误合并 web.search）。"""
    steps = heuristic_plan("搜索 Python 然后搜索 Rust", ap._CAPS)
    # "然后"是顺序连词，应拆成多步
    assert len(steps) >= 2, "不同搜索主题应保持多步"
