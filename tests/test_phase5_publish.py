"""验证 workflow_engine.phase5_publish 不再伪造成功（双轨债 ⑦）。

旧版对所有平台返回 status=pending（"API 对接后续迭代"），掩盖了未实现。
诚实版：无产物→skipped，无发布器→unavailable，绝不假装已发布。
"""
import pytest

from kernel.workflow_engine import WorkflowEngine


def _make_engine():
    eng = WorkflowEngine()
    eng.save = lambda: None  # 测试中不写状态文件
    eng.state.approved = True
    return eng


def test_phase5_skipped_without_artifacts():
    eng = _make_engine()
    eng._detect_artifacts = lambda result: []  # 隔离产物检测，专测"无产物→skipped"
    eng.state.execution_result = {}
    res = eng.phase5_publish()
    assert res["status"] == "skipped"
    assert res["reason"] == "no_artifacts"
    # 诚实：绝不出现伪造成功的 pending
    assert "pending" not in str(res)


def test_phase5_unavailable_without_publisher():
    eng = _make_engine()
    eng._detect_artifacts = lambda result: [{"type": "file", "path": "/tmp/x.mp4"}]
    eng.state.execution_result = {}
    res = eng.phase5_publish(platforms=["bilibili"])
    assert res["bilibili"]["status"] == "unavailable"
    assert res["bilibili"]["reason"] == "no_publisher_configured"


def test_phase5_publishes_with_registry():
    eng = _make_engine()
    eng._detect_artifacts = lambda result: [{"type": "file", "path": "/tmp/x.mp4"}]

    class FakePub:
        def publish(self, arts):
            return {"ok": True}

    WorkflowEngine._PUBLISHERS = {"bilibili": FakePub()}
    try:
        eng.state.execution_result = {}
        res = eng.phase5_publish(platforms=["bilibili"])
        assert res["bilibili"]["status"] == "published"
    finally:
        WorkflowEngine._PUBLISHERS = {}
