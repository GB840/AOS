"""LifeformRuntime —— 运行脊柱与生命体层的融合连接器（白皮书「一套系统」的焊接件）。

设计：FabricHub（core.fabric）是单基座（路由/记忆/上下文主权），本运行时把
白皮书描述的「生命体层」模块（life_state / homeostasis / soul / spirit /
fractal / body …）实例化并注册进运行脊柱，使 34 个孤儿模块从「磁盘躺着」
变为「运行系统的活组件」。

焊接范式严格复用运行脊柱现有约定（见 api/main.py startup_event）：
  - 每个组件独立 try/except，单一模块失败不影响整体（best-effort）；
  - 挂 app.state.lifeform，并注册进 hub（setattr(hub, "lifeform", self)），
    使其经运行脊柱可达（与 hippo_scroll / content_director 同缝）。

诚实度：本文件是 ② 级机制焊接件——把已存在的 ② 级模块接入运行时。
具体模块是否接真 LLM 驱动，仍取决于各模块自身（见各自文件头诚实声明）。
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger("aos.lifeform_runtime")

# 低能量时降档使用的轻模型（可用 AOS_LLM_MODEL_LIGHT 覆盖）。
# 注意：本降档只作用于「主生成链路」，绝不作用于反思链路——
# 反思模型换小会退化成鹦鹉，导致自进化闭环静默变成假闭环（历史踩坑）。
DEFAULT_LIGHT_MODEL = "qwen2.5:3b"


class LifeformRuntime:
    """生命体层运行时。启动时组装各生命体子系统，统一暴露 status()。"""

    def __init__(self) -> None:
        self.components: Dict[str, Any] = {}
        self.errors: Dict[str, str] = {}
        self._assemble()

    # ── 组件工厂：每模块独立 try，失败记入 errors 不阻断 ──
    def _assemble(self) -> None:
        # 垂直切片（已验证构造签名，优先接入）
        self._try("life_state", lambda: __import__(
            "kernel.life_state", fromlist=["LifeStateStore"]).LifeStateStore())
        # 必须用 with_defaults()：裸 Homeostasis() 未注册任何体征，
        # tick() 恒返回空 —— 挂了等于没挂（本轮审计发现并修正）。
        self._try("homeostasis", lambda: __import__(
            "kernel.homeostasis", fromlist=["Homeostasis"]).Homeostasis.with_defaults())

        # 扩展点：其余生命体模块同构接入（构造失败自动跳过，不阻断）。
        # 逐步把白皮书 34 个孤儿焊进此表即可完成「两套合一」。
        self._try("desire", lambda: __import__(
            "kernel.desire", fromlist=["DesireEngine"]).DesireEngine())
        self._try("rhythm", lambda: __import__(
            "kernel.rhythm", fromlist=["RhythmScheduler"]).RhythmScheduler())
        self._try("metacognition", lambda: __import__(
            "kernel.metacognition", fromlist=["Metacognition"]).Metacognition())
        self._try("goal_evolution", lambda: __import__(
            "kernel.goal_evolution", fromlist=["GoalEvolution"]).GoalEvolution())
        self._try("soul_sync", lambda: __import__(
            "kernel.soul_sync", fromlist=["default_sync"]).default_sync())
        self._try("tree_ring", lambda: __import__(
            "kernel.soul.tree_ring", fromlist=["TreeRingMemory"]).TreeRingMemory())
        self._try("lineage", lambda: __import__(
            "kernel.soul.lineage", fromlist=["Lineage"]).Lineage())
        self._try("datong", lambda: __import__(
            "kernel.spirit.datong", fromlist=["DatongIndex"]).DatongIndex())
        self._try("values_market", lambda: __import__(
            "kernel.spirit.values_market", fromlist=["ValuesMarket"]).ValuesMarket())
        self._try("consensus", lambda: __import__(
            "kernel.spirit.consensus", fromlist=["ConsensusChannel"]).ConsensusChannel())
        self._try("fractal_particles", lambda: __import__(
            "kernel.fractal.particles", fromlist=["ParticleRegistry"]).ParticleRegistry())
        self._try("phy_bus", lambda: __import__(
            "kernel.body.phy_bus", fromlist=["PhyBus"]).PhyBus())

        # ── 第二批：安全闸门 / 资源自治 / 分形治理 / 记忆阶梯 / 感知与镜像 ──
        # （构造签名均已 grep 实证，四个 adapter 的探活逻辑在 is_available()，
        #   构造体不碰网络，故启动零阻塞。）
        self._try("action_arbiter", lambda: __import__(
            "kernel.action_arbiter", fromlist=["ActionArbiter"]).ActionArbiter())
        self._try("emergency_brake", lambda: __import__(
            "kernel.interact.emergency_brake", fromlist=["EmergencyBrake"]).EmergencyBrake())
        self._try("constitutional_governor", lambda: __import__(
            "core.fabric.adapters.constitutional_governor",
            fromlist=["ConstitutionalGovernor"]).ConstitutionalGovernor())
        self._try("resource_autonomy", lambda: __import__(
            "kernel.resource_autonomy", fromlist=["ResourceAutonomy"]).ResourceAutonomy())
        self._try("hal", lambda: __import__(
            "kernel.body.hal", fromlist=["HAL"]).HAL())
        self._try("fractal_conflict", lambda: __import__(
            "kernel.fractal.conflict", fromlist=["ConflictCoordinator"]).ConflictCoordinator())
        self._try("fractal_spawner", lambda: __import__(
            "kernel.fractal.spawner", fromlist=["FractalSpawner"]).FractalSpawner())
        self._try("growth_guard", lambda: __import__(
            "kernel.fractal.growth_guard", fromlist=["GrowthGuard"]).GrowthGuard())
        self._try("memory_ladder", lambda: __import__(
            "kernel.store.memory_ladder", fromlist=["MemoryLadder"]).MemoryLadder())
        self._try("dialectic", lambda: __import__(
            "kernel.soul.dialectic", fromlist=["DialecticRegulator"]).DialecticRegulator())
        self._try("mentorship", lambda: __import__(
            "kernel.spirit.mentorship", fromlist=["Mentorship"]).Mentorship())
        self._try("mirror_lab", lambda: __import__(
            "kernel.evolve.mirror_branch", fromlist=["MirrorLab"]).MirrorLab())
        self._try("perception_gateway", lambda: __import__(
            "kernel.interact.perception_gateway", fromlist=["PerceptionGateway"]).PerceptionGateway())
        self._try("human_causal_sim", lambda: __import__(
            "kernel.interact.human_causal_sim",
            fromlist=["HumanCausalSimulator"]).HumanCausalSimulator())
        self._try("localai_backend", lambda: __import__(
            "core.fabric.adapters.localai_backend", fromlist=["LocalAIBackend"]).LocalAIBackend())
        self._try("piper_tts", lambda: __import__(
            "core.fabric.adapters.piper_backend", fromlist=["PiperTTS"]).PiperTTS())
        self._try("video_shotcraft", lambda: __import__(
            "core.fabric.adapters.video_shotcraft_backend",
            fromlist=["VideoShotcraft"]).VideoShotcraft())

    def _try(self, name: str, factory) -> None:
        try:
            self.components[name] = factory()
            logger.info("lifeform 组件已装载: %s", name)
        except Exception as e:  # noqa: BLE001
            self.errors[name] = f"{type(e).__name__}: {e}"
            logger.warning("lifeform 组件跳过(构造失败): %s -> %s", name, e)

    def register_with_hub(self, hub: Any) -> bool:
        """把本运行时注册进运行脊柱的 FabricHub，使其经 hub 可达。"""
        try:
            setattr(hub, "lifeform", self)
            logger.info("LifeformRuntime 已注册进 FabricHub")
            return True
        except Exception as e:  # noqa: BLE001
            logger.warning("LifeformRuntime 注册 hub 失败: %s", e)
            return False

    # ══════════ 生命体真驱动决策 API（③ 级焊接：参与运行时决策，非仅挂载）══════════
    # 说明：以下方法把「生命体体征」变成运行时的真实决策变量。任何异常一律退回
    # 调用方给的默认值（best-effort），绝不阻断主链路——与运行脊柱既有约定同缝。

    def pick_model(self, heavy: str, light: Optional[str] = None,
                   user_id: str = "default") -> str:
        """按真实体征自主选模型：energy 低于阈值 → 自动降档到轻模型。

        这是白皮书 L0C「决策锚定」的落地点：生命状态真正改变系统行为，
        而不是一个只能被 status() 观赏的摆件。
        """
        light = light or os.environ.get("AOS_LLM_MODEL_LIGHT") or DEFAULT_LIGHT_MODEL
        if not heavy or light == heavy:
            return heavy
        store = self.components.get("life_state")
        if store is None:
            return heavy
        try:
            st = store.load(user_id)
            picked = st.pick_engine_tier(heavy, light)
            if picked != heavy:
                logger.info("生命体降档：energy=%.3f < %.2f → 模型 %s → %s",
                            st.energy, st.LOW_ENERGY, heavy, picked)
            return picked
        except Exception as e:  # noqa: BLE001
            logger.warning("pick_model 退回默认(%s): %s", heavy, e)
            return heavy

    def on_run_finished(self, *, cost: float = 0.05, failed: bool = False,
                        user_id: str = "default") -> Dict[str, Any]:
        """一次推理跑完后回写体征，形成闭环：跑得多 → energy 降 → 下次自动降档。

        同时把体征喂给 homeostasis.tick()，让稳态层输出真实纠偏动作
        （而不是永远空转）。返回本次的体征与纠偏摘要，供上层记录/展示。
        """
        out: Dict[str, Any] = {"applied": False}
        store = self.components.get("life_state")
        if store is None:
            return out
        try:
            st = store.load(user_id)
            st.decay(cost=cost, failed=0.5 if failed else 0.0)
            store.save(user_id, st)
            out["applied"] = True
            out["vital"] = st.to_dict()
        except Exception as e:  # noqa: BLE001
            logger.warning("on_run_finished 回写体征失败: %s", e)
            return out

        homeo = self.components.get("homeostasis")
        if homeo is not None:
            try:
                corrections = homeo.tick({
                    "energy": st.energy, "focus": st.focus,
                    "mood": st.mood, "debt": st.debt,
                    "error_rate": 1.0 if failed else 0.0,
                })
                out["corrections"] = [c.to_dict() for c in corrections]
                out["should_hibernate"] = homeo.should_hibernate()
            except Exception as e:  # noqa: BLE001
                logger.warning("homeostasis.tick 失败: %s", e)
        return out

    def status(self) -> Dict[str, Any]:
        """活体快照——证明生命体层已是运行系统的活组件（非孤儿）。"""
        living = list(self.components.keys())
        failed = self.errors
        # 抽 life_state 实时值（若存在）作真实体征示例
        life = self.components.get("life_state")
        vital_sample = None
        if life is not None:
            try:
                st = life.load("default")
                vital_sample = st.to_dict()
            except Exception:
                vital_sample = None
        return {
            "lifeform_runtime": "active",
            "components_loaded": len(living),
            "components": living,
            "components_failed": failed,
            "vital_sample": vital_sample,
        }


def get_lifeform_runtime() -> LifeformRuntime:
    """进程内单例（与 hub / hippo_scroll 同范式）。"""
    rt = getattr(get_lifeform_runtime, "_inst", None)
    if rt is None:
        rt = LifeformRuntime()
        get_lifeform_runtime._inst = rt
    return rt
