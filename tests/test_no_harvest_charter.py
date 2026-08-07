"""母纲守门测试：让 AI 不再收割老百姓，而是陪伴老百姓。

这不是普通单测，是**宪法的可执行版本**。

AGENTS.md §0.0.3 定义了「不收割」的四条硬检验，但文档只是文字，
会被遗忘、会被绕过。本文件把这四条变成 CI 红线：
任何人（包括未来的我）往代码里加功能墙、加锁定、加抽成，这里立刻红。

    对齐理念 9「可验证即真理」：不是「我觉得没收割」，是「测试证明没收割」。

四条硬检验：
    1. 断网检验   —— 断网 + 不付费，核心功能能否全量跑通？
    2. 出走检验   —— 能否一键完整导出全部数据，且导出物在别处可直接用？
    3. 付费墙检验 —— 收费挡的是「服务」还是「功能」？挡功能即收割。
    4. 抽成检验   —— 是否从用户自身创造的收益里抽成？
"""
from __future__ import annotations

import io
import json
import os
import re
import socket
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


# ===========================================================================
# 硬检验 1：断网检验 —— 断网 + 不付费，核心功能必须全量跑通
# ===========================================================================

class _BlockedSocket(socket.socket):
    """任何外连直接爆炸——用来证明代码真的没偷偷联网。"""

    def connect(self, *a, **k):
        raise OSError("NETWORK BLOCKED BY CHARTER TEST")

    def connect_ex(self, *a, **k):
        raise OSError("NETWORK BLOCKED BY CHARTER TEST")


@pytest.fixture
def no_network(monkeypatch):
    monkeypatch.setattr(socket, "socket", _BlockedSocket)
    yield


def test_offline_resilience_loop_runs(no_network):
    """断网检验：自愈闭环（熔断+蒸馏）必须能在零网络下完整跑通。"""
    from core.fabric.resilience_bus import ResilienceBus
    from kernel.evolution_distiller import EvolutionDistiller

    bus = ResilienceBus(distiller=EvolutionDistiller(store_path=None))
    for _ in range(4):
        bus.on_outcome("engine_offline", False, "boom")

    assert bus.should_skip("engine_offline") is True, "断网下熔断必须生效"
    h = bus.health()
    assert h["circuit_trips"] >= 1
    assert h["distiller_connected"] is True, "断网下蒸馏学习必须照常工作"


def test_offline_distiller_persists(no_network, tmp_path):
    """断网检验：失败经验必须能在离线状态下落盘（理念2 失败即训练）。"""
    from kernel.evolution_distiller import EvolutionDistiller

    store = tmp_path / "distill.jsonl"
    d = EvolutionDistiller(store_path=str(store))
    for _ in range(3):
        d.record_outcome("cap.x", "engine_y", False, "offline failure")
    d._save()

    assert store.exists(), "离线必须能落盘，否则断网就失忆"
    content = store.read_text(encoding="utf-8").strip()
    assert "engine_y" in content


def test_core_modules_import_without_network(no_network):
    """断网检验：核心模块 import 阶段不得有任何网络副作用。"""
    import importlib

    for mod in ("core.fabric.resilience_bus",
                "kernel.evolution_distiller",
                "kernel.sovereignty"):
        importlib.import_module(mod)  # 抛异常即失败


# ===========================================================================
# 硬检验 2：出走检验 —— 必须能一键完整导出，导出物在别处可直接用
# ===========================================================================

def test_export_all_exists_and_runs(tmp_path):
    """出走检验：必须存在一键导出入口，且真能产出文件。"""
    from kernel.sovereignty import export_all

    # 造一个假仓库根，避免依赖真实数据是否存在
    fake_root = tmp_path / "repo"
    (fake_root / "data" / "memory").mkdir(parents=True)
    (fake_root / "data" / "memory" / "m.json").write_text(
        '{"hello":"world"}', encoding="utf-8")

    dest = tmp_path / "out"
    manifest = export_all(str(dest), root=str(fake_root))

    assert manifest["total_files"] >= 1, "导出必须真的产出文件"
    assert (dest / "MANIFEST.json").exists(), "必须有清单，否则备份是黑箱"


def test_export_is_readable_without_aos(tmp_path):
    """出走检验：导出物必须是通用格式，没有 AOS 也能直接读。

    不可读 = 变相锁定，等同于收割。
    """
    from kernel.sovereignty import export_all

    fake_root = tmp_path / "repo"
    (fake_root / "data" / "memory").mkdir(parents=True)
    payload = {"note": "用户的记忆"}
    (fake_root / "data" / "memory" / "m.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    dest = tmp_path / "out"
    export_all(str(dest), root=str(fake_root))

    # 用最朴素的标准库读——模拟「一台没装 AOS 的电脑」
    got = json.loads((dest / "memory" / "m.json").read_text(encoding="utf-8"))
    assert got == payload, "导出物必须原样可读，不能是私有格式"

    mani = json.loads((dest / "MANIFEST.json").read_text(encoding="utf-8"))
    assert mani["format_version"], "清单必须自带格式版本"


def test_export_skips_secrets_by_default(tmp_path):
    """出走检验：默认导数据不导密钥（导出的是你的数据，不是你的凭据）。"""
    from kernel.sovereignty import export_all

    fake_root = tmp_path / "repo"
    d = fake_root / "data" / "memory"
    d.mkdir(parents=True)
    (d / "ok.json").write_text("{}", encoding="utf-8")
    (d / ".env").write_text("API_KEY=secret", encoding="utf-8")

    dest = tmp_path / "out"
    export_all(str(dest), root=str(fake_root))

    assert (dest / "memory" / "ok.json").exists()
    assert not (dest / "memory" / ".env").exists(), "默认不得导出凭据"


def test_export_zip_mode(tmp_path):
    """出走检验：支持打包成 zip，方便真正「带走」。"""
    import zipfile

    from kernel.sovereignty import export_all

    fake_root = tmp_path / "repo"
    (fake_root / "data" / "memory").mkdir(parents=True)
    (fake_root / "data" / "memory" / "m.json").write_text("{}",
                                                          encoding="utf-8")

    dest = tmp_path / "backup.zip"
    manifest = export_all(str(dest), root=str(fake_root))

    assert dest.exists()
    assert manifest.get("archive")
    with zipfile.ZipFile(dest) as zf:
        assert "MANIFEST.json" in zf.namelist()


def test_export_preserves_single_file_extension(tmp_path):
    """出走检验：单文件源（如 value_ledger.jsonl）导出后必须保留原扩展名，
    否则「无 AOS 也能直接读」会破功。"""
    from kernel.sovereignty import export_all

    fake_root = tmp_path / "repo"
    (fake_root / "data" / "workspaces").mkdir(parents=True)
    src_file = fake_root / "data" / "workspaces" / "value_ledger.jsonl"
    src_file.write_text("{\"credited_to\": \"user\"}\n", encoding="utf-8")

    custom = [("value_ledger", "data/workspaces/value_ledger.jsonl", "价值账本")]
    dest = tmp_path / "out"
    export_all(str(dest), sources=custom, root=str(fake_root))

    kept = dest / "value_ledger" / "value_ledger.jsonl"
    assert kept.exists(), "单文件源必须保留 .jsonl 扩展名"
    assert kept.read_text(encoding="utf-8").strip() == '{"credited_to": "user"}'


# ===========================================================================
# 硬检验 3：付费墙检验 —— 收费只能挡「服务」，绝不能挡「功能」
# ===========================================================================

def test_local_mode_is_default_and_unlimited(monkeypatch):
    """付费墙检验：默认必须是本地自持模式，且配额一律无限。

    用户跑在自己机器上、烧自己的算力、存自己的数据——不许卡任何数字。
    """
    monkeypatch.delenv("AOS_SAAS_MODE", raising=False)
    from kernel.danchuang.tenant.saas_manager import is_local_sovereign_mode

    assert is_local_sovereign_mode() is True, "默认必须是本地自持模式"


def test_saas_mode_requires_explicit_optin(monkeypatch):
    """付费墙检验：只有显式 AOS_SAAS_MODE=1 才启用配额，不得偷偷默认开。"""
    from kernel.danchuang.tenant.saas_manager import is_local_sovereign_mode

    monkeypatch.setenv("AOS_SAAS_MODE", "1")
    assert is_local_sovereign_mode() is False
    monkeypatch.setenv("AOS_SAAS_MODE", "0")
    assert is_local_sovereign_mode() is True


def test_no_feature_wall_zero_quota_in_any_plan():
    """付费墙检验（核心红线）：任何套餐的任何指标都不得为 0。

    限量（比如 200 次）是「服务费」，可以；
    直接给 0（比如工作流禁用）是「功能墙」，是卖准入，判定为收割。

    历史教训：FREE 档曾有 WORKFLOW_COUNT: 0，即免费版工作流完全禁用，
    与 AGENTS.md §0.0.4「绝不卖准入」直接冲突，已拆除。此测试防止回归。
    """
    from kernel.danchuang.tenant.saas_manager import _PLAN_QUOTAS

    offenders = []
    for tier, plan in _PLAN_QUOTAS.items():
        for metric, value in plan.quotas.items():
            if value == 0:
                offenders.append(f"{tier.value}.{metric.value}=0")

    assert not offenders, (
        "检测到功能墙（配额为 0 = 该功能被锁死，属于卖准入）："
        + ", ".join(offenders)
        + "。限量请用正数，禁止用 0 锁死功能。见 AGENTS.md §0.0.3 付费墙检验。"
    )


def test_free_plan_covers_every_metric():
    """付费墙检验：free 档必须覆盖全部指标，不许漏掉某项变相禁用。"""
    from kernel.danchuang.tenant.saas_manager import (_PLAN_QUOTAS, PlanTier,
                                                      UsageMetric)

    free = _PLAN_QUOTAS[PlanTier.FREE]
    missing = [m.value for m in UsageMetric if m not in free.quotas]
    assert not missing, f"free 档缺失指标（变相禁用）：{missing}"


# ===========================================================================
# 硬检验 4：抽成检验 —— 不得从用户自身创造的收益里抽成
# ===========================================================================

def test_no_revenue_commission_logic():
    """抽成检验：全库不得出现对用户收益的抽成逻辑。

    注意区分：decommission（淘汰下线）不是 commission（佣金抽成），
    这里只匹配真正的抽成语义。
    """
    pat = re.compile(
        r"(take_rate|revenue_share|platform_fee|抽成比例|佣金率"
        r"|\bcommission_rate\b|\bcut_rate\b)")
    offenders = []
    for dp, dn, fs in os.walk(SRC):
        dn[:] = [d for d in dn if d not in ("__pycache__", "_traces")]
        for f in fs:
            if not f.endswith(".py"):
                continue
            p = Path(dp) / f
            try:
                s = io.open(p, encoding="utf-8", errors="ignore").read()
            except OSError:
                continue
            if pat.search(s):
                offenders.append(str(p.relative_to(ROOT)))

    assert not offenders, (
        "检测到疑似抽成逻辑（违反宪法原则5「无抽成」/原则6「价值回流」）："
        + ", ".join(offenders))


# ===========================================================================
# 附加守门：硬编码绝对路径 —— 违反理念7「千人千面·贴合本地环境」
# ===========================================================================

def test_no_hardcoded_absolute_repo_path_in_tenant_module():
    """别人 clone 下来必须能跑：租户模块不得硬编码 d:\\AOS 这类绝对路径。

    历史教训：saas_manager.py 曾有 DEFAULT_USAGE_DATA_PATH = r"d:\\AOS\\..."，
    换台机器直接废掉，违反原则 7「技术普惠·人人用得起」。
    """
    p = SRC / "kernel" / "danchuang" / "tenant" / "saas_manager.py"
    s = p.read_text(encoding="utf-8")
    bad = re.findall(r'r?"[a-zA-Z]:\\\\?[Aa][Oo][Ss]', s)
    assert not bad, f"检测到硬编码绝对路径：{bad}"


def test_usage_data_path_is_portable():
    """用量数据路径必须可移植（跟随仓库根或环境变量）。"""
    from kernel.danchuang.tenant.saas_manager import _default_usage_data_path

    got = _default_usage_data_path()
    assert "usage_data.json" in got
    # 必须指向本仓库内，而非某台机器写死的 d:\AOS
    assert str(ROOT) in got or os.environ.get("AOS_USAGE_DATA_PATH")


# ===========================================================================
# 附加守门：诚实指标 —— 理念6「绝不伪造成功」
# ===========================================================================

def test_health_does_not_inflate_heal_count():
    """诚实检验：自愈没成功就不许计入 heal_succeeded 充数。

    历史教训：health() 曾用 len(_heal_history) 当 heal_actions，
    把 action="none"（三招全没成）也算成一次自愈，属于指标虚高。
    """
    from core.fabric.resilience_bus import ResilienceBus

    bus = ResilienceBus()  # 无 restart/fallback/isolate，自愈必然全败
    for _ in range(3):
        bus.on_outcome("e_fail", False, "x")

    h = bus.health()
    assert h["heal_attempts"] >= 1, "尝试次数要如实记录"
    assert h["heal_succeeded"] == 0, "一次都没治好，不许报成功"
    assert h["heal_actions"] == 0, "旧字段语义必须是「真正生效」而非「尝试过」"
    assert h["heal_failed"] == h["heal_attempts"]


def test_health_counts_real_heal():
    """诚实检验：真的自愈成功了，必须如实计入（不许反向瞒报）。"""
    from core.fabric.resilience_bus import ResilienceBus

    bus = ResilienceBus(restart_engine=lambda eid: True)
    for _ in range(3):
        bus.on_outcome("e_ok", False, "x")

    h = bus.health()
    assert h["heal_succeeded"] >= 1, "真成功了要如实报"
    assert h["recent_heals"][-1]["action"] == "restart"


# ===========================================================================
# 母纲原则 6：价值回流·劳动有报 —— 用户创造的价值流回用户口袋
# ===========================================================================

def test_value_ledger_local_and_user_credited():
    """价值回流：用户的劳动产物被记账，且永远归用户（不归平台）。"""
    import tempfile, os
    from kernel.value_ledger import ValueLedger

    with tempfile.TemporaryDirectory() as d:
        led = ValueLedger(path=os.path.join(d, "vl.jsonl"))
        e = led.record("lesson", "search::vosk", "不可靠引擎已沉底")
        assert e["credited_to"] == "user", "价值必须归用户"
        assert led.total().get("lesson") == 1
        led2 = ValueLedger(path=os.path.join(d, "vl.jsonl"))
        assert led2.all()[0]["credited_to"] == "user"


def test_value_ledger_exportable_back_to_user():
    """价值回流：账本可导出为通用格式，没有 AOS 也能读（回流到用户口袋）。"""
    import tempfile, os, json
    from kernel.value_ledger import ValueLedger

    with tempfile.TemporaryDirectory() as d:
        led = ValueLedger(path=os.path.join(d, "vl.jsonl"))
        led.record("lesson", "a::b", "note")
        out = os.path.join(d, "export.jsonl")
        led.export(out)
        with open(out, encoding="utf-8") as f:
            rows = [json.loads(l) for l in f if l.strip()]
        assert rows and rows[0]["credited_to"] == "user"


def test_value_siphon_scanner_actually_works():
    """阳性对照：扫描器必须能在已知含外联的样本上报出命中。

    为什么必须有这条：``test_no_value_siphon`` 断言的是「结果为空」。
    如果扫描器本身坏掉（比如恒抛异常被 except 吞掉、恒返回 []），
    那条测试会**永远绿**——它证明的是「函数没崩」，不是「没有虹吸」。
    绿灯说谎比红灯更危险。

    历史教训（2026-08-07 深度检查实测）：``value_ledger.py`` 曾把
    ``import ast`` 写在某个函数体内部，而模块级的 ``_ast_imports``
    也要用 ``ast`` → ``NameError`` 被外层 ``except Exception`` 吞掉
    → ``scan_value_siphon()`` 恒返回 ``[]`` → 母纲原则 6「零外泄证明」
    整整空转，而 CI 一路绿灯。

    本测试红 = 扫描器坏了（先修扫描器）；
    ``test_no_value_siphon`` 红 = 真有外泄风险（修业务代码）。
    两者语义严格分离，不许再混。
    """
    import tempfile
    import os
    from kernel.value_ledger import scan_value_siphon

    with tempfile.TemporaryDirectory() as d:
        # 已知阳性样本：显式外联上报
        with open(os.path.join(d, "siphon_sample.py"), "w", encoding="utf-8") as f:
            f.write(
                "import requests\n"
                "import socket\n"
                "def upload(user_data):\n"
                "    requests.post('https://example.com/collect', json=user_data)\n"
            )
        hits = scan_value_siphon(d)

    assert hits, (
        "反虹吸扫描器失效：对已知含外联上报的阳性样本返回了空结果。"
        "在扫描器修好之前，test_no_value_siphon 的绿灯没有任何意义（假绿）。"
        "排查方向：scan_value_siphon / _ast_imports 是否有异常被 except 吞掉"
        "（例如模块级缺 import ast 导致 NameError）。"
    )


def test_no_value_siphon():
    """反虹吸：扫描全仓，证明没有代码把用户价值偷偷发往远端（零泄漏）。

    注意：本测试只有在 ``test_value_siphon_scanner_actually_works``
    也为绿时才有意义。那条是本条的阳性对照，缺一不可。
    """
    from kernel.value_ledger import scan_value_siphon

    hits = scan_value_siphon(str(ROOT))
    assert hits == [], f"发现价值外泄风险: {hits}"


def test_distiller_feeds_value_ledger():
    """劳动有报：蒸馏出经验时，自动记入用户价值账本（真实接线，非死代码）。"""
    import tempfile, os
    from kernel.evolution_distiller import EvolutionDistiller
    from kernel.value_ledger import ValueLedger

    with tempfile.TemporaryDirectory() as d:
        store = os.path.join(d, "distill.jsonl")
        led = ValueLedger(path=os.path.join(d, "vl.jsonl"))
        dist = EvolutionDistiller(store_path=store, value_ledger=led)
        for _ in range(6):
            dist.record_outcome("search", "vosk", ok=False, error="boom")
        recs = dist.distill()
        assert len(recs) >= 1, "必须蒸馏出沉底建议"
        assert led.total().get("lesson", 0) >= 1, "蒸馏经验必须记入用户账本"


# ===========================================================================
# 母纲原则 7：中文优先·方言平等 —— 听懂 22 种方言（真能力 + 反虚报双守门）
# ===========================================================================

def test_dialect_capability_layer_is_real_not_placeholder():
    """能力层必须真存在：真实路由代码，不是占位符。"""
    from kernel import dialect_asr
    from kernel.constitution_gaps import dialect_summary

    s = dialect_summary()
    assert s["targets"] == 22, "母纲目标 22 种方言"
    assert s["capability_layer"] is True, "方言能力层必须已落地，不许是占位"
    # 已核实开源引擎（Fun-ASR-Nano，Apache-2.0）官方声明覆盖 18 种
    assert s["declared_covered"] >= 18, "能力矩阵必须覆盖已核实引擎声明的方言"
    assert s["no_engine"] == 4, "剩 4 种全球暂无已核实引擎声明支持，是真缺口"
    # 矩阵里的方言必须全在宪法目标清单内（不许自造方言名充数）
    for engine, dialects in dialect_asr.ENGINE_COVERAGE.items():
        for d in dialects:
            assert d in dialect_asr.all_targets(), f"{engine} 覆盖了非目标方言 {d}"


def test_dialect_supported_never_exceeds_really_ready():
    """反虚报：报出来的「已支持」必须 ⊆ 此刻真就绪引擎的覆盖，一个都不许多报。"""
    from kernel import dialect_asr
    from kernel.constitution_gaps import supported_dialects

    ready = set(dialect_asr.ready_engines())
    allowed = {d for e in ready for d in dialect_asr.ENGINE_COVERAGE.get(e, [])}
    reported = set(supported_dialects())
    assert reported <= allowed, f"虚报方言支持：{reported - allowed}"
    if not ready:
        assert reported == set(), "没有任何引擎就绪时必须报 0，不许造假"


def test_dialect_routing_really_dispatches():
    """真路由：注入后端后，方言必须被真分派到正确引擎（验证路由逻辑本身）。"""
    from kernel.dialect_asr import DialectASR

    calls = []

    def fake_funasr(path, dialect):
        calls.append(("funasr", dialect))
        return "识别结果-方言"

    def fake_vosk(path, dialect):
        calls.append(("vosk", dialect))
        return "识别结果-普通话"

    with tempfile.TemporaryDirectory() as d:
        wav = os.path.join(d, "a.wav")
        with open(wav, "wb") as f:
            f.write(b"RIFF0000WAVE")

        asr = DialectASR(backends={"funasr": fake_funasr, "vosk": fake_vosk})
        r = asr.transcribe(wav, "粤语")
        assert r["ok"] is True and r["engine"] == "funasr", "粤语必须走 funasr"
        r2 = asr.transcribe(wav, "官话-北京")
        assert r2["engine"] == "funasr", "两者都能时按优先级选 funasr"
        assert calls == [("funasr", "粤语"), ("funasr", "官话-北京")]


def test_dialect_unavailable_rejects_honestly_with_plan():
    """诚实拒绝：只有 vosk 时问粤语，必须明确拒绝并给可照敲命令，
    绝不静默换普通话模型冒充识别成功（这是收割式糊弄）。"""
    from kernel.dialect_asr import DialectASR

    def fake_vosk(path, dialect):
        return "不该被调用"

    with tempfile.TemporaryDirectory() as d:
        wav = os.path.join(d, "a.wav")
        with open(wav, "wb") as f:
            f.write(b"RIFF0000WAVE")

        asr = DialectASR(backends={"vosk": fake_vosk})
        r = asr.transcribe(wav, "粤语")
        assert r["ok"] is False, "vosk 不支持粤语，必须诚实失败"
        assert "engine" not in r or r.get("engine") != "vosk", "绝不许拿普通话模型冒充"
        plan = r.get("plan") or {}
        assert plan.get("known_target") is True
        steps = plan.get("steps") or []
        assert steps and any(s.get("install") for s in steps), "必须给出可照敲的安装命令"
        # 同一个 asr 问普通话则应该真走 vosk
        assert asr.transcribe(wav, "官话-北京")["engine"] == "vosk"


def test_dialect_real_transcription_end_to_end():
    """③ 级实证：真模型 + 真音频 + 真识别，必须出正确文本。

    这条把「引擎就绪」抬升为「真能听懂」。环境不全（无模型/无 ffmpeg/无网）
    自动 skip——**但绝不因此改判为通过**，skip 就是 skip，不算数。
    合成音非真人方言录音，所以只覆盖普通话（官话-北京），方言仍待真人验。
    """
    import subprocess

    from kernel.dialect_asr import DialectASR, route

    if route("官话-北京") is None:
        pytest.skip("无就绪 ASR 引擎（跑 scripts/fetch_vosk_model.py 下模型）")
    try:
        import edge_tts  # noqa: F401
        import imageio_ffmpeg
    except Exception:
        pytest.skip("缺 edge-tts / imageio-ffmpeg，无法合成验证音频")

    text = "今天天气很好"
    with tempfile.TemporaryDirectory() as d:
        mp3 = os.path.join(d, "s.mp3")
        wav = os.path.join(d, "s.wav")
        try:
            import asyncio

            import edge_tts as _t

            asyncio.run(_t.Communicate(text, "zh-CN-XiaoxiaoNeural").save(mp3))
        except Exception as exc:  # 合成需联网
            pytest.skip(f"TTS 合成失败（需联网）: {exc!r}"[:120])

        ff = imageio_ffmpeg.get_ffmpeg_exe()
        subprocess.run([ff, "-y", "-loglevel", "error", "-i", mp3,
                        "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", wav],
                       check=True)

        out = DialectASR().transcribe(wav, "官话-北京")
        assert out.get("ok") is True, f"真识别失败: {out}"
        got = (out.get("text") or "").replace(" ", "")
        hits = sum(1 for ch in "今天天气好" if ch in got)
        assert hits >= 3, f"识别文本偏差过大: 期望≈{text} 实得={got}"


def test_dialect_capability_is_wired_not_orphan():
    """反孤儿模块：方言能力必须真接进对外入口，建了没人调等于没建。"""
    src = Path(__file__).resolve().parents[1] / "src" / "core" / "fabric" / \
        "http_server.py"
    text = src.read_text(encoding="utf-8", errors="ignore")
    assert "kernel.dialect_asr" in text, "方言路由未接进 HTTP 语音入口"
    assert "/api/charter/status" in text, "缺少母纲能力自查端点，用户无法当场复核"
    assert "_get_charter_status" in text


def test_dialect_no_engine_gap_not_fabricated():
    """真缺口不脑补：无引擎声明的方言，install_plan 必须承认没辙，不许编造。"""
    from kernel.constitution_gaps import dialect_install_plan

    plan = dialect_install_plan("儋州话")
    assert plan["known_target"] is True
    assert plan.get("available_now") is False
    assert not plan.get("engines"), "没有引擎就不许编出引擎来"


# ===========================================================================
# 母纲原则 10：身体延伸·灵魂唯一 —— 同一个灵魂，在不同设备里
# ===========================================================================

def test_soul_identity_stable_and_portable():
    """灵魂唯一：灵魂 ID 本地稳定、跨调用一致、可随身带走（原语就位）。"""
    import tempfile, os
    from kernel.constitution_gaps import get_or_create_soul_id, soul_identity

    with tempfile.TemporaryDirectory() as d:
        os.environ["AOS_SOUL_ID_PATH"] = os.path.join(d, "soul_id.txt")
        try:
            a = get_or_create_soul_id()
            b = get_or_create_soul_id()
            assert a == b, "同一机器上灵魂 ID 必须稳定"
            ident = soul_identity()
            assert ident["soul_id"] == a
            assert ident["portable"] is True, "灵魂必须可随导出带走"
        finally:
            os.environ.pop("AOS_SOUL_ID_PATH", None)


def test_soul_sync_protocol_is_real_and_offline_first():
    """同步协议必须真实存在，且默认路径零联网（§0.0.3 断网检验）。"""
    from kernel.constitution_gaps import soul_identity

    ident = soul_identity()
    proto = ident["sync_protocol"]
    assert proto != "NOT_IMPLEMENTED", "同步协议已落地，追踪器必须回报真实协议名"
    assert proto.startswith("aospkg/"), f"协议标识异常: {proto}"
    assert ident["requires_network"] is False, "默认通道必须零联网（U 盘也能同步）"
    names = {t["name"] for t in ident["transports"]}
    assert "local_dir" in names, "必须有零网络的本地目录通道"
    default = [t for t in ident["transports"] if t["default"]]
    assert default and default[0]["requires_network"] is False, \
        "默认通道不许要求联网，否则断网就成了收割筹码"


def test_soul_sync_cross_device_round_trip_real():
    """真跨设备：A 推 → B 认领 → B 改 → B 推 → A 拉，灵魂统一且数据不丢。"""
    from kernel.soul_sync import LocalDirTransport, SoulSync

    with tempfile.TemporaryDirectory() as base:
        dev_a = Path(base) / "deviceA"
        dev_b = Path(base) / "deviceB"
        udisk = Path(base) / "udisk"
        for p in (dev_a, dev_b, udisk):
            p.mkdir(parents=True, exist_ok=True)

        # A 设备写入灵魂内容
        (dev_a / "data" / "soul").mkdir(parents=True, exist_ok=True)
        (dev_a / "data" / "soul" / "soul_id.txt").write_text(
            "soulA1234567890", encoding="utf-8")
        (dev_a / ".workbuddy" / "memory").mkdir(parents=True, exist_ok=True)
        (dev_a / ".workbuddy" / "memory" / "note.md").write_text(
            "A设备的记忆", encoding="utf-8")

        a = SoulSync(LocalDirTransport(udisk), root=dev_a)
        pushed = a.push()
        assert pushed["ok"] is True, f"推送失败: {pushed}"

        # B 设备（全新）认领同一个灵魂
        b = SoulSync(LocalDirTransport(udisk), root=dev_b)
        adopted = b.adopt()
        assert adopted["ok"] is True, f"认领失败: {adopted}"
        assert b.soul_id == a.soul_id, "跨设备必须是同一个灵魂"
        assert (dev_b / ".workbuddy" / "memory" / "note.md").exists(), \
            "记忆必须真的传过去"

        # B 改内容后推回
        (dev_b / ".workbuddy" / "memory" / "note.md").write_text(
            "A设备的记忆\nB设备新增一行", encoding="utf-8")
        assert b.push()["ok"] is True

        # A 拉取：必须真采纳 B 的更新，且旧版存档不丢
        pulled = a.pull()
        assert pulled["ok"] is True, f"拉取失败: {pulled}"
        text = (dev_a / ".workbuddy" / "memory" / "note.md").read_text(
            encoding="utf-8")
        assert "B设备新增一行" in text, "远端更新必须真落地，不许静默丢弃"
        assert a.status()["requires_network"] is False, "全程零联网"


def test_soul_sync_package_encrypted_at_rest():
    """同步包落盘必须加密（复用 utils.keystore），U 盘丢了也不泄露灵魂。"""
    from kernel import soul_sync
    from kernel.soul_sync import LocalDirTransport, SoulSync

    if not soul_sync.encryption_available():
        pytest.skip("keystore 主密钥不可用，跳过加密断言")

    with tempfile.TemporaryDirectory() as base:
        root = Path(base) / "dev"
        (root / "data" / "soul").mkdir(parents=True, exist_ok=True)
        (root / "data" / "soul" / "soul_id.txt").write_text(
            "soulENC000000001", encoding="utf-8")
        (root / ".workbuddy" / "memory").mkdir(parents=True, exist_ok=True)
        (root / ".workbuddy" / "memory" / "secret.md").write_text(
            "我的私密日记明文标记XYZ", encoding="utf-8")

        udisk = Path(base) / "udisk"
        s = SoulSync(LocalDirTransport(udisk), root=root, encrypt=True)
        res = s.push()
        assert res["ok"] is True and res.get("encrypted") is True

        blobs = list(udisk.glob("*" + soul_sync.PACKAGE_SUFFIX))
        assert blobs, "同步包必须真写到通道里"
        raw = blobs[0].read_bytes()
        assert soul_sync.is_encrypted(raw), "落盘包必须是加密态"
        assert b"XYZ" not in raw, "明文内容绝不许出现在落盘包里"
