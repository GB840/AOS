"""防御型本地漏洞自查适配器测试。

核心验证：① 能力已声明；② 外部目标被诚实拒绝（红线）；③ libssh2 受影响/
已修复版本判定正确；④ Gitea 受影响判定；⑤ 知识库含已核实 CVE 且字段完整。
探测通过注入 _runner 伪造，不触碰任何真实外部/本地攻击面。
"""
from core.fabric.adapter import InvokeRequest
from core.fabric.capability import Capability
from core.fabric.adapters.security_audit_adapter import (
    SecurityAuditAdapter,
    ADVISORIES,
    WATCHLIST,
)


def _invoke(adapter, payload=None):
    req = InvokeRequest(capability=Capability.SECURITY_AUDIT, payload=payload or {})
    return adapter.invoke(req)


def test_advertises_security_audit():
    caps = SecurityAuditAdapter().advertise_capabilities()
    assert Capability.SECURITY_AUDIT in caps


def test_refuses_external_target():
    adapter = SecurityAuditAdapter()
    res = _invoke(adapter, {"external_target": "192.168.1.10", "scope": "localhost"})
    assert res.ok is False
    assert "外部目标" in (res.error or "")
    # 非 localhost scope 同样拒绝
    res2 = _invoke(adapter, {"scope": "remote"})
    assert res2.ok is False


def test_audit_libssh2_vulnerable():
    adapter = SecurityAuditAdapter()
    adapter._runner = lambda cmd: "curl 8.9.0 (x86_64) libcurl/8.9.0 libssh2/1.11.1"
    res = _invoke(adapter)
    assert res.ok is True
    data = res.data
    f = next(f for f in data["findings"] if f["cve"] == "CVE-2026-55200")
    assert f["status"] == "affected"
    assert f["detected_version"] == "1.11.1"
    assert "回灌" in f["recommendation"]  # 诚实标注发行版回灌不确定性


def test_audit_libssh2_patched_version():
    adapter = SecurityAuditAdapter()
    adapter._runner = lambda cmd: "curl 8.10.0 libcurl/8.10.0 libssh2/1.12.0"
    res = _invoke(adapter)
    f = next(f for f in res.data["findings"] if f["cve"] == "CVE-2026-55200")
    assert f["status"] == "patched"


def test_audit_gitea_vulnerable():
    adapter = SecurityAuditAdapter()
    # gitea 未被检测命令命中（curl 不带 gitea），此处让 gitea 命令返回旧版本
    def fake_run(cmd):
        if cmd == "gitea":
            return "Gitea version 1.26.0"
        return None
    adapter._runner = fake_run
    res = _invoke(adapter)
    f = next(f for f in res.data["findings"] if f["cve"] == "CVE-2026-20896")
    assert f["status"] == "affected"
    assert f["detected_version"] == "1.26.0"


def test_knowledge_base_has_verified_cves():
    cves = {a.cve for a in ADVISORIES}
    assert {
        "CVE-2026-55200", "CVE-2026-55199", "CVE-2025-15661",
        "CVE-2026-20896", "CVE-2026-58053",
    }.issubset(cves)
    # 每个已核实条目都有可复核参考链接 + 修复说明
    for a in ADVISORIES:
        assert a.verified is True
        assert a.references
        assert a.fixed
    # watchlist 为未核实线索，不计入受影响判定
    assert any(w["product"] == "7-Zip" for w in WATCHLIST)


def test_watchlist_included_on_request():
    adapter = SecurityAuditAdapter()
    adapter._runner = lambda cmd: None
    res = _invoke(adapter, {"include_watchlist": True})
    watch = [f for f in res.data["findings"] if f["status"] == "watch"]
    assert watch and all(f["verified"] is False for f in watch)
