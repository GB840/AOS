# AOS 防御型本地漏洞自查能力（security.audit）

> 一句话：把「exploitarium 式零日情报」转化为**对自家环境的只读巡检能力**，而非攻击能力。

## 1. 它是什么 / 不是什么

AOS（`src/core/fabric/adapters/security_audit_adapter.py`，能力 `security.audit`）是一个
**只读、仅本机、纯防御**的漏洞自查适配器，按 AOS「能力即路由」架构注册，可被
`FabricHub.route(capability="security.audit")` 直接调度。

| 是 | 不是 |
|---|---|
| 用**公开 CVE 元数据**（受影响版本/补丁/参考链接）对照你本机组件版本 | 任何 exploit / PoC 代码的载体 |
| 只读 `--version` 类探测，零副作用 | 下载、运行或改编 exploitarium 等攻击代码 |
| 仅扫描 localhost，外部目标一律拒绝 | 一个能去打陌生系统的「攻击能力」 |
| 诚实标注「版本 ≤ 受影响区间 ≠ 一定中招」（发行版常回灌补丁） | 夸大或伪造风险结论 |

## 2. 红线（对应 AGENTS.md 理念 5「权限即边界」+ 6/9「诚实可验证」）

1. **绝不武器化**：本适配器不包含、不下载、不运行任何 exploit。它只消费已公开的
   漏洞**元数据**。把零日 PoC 合集做成「可自主调度的攻击能力」越界且不可审计，故不做。
2. **仅本机**：载荷里一旦出现 `external_target` / 非 `localhost` 的 `scope`，直接
   返回 `ok=False` 并说明拒绝理由（见 `test_refuses_external_target`）。
3. **可复核**：知识库每条都带 `references`（NVD / 上游 commit / 发行版 USN），
   声明都可追到公开来源，不混编臆测。

## 3. 情报来源与诚实说明

2026-06 出现的 `bikini/exploitarium` 零日 PoC 合集，**其攻击代码本能力一概不取**；
我们只把其中**已被防御方独立确认、分配了 CVE 的真实漏洞**转译为自查项，其余
（7-Zip / FFmpeg / VLC / RustDesk / OpenVPN / c-ares / Docker / nmap / Firefox /
PHP / Splunk / Floci / QEMU / ImageMagick / Ghidra / MyBB 等点名项）仅作为
`watchlist` 排查线索，且**明确标注「无 CVE / 未独立复现，须核实」**，不计入受影响判定。

> 这正是 AOS 对「把这份情报变成系统能力」诉求的合规落地：同一条情报，我们做**盾**（自查），
> 不做**矛**（攻击）。也契合 AOS 新范式「诚实可验证」的第一公民定位。

## 4. 已核实知识库（截至 2026-07-19，多源交叉核实）

| CVE | 产品 | 严重度 | CVSS | 受影响 | 修复 |
|---|---|---|---|---|---|
| CVE-2026-55200 | libssh2 | critical | 9.2 | ≤ 1.11.1 | 上游 commit `97acf3df`（PR#2052）；发行版回灌至 1.11.1，无独立新版本号 |
| CVE-2026-55199 | libssh2 | high | 8.2 | ≤ 1.11.1 | 同上（pre-auth DoS） |
| CVE-2025-15661 | libssh2 | high | 8.3 | ≤ 1.11.1 | 同上（SFTP 堆越界读） |
| CVE-2026-20896 | Gitea (Docker 自托管) | critical | 9.8 | < 1.26.3 | Gitea 1.26.3 |
| CVE-2026-58053 | Gitea act_runner (Docker 后端) | critical | 9.9 | act 0.262.0 | 固定版本撰写时未全公开；缓解：避免 Docker 后端跑不可信工作流 |

检测方式：`curl --version` 暴露 `libssh2/x.y.z`；`gitea --version` 取版本。
检测不到的组件标 `not_present` / `unknown`，绝不谎报「安全」。

## 5. 用法

```python
from core.fabric.adapter import InvokeRequest
from core.fabric.capability import Capability
from core.fabric.adapters.security_audit_adapter import SecurityAuditAdapter

ad = SecurityAuditAdapter()
res = ad.invoke(InvokeRequest(
    capability=Capability.SECURITY_AUDIT,
    payload={"scope": "localhost", "include_watchlist": False},
))
# res.data: { scope, mode, summary, findings[], confidence, disclaimer }
```

返回 `findings` 每条含 `status`：`affected` / `patched` / `not_present` / `unknown` /
`watch`（线索），并附 `recommendation` 与 `references`。整体带三级量化置信（理念 6）。

## 6. 测试

`tests/test_security_audit_adapter.py`（7 passed）：能力声明、外部目标拒绝、libssh2
受影响/已修复判定、Gitea 受影响判定、知识库完整性、watchlist 按需纳入。
探测通过注入 `_runner` 伪造，不触碰任何真实攻击面。
