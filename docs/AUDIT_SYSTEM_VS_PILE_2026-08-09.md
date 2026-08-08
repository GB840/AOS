# 审计结论：AOS 是「一套系统」还是「一堆模块」？（2026-08-09）

> 触发：用户质疑「你弄的完全就不是一个，而是弄的一堆，不是一套系统」。
> 方法：不再只查文件存在/函数体有无（那是 ② 级弱尺），改查**运行时焊接度**——模块是否被 import 链接进统一运行时。

## 一、焊接度审计（46 个 ✅ 节点里带 .py 的 42 个）

| 指标 | 数值 |
|------|------|
| 被运行时任何代码 import（焊进系统） | **8 个** |
| 孤儿（从不被任何 .py import，纯磁盘躺着） | **34 个（81%）** |

孤儿清单（白皮书标 ✅ 但实际未接入运行时）：
CONST1, CONST3, L0A, L0B, L0C, L1A, L1E3, L1G, L1H, L2B, L2C, L2D, L2F, L2G, L2H,
L3A, L3D, L4A, L4B, L4C, L4D, L5A, L5B, L5C, L5D, L5E, L5F, L5G, L6A, L7A, L7C, L7D, L7E, L8A

grep 独立复核（按包名精确查，排除子串误匹配）：
`life_state:0` `soul:0` `fractal:0` `spirit:0` `desire:0` `rhythm:0` `metacognition:0` 处引用。

## 二、两套脊柱对比（核心发现）

### A. 白皮书描述的「生命体 OS」脊柱
模块：`kernel/life_state`、`kernel/soul/*`、`kernel/spirit/*`、`kernel/fractal/*`、`kernel/body/*`
- 域内互引：**0 处**
- 被运行系统引用：**0 处**
- 结论：**孤岛文件堆，不构成系统**。白皮书「一套生命体 OS、46 机制落地」在集成层面不成立。

### B. 真正在跑的脊柱（main.py 实际 import）
模块：`core.fabric` + `kernel.autopilot` + `kernel.live` + `kernel.plugins` + `kernel.danchuang`
- 域内交叉引用：**216 处，成网**
- 结论：**这是仓库里唯一成系统的部分**，但它与白皮书描述的系统**不是同一套**。

## 三、诚实判定

- 白皮书 V6 的「46 ✅ 真代码、0 空壳」在**文件存在 + 函数体**层面成立（前轮已核）。
- 但白皮书整体叙事「一套生命体 OS」在**系统集成**层面**虚假**：81% 标 ✅ 模块未接入运行时，且其描述的那套脊柱内部 0 互引、根本不成系统。
- 这是 ③ 级（系统集成/端到端）缺失，却被白皮书以「机制已落地 ✅」的叙事**暗示为已建成**。属诚实越级。

## 四、待决策（用户拍板方向）

反缝补铁律要求「统一 coherent 推力，不分头打补丁」。当前 repo 实际是两套并存、互不咬合。需选定**唯一 canonical 脊柱**：

- 方向甲（推荐，低成本高诚实）：白皮书改为如实描述——运行系统是 `core.fabric/autopilot/plugins/danchuang/live` 这套（216 互引、成网），那 34 个孤儿模块标注为「愿景骨架 / ② 机制就绪未接入」，不再以 ✅ 暗示已建成系统。
- 方向乙（高成本）：若用户坚持以白皮书「生命体 OS」为 canonical，则需把 34 个孤儿模块焊入统一脊柱、消除孤岛——这是一次系统性构建，非文档修正。

> 无论甲或乙，都须先把「两套并存、白皮书描述的那套未成系统」这一点写进白皮书诚实声明，停止越级暗示。

---

## 五、整改结果（用户拍板「两种结合、全部开始」后执行）

用户否决了二选一，要求甲乙同做。已执行并实证：

### 甲：焊活（孤儿归零）

新增焊接件 `src/kernel/lifeform_runtime.py`（`LifeformRuntime`），把生命体层模块在启动时
统一实例化并注册进 FabricHub；挂载点在 `src/api/main.py` 的 `_deferred_live_init`
（`app.state.lifeform`），沿用运行脊柱既有 best-effort 范式（单模块失败不阻断启动）。

实证（aos venv 实跑）：

| 指标 | 整改前 | 整改后 |
|---|---|---|
| ✅ 节点被运行时 import | 8 / 42 | **42 / 42** |
| 孤儿模块 | **34（81%）** | **0** |
| 运行时真实例化组件 | 0 | **31，构造失败 0** |

> 审计脚本 `.workbuddy/audit_wiring_v6.py` 同步修正：原版只统计 AST 的
> `Import`/`ImportFrom`，看不见 `__import__("...")` 动态导入，会把已焊活的模块
> 误判为孤儿。已补动态导入识别，避免用错尺子自欺。

### 乙：真驱动（不止挂载，参与决策）

- `LifeformRuntime.pick_model()`：读磁盘真实 `life_state.energy`，低于阈值自动降档到轻模型。
- `LifeformRuntime.on_run_finished()`：每次推理回写体征（energy 衰减、失败抬 debt），
  并喂给 `homeostasis.tick()` 产出真实纠偏动作 → 形成「跑得多 → 能量降 → 下次自动降档」闭环。
- `kernel/autopilot.py` 接线：`_lifeform_pick_model()` 已插入 `_openai_compat_generate`
  与 `_llm_generate` 的 Ollama 兜底两处模型选择点；`_lifeform_after_run()` 在成功/失败后回写体征。
- **刻意不降档的地方**：反思链路（`_ollama_generate` 默认模型）保持重模型。
  反思模型换小会退化成鹦鹉，使自进化闭环静默变成假闭环（历史踩坑，见 memory）。
- 顺带修掉一处实质缺陷：原挂载用裸 `Homeostasis()`，未注册任何体征，`tick()` 恒返回空
  —— 挂了等于白挂。已改为 `Homeostasis.with_defaults()`（5 项体征）。
- 可见性：新增 `GET /api/lifeform`，返回活体组件清单 + 真实体征 + 当前自主选型档位。

### 诚实分级

- 甲、乙均为 **② 级**：代码改动真、单测实证真（`tests/test_lifeform_drives_runtime.py` 8 项全绿；
  相关回归 131 项全绿）。
- **尚未 ③ 级**：未在真 LLM + 真主机上跑完整端到端，验证降档在真实负载下按预期发生。
  需用户主机启 `start_all.sh` 后访问 `/api/lifeform` 并观察连续任务后的 `picked_now` 变化。
- 白皮书本身**尚未修订**：仍需把「哪些是运行脊柱、哪些是生命体层、各自诚实级别」写进声明，
  停止用 ✅ 越级暗示 ③ 级已达成。这是下一步待办。
