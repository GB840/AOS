"""防御型本地漏洞自查适配器 —— AOS fabric 的 SECURITY_AUDIT 平面。

设计红线（对应 AGENTS.md 理念5「权限即边界」+ 理念6/9「诚实可验证」）：

1. **纯防御，绝不攻击**：本适配器**只巡检你自己的本机环境**，用来回答
   「我机器上跑的组件有没有中招、该升到哪个版本」。它**不包含、不下载、
   不运行任何 exploit / PoC 代码**。
2. **只用公开 CVE 元数据**：知识库来自各厂商/ NVD / CERT 已公开的漏洞情报
   （受影响版本区间、补丁版本、修复提交、参考链接），全部可复核（理念9）。
3. **仅本机、只读**：所有探测只用 `--version` 这类只读命令抓取本地组件版本；
   一旦载荷里出现外部目标（host/ip/url），直接诚实拒绝（理念5）。
4. **诚实标注不确定**：版本 ≤ 受影响区间不等于一定中招（发行版常把补丁回灌到
   原版本号），此时状态标 `affected_unconfirmed` 并提示按发行版公告核实。

情报来源说明：业界 2026-06 出现的 `bikini/exploitarium` 零日 PoC 合集，其**攻击代码**
本适配器一概不取；我们只把其中**已被防御方独立确认、分配了 CVE 的真实漏洞**转译为
对自家环境的自查项。这样既回应了「把这份情报变成系统能力」的诉求，又不越界成攻击工具。
"""
from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from core.fabric.adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from core.fabric.capability import Capability
from kernel.confidence import assess

logger = logging.getLogger(__name__)


@dataclass
class Advisory:
    """一条已核实（分配 CVE、被防御方复现）的漏洞情报。仅含元数据，无攻击代码。"""
    cve: str
    product: str
    summary: str
    severity: str          # critical / high / medium
    cvss: float
    affected_max: Optional[Tuple[int, ...]]  # 最后一个受影响版本；None=固定版本未知
    affected_range: str    # 人类可读区间（展示用）
    fixed: str             # 人类可读修复说明（版本号或 commit）
    detect_cmd: Optional[str]   # 本地探测命令（仅取版本字符串）
    detect_parse: str = ""      # 从命令输出里抓版本的正则/关键字提示（展示用）
    references: List[str] = field(default_factory=list)
    verified: bool = True       # True=已分配 CVE 且防御方复现；False=未核实线索


# ── 已核实漏洞知识库（公开 CVE 元数据，来源见 references，均可复核）─────────────
# 数据截至 2026-07-19，依据：NVD / libssh2 PR#2052(commit 97acf3df) / Gitea 1.26.3
# 公告 / Field Effect / The Hacker News / Ubuntu USN-8486-1 等公开来源交叉核实。
ADVISORIES: List[Advisory] = [
    Advisory(
        cve="CVE-2026-55200",
        product="libssh2",
        summary="ssh2_transport_read() 未校验 packet_length 上界，畸形 SSH 包触发整数溢出→堆越界写，"
                "恶意/被控 SSH 服务器可在客户端认证前触发内存损坏趋向 RCE（pre-auth）。",
        severity="critical", cvss=9.2,
        affected_max=(1, 11, 1), affected_range="≤ 1.11.1",
        fixed="上游修复 commit 97acf3dfda80c91c3a8c9f2372546301d4a1a7a8 (PR #2052)；"
              "各发行版回灌至 1.11.1（如 Ubuntu 1.11.1-1ubuntu0.x.x.2），"
              "无独立新版本号——须按发行版公告核实是否含补丁。",
        detect_cmd="curl", detect_parse="curl --version 输出中的 libssh2/x.y.z",
        references=[
            "https://nvd.nist.gov/vuln/detail/CVE-2026-55200",
            "https://github.com/libssh2/libssh2/commit/97acf3dfda80c91c3a8c9f2372546301d4a1a7a8",
            "https://usn.ubuntu.com/USN-8486-1/",
        ],
    ),
    Advisory(
        cve="CVE-2026-55199",
        product="libssh2",
        summary="SSH_MSG_EXT_INFO 处理中的 pre-auth 拒绝服务：恶意 SSH 服务器可令客户端陷入 CPU 死循环。",
        severity="high", cvss=8.2,
        affected_max=(1, 11, 1), affected_range="≤ 1.11.1",
        fixed="同 CVE-2026-55200 上游修复（commit 97acf3df，发行版回灌）。",
        detect_cmd="curl", detect_parse="curl --version 中的 libssh2/x.y.z",
        references=[
            "https://nvd.nist.gov/vuln/detail/CVE-2026-55199",
            "https://usn.ubuntu.com/USN-8486-1/",
        ],
    ),
    Advisory(
        cve="CVE-2025-15661",
        product="libssh2",
        summary="sftp_symlink() 处理不当，恶意 SSH 服务器/中间人可泄露敏感信息或致拒绝服务（SFTP 堆越界读）。",
        severity="high", cvss=8.3,
        affected_max=(1, 11, 1), affected_range="≤ 1.11.1",
        fixed="同 CVE-2026-55200 上游修复（commit 97acf3df，发行版回灌）。",
        detect_cmd="curl", detect_parse="curl --version 中的 libssh2/x.y.z",
        references=[
            "https://nvd.nist.gov/vuln/detail/CVE-2025-15661",
            "https://usn.ubuntu.com/USN-8486-1/",
        ],
    ),
    Advisory(
        cve="CVE-2026-20896",
        product="Gitea (Docker 自托管)",
        summary="Docker 部署的自托管 Gitea 存在鉴权绕过/用户冒充，未认证攻击者可控任意账户并接管 Git 服务器。",
        severity="critical", cvss=9.8,
        affected_max=(1, 26, 2), affected_range="< 1.26.3",
        fixed="Gitea 1.26.3（升级容器镜像、重启、轮换凭据并审查 token/管理员会话）。",
        detect_cmd="gitea", detect_parse="gitea --version",
        references=[
            "https://nvd.nist.gov/vuln/detail/CVE-2026-20896",
        ],
    ),
    Advisory(
        cve="CVE-2026-58053",
        product="Gitea act_runner (Docker 后端)",
        summary="通过 act 0.262.0 Docker 后端的 act_runner，具工作流执行权限者可在 runner 宿主机上从工作流提升到 root。",
        severity="critical", cvss=9.9,
        affected_max=None, affected_range="act_runner + Docker 后端 (act 0.262.0)",
        fixed="官方修复状态撰写时未全部纳入概览；临时缓解：避免用 Docker 后端跑不可信工作流、"
              "收紧 runner 权限与宿主机命名空间隔离。",
        detect_cmd="gitea", detect_parse="act_runner 版本（如已安装）",
        references=[
            "https://nvd.nist.gov/vuln/detail/CVE-2026-58053",
        ],
    ),
]

# ── 未核实线索（exploitarium 点名但无 CVE / 多为 AI 模糊测试噪声）──────────────
# 诚实标注：仅作排查线索，须以待厂商/研究者复核后的官方公告为准，不计入「受影响」判定。
WATCHLIST: List[Dict[str, str]] = [
    {"product": p, "note": "exploitarium 点名，尚无 CVE / 未独立复现；按官方公告核实后再处置。"}
    for p in (
        "7-Zip", "FFmpeg (RASC 解码器)", "VLC", "AnyDesk", "RustDesk", "OpenVPN",
        "c-ares", "Docker (cp copyout 逃逸)", "nmap", "Firefox", "PHP", "Splunk",
        "Floci", "QEMU", "ImageMagick", "Ghidra", "MyBB",
    )
]


def _parse_version(text: str) -> Optional[Tuple[int, ...]]:
    """从任意版本字符串里抓第一个 x[.y[.z]] 元组。无法解析返回 None。"""
    import re
    m = re.search(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?", text)
    if not m:
        return None
    return tuple(int(x) for x in m.groups() if x is not None)


class SecurityAuditAdapter(BaseAgentAdapter):
    """防御型本地漏洞自查：只读巡检本机组件版本，对照公开 CVE 元数据给处置建议。

    绝不包含/下载/运行任何 exploit 代码；拒绝任何外部目标。
    """

    engine_id = "security-audit"

    def __init__(self) -> None:
        # 探测执行器（测试可注入伪造返回值，默认走真实本地只读子进程）。
        self._runner = self._real_run

    # ── BaseAgentAdapter 契约 ──────────────────────────────────────────────
    def advertise_capabilities(self) -> list[Capability]:
        return [Capability.SECURITY_AUDIT]

    def health(self) -> bool:
        # 纯本地只读能力，构造即健康（不依赖任何外部服务/密钥）。
        return True

    def invoke(self, req: InvokeRequest) -> InvokeResult:
        payload = req.payload or {}
        # 红线：只扫本机。任何外部目标一律诚实拒绝（理念5 权限边界）。
        scope = payload.get("scope", "localhost")
        external = payload.get("external_target") or payload.get("target")
        if external or scope not in ("localhost", "local", None, ""):
            return InvokeResult(
                ok=False,
                error="security.audit 仅巡检本机环境（理念5 权限边界），拒绝外部目标 "
                      f"{external or scope!r}；本适配器不含也不运行任何攻击代码。",
            )
        include_watch = bool(payload.get("include_watchlist", False))
        findings = self._audit(include_watch=include_watch)
        report = self._build_report(findings, include_watch)
        # 整体置信：能真实探测到的组件数越多，结论越可信（延续理念6 三级量化）。
        detectable = sum(1 for f in findings if f["status"] != "not_present")
        conf = assess(detectable, reason_fmt=lambda n: f"本机真实探测到 {n} 个相关组件：置信随可观测样本数上升")
        report["confidence"] = conf.to_dict()
        return InvokeResult(ok=True, data=report)

    # ── 内部实现 ──────────────────────────────────────────────────────────
    def _real_run(self, cmd: str) -> Optional[str]:
        """运行只读版本探测命令，返回 stdout 文本或 None。仅本机、超时保护。"""
        exe = shutil.which(cmd)
        if not exe:
            return None
        try:
            proc = subprocess.run(
                [exe, "--version"], capture_output=True, text=True,
                timeout=5, shell=False,
            )
            out = (proc.stdout or "") + (proc.stderr or "")
            return out.strip() or None
        except Exception as e:  # noqa: BLE001 - 探测失败不影响整体（诚实标 unknown）
            logger.debug("security.audit 探测 %s 失败: %s", cmd, e)
            return None

    def _detect(self, adv: Advisory) -> Tuple[bool, Optional[str]]:
        """返回 (是否安装, 抓到的版本文本)。detect_cmd 为空或探测失败→(False, None)。"""
        if not adv.detect_cmd:
            return (False, None)
        out = self._runner(adv.detect_cmd)
        if not out:
            return (False, None)
        # libssh2 通过 curl --version 暴露，需从输出里抓 libssh2/x.y.z
        if adv.product == "libssh2":
            import re
            m = re.search(r"libssh2/(\d+\.\d+\.\d+)", out)
            return (True, (m.group(1) if m else None))
        # 通用：抓首个 x.y.z 版本号，保证 detected_version 干净可复核
        tup = _parse_version(out)
        return (True, (".".join(map(str, tup)) if tup else None))

    def _status_for(self, adv: Advisory, present: bool, version: Optional[str]):
        """对照版本区间判定状态。"""
        if not present:
            return "not_present", "本机未检测到该组件（或无法定位可执行文件）。"
        if version is None:
            return "unknown", "组件存在但无法解析版本；请人工按参考链接核实。"
        if adv.affected_max is None:
            return "unknown", "组件存在；该漏洞固定版本撰写时未全部公开，请按参考链接核实是否已修复。"
        det = _parse_version(version)
        if det is None:
            return "unknown", f"版本文本『{version}』无法解析；请人工核实。"
        if det <= adv.affected_max:
            note = ("版本处于受影响区间；注意发行版可能已将补丁回灌至同版本号，"
                    "须按发行版安全公告确认是否含修复。") if adv.product == "libssh2" else \
                   "版本处于受影响区间，建议尽快升级。"
            return "affected", note
        return "patched", "版本已超出受影响区间，视为已修复。"

    def _audit(self, include_watch: bool) -> List[Dict[str, Any]]:
        findings: List[Dict[str, Any]] = []
        for adv in ADVISORIES:
            present, version = self._detect(adv)
            status, note = self._status_for(adv, present, version)
            findings.append({
                "cve": adv.cve,
                "product": adv.product,
                "severity": adv.severity,
                "cvss": adv.cvss,
                "status": status,
                "detected_version": version,
                "affected_range": adv.affected_range,
                "fixed": adv.fixed,
                "summary": adv.summary,
                "recommendation": note,
                "references": adv.references,
                "verified": adv.verified,
            })
        if include_watch:
            for w in WATCHLIST:
                findings.append({
                    "cve": None,
                    "product": w["product"],
                    "severity": "unverified",
                    "cvss": None,
                    "status": "watch",
                    "detected_version": None,
                    "affected_range": "未确认",
                    "fixed": "待核实",
                    "summary": w["note"],
                    "recommendation": "作为排查线索；仅在厂商/研究者发布官方公告后才计入受影响判定。",
                    "references": [],
                    "verified": False,
                })
        return findings

    def _build_report(self, findings: List[Dict[str, Any]], include_watch: bool) -> Dict[str, Any]:
        counts: Dict[str, int] = {}
        for f in findings:
            counts[f["status"]] = counts.get(f["status"], 0) + 1
        return {
            "capability": "security.audit",
            "scope": "localhost",
            "mode": "defensive-only / read-only / no exploit code",
            "generated_at": _now_iso(),
            "summary": counts,
            "findings": findings,
            "disclaimer": "纯防御性本地自查：仅使用公开 CVE 元数据，不含/不下载/不运行任何 "
                          "exploit 或 PoC 代码；外部目标一律拒绝。情报源于公开安全公告，"
                          "建议以厂商官方公告为最终处置依据。",
        }


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
