# AOS 深度检查报告（2026-08-07）

> 诚实分级：**②级**（代码静态审计 + 单元/脚本实测实证）。
> 未做③级（真 LLM 端到端 + 真主机联网）。
> 基线提交：`83a417c`（feature/infra-setup）。检查范围：32 个未提交的 M 文件 + 全仓交叉扫描。
> 方法：4 组只读审计 agent 读源码 → **每一条结论由我本人重新实跑复核**，站不住的直接驳回。

---

## 〇、可直接照贴的改动清单（全部在你的 M 文件里，我一个都没动）

按修复性价比排序。每条都是"找到这行 → 换成这行"，不需要理解上下文。

**① `src/kernel/value_ledger.py`** —— 把 `import ast` 从第 211 行的函数体内**提到文件顶部**的 import 区。（一行，修完母纲原则 6 的守门就真生效了，`test_value_siphon_scanner_actually_works` 随之转绿）

**② `src/kernel/evolve/evolve_engine.py:980-981`**
```python
# 改前
            decided = [p for p in updated if p.status in ("applied", "rejected")]
            pending = [p for p in updated if p.status not in ("applied", "rejected")]
# 改后
            decided = [p for p in updated if p.applied or p.rejected]
            pending = [p for p in updated if not (p.applied or p.rejected)]
```

**③ `src/kernel/compliance.py:298`**
```python
# 改前
        "bank_card":   re.compile(r"(?<!\d)\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{1,7}(?!\d)"),
# 改后
        "bank_card":   re.compile(r"(?<![0-9a-zA-Z])\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{1,7}(?![0-9a-zA-Z])"),
```

**④ `src/kernel/immunity.py:358` 和 `:374`**（两处一模一样）
```python
# 改前
                           lambda: self._fallback(model) if self._fallback(model) else None)
# 改后
                           lambda: self._fallback(model) or None)
```

**⑤ `src/kernel/approval/approval_store.py`** —— `approve()`（第 320 行）与 `reject()`（第 358 行）开头补过期判定。建议先把 `list_pending` 里第 248-254 行那段抽成方法：
```python
    def _is_expired(self, a) -> bool:
        if not a.expires_at:
            return False
        try:
            return time.mktime(time.strptime(a.expires_at[:19], "%Y-%m-%dT%H:%M:%S")) < time.time()
        except (ValueError, OverflowError):
            return False
```
然后在 `approve()` 里 `if a.status != "pending"` 那个判断**之后**加：
```python
                if self._is_expired(a):
                    a.status = "expired"
                    items[i] = a
                    self._cache = items
                    self._persist()
                    return {"ok": False, "error": "审批已过期", "approval": a.to_dict()}
```

**⑥ `src/core/fabric/resilience.py:78-83`** —— 超时不要写死 `None`，改成挂起待收割：
```python
# 改前
    if th.is_alive() or 'err' in box:
        logger.warning('guarded_import: %s unavailable (timeout=%.1fs)', name, to)
        with _PROBE_LOCK:
            _PROBED[name] = None
        return None
# 改后
    if th.is_alive():
        # 超时不等于失败：线程仍在跑，稍后可能成功。挂起待下次收割，
        # 不写死 _PROBED，避免慢依赖（torch/transformers 冷启动）被永久判死。
        with _PROBE_LOCK:
            _PENDING[name] = (th, box)
        logger.warning('guarded_import: %s 探测超时(%.1fs)，挂起待重试', name, to)
        return None
    if 'err' in box:
        with _PROBE_LOCK:
            _PROBED[name] = None
        return None
```
并在函数开头的快速路径后补一段收割：
```python
    # 收割上次超时挂起的探测：线程若已完成则取结果，无需重新 import
    pend = _PENDING.get(name)
    if pend is not None and not pend[0].is_alive():
        with _PROBE_LOCK:
            _PENDING.pop(name, None)
            _PROBED[name] = pend[1].get('m')
        return _PROBED[name]
```
（模块级加 `_PENDING: dict = {}`）

**⑦ `src/execution/sandbox.py::_check_dangerous_patterns`** —— 这条**不要用补丁思路加正则**，见 P0-3，需要换成 AST 白名单。工作量最大，建议单独排期。

**⑧ `src/kernel/memory_control.py::_compact`** —— 见 P1-2，建议把 `compliance/audit.py::_enforce_rotation` 抽成公共 `utils/rotate_jsonl.py`，三处（audit / cost_tracker / memory_control）统一调用。

---

## 零、结论速览

| 级别 | 条数 | 说明 |
|---|---|---|
| P0 已修 | 1 | `lfm_adapter` tier 少括号 → 已提交 `83a417c` |
| P0 待修 | 3 | 反虹吸扫描恒空 / 沙箱形同虚设 / evolve 字段漂移 |
| P1 待修 | 5 | 审批过期无效 / 限存储无效 / 免疫双调 / 导入永久判死 / 银行卡正则误伤 |
| P1 数据 | 1 | 蒸馏记忆重复率 95.6% |
| **驳回** | **5** | 审计 agent 过报，实测不成立 |

**最严重的不是某个 bug，而是一条"假绿链"**：母纲原则 6 的守门测试 `test_no_value_siphon` 是绿的，但它绿得毫无意义——被测函数因作用域错误恒返回空集，测试断言"空集"当然永远通过。**绿灯本身在说谎。**

---

## 一、P0 —— 已修复

### P0-1 `LFMAdapter.health_detail` 把方法对象塞进字典 → `/api/lnn/info` 恒 500 ✅ 已修

- **位置**：`src/core/fabric/adapters/lfm_adapter.py:118`
- **原码**：`"tier": self.tier,`（少了括号，塞进去的是绑定方法对象）
- **后果**：`json.dumps` 抛 `TypeError: Object of type method is not JSON serializable` → 被 `_get_lnn_info` 的 `except` 吞掉 → 在 `_send_json` 二次抛 → 对外恒返回 `{"error":"internal server error"}`。**这个接口对所有人 100% 不可用。**
- **实证**：直调 handler 复现 500；改后 `json.dumps` 通过；`tests/test_lnn_chiplet.py` 由 7/8 转 **8/8 绿**。
- **交叉扫描**：全仓 AST 扫出 25 处同形态写法，逐一排除"合法分发表"与 `@property` 后，**确认这是唯一真 bug**（其余 24 处是 `protocol`/`llm_router`/`engineering`/`repo_agent` 的方法分发表，正当用法）。
- **提交**：`83a417c`（同时修了 `test_lnn_http_dispatch` 与 `http_server` 新增强制 Bearer 鉴权不对齐的问题）

---

## 二、P0 —— 待修（均在 M 文件，我未动）

### P0-2 反虹吸扫描恒空 → 母纲原则 6「零外泄证明」空转，且守门测试假绿

- **位置**：`src/kernel/value_ledger.py`，`import ast` 写在 **211 行的函数体内部**，而真正做解析的 `_ast_imports` 是**模块级函数**。
- **失效链**：`_ast_imports` 里用 `ast.parse` → 模块全局无 `ast` → `NameError` → 被外层 `except Exception` 吞掉 → `scan_value_siphon()` **恒返回 `[]`**。
- **实证**：
  ```
  _ast_imports(含 requests 的文件) -> []          # 应该返回 ['requests','socket']
  scan_value_siphon(该目录)        -> []          # 应该报告外联风险
  模块 globals 里有 ast 吗          -> False
  ```
- **假绿链（最要命）**：`tests/test_no_harvest_charter.py::test_no_value_siphon` 断言"扫描结果为空"，而被测函数**恒空** → 测试**永远绿**，但它证明的是"函数坏了"，不是"没有虹吸"。**这条绿灯目前不具备任何守门能力。**
- **改法**：把 `import ast` 提到模块顶部。**同时**把守门测试改成"先喂一个已知含外联的样本文件，断言能扫出来（阳性对照），再断言真实代码库为空"——否则同类假绿还会再犯。

### P0-3 代码沙箱危险模式检查形同虚设

- **位置**：`src/execution/sandbox.py::_check_dangerous_patterns`
- **实证**（7 个恶意载荷，只拦住 1 个）：

  | 载荷 | 结果 |
  |---|---|
  | `import os; os.system("calc")` | **BLOCKED** ✅ |
  | `from subprocess import *` + `Popen([...])` | BYPASS ❌ |
  | `f = os.system; f("calc")`（别名） | BYPASS ❌ |
  | `getattr(os, "sys"+"tem")("calc")` | BYPASS ❌ |
  | `importlib.import_module("os").system(...)` | BYPASS ❌ |
  | `eval("__import__(chr(111)+chr(115)).system(1)")` | BYPASS ❌ |
  | `builtins.__import__("os").system(...)` | BYPASS ❌ |

- **性质**：字符串/正则黑名单在 Python 上**原理性不可能拦住动态求值**。
- **改法（不要继续加正则）**：走 AST 白名单 —— 解析后拒绝 `Import`/`ImportFrom` 非白名单模块、拒绝 `eval`/`exec`/`compile`/`__import__`/`getattr` 动态调用节点；真正的隔离交给子进程 + 资源限制，黑名单只当第一道提示。

### P0-4 `evolve_engine` 字段名漂移 → 5 个测试红

- **位置**：`src/kernel/evolve/evolve_engine.py:980-981`
- **原码**：
  ```python
  decided = [p for p in updated if p.status in ("applied", "rejected")]
  pending = [p for p in updated if p.status not in ("applied", "rejected")]
  ```
- **事实**：`OptimizationProposal` 只有 `applied: bool`（第 88 行）与 `rejected: bool`（第 98 行），**没有 `status` 字段** → 运行时 `AttributeError`。
- **触发条件很关键**：这段代码在 `if len(updated) > _MAX_PROPOSALS_PER_WF:`（第 979 行，上限 200）**内部**——也就是说，**它恰好长在理念8「限存储」的淘汰路径上**。平时不触发，一旦提案数超 200 需要淘汰，`_update_proposal` 直接抛异常，提案文件写不进去。
- **改法**：
  ```python
  decided = [p for p in updated if p.applied or p.rejected]
  pending = [p for p in updated if not (p.applied or p.rejected)]
  ```

> **横向发现（比单条 bug 重要）**：理念8「限存储」的三处实现里，**两处是坏的**——
> `memory_control._compact` 上限完全不生效（P1-2）、`evolve._update_proposal` 淘汰时抛异常（本条）；
> 只有 `compliance/audit.py::_enforce_rotation` + `pulse/cost_tracker.py` 那套（最旧搬 `.archived.jsonl` 冷存）是对的。
> 建议把 audit.py 那段抽成公共工具 `utils/rotate_jsonl.py`，三处统一调用，而不是各写各的。这是 coherent 修法，不是打补丁。

---

## 三、P1 —— 待修

### P1-1 审批过期形同虚设：过期件"从列表消失"但仍可批准

- **位置**：`src/kernel/approval/approval_store.py` —— `expires_at` **只在 `list_pending`（第 248 行）被检查**，`approve()`（第 320 行）**只看 `status`，从不看过期**。
- **实证**：
  ```
  创建 high 风险审批（ttl=1s）
  过期后 list_pending 条数 = 0        <- 已从人工审阅列表消失
  过期后调 approve      -> ok=True status=approved
  ```
- **危害**：任何持有 id 的调用方（陈旧 UI、自动化脚本、日志里翻出来的 id）都能批准一条**已过期的高风险操作**；更隐蔽的是——因为它不在待审列表里，**人工审阅者根本看不见它被批准了**。
- **改法**：`approve()` / `reject()` 里复用同一份过期判定（抽成 `_is_expired(a)`），过期返回 `{"ok": False, "error": "已过期"}`，并把状态落成 `expired` 而非留在 `pending`。

### P1-2 理念8「限存储」在 `memory_control` 上完全没生效

- **位置**：`src/kernel/memory_control.py::_compact`，常量 `_MAX_CONTROLLABLE = 2000`
- **事实**：`_compact` 只做"同 id 去重"，对 **N 条不同 id 不做任何淘汰**。
- **实证**：写入 2600 条不同 id → 文件实际 **2600 行**，上限完全未生效，可无限增长。
- **改法（照抄本项目自己的先例，不要静默删）**：用户手工记忆静默删除更违背数据主权。应仿照 `compliance/audit.py::_enforce_rotation` 与 `pulse/cost_tracker.py`：**最旧条目搬 `.archived.jsonl` 冷存**，主文件保持上限。`audit.py` 那套（先写归档、再重写主文件，崩溃只重复不丢失）是本仓标杆实现，直接复用。

### P1-3 免疫自愈把 fallback 回调调用两次

- **位置**：`src/kernel/immunity.py:358` 与 `:374`
- **原码**：`lambda: self._fallback(model) if self._fallback(model) else None`
- **事实**：`self._fallback` 是外部注入的回调（第 316 行）。若它有副作用（真去切换模型），这行会**一次性降两级**，跳过一个本来可用的模型。
- **改法**：`lambda: self._fallback(model) or None`（语义完全等价，只调一次）。

### P1-4 `guarded_import` 超时后永久判死，无恢复路径

- **位置**：`src/core/fabric/resilience.py:48-86`
- **事实**：`th.join(timeout)` 超时后写 `_PROBED[name] = None` **永久缓存**，但那个 daemon 线程其实还在跑、几秒后就 import 成功了。默认超时 20s，而 `torch`/`transformers`/`chromadb`/`vosk` **都不在分级表里**——冷启动 + 杀毒扫描下极易超过 20s。
- **实证**：
  ```
  第一次（超时 0.1ms） -> None
  第二次（超时 60s）   -> None      # 仍然 None！
  直接 importlib       -> <module ...>   # 模块完全可用
  ```
  一旦误判，**整个进程生命周期内该能力永久死亡**，只能重启恢复。
- **改法**：超时时不要写死 `None`。把 `(thread, box)` 存进 `_PENDING[name]`；下次调用先看该线程是否已完成——完成就"收割"结果写入 `_PROBED`，未完成才返回 None。这样慢依赖会自动恢复，且不增加任何阻塞。

### P1-5 银行卡正则字母边界放行 → 误伤

- **位置**：`src/kernel/compliance.py:298`
- **原码**：`r"(?<!\d)\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{1,7}(?!\d)"` —— 只禁数字前后缀，**放行字母前后** → `abc1234567890123456def` 被当成银行卡脱敏。
- **改法**：`r"(?<![0-9a-zA-Z])\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{1,7}(?![0-9a-zA-Z])"`
- **已独立验证**：5 个有效卡号仍全部命中；字母前后 case 由 True → False；连字符 case 保持 False。
- 对应红：`tests/test_compliance_bankcard.py::test_bank_card_exact_match`

### P1-6 蒸馏记忆重复污染 95.6%

- **位置**：`src/_traces/distilled_memory.jsonl`
- **实证**：总 **5683 条**，唯一内容仅 **251 条** → 重复率 **95.6%**。
- **危害**：蒸馏本应压缩，现在在放大。检索命中被同一条内容刷屏，长期挤占上下文预算。
- **改法**：写入前按内容哈希去重（`content` 归一化后 sha1 作为幂等键）；已有文件做一次离线去重（保留最新时间戳那条）。

---

## 四、驳回 —— 审计 agent 过报，我实测不成立

诚实起见，这几条我明确驳回，不计入债务：

1. **`security.py` 本地回环免鉴权可被浏览器 CSRF 打穿** —— **不成立**。实测本仓 FastAPI 版本在 `Content-Type: text/plain` 与**无 Content-Type** 时均返回 422，不会当 JSON 解析；要打进去必须带 `application/json`，那就触发预检、被 CORS 挡住。且 `_is_trusted_localhost` 用的是 `request.client.host`（真 TCP 对端，伪造不了），还额外拒了 5 个代理头。
2. **DNS rebinding** —— **不成立**。`main.py:236` 已启用 `TrustedHostMiddleware`，默认白名单 `localhost/127.0.0.1/[::1]`。
3. **CORS 通配符 + 凭据泄露** —— **不成立**。`main.py:178-185` 生产环境含 `*` 直接 `raise`，开发环境自动关 `allow_credentials`。
4. **`keystore.py` 密钥明文落盘 / 权限未收紧** —— **不成立**。`os.open(..., 0o600)` 最小权限创建 + `chmod` + Fernet + HKDF 派生 + 双检锁；生产缺密钥是 **fail-fast raise**，只有开发环境才自动生成。
5. **`resilience.py` 熔断器状态机写反** —— **不成立**。该文件里根本没有熔断器（只有守护导入），熔断在 `resilience_bus.py`。此条系 agent 脑补。

另：`/studio`、`/bidding` 两个免鉴权前缀经查只是 `StaticFiles` 静态前端挂载，无 API 副作用面，不构成漏洞。

---

## 五、方法论教训（比单个 bug 更值钱）

1. **"测试绿"≠"功能对"。** `test_no_value_siphon` 是活教材：断言空集 + 被测函数恒空 = 永久假绿。**凡是断言"结果为空/无违规"的守门测试，必须配一个阳性对照样本**，否则它只能证明函数没崩，证明不了它在工作。

   **本轮已做全仓排查（结论收窄，不夸大）**：AST 扫出 110 个"断言全为空/假"的测试，其中绝大多数是正当负向用例（`get_nonexistent_returns_none` 之类，另有正向测试配对）。真正危险的只有"扫全仓再断言无违规"这一族。逐个做阳性对照后：
   - `test_no_revenue_commission_logic` —— **健康**。实测 `os.walk(SRC)` 扫到 **681 个 .py 文件**，正则对阳性样本 `platform_fee` 命中。
   - `test_no_feature_wall_zero_quota_in_any_plan` / `test_free_plan_covers_every_metric` —— **健康**。遍历真实字典 `_PLAN_QUOTAS`，导入失败会 error 而非静默绿。
   - `test_no_hardcoded_absolute_repo_path_in_tenant_module` —— **健康**。读具体文件，文件缺失会抛异常。
   - `test_no_value_siphon` —— **唯一假绿**。

   即：**宪章守门 32 项里只有 1 项失效**，不是一片假绿。
2. **字段名漂移是重构期的头号杀手。** `p.status` 这类"改了 dataclass 没改调用点"，静态检查抓不到（动态属性），单测没覆盖就直接带进生产。建议对核心 dataclass 加 `__slots__` 或跑一遍 AST 属性访问比对。
3. **黑名单式安全（沙箱正则）在动态语言上是纸糊的。** 7 打 1 的结果说明问题不在"规则不够多"，而在方法选错了。
4. **审计要复核。** 4 组 agent 报上来的条目里，**5 条经实测不成立**（占比不低）。凡是"我读代码觉得有问题"的结论，都必须能跑出复现证据才算数。

---

## 六、附：本轮我实际改动的文件（只此两处）

| 文件 | 改动 | 是否 M 文件 |
|---|---|---|
| `src/core/fabric/adapters/lfm_adapter.py` | `"tier": self.tier` → `self.tier()` | 否（已提交代码） |
| `tests/test_lnn_chiplet.py` | 补 Bearer token 与请求头，对齐 `http_server` 新增强制鉴权 | 否 |

**你正在编辑的 32 个 M 文件，本轮一个都没碰。** 上面所有 P0-2 ~ P1-5 都只给了精确改法，等你自己贴或授权我动。
