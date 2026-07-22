"""repo_agent（action.repo 仓库自进化芯粒）测试。

不依赖重型链：repo_agent 自身 try-import core.fabric.adapter fallback；
而 kernel.plugins 包的 __init__ 会触发 numpy 等重型依赖，在轻环境（无 numpy）
下整包 import 失败。因此测试用 importlib 直接加载 repo_agent 模块体，
复用其内置 fallback，使其可在任意环境运行/测试。
"""
import importlib.util
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))


def _load_repo_agent():
    """优先正常 import（主机 numpy 齐），失败则用 importlib 隔离加载。"""
    try:
        from kernel.plugins.repo_agent import RepoAgent, InvokeRequest
        return RepoAgent, InvokeRequest
    except Exception:
        spec = importlib.util.spec_from_file_location(
            "repo_agent_iso",
            os.path.join(os.path.dirname(__file__), "..", "src",
                         "kernel", "plugins", "repo_agent.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.RepoAgent, mod.InvokeRequest


RepoAgent, InvokeRequest = _load_repo_agent()
from kernel.opc_loop import build_default_stages  # noqa: E402


def _req(op, **kw):
    return InvokeRequest(capability="action.repo", payload={"operation": op, **kw})


def test_status_real_execution():
    """真实 git status 调用：不 mock，验证芯粒真能跑。"""
    a = RepoAgent()
    res = a.invoke(_req("status"))
    assert res.ok, res.error
    assert res.data["engine"] == "git"
    assert res.data["real"] is True
    assert res.data.get("branch")
    assert "repo_root" in res.data


def test_readonly_ops_no_auth():
    """只读操作（diff/log/branch）默认放行，不要求 confirm。"""
    a = RepoAgent()
    for op in ("diff", "log", "branch"):
        res = a.invoke(_req(op))
        assert res.ok, f"{op} 应默认放行: {res.error}"
        assert res.data["engine"] == "git"


def test_commit_requires_confirm():
    """写操作未授权必被拒（权限边界）。"""
    a = RepoAgent()
    res = a.invoke(_req("commit", message="valid message here"))
    assert res.ok is False
    assert "需授权" in (res.error or "")


def test_push_requires_env():
    """push 默认关闭，需 AOS_REPO_PUSH=1。"""
    a = RepoAgent()
    os.environ.pop("AOS_REPO_PUSH", None)
    res = a.invoke(_req("push"))
    assert res.ok is False
    assert "默认关闭" in (res.error or "")


def test_commit_with_confirm_calls_git():
    """授权后 commit 真调用 git（mock git 验证调用路径，不污染仓库）。"""
    a = RepoAgent()
    calls = []

    def fake_run(self, args, timeout=60):
        calls.append(list(args))
        if args[:1] == ["status"] and any("porcelain" in a for a in args):
            return 0, " M src/x.py\n", ""   # 有改动，非敏感
        if args[:1] == ["commit"]:
            return 0, "[main abc123] valid msg here", ""
        return 0, "", ""  # add 等

    with patch.object(RepoAgent, "_run", fake_run):
        res = a.invoke(_req("commit", message="valid msg here", confirm=True))
    assert res.ok, res.error
    assert res.data["operation"] == "commit"
    assert res.data["message"] == "valid msg here"
    assert res.data["pushed"] is False
    assert any(c[:1] == ["commit"] for c in calls), "commit 应被真实调用"


def test_sensitive_file_rejected():
    """工作树含敏感文件时拒绝 commit。"""
    a = RepoAgent()
    calls = []

    def fake_run(self, args, timeout=60):
        calls.append(list(args))
        if args[:1] == ["status"] and any("porcelain" in a for a in args):
            return 0, " M .env\n", ""   # 含敏感文件
        return 0, "", ""

    with patch.object(RepoAgent, "_run", fake_run):
        res = a.invoke(_req("commit", message="valid msg here", confirm=True))
    assert res.ok is False
    assert "敏感" in (res.error or "")
    assert not any(c[:1] == ["commit"] for c in calls), "敏感文件不应触发 commit"


def test_opc_evolve_stage_registered():
    """OPC 飞轮已含 evolve 阶段，且绑定 action.repo 能力。"""
    stages = build_default_stages()
    ids = [s.id for s in stages]
    assert "evolve" in ids
    ev = [s for s in stages if s.id == "evolve"][0]
    assert ev.capability == "action.repo"
    assert ev.side_effect is True
    assert ev.confirm is True
    # 顺序：交付 -> 进化 -> 维护
    assert ids.index("deliver") < ids.index("evolve") < ids.index("maintain")


if __name__ == "__main__":
    test_status_real_execution()
    test_readonly_ops_no_auth()
    test_commit_requires_confirm()
    test_push_requires_env()
    test_commit_with_confirm_calls_git()
    test_sensitive_file_rejected()
    test_opc_evolve_stage_registered()
    print("ALL REPO_AGENT TESTS PASSED")
