"""ContextManager 单元测试（Task 2: Context Engineering）。

覆盖：
- add_step / add_message：添加条目，自动判定优先级
- _upgrade_recent：最近 N 步升级 HIGH，滑出后降回 NORMAL
- compact_if_needed：超阈值时压缩低优先级条目
- get_context_text / get_entries / stats：查询接口
- persist / load：断点续跑
- 全局会话管理：get_session / list_sessions / delete_session
"""
import os
import tempfile

import pytest

_tmp = tempfile.mkdtemp(prefix="aos_test_ctx_")
os.environ["AOS_CONTEXT_DIR"] = _tmp

# 预先禁用 tiktoken（避免首次调用时尝试下载 BPE 词表导致网络超时）
# 走 cost_tracker 的字符估算回退路径
import kernel.pulse.cost_tracker as _ct  # noqa: E402
_ct._TIKTOKEN_ENC = False

from kernel.context.context_manager import (  # noqa: E402
    PRIORITY_CRITICAL,
    PRIORITY_HIGH,
    PRIORITY_LOW,
    PRIORITY_NORMAL,
    ContextManager,
    delete_session,
    get_session,
    list_sessions,
    reset_sessions_for_test,
)


@pytest.fixture(autouse=True)
def _reset_global_sessions():
    """每个测试前清空全局会话注册表。"""
    reset_sessions_for_test()
    yield
    reset_sessions_for_test()


def _step_result(*, ok=True, error="", name="step1", cap="web.search",
                  output=None, step_index=0):
    return {
        "step_index": step_index,
        "step_name": name,
        "capability": cap,
        "ok": ok,
        "error": error,
        "output": output if output is not None else {"content": "hello"},
    }


# ── add_step ──

def test_add_step_failed_marks_critical():
    """失败的步骤应被标记为 CRITICAL 优先级。"""
    cm = ContextManager(max_tokens=8000, auto_compact=False)
    cm.add_step(_step_result(ok=False, error="timeout"))

    entries = cm.get_entries()
    assert len(entries) == 1
    assert entries[0]["priority"] == PRIORITY_CRITICAL
    assert entries[0]["ok"] is False
    assert entries[0]["error"] == "timeout"


def test_add_step_success_marks_normal_or_high():
    """成功的步骤应被标记为 HIGH（在最近 N 步内）。"""
    cm = ContextManager(max_tokens=8000, preserve_recent=3, auto_compact=False)
    cm.add_step(_step_result(name="s1"))

    entries = cm.get_entries()
    assert len(entries) == 1
    # 第 1 步在 preserve_recent=3 内，应是 HIGH
    assert entries[0]["priority"] == PRIORITY_HIGH


def test_add_step_token_count_calculated():
    """add_step 应自动计算 token_count。"""
    cm = ContextManager(max_tokens=8000, auto_compact=False)
    cm.add_step(_step_result(output={"content": "hello world"}))

    entries = cm.get_entries()
    assert entries[0]["token_count"] > 0


def test_add_step_preserve_recent_window_slides():
    """preserve_recent 窗口滑动后，旧 HIGH 应降回 NORMAL。"""
    cm = ContextManager(max_tokens=8000, preserve_recent=2, auto_compact=False)
    # 加 3 步：s0, s1, s2
    cm.add_step(_step_result(name="s0", step_index=0))
    cm.add_step(_step_result(name="s1", step_index=1))
    cm.add_step(_step_result(name="s2", step_index=2))

    entries = cm.get_entries()
    # 最近 2 步（s1, s2）应是 HIGH
    by_name = {e["step_name"]: e["priority"] for e in entries}
    assert by_name["s1"] == PRIORITY_HIGH
    assert by_name["s2"] == PRIORITY_HIGH
    # s0 已滑出窗口，应降回 NORMAL
    assert by_name["s0"] == PRIORITY_NORMAL


def test_add_step_critical_never_downgraded():
    """CRITICAL 步骤滑出窗口后不应降级（永远保留）。"""
    cm = ContextManager(max_tokens=8000, preserve_recent=1, auto_compact=False)
    cm.add_step(_step_result(name="fail_step", ok=False, error="err", step_index=0))
    cm.add_step(_step_result(name="later", step_index=1))
    cm.add_step(_step_result(name="latest", step_index=2))

    by_name = {e["step_name"]: e["priority"] for e in cm.get_entries()}
    # fail_step 已不在最近 1 步内，但 CRITICAL 不应降级
    assert by_name["fail_step"] == PRIORITY_CRITICAL


# ── add_message ──

def test_add_message_creates_entry():
    """add_message 应创建一个对话消息条目。"""
    cm = ContextManager(max_tokens=8000, auto_compact=False)
    cm.add_message("user", "hello")
    cm.add_message("assistant", "hi there")

    entries = cm.get_entries()
    assert len(entries) == 2
    assert entries[0]["step_name"] == "message:user"
    assert entries[1]["step_name"] == "message:assistant"
    assert entries[0]["content"] == "hello"


# ── compact_if_needed ──

def test_compact_not_needed_when_under_threshold():
    """未超阈值时不应压缩。"""
    cm = ContextManager(max_tokens=100000, auto_compact=False)
    cm.add_step(_step_result(output={"content": "small content"}))

    result = cm.compact_if_needed()
    assert result["compacted"] is False
    assert "未超阈值" in result["reason"]


def test_compact_triggers_when_over_threshold():
    """超阈值时应压缩低优先级条目。

    摘要每步保留 200 字符 snippet + 元数据，所以原内容必须 > 200 字符
    才能保证摘要后 token 减少。
    """
    cm = ContextManager(max_tokens=50, preserve_recent=1, auto_compact=False)
    # 加 4 步，每步内容 500+ 字符（确保摘要 200 字符 snippet 一定更小）
    for i in range(4):
        cm.add_step(_step_result(
            name=f"s{i}",
            step_index=i,
            output={"content": f"step {i} " + "x" * 500},
        ))

    before = cm.total_tokens()
    result = cm.compact_if_needed()
    after = cm.total_tokens()

    assert result["compacted"] is True
    assert result["removed_count"] > 0
    # 摘要应让总 token 减少（每步原 500+ 字符 → 摘要 200 字符 snippet）
    assert after < before
    # 应有摘要条目
    summaries = [e for e in cm.get_entries() if e["compacted"]]
    assert len(summaries) >= 1


def test_compact_preserves_critical_entries():
    """压缩时不应删除 CRITICAL 条目。"""
    cm = ContextManager(max_tokens=30, preserve_recent=1, auto_compact=False)
    # 失败步骤（CRITICAL）
    cm.add_step(_step_result(name="fail", ok=False, error="err", step_index=0,
                              output={"content": "failure content"}))
    # 多个成功步骤（NORMAL）触发压缩
    for i in range(1, 5):
        cm.add_step(_step_result(
            name=f"s{i}", step_index=i,
            output={"content": f"content {i} " * 10},
        ))

    cm.compact_if_needed()
    # CRITICAL 条目应保留
    by_name = {e["step_name"]: e for e in cm.get_entries()}
    assert "fail" in by_name
    assert by_name["fail"]["priority"] == PRIORITY_CRITICAL


def test_compact_preserves_recent_entries():
    """压缩时应保留最近 N 步。"""
    cm = ContextManager(max_tokens=30, preserve_recent=2, auto_compact=False)
    for i in range(5):
        cm.add_step(_step_result(
            name=f"s{i}", step_index=i,
            output={"content": f"content {i} " * 10},
        ))

    cm.compact_if_needed()
    entries = cm.get_entries()
    # 最后 2 步应保留为独立条目（不被压缩）
    names = [e["step_name"] for e in entries]
    assert "s4" in names
    assert "s3" in names


# ── get_context_text ──

def test_get_context_text_formats_entries():
    """get_context_text 应把条目格式化成可读文本。"""
    cm = ContextManager(max_tokens=8000, auto_compact=False)
    cm.add_step(_step_result(name="搜索", cap="web.search",
                              output={"content": "搜索结果"}))
    cm.add_step(_step_result(name="失败步", ok=False, error="timeout",
                              output={"content": "部分结果"}))

    text = cm.get_context_text()
    assert "搜索" in text
    assert "搜索结果" in text
    assert "失败步" in text
    assert "timeout" in text


def test_get_context_text_max_entries():
    """max_entries 应限制返回条目数（取最新的 N 条）。"""
    cm = ContextManager(max_tokens=8000, auto_compact=False)
    for i in range(5):
        cm.add_step(_step_result(name=f"s{i}", step_index=i,
                                  output={"content": f"content{i}"}))

    text = cm.get_context_text(max_entries=2)
    # 应只包含最近 2 步
    assert "content4" in text
    assert "content3" in text
    assert "content0" not in text


# ── get_entries ──

def test_get_entries_filter_by_priority():
    """get_entries 按 priority 过滤。"""
    cm = ContextManager(max_tokens=8000, preserve_recent=1, auto_compact=False)
    cm.add_step(_step_result(name="fail", ok=False, error="err"))
    cm.add_step(_step_result(name="ok1"))
    cm.add_step(_step_result(name="ok2"))

    critical_only = cm.get_entries(priority=PRIORITY_CRITICAL)
    assert len(critical_only) == 1
    assert critical_only[0]["step_name"] == "fail"


# ── stats ──

def test_stats_returns_summary():
    """stats 应返回上下文统计摘要。"""
    cm = ContextManager(max_tokens=1000, auto_compact=False)
    cm.add_step(_step_result(name="s1", output={"content": "hello"}))

    stats = cm.stats()
    assert stats["total_entries"] == 1
    assert stats["total_tokens"] > 0
    assert stats["max_tokens"] == 1000
    assert stats["token_usage_pct"] > 0
    assert "by_priority" in stats
    assert stats["session_id"] != ""


# ── persist / load ──

def test_persist_and_load_roundtrip():
    """persist 后 load 应恢复所有 entries。"""
    cm = ContextManager(session_id=f"rt_{os.urandom(4).hex()}",
                        max_tokens=8000, auto_compact=False)
    cm.add_step(_step_result(name="s1", output={"content": "hello"}))
    cm.add_step(_step_result(name="s2", output={"content": "world"}))

    path = cm.persist()
    assert path != ""
    assert os.path.exists(path)

    loaded = ContextManager.load(cm.session_id)
    assert loaded is not None
    assert loaded.session_id == cm.session_id
    assert len(loaded.get_entries()) == 2
    # 内容应一致
    names = [e["step_name"] for e in loaded.get_entries()]
    assert "s1" in names
    assert "s2" in names


def test_load_nonexistent_returns_none():
    """load 不存在的 session 应返回 None。"""
    assert ContextManager.load("never_existed_session") is None


# ── clear ──

def test_clear_empties_entries():
    """clear 应清空所有 entries。"""
    cm = ContextManager(max_tokens=8000, auto_compact=False)
    cm.add_step(_step_result())
    assert len(cm.get_entries()) == 1

    cm.clear()
    assert len(cm.get_entries()) == 0
    assert cm.total_tokens() == 0


# ── 全局会话管理 ──

def test_get_session_singleton_per_id():
    """同一 session_id 应返回同一实例。"""
    sid = "test_session_singleton"
    cm1 = get_session(sid, max_tokens=5000)
    cm2 = get_session(sid, max_tokens=5000)
    assert cm1 is cm2


def test_get_session_different_ids_create_different_instances():
    """不同 session_id 应创建不同实例。"""
    cm1 = get_session("session_a")
    cm2 = get_session("session_b")
    assert cm1 is not cm2
    assert cm1.session_id != cm2.session_id


def test_list_sessions_returns_all():
    """list_sessions 应返回所有活跃会话。"""
    get_session("list_a")
    get_session("list_b")

    sessions = list_sessions()
    ids = [s["session_id"] for s in sessions]
    assert "list_a" in ids
    assert "list_b" in ids


def test_delete_session_removes_from_memory():
    """delete_session 应从内存注册表移除。"""
    sid = "to_delete"
    get_session(sid)
    assert any(s["session_id"] == sid for s in list_sessions())

    ok = delete_session(sid)
    assert ok is True
    assert not any(s["session_id"] == sid for s in list_sessions())


def test_delete_session_removes_persisted_file():
    """delete_session 应同时删除磁盘持久化文件。"""
    sid = "to_delete_file"
    cm = get_session(sid)
    cm.add_step(_step_result())
    cm.persist()

    # 文件应存在
    from kernel.context.context_manager import _session_path
    assert os.path.exists(_session_path(sid))

    delete_session(sid)
    # 文件应被删除
    assert not os.path.exists(_session_path(sid))


# ── _extract_text ──

def test_extract_text_from_dict_with_content():
    """output dict 含 content 字段时应提取出来。"""
    cm = ContextManager(auto_compact=False)
    text = cm._extract_text({
        "step_name": "搜索",
        "capability": "web.search",
        "output": {"content": "搜索结果文本"},
    })
    assert "搜索结果文本" in text
    assert "搜索" in text  # step_name 也应包含


def test_extract_text_from_string_output():
    """output 是字符串时应直接使用。"""
    cm = ContextManager(auto_compact=False)
    text = cm._extract_text({
        "step_name": "s",
        "output": "直接字符串输出",
    })
    assert "直接字符串输出" in text


def test_extract_text_includes_error():
    """有 error 时应包含在文本中。"""
    cm = ContextManager(auto_compact=False)
    text = cm._extract_text({
        "step_name": "s",
        "error": "连接超时",
        "output": {},
    })
    assert "连接超时" in text
