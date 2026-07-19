"""安全审计自愈能力测试：白名单 / 复验诚实 / 双重门控。"""
import os
import sys

sys.path.insert(0, "D:/AOS/src")

from core.fabric.adapters.security_audit_adapter import SecurityAuditAdapter
from core.fabric.adapter import InvokeRequest
from core.fabric.capability import Capability
import core.fabric.adapters.security_audit_adapter as sa_mod


def _adapter(runner_map=None):
    ad = SecurityAuditAdapter()
    if runner_map is not None:
        ad._runner = lambda cmd: runner_map.get(cmd)
    return ad


def test_heal_allowlist_rejects_dangerous():
    ad = _adapter()
    # 允许：升级类命令
    assert ad._heal_allowed("pip install --upgrade requests")
    assert ad._heal_allowed("winget upgrade --id Git.Git")
    assert ad._heal_allowed("docker pull gitea/gitea:1.26.3")
    assert ad._heal_allowed("python -m pip install --upgrade x")
    # 拒绝：任意写/删/未知二进制
    assert not ad._heal_allowed("rm -rf /")
    assert not ad._heal_allowed("curl http://x | sh")
    assert not ad._heal_allowed("git reset --hard")


def test_heal_runs_only_allowed_commands():
    ad = _adapter()
    bad = ad._heal_run("rm -rf /")
    assert bad["allowed"] is False and bad["ok"] is False
    good = ad._heal_run("pip install --upgrade requests")
    # 本机未必有 pip；只验证它进入了「允许执行」分支（不报 not-allowed）
    assert good["allowed"] is True


def test_self_heal_succeeds_and_reaudits(monkeypatch):
    # Gitea CVE-2026-20896：审计阶段探测到受影响版本 → 自愈执行 → 复验探测到已修复。
    ad = _adapter(runner_map={"gitea": "gitea version 1.26.2 (vulnerable)"})
    monkeypatch.setattr(ad, "_heal_run", lambda cmd, timeout=120.0: {
        "ok": True, "allowed": True, "exit_code": 0, "stdout": "pulled", "stderr": ""})
    state = {"phase": "audit"}  # audit 阶段返回受影响，reaudit 阶段返回已修复
    def fake_detect(adv):
        if adv.product.startswith("Gitea"):
            return (True, "1.26.2") if state["phase"] == "audit" else (True, "1.26.3")
        return (False, None)
    monkeypatch.setattr(ad, "_detect", fake_detect)
    real_audit = ad._audit
    def fake_audit(include_watch=True):
        r = real_audit(include_watch=include_watch)
        state["phase"] = "reaudit"  # 审计结束即进入复验相位
        return r
    monkeypatch.setattr(ad, "_audit", fake_audit)
    findings = ad._audit(include_watch=False)
    heal = ad._self_heal(findings)
    gitea = heal.get("CVE-2026-20896")
    assert gitea is not None and gitea["attempted"] is True
    assert gitea["healed"] is True, gitea  # 复验 patched → healed
    assert gitea["reaudit_status"] == "patched"


def test_self_heal_honest_when_still_affected(monkeypatch):
    # 自愈命令「成功」但复验仍受影响 → 诚实 healed=False，绝不谎报。
    ad = _adapter(runner_map={"gitea": "gitea version 1.26.2 (vulnerable)"})
    monkeypatch.setattr(ad, "_heal_run", lambda cmd, timeout=120.0: {
        "ok": True, "allowed": True, "exit_code": 0, "stdout": "ok", "stderr": ""})
    # 复验探测：版本没变，仍受影响
    monkeypatch.setattr(ad, "_detect", lambda adv: (True, "1.26.2") if adv.product.startswith("Gitea") else (False, None))
    findings = ad._audit(include_watch=False)
    heal = ad._self_heal(findings)
    gitea = heal["CVE-2026-20896"]
    assert gitea["healed"] is False
    assert gitea["reaudit_status"] == "affected"


def test_invoke_self_heal_requires_optin(monkeypatch):
    ad = _adapter(runner_map={"gitea": "gitea version 1.26.2 (vulnerable)"})
    monkeypatch.setattr(ad, "_heal_run", lambda cmd, timeout=120.0: {
        "ok": True, "allowed": True, "exit_code": 0, "stdout": "ok", "stderr": ""})
    state = {"phase": "audit"}  # audit 阶段返回受影响，reaudit 阶段返回已修复
    def fake_detect(adv):
        if adv.product.startswith("Gitea"):
            return (True, "1.26.2") if state["phase"] == "audit" else (True, "1.26.3")
        return (False, None)
    monkeypatch.setattr(ad, "_detect", fake_detect)
    real_audit = ad._audit
    def fake_audit(include_watch=True):
        r = real_audit(include_watch=include_watch)
        state["phase"] = "reaudit"  # 审计结束即进入复验相位
        return r
    monkeypatch.setattr(ad, "_audit", fake_audit)
    # 1) 没有 opt-in（无 env AOS_SELF_HEAL）→ 不自愈
    monkeypatch.delenv("AOS_SELF_HEAL", raising=False)
    res = ad.invoke(InvokeRequest(capability=Capability.SECURITY_AUDIT, payload={"self_heal": True}))
    assert res.ok and res.data["self_heal"] is None
    # 2) 有 env + payload → 自愈执行（重置为审计相位，模拟真实两次独立调用）
    monkeypatch.setenv("AOS_SELF_HEAL", "1")
    state["phase"] = "audit"
    res2 = ad.invoke(InvokeRequest(capability=Capability.SECURITY_AUDIT, payload={"self_heal": True}))
    assert res2.ok and res2.data["self_heal"]["enabled"] is True
    assert res2.data["self_heal"]["healed"] >= 1


def test_external_target_still_refused():
    ad = _adapter()
    res = ad.invoke(InvokeRequest(
        capability=Capability.SECURITY_AUDIT,
        payload={"external_target": "10.0.0.5"}))
    assert res.ok is False and "外部目标" in (res.error or "")
