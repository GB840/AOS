"""AOS v5_bridge — 把 v1.0 内核接到 v5.0 基础设施上。

一次性桥接 7 个缺口，不改 brain.py / api/main.py 一行：
  1. /api/chat     → kernel.send_message (替代 brain.chat)
  2. JWT RS256     → kernel AuthBridge (v5.0 非对称密钥)
  3. brain.py路由  → kernel 双轨并存 (brain.py继续跑, 内核顺行)
  4. skills 执行   → kernel SkillsBridge.call_skill (打通call路径)
  5. MCP server    → kernel MCPBusLayer (起服务端)
  6. Web console   → kernel UILayer (暴露给 Streamlit)
  7. DeerFlow/Hermes → kernel AgentRuntime 插件调度

用法（加在 api/main.py 的 startup_event 里）：
    from kernel.v5_bridge import V5Bridge
    bridge = V5Bridge()
    bridge.mount(app)  # 注入内核到 FastAPI app
    # 此后 app.state.kernel 可用
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# ─── 内核 ───
from kernel.system import build_default_system, AOSSystem
from kernel.types import AgentSpec, Message, Response
from kernel.auth_bridge import AuthBridge, AuthProvider
from kernel.skills_bridge import SkillsBridge
from kernel.compliance import ComplianceLayer
from kernel.evolution import FitnessTracker


class V5Bridge:
    """v5.0 ↔ v1.0 统一桥接层。

    一个 mount(app) 调用，7 个缺口全接上。
    """

    def __init__(self, env_file: str = ""):
        # 加载环境
        if env_file and os.path.exists(env_file):
            try:
                from dotenv import load_dotenv
                load_dotenv(env_file)
            except ImportError as e:
                logger.debug("python-dotenv not installed, skipping env file loading: %s", e)

        # 内核
        self.system: AOSSystem = build_default_system()
        self.kernel = self.system.kernel
        self._mounted = False

        # 桥接实例
        self.auth: Optional[AuthBridge] = None
        self.skills: Optional[SkillsBridge] = None
        self.compliance: Optional[ComplianceLayer] = None
        self.fitness = FitnessTracker()

        # 统计
        self._started_at = time.time()
        self._request_count = 0

        # 切流遥测计数器（Layer 1：让切流可见，而非猜测）
        self._mount_attempts = 0
        self._mount_success = 0
        self._mount_failures = 0
        self._last_mount_error: Optional[str] = None
        self._chat_total = 0
        self._chat_kernel_ok = 0
        self._chat_kernel_fail = 0

        # 切流分流精确计数（让切流真实比例可见；fabric/kernel/brain 三档分开数）
        self._chat_request_total = 0   # 每次 /api/chat 命中（无论最终路由）
        self._chat_route_fabric = 0    # 实际走 FabricHub 的请求数
        self._chat_route_kernel = 0    # 实际走内核的请求数
        self._chat_route_brain = 0     # 实际走 brain.py 的请求数

    # ═══════════════════════════════════════════════════════════════
    # mount — 一键注入
    # ═══════════════════════════════════════════════════════════════

    def mount(self, app) -> V5Bridge:
        """把内核注入到 FastAPI app。7 个缺口全接上。"""
        self._mount_attempts += 1
        try:
            self.auth = AuthBridge(self.kernel)
            self.skills = SkillsBridge(self.kernel._skill_bus)
            self.compliance = ComplianceLayer(guard_mode="audit")
            self.compliance.audit.subscribe_to_kernel(self.kernel)

            # 注册 skills（非致命：配置缺失不应让 mount 崩溃）
            registered = 0
            try:
                registered = self.skills.register_all()
            except Exception as e:
                logger.warning("v5_bridge.mount: skills.register_all 失败（非致命）: %s", e)

            # 注入到 app.state
            app.state.kernel = self.kernel
            app.state.bridge = self
            app.state.kernel_version = "1.0.0"
            app.state.skills_registered = registered

            self._mounted = True
            self._mount_success += 1
            return self
        except Exception as e:
            self._mount_failures += 1
            self._last_mount_error = str(e)
            logger.error("v5_bridge.mount 失败, 回退 brain.py: %s", e)
            raise

    # ═══════════════════════════════════════════════════════════════
    # 缺口 1: /api/chat → kernel.send_message
    # ═══════════════════════════════════════════════════════════════

    def chat(self, prompt: str, session_id: str = "",
             engine: str = "litellm", caller: str = "api") -> Response:
        """v5.0 聊天 → v1.0 内核路由。

        替代 brain.chat() 的调用点。
        """
        self._request_count += 1
        self._chat_total += 1
        agent_id = f"api-chat-{engine}"

        if self.kernel.get_agent(agent_id) is None:
            self.kernel.register_agent(AgentSpec(
                agent_id=agent_id, name="APIChatBot",
                engine=engine, capabilities=["chat"],
            ))

        # 零信任：内核默认拒绝，必须为该会话 agent 授予 receive 权限，
        # 否则 send_message 会因无 receive 授权而被拒（见 kernel.send_message）。
        try:
            self.kernel.grant_permission(agent_id, "receive", True)
        except Exception as e:
            logger.warning("v5_bridge.chat: grant_permission 失败（非致命）: %s", e)

        t0 = time.monotonic()
        try:
            response = self.kernel.send_message(Message(
                sender=caller, recipient=agent_id,
                payload={"prompt": prompt, "session_id": session_id},
            ))
        except Exception as e:
            self._chat_kernel_fail += 1
            logger.error("v5_bridge.chat: kernel.send_message 抛异常, 回退 brain.py: %s", e)
            raise
        latency = time.monotonic() - t0

        # 记录真实 fitness + 切流遥测
        if response.ok:
            self._chat_kernel_ok += 1
            content_len = len(response.data.get("content", "")) if response.data else 0
            self.fitness.record_success(agent_id, latency=latency,
                                        tokens=max(10, content_len // 3))
        else:
            self._chat_kernel_fail += 1
            self.fitness.record_failure(agent_id)

        return response

    # ═══════════════════════════════════════════════════════════════
    # think→do 闭环：run_task — 规划→解析步骤→逐跳执行真实工具
    # ═══════════════════════════════════════════════════════════════

    def run_task(self, task: str, planner: str = "heuristic", session_id: str = None) -> Dict[str, Any]:
        """think→do 自主执行：规划 → steps[] → OrchestrationChiplet 逐跳执行。

        与 chat() 的区别：chat 只调一次 LLM（文本进文本出）；
        run_task 把任务拆成多步，每步路由到真实工具（搜索/代码执行/浏览器…），
        上一步产出喂下一步，端到端完成「想→做」闭环。

        参数：
          task: 用户自然语言任务，如 "搜索 Python 最新版本并写代码打印结果"
          planner: "heuristic"（本地关键词切分，零依赖）或 "ag2"（LLM 规划）
          session_id: 会话 ID，传入则记住之前对话，支持多轮连续交互
        """
        hub = self.kernel.fabric_hub
        if hub is None:
            return {"ok": False, "error": "fabric 能力枢纽未挂载"}
        try:
            result = hub.run_task(task, planner=planner, session_id=session_id)
            return result
        except Exception as e:
            logger.error("run_task 失败: %s", e, exc_info=True)
            return {"ok": False, "error": str(e), "task": task}

    # ═══════════════════════════════════════════════════════════════
    # 缺口 2: JWT RS256 → AuthBridge
    # ═══════════════════════════════════════════════════════════════

    def authenticate(self, bearer_token: str) -> Dict[str, Any]:
        """v5.0 JWT → v1.0 鉴权。

        在 api/security.py 的 JWT 验证之后调用，把结果注入内核权限。
        """
        result = self.auth.login_bearer(bearer_token)
        return {
            "authenticated": result.authenticated,
            "identity_id": result.identity_id,
            "identity_type": result.identity_type,
            "error": result.error,
        }

    def verify_jwt_hook(self, verify_fn):
        """注入 v5.0 的 JWT RS256 验证函数到内核 AuthProvider。

        用法: bridge.verify_jwt_hook(api.security.verify_jwt_token)
        """
        self.auth._provider = AuthProvider(verify_token=verify_fn)

    # ═══════════════════════════════════════════════════════════════
    # 缺口 3: brain.py 双轨并存
    # ═══════════════════════════════════════════════════════════════

    def dual_route(self, brain_module, prompt: str, session_id: str = "",
                   engine: str = "litellm") -> Dict[str, Any]:
        """双轨路由：同时走 brain.py 和 kernel，比较结果。

        用于渐进迁移：先并行跑，验证内核路由结果等同或优于 brain.py，
        确认无误后再切流。
        """
        # v5.0 路径
        try:
            if hasattr(brain_module, "chat"):
                v5_result = brain_module.chat(prompt)
            else:
                v5_result = str(brain_module.hermes.chat(prompt)) if hasattr(brain_module, "hermes") else None
        except Exception:
            v5_result = None

        # v1.0 路径
        v1_result = self.chat(prompt, session_id, engine)

        return {
            "v5": v5_result,
            "v1": v1_result,
            "v1_ok": v1_result.ok,
            "migrated": True,
        }

    # ═══════════════════════════════════════════════════════════════
    # 缺口 4: Skills 执行 — 打通调用
    # ═══════════════════════════════════════════════════════════════

    def call_skill(self, skill_id: str, params: Dict[str, Any],
                   caller: str = "api") -> Dict[str, Any]:
        """通过内核 SkillBus 执行一个技能。

        旧的调用: brain.hermes.execute_skill(name, params)
        新的调用: bridge.call_skill(name, params)
        """
        # 先通过 MCP 总线（含权限校验）
        if self.system.mcp_bus:
            result = self.system.mcp_bus.route_call(skill_id, params, caller)
            if result.ok:
                return {"ok": True, "data": result.data}

        # 回退：直接通过 SkillsBridge
        result = self.skills.call_skill(skill_id, params)
        return {"ok": result.ok, "data": result.data, "error": result.error}

    def list_skills(self) -> List[Dict[str, Any]]:
        """列出所有可用技能。替代 SkillRegistry.list_all()。"""
        if self.system.mcp_bus:
            return [{"id": s.skill_id, "desc": s.description}
                    for s in self.system.mcp_bus.discover()]
        return []

    # ═══════════════════════════════════════════════════════════════
    # 缺口 5: MCP server
    # ═══════════════════════════════════════════════════════════════

    def get_mcp_routes(self) -> Dict[str, Callable]:
        """暴露 MCP 协议路由给 ASGI 挂载。

        在 main.py 中可以这样用:
            from kernel.v5_bridge import get_bridge
            app.mount("/mcp", get_bridge().get_mcp_routes())
        """
        return {
            "tools/list": lambda: [s.skill_id for s in self.system.mcp_bus.discover()] if self.system.mcp_bus else [],
            "tools/call": lambda name, params: self.call_skill(name, params),
        }

    # ═══════════════════════════════════════════════════════════════
    # 缺口 6: Web console
    # ═══════════════════════════════════════════════════════════════

    def web_ui_data(self) -> Dict[str, Any]:
        """给 Streamlit / Web 前端提供 UI 数据。"""
        return {
            "surfaces": [
                {"id": s.id, "title": s.title, "kind": s.kind}
                for s in (self.system.ui.list_surfaces() if self.system.ui else [])
            ],
            "agents": [
                {"id": a.agent_id, "engine": a.spec.engine, "status": a.status.value}
                for a in self.kernel.list_agents()
            ],
            "skills": self.list_skills(),
            "health": self.system.health_report() if self.system else {},
            "fitness": [
                {"agent": s.agent_id, "score": s.overall, "success": s.success_rate}
                for s in self.fitness.top_agents(5)
            ],
            "compliance": {
                "audit_entries": (self.compliance.audit.total_entries
                                  if self.compliance else 0),
                "content_checks": (self.compliance.guard.redacted_count
                                   if self.compliance else 0),
                "policy_rules": (len(self.compliance.policy.rules)
                                 if self.compliance else 0),
            },
        }

    # ═══════════════════════════════════════════════════════════════
    # 缺口 7: DeerFlow / Hermes 引擎调度
    # ═══════════════════════════════════════════════════════════════

    def register_engine_callback(self, engine: str, handler: Callable) -> None:
        """注册一个引擎的真实回调。

        用法:
            bridge.register_engine_callback("hermes", brain.hermes.chat)
            bridge.register_engine_callback("deerflow", brain.deerflow.execute)
        """
        from kernel.interfaces import AgentRuntime

        class BridgeAgentRuntime(AgentRuntime):
            def run_agent(self, agent, task: dict) -> Response:
                try:
                    result = handler(task.get("prompt", ""), **task)
                    return Response(ok=True, data={"content": str(result)})
                except Exception as e:
                    return Response(ok=False, error=str(e))

            def get_status(self, resource: str) -> str:
                return "healthy"

            def list_agents(self):
                return []

            def create_agent(self, spec):
                pass

            def stream_run(self, agent, task):
                raise NotImplementedError

        self.kernel._runtimes[engine] = BridgeAgentRuntime()

    # ═══════════════════════════════════════════════════════════════
    # 健康检查
    # ═══════════════════════════════════════════════════════════════

    def health(self) -> Dict[str, Any]:
        """统一健康报告。替代 brain.health_check()。"""
        hr = self.system.health_report() if self.system else {}
        return {
            "status": "ok" if hr.get("kernel", {}).get("ok") else "degraded",
            "version": "1.0.0",
            "uptime_seconds": round(time.time() - self._started_at, 1),
            "requests": self._request_count,
            "kernel": hr,
            "compliance": {
                "audit_entries": (self.compliance.audit.total_entries
                                  if self.compliance else 0),
                "integrity": (self.compliance.audit.verify_integrity()
                              if self.compliance else False),
            },
            "skills_registered": (len(self.list_skills())
                                  if self.skills else 0),
        }


    # ═══════════════════════════════════════════════════════════════
    # 切流精确计数（Layer 1：回答"分流比例到底几成"）
    # ═══════════════════════════════════════════════════════════════

    def record_chat_request(self) -> None:
        """每次 /api/chat 命中调用一次（无论最终路由到哪）。"""
        self._chat_request_total += 1

    def record_chat_route(self, route: str) -> None:
        """记录一次请求最终路由到的引擎：'fabric' | 'kernel' | 'brain'。

        三档分开计数，避免 fabric（默认主后端）被误计为 brain，
        使切流比例真实可见（理念6/9 量化）。
        """
        if route == "fabric":
            self._chat_route_fabric += 1
        elif route == "kernel":
            self._chat_route_kernel += 1
        else:
            self._chat_route_brain += 1

    def telemetry(self) -> Dict[str, Any]:
        """切流遥测快照（Layer 1）。

        暴露给 /api/v1/health，用于回答"切流到底做到几成"——
        0% 还是 100%，靠数据而非猜测。计数器为进程内存态，
        多 worker / 重启会归零；生产环境应接入持久化指标后端。

        两个互补视角：
        - chat_kernel_ratio   : 走内核的请求里，成功 / (成功+失败) —— 内核健康度
        - kernel_split_ratio  : 走内核的请求 / 总请求 —— 真实分流比例
          （此前只数"走内核成功"，当 AOS_KERNEL_TRAFFIC_PCT<100 时
           brain 回退流量不计入，比例会被低估；现用 chat_request_total
           做分母，比例精确）
        """
        ratio = (self._chat_kernel_ok / self._chat_total) if self._chat_total > 0 else 0.0
        split = (self._chat_route_kernel / self._chat_request_total) if self._chat_request_total > 0 else 0.0
        fabric_split = (self._chat_route_fabric / self._chat_request_total) if self._chat_request_total > 0 else 0.0
        brain_split = (self._chat_route_brain / self._chat_request_total) if self._chat_request_total > 0 else 0.0
        return {
            "mount_attempts": self._mount_attempts,
            "mount_success": self._mount_success,
            "mount_failures": self._mount_failures,
            "last_mount_error": self._last_mount_error,
            "chat_total": self._chat_total,
            "chat_kernel_ok": self._chat_kernel_ok,
            "chat_kernel_fail": self._chat_kernel_fail,
            "chat_kernel_ratio": round(ratio, 4),
            "chat_request_total": self._chat_request_total,
            "chat_route_fabric": self._chat_route_fabric,
            "chat_route_kernel": self._chat_route_kernel,
            "chat_route_brain": self._chat_route_brain,
            "kernel_split_ratio": round(split, 4),
            "fabric_split_ratio": round(fabric_split, 4),
            "brain_split_ratio": round(brain_split, 4),
        }


# ─── 全局单例 ─────────────────────────────────────────────────────

_bridge: Optional[V5Bridge] = None


def get_bridge() -> V5Bridge:
    """获取全局 V5Bridge 实例。"""
    global _bridge
    if _bridge is None:
        _bridge = V5Bridge()
    return _bridge


__all__ = ["V5Bridge", "get_bridge"]
