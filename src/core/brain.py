"""
Unified Brain Module - the central hub of AOS v5.0

Orchestrates:
  - REAL Hermes Agent (Nous Research v0.18.0)
  - REAL DeerFlow (ByteDance v2.1.0)
  - Execution Layer (sandbox + tool executor + task runner)
  - Memory Bridge (AOS MemoryManager <-> DeerFlow Memory)
  - Skill Sync (AOS SkillRegistry <-> DeerFlow Skill Storage)
  - Checkpointing (SQLite persistence for multi-turn conversations)

Single entry point for the entire AOS system.
"""

import sys
import os
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Generator

from utils.config import config

logger = logging.getLogger(__name__)


class DeerFlowGatewayClient:
    """DeerFlow Gateway API Client - REAL DeerFlow 2.x gateway (port 2026).

    适配 ByteDance DeerFlow 2.x 的 LangGraph 风格 API:
      - 跑任务: POST /api/runs/wait (阻塞) 或 /api/runs/stream (SSE)
      - 模型:   GET /api/models        -> {"models": [...]}
      - 技能:   GET /api/skills        -> {"skills": [...]}
      - 线程:   GET /api/threads, GET /api/threads/{id}
      - 记忆:   POST /api/memory/import, GET /api/memory/export
    1.x 风格路径(/api/v1/*, CSRF)作为降级保留, 但 2.x 为本实现主路径。
    """

    def __init__(self, base_url="http://localhost:2026"):
        self.base_url = base_url
        self.real_deerflow = True
        self.api_version = "2.x"
        self._handlers = {}
        self._tasks = {}
        import threading
        self._task_lock = threading.Lock()
        self._session = None
        self._token = None
        self._connected = False
        self._default_model = "glm-4-flash"

    def _ensure_session(self):
        if self._session is None:
            import requests
            self._session = requests.Session()
            self._session.headers["Accept"] = "application/json"
        return self._session

    def _api_request(self, method, endpoint, **kwargs):
        """Generic request with 2.x-friendly auth (Bearer only, no CSRF)."""
        session = self._ensure_session()
        url = f"{self.base_url}{endpoint}"
        kwargs.setdefault("timeout", 30)
        if self._token:
            session.headers["Authorization"] = f"Bearer {self._token}"
        try:
            response = session.request(method, url, **kwargs)
            if response.status_code == 401 and self._token is None:
                # try once to authenticate (2.x local auth)
                if self._login():
                    session.headers["Authorization"] = f"Bearer {self._token}"
                    response = session.request(method, url, **kwargs)
            try:
                return response.json()
            except Exception:
                return {"status_code": response.status_code, "text": response.text[:500]}
        except Exception as e:
            logger.warning(f"DeerFlow API request failed: {e}")
            return {"error": str(e)}

    def _login(self):
        """Attempt 2.x local auth; returns True if a token was obtained.

        凭证从 config (AOS_DEERFLOW_ADMIN_USER / AOS_DEERFLOW_ADMIN_PASSWORD) 读取,
        不再硬编码明文口令 (此前写死 admin/aos123456, 属高危硬编码)。
        """
        try:
            from utils.config import config as _cfg
            user = getattr(_cfg, "DEERFLOW_ADMIN_USER", "admin") or "admin"
            pwd = getattr(_cfg, "DEERFLOW_ADMIN_PASSWORD", "aos123456") or "aos123456"
        except Exception:
            user, pwd = "admin", "aos123456"
        try:
            session = self._ensure_session()
            resp = session.post(
                f"{self.base_url}/api/v1/auth/login/local",
                json={"username": user, "password": pwd},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                self._token = data.get("access_token")
                self._connected = True
                logger.info("✅ DeerFlow gateway authenticated (2.x)")
                return True
        except Exception as e:
            logger.debug(f"DeerFlow login skipped: {e}")
        return False

    # ------------------------------------------------------------------
    #  Run / Chat (长时任务执行 — 2.x 主路径)
    # ------------------------------------------------------------------
    def _build_run_payload(self, message, thread_id=None, model_name=None, stream_mode=None):
        import uuid
        return {
            "input": {"messages": [{"role": "user", "content": message}]},
            "config": {"configurable": {"thread_id": thread_id or f"aos-{uuid.uuid4().hex[:12]}"}},
            "context": {"model_name": model_name or self._default_model, "thinking_enabled": False},
            "stream_mode": stream_mode or ["values"],
            "on_disconnect": "continue",
            "if_not_exists": "create",
        }

    @staticmethod
    def _extract_answer(state):
        """Extract the final assistant text from a 2.x run state dict."""
        import json as _json
        messages = (state or {}).get("messages") or []
        # 优先取最后一条 AI 消息
        for msg in reversed(messages):
            if isinstance(msg, dict) and msg.get("type") in ("ai", "assistant"):
                content = msg.get("content")
                if isinstance(content, str) and content.strip():
                    return content
                if isinstance(content, list):  # content blocks
                    txt = "\n".join(b.get("text", "") for b in content if isinstance(b, dict))
                    if txt.strip():
                        return txt
        # 兜底: 任意有内容的消息
        for msg in reversed(messages):
            if isinstance(msg, dict) and msg.get("content"):
                c = msg["content"]
                return c if isinstance(c, str) else _json.dumps(c, ensure_ascii=False)
        return (state or {}).get("title") or ""

    def run(self, message, thread_id=None, model_name=None, timeout=240, **kwargs):
        """Execute a long-running task (blocking). Returns final text answer."""
        import json as _json
        session = self._ensure_session()
        payload = self._build_run_payload(message, thread_id, model_name, stream_mode=["values"])
        try:
            resp = session.post(
                f"{self.base_url}/api/runs/wait", json=payload, timeout=timeout,
            )
            if resp.status_code == 200:
                try:
                    data = resp.json()
                except Exception:
                    return resp.text
                return self._extract_answer(data)
            logger.warning(f"DeerFlow /api/runs/wait -> {resp.status_code}; {resp.text[:200]}")
        except Exception as e:
            logger.warning(f"DeerFlow run failed: {e}")
        # 降级: 1.x /api/runs/stream
        return self._chat_legacy(message, thread_id)

    def chat(self, message, thread_id=None, **kwargs):
        return self.run(message, thread_id=thread_id, **kwargs)

    def stream(self, message, thread_id=None, model_name=None, timeout=240, **kwargs):
        """Stream a conversation turn through DeerFlow 2.x (SSE, values mode)."""
        import json as _json
        session = self._ensure_session()
        payload = self._build_run_payload(message, thread_id, model_name, stream_mode=["values"])
        try:
            resp = session.post(
                f"{self.base_url}/api/runs/stream", json=payload, stream=True, timeout=timeout,
            )
            if resp.status_code != 200:
                # SSE 不可用 -> 阻塞跑一次并返回答案
                answer = self.run(message, thread_id=thread_id, model_name=model_name, timeout=timeout)
                if answer:
                    yield answer
                return
            last = ""
            got_any = False
            for raw in resp.iter_lines(decode_unicode=True):
                if not raw:
                    continue
                if raw.startswith("event:"):
                    continue
                if not raw.startswith("data:"):
                    continue
                data_str = raw[len("data:"):].strip()
                if not data_str or data_str == "[DONE]":
                    continue
                try:
                    evt = _json.loads(data_str)
                except Exception:
                    continue
                if not isinstance(evt, dict):
                    continue
                ans = self._extract_answer(evt)
                if ans and ans != last:
                    if ans.startswith(last) and len(ans) > len(last):
                        delta = ans[len(last):]
                    else:
                        delta = ans
                    last = ans
                    got_any = True
                    yield delta
            if not got_any:
                # SSE 未产出可用内容 -> 阻塞兜底
                answer = self._extract_answer({})
                if not answer:
                    answer = self.run(message, thread_id=thread_id, model_name=model_name, timeout=timeout)
                if answer:
                    yield answer
        except Exception as e:
            logger.warning(f"DeerFlow stream failed: {e}")
            yield f"Failed to get response from DeerFlow: {e}"

    def _chat_legacy(self, message, thread_id=None):
        """1.x 降级路径 (保留兼容): /api/runs/stream 旧式 content 帧。"""
        import json as _json
        session = self._ensure_session()
        payload = {
            "messages": [{"role": "user", "content": message}],
            "config": {"configurable": {"thread_id": thread_id or "default-thread"}},
        }
        try:
            resp = session.post(f"{self.base_url}/api/runs/stream", json=payload, stream=True, timeout=120)
            if resp.status_code == 200:
                for line in resp.iter_lines():
                    if line:
                        decoded = line.decode("utf-8")
                        if "event: message" in decoded or "event: completion" in decoded:
                            try:
                                data = decoded.split("data: ", 1)[1]
                                parsed = _json.loads(data)
                                content = parsed.get("content", "")
                                if content:
                                    return content
                            except Exception:
                                continue
                return "DeerFlow responded"
        except Exception as e:
            logger.warning(f"DeerFlow legacy chat failed: {e}")
        return "Failed to get response from DeerFlow"

    # ------------------------------------------------------------------
    #  Catalog / Memory (2.x 路径, 1.x 降级)
    # ------------------------------------------------------------------
    def list_models(self):
        return self._api_request("GET", "/api/models")

    def list_skills(self):
        return self._api_request("GET", "/api/skills")

    def list_threads(self, limit=10):
        return self._api_request("GET", f"/api/threads?limit={limit}")

    def get_thread(self, thread_id):
        return self._api_request("GET", f"/api/threads/{thread_id}")

    def import_memory(self, data):
        return self._api_request("POST", "/api/memory/import", json=data)

    def export_memory(self):
        return self._api_request("GET", "/api/memory/export")

    def get_stats(self):
        models = self.list_models() or {}
        skills = self.list_skills() or {}
        m = models.get("models") or models.get("data") or []
        s = skills.get("skills") or skills.get("data") or []
        return {
            "models": len(m) if isinstance(m, list) else 0,
            "skills": len(s) if isinstance(s, list) else 0,
            "handlers": len(self._handlers),
            "api_version": self.api_version,
        }

    def sync_aos_skills_to_deerflow(self, skill_registry):
        synced = 0
        for skill_name, skill in getattr(skill_registry, "_skills", {}).items():
            try:
                self._handlers[skill_name] = skill
                synced += 1
                logger.info(f"Synced AOS skill to DeerFlow: {skill_name}")
            except Exception as e:
                logger.warning(f"Failed to sync skill {skill_name}: {e}")
        return synced

    def register_handler(self, name, handler):
        self._handlers[name] = handler
        logger.info(f"Registered task handler: {name}")

    def create_memory_fact(self, content, category="context", confidence=0.5):
        try:
            self.import_memory({"facts": [{"content": content, "category": category, "confidence": confidence}]})
        except Exception as e:
            logger.debug(f"DeerFlow memory sync skipped: {e}")

    # ------------------------------------------------------------------
    #  Async Task API (让 /api/tasks 在 REAL 2.x 模式可用)
    # ------------------------------------------------------------------
    def submit_task(self, task_type, input_data, thread_id=None, model_name=None, **kwargs):
        """提交一个长时任务：后台线程跑 run()，任务池跟踪状态。"""
        import threading, uuid, time
        if self._task_lock is None:
            self._task_lock = threading.Lock()
        task_id = f"df-{uuid.uuid4().hex[:12]}"
        # 从 input_data 抽取提示词
        if isinstance(input_data, dict):
            prompt = (input_data.get("message") or input_data.get("prompt")
                      or input_data.get("content") or input_data.get("task") or "")
        elif isinstance(input_data, str):
            prompt = input_data
        else:
            prompt = str(input_data)
        if not prompt:
            prompt = f"执行任务: {task_type}"
        rec = {
            "task_id": task_id,
            "task_type": task_type,
            "status": "running",
            "result": None,
            "error": None,
            "thread_id": thread_id or f"aos-{uuid.uuid4().hex[:12]}",
            "created_at": time.time(),
        }
        with self._task_lock:
            self._tasks[task_id] = rec

        def _worker():
            try:
                out = self.run(prompt, thread_id=rec["thread_id"],
                               model_name=model_name, **kwargs)
                rec["result"] = out
                rec["status"] = "completed"
            except Exception as e:  # noqa: BLE001
                rec["error"] = str(e)
                rec["status"] = "failed"
            finally:
                rec["finished_at"] = time.time()

        threading.Thread(target=_worker, daemon=True).start()
        return task_id

    def list_tasks(self, status=None, limit=50):
        with self._task_lock:
            items = list(self._tasks.values())
        items.sort(key=lambda x: x.get("created_at", 0), reverse=True)
        if status:
            items = [i for i in items if i.get("status") == status]
        return items[:limit]

    def get_task_status(self, task_id):
        with self._task_lock:
            return self._tasks.get(task_id)

    def get_running_tasks(self):
        return self.list_tasks(status="running")

    def cancel_task(self, task_id):
        with self._task_lock:
            rec = self._tasks.get(task_id)
            if rec and rec.get("status") == "running":
                rec["status"] = "cancelled"
                return True
        return False

    def shutdown(self, wait=True):
        if self._session:
            self._session.close()
        logger.info("DeerFlow gateway client shutdown")

    @property
    def _sandbox_bridge(self):
        return None

    @property
    def _guardrails_bridge(self):
        return None

    @property
    def _agents_bridge(self):
        return None

    @property
    def _subagent_bridge(self):
        return None

    @property
    def deep_deerflow(self):
        return None

    # ------------------------------------------------------------------
    #  SubAgent delegation (兼容 REAL 网关模式)
    # ------------------------------------------------------------------
    # 此前这些子智能体方法只存在于 fallback (DeerFlowScheduler), 而线上
    # REAL 模式走 DeerFlowGatewayClient, 调用方 brain.deerflow.* 会
    # AttributeError -> HTTP 500。这里统一委托给 AOSSubagentBridge
    # (与 Scheduler 共用同一 harness 桥), 缺失依赖时抛出清晰异常,
    # 由 API 层捕获为干净的 503/error 响应, 不再崩溃。
    def _ensure_subagents(self):
        if not hasattr(self, "_subagent_bridge"):
            self._subagent_bridge = None
            try:
                from deerflow.subagent_executor import AOSSubagentBridge
                self._subagent_bridge = AOSSubagentBridge()
            except Exception as e:  # noqa: BLE001
                logger.warning("[deerflow] 子智能体桥不可用: %s", e)
                self._subagent_bridge = None
        if self._subagent_bridge is None:
            raise RuntimeError(
                "DeerFlow 子智能体后端在本运行时不可用 "
                "(harness deerflow 包未导入或依赖未装); "
                "请确认 AOS 通过 DeerFlow gateway(:2026) 或补全 harness 依赖"
            )
        return self._subagent_bridge

    def register_subagent(self, name, description, **kwargs):
        return self._ensure_subagents().register_subagent(name, description, **kwargs)

    def list_subagents(self):
        return self._ensure_subagents().list_subagents()

    def execute_subagent(self, name, task, thread_id=None, **kwargs):
        return self._ensure_subagents().execute(name, task, thread_id=thread_id, **kwargs)

    def execute_subagent_async(self, name, task, thread_id=None, **kwargs):
        return self._ensure_subagents().execute_async(name, task, thread_id=thread_id, **kwargs)

    def get_subagent_result(self, task_id):
        return self._ensure_subagents().get_task_result(task_id)

    def cancel_subagent(self, task_id):
        return self._ensure_subagents().cancel_task(task_id)


class UnifiedBrain:
    """The one brain to rule them all.

    Initializes REAL Hermes-Agent (Nous Research v0.18.0) + REAL DeerFlow (ByteDance v2.1.0)
    with shared memory, synced skills, execution layer, and checkpointing.
    All AOS modules should route through this class.
    """

    def __init__(self):
        """初始化UnifiedBrain，带错误边界和状态管理"""
        # 初始化状态管理
        self.init_status = {}
        self._initialization_errors = []
        
        # 定义初始化步骤
        init_steps = [
            ("persistence", self._init_persistence),
            ("memory", self._init_memory),
            ("hermes", self._init_hermes_brain),
            ("deerflow", self._init_deerflow_scheduler),
            ("execution", self._init_execution_layer),
            ("skills", self._init_skills_registry),
            ("skill_sync", self._init_skill_sync),
            ("mcp", self._init_mcp_protocol),
            ("subagents", self._init_subagents_registry),
            ("compliance", self._init_compliance),
            ("identity", self._init_identity),
            ("audit_startup", self._init_audit_startup),
            ("deep_hermes", self._init_deep_hermes),
            ("deep_deerflow", self._init_deep_deerflow),
            ("task_classifier", self._init_task_classifier),
            ("meta_debate", self._init_meta_debate),
            ("meta_orchestrator", self._init_meta_orchestrator),
            ("mem0", self._init_mem0_store),
            ("langfuse", self._init_langfuse_tracer),
            ("router", self._init_router),
            ("fabric", self._init_fabric),
        ]
        
        # 逐步初始化，每步都有错误恢复
        for step_name, init_func in init_steps:
            try:
                init_func()
                self.init_status[step_name] = "success"
                logger.info(f"✅ 组件 {step_name} 初始化成功")
            except Exception as e:
                error_msg = f"{type(e).__name__}: {str(e)}"
                self.init_status[step_name] = error_msg
                self._initialization_errors.append((step_name, error_msg))
                logger.error(f"❌ 组件 {step_name} 初始化失败: {error_msg}")
                # 继续初始化其他组件，不中断
                logger.warning(f"⚠️ 继续初始化其他组件...")
        
        # 最终状态检查
        self._final_initialization_check()
    
    def _init_persistence(self):
        """步骤0: 持久化层 (SQLite foundation)"""
        # 单一真相层: 启动时幂等创建全部 38 张表 (即使下方 persistence 初始化失败也保证 schema 存在)
        try:
            from core.database import init_db
            init_db()
        except Exception as e:  # pragma: no cover - 兜底，避免阻断后续初始化
            logger.warning("init_db() 提前建表失败 (将在 persistence 初始化时重试): %s", e)
        from deerflow.persistence_bridge import get_persistence
        self.persistence = get_persistence()
        logger.info("Persistence ready (SQLite WAL, %s)", self.persistence.db_path)
    
    def _init_memory(self):
        """步骤1: 记忆层"""
        from memory import MemoryManager
        self.memory = MemoryManager()
        logger.info("Memory layer ready (SQLite + ChromaDB)")
    
    def _init_hermes_brain(self):
        """步骤2: Hermes大脑"""
        self._init_real_hermes()
        logger.info("Hermes brain ready (REAL v0.18.0 from Nous Research)")
    
    def _init_deerflow_scheduler(self):
        """步骤3: DeerFlow调度器"""
        self._init_real_deerflow()
        logger.info("DeerFlow scheduler ready (REAL v2.1.0 from ByteDance)")
    
    def _init_skills_registry(self):
        """步骤5: 技能注册表"""
        from skills import SkillRegistry
        from skills.loop_engineering import LoopEngineeringSkill
        from skills.vimax import ViMaxSkill
        from skills.ruflo import RuFloSkill
        from skills.pixelle_video import PixelleVideoSkill
        from skills.codebase_memory import CodebaseMemorySkill
        from skills.searxng import SearXNGSkill
        from skills.lightrag import LightRAGSkill
        from skills.jina_reader import JinaReaderSkill
        from skills.ollama import OllamaSkill
        from skills.viitor_voice import ViiTorVoiceSkill
        from skills.uitars import UITarsSkill
        from skills.zvec import ZvecSkill
        from skills.llama_cpp import LlamaCppSkill
        from skills.comfyui import ComfyUISkill
        from skills.codebase_memory_mcp import CodebaseMemoryMCPSkill
        from skills.agency_agents import AgencyAgentsSkill
        from skills.omni_route import OmniRouteSkill
        from skills.open_montage import OpenMontageSkill
        from skills.video_use import VideoUseSkill
        from skills.cognee import CogneeSkill
        from skills.herdr import HerdrSkill
        from skills.design_md import DesignMdSkill
        from skills.no_mistakes import NoMistakesSkill
        from skills.lingbot_map import LingbotMapSkill
        
        self.skill_registry = SkillRegistry()
        
        skill_classes = [
            LoopEngineeringSkill, ViMaxSkill, RuFloSkill, PixelleVideoSkill,
            CodebaseMemorySkill, SearXNGSkill, LightRAGSkill, JinaReaderSkill,
            OllamaSkill, ViiTorVoiceSkill, UITarsSkill,
            ZvecSkill, LlamaCppSkill, ComfyUISkill,
            CodebaseMemoryMCPSkill, AgencyAgentsSkill,
            OmniRouteSkill, OpenMontageSkill, VideoUseSkill,
            CogneeSkill, HerdrSkill,
            DesignMdSkill, NoMistakesSkill, LingbotMapSkill,
        ]
        
        for skill_cls in skill_classes:
            try:
                skill = skill_cls()
                self.skill_registry.register(skill)
                logger.info(f"技能已注册: {skill.name}")
            except Exception as e:
                logger.warning(f"技能注册失败 {skill_cls.__name__}: {e}")
    
    def _init_skill_sync(self):
        """步骤6: 技能同步到DeerFlow"""
        if hasattr(self, 'skill_registry') and hasattr(self, 'deerflow'):
            synced = self.deerflow.sync_aos_skills_to_deerflow(self.skill_registry)
            logger.info("Skill sync: %d AOS skills -> DeerFlow", synced)
        else:
            raise Exception("skill_registry或deerflow未初始化")
    
    def _init_mcp_protocol(self):
        """步骤7: MCP协议"""
        from mcp import MCPProtocol
        self.mcp = MCPProtocol()
        logger.info("MCP protocol ready")
    
    def _init_subagents_registry(self):
        """步骤8: 子智能体注册表"""
        from subagents import SubAgentRegistry
        from subagents import OpenClawSubAgent, UITarsSubAgent, LobsterSubAgent
        from utils.config import config as cfg
        
        self.subagents = SubAgentRegistry()
        self._register_subagents(cfg)
        logger.info("Sub-agent registry ready")
    
    def _init_compliance(self):
        """步骤9: 合规层"""
        from compliance.audit import get_audit_logger
        from compliance.identity import get_aid_generator
        from compliance.trace import get_tracer
        
        self.audit = get_audit_logger()
        self.aid_gen = get_aid_generator()
        self.tracer = get_tracer()
        logger.info("Compliance layer ready (Audit + Identity + Trace)")
    
    def _init_identity(self):
        """步骤10: 身份创建"""
        from utils.config import config as cfg
        
        # Create root AOS identity
        self.identity = self.aid_gen.create_identity(
            name="AOS-v5.0",
            capabilities=["chat","reasoning","code_execution","web_search","gui_automation","office_automation","skill_management","multi_agent_orchestration","audit","identity"],
        )
        logger.info("AOS Identity: %s", self.identity.aid)
    
    def _init_audit_startup(self):
        """步骤11: 启动审计"""
        from utils.config import config as cfg
        
        # Audit system startup
        self.audit.log("system.startup", agent_id=self.identity.aid,
                       details={"version": cfg.APP_VERSION, "components": ["hermes","deerflow","mcp","compliance"]})
        logger.info("Startup audit logged")
    
    def _init_deep_hermes(self):
        """步骤12: 深度Hermes集成"""
        self._deep_hermes_enabled = True
        logger.info("Deep Hermes integration enabled")
    
    def _init_deep_deerflow(self):
        """步骤13: 深度DeerFlow集成"""
        self._deep_deerflow_enabled = True
        logger.info("Deep DeerFlow integration enabled")
    
    def _init_task_classifier(self):
        """步骤14: 任务分类器"""
        from core.task_classifier import TaskClassifier
        self.task_classifier = TaskClassifier(brain=self)
        logger.info("Task classifier ready (L1-L5 five-level classification)")
    
    def _init_meta_debate(self):
        """步骤15: 元辩论系统"""
        from core.meta_debate import MetaDebate
        self.meta_debate = MetaDebate(skill_registry=self.skill_registry, brain=self)
        logger.info("Meta Debate system ready (self-pitch + peer review + voting)")
    
    def _init_router(self):
        """步骤16: 路由器"""
        from router import LLMRouter
        self.router = LLMRouter()
        logger.info("Router ready")

    def _init_fabric(self):
        """步骤17: 开放 Agent Fabric 薄缝 —— 新能力可选经 fabric 路由到真实引擎。

        双轨共存: 不取代现有装配, 仅作为'更优薄缝'供新能力按需委派。
        所有适配器均懒加载重依赖, 缺包时 health()=False, registry 自动绕开,
        故注册过程永不崩; 任一适配器导入失败都被单独吞掉, 不影响其余。
        """
        try:
            from core.fabric import FabricRegistry
            from core.fabric.adapters import (
                OpenClawAdapter, AG2Adapter, LiteLLMAdapter,
                Mem0Adapter, BrowserUseAdapter, LangfuseAdapter,
            )
        except Exception as e:
            logger.warning("fabric 不可用(跳过): %s", e)
            self.fabric = None
            return

        reg = FabricRegistry()
        for ad_cls in (OpenClawAdapter, AG2Adapter, LiteLLMAdapter,
                       Mem0Adapter, BrowserUseAdapter, LangfuseAdapter):
            try:
                reg.register(ad_cls())
            except Exception as e:
                logger.warning("fabric adapter 注册失败 %s: %s", ad_cls.__name__, e)
        self.fabric = reg
        live = [eid for eid, a in reg._adapters.items() if a.health()]
        logger.info("Fabric 薄缝就绪: 注册 %d 适配器, 当前 live %d (%s)",
                    len(reg._adapters), len(live), ", ".join(live) or "无")

    def route_via_fabric(self, capability, payload, trace_id=None):
        """经 fabric 薄缝路由一项能力(双轨: 新能力优先走 fabric)。

        返回 InvokeResult; 若 fabric 不可用或无 live provider, 返回 None,
        调用方据此回退到现有装配(brain 内部路由), 绝不阻断服务。
        """
        reg = getattr(self, "fabric", None)
        if reg is None:
            return None
        try:
            from core.fabric.adapter import InvokeRequest
            res = reg.route(InvokeRequest(capability=capability, payload=payload, trace_id=trace_id))
            return res if res.ok else None
        except Exception as e:
            logger.warning("fabric 路由失败, 回退现有装配: %s", e)
            return None

    def route_capability(self, capability: str, payload: Dict[str, Any], trace_id=None):
        """能力路由的**单一公共入口** (薄缝到 fabric)。

        此前 fabric 的 registry/adapter 是「死设计」——生产链路零调用、真实路由另有
        一套。现统一所有能力委派都经此方法 (groupchat 等已接), 杜绝重复路由逻辑。
        无 live provider 时返回 None, 调用方回退到 brain 现有装配, 绝不阻断服务。
        """
        return self.route_via_fabric(capability, payload, trace_id=trace_id)

    def resolve_engine(self, capability: str) -> Optional[str]:
        """单一可信源：返回当前能服务某能力(capability)的 live 引擎 id。

        若 fabric 不可用或无 live provider, 返回 None。供 introspection/日志使用,
        让「哪个引擎负责哪个能力」只有这一个答案, 不再双轨并存。
        """
        reg = getattr(self, "fabric", None)
        if reg is None:
            return None
        try:
            for eid, adapter in reg._adapters.items():
                caps = [c.value if hasattr(c, "value") else str(c)
                        for c in adapter.advertise_capabilities()]
                if capability in caps and adapter.health():
                    return eid
        except Exception:
            return None
        return None

    def _init_meta_orchestrator(self):
        """步骤: 元调度引擎 (L3.5 顶层调度/策略/信任)。

        此前这是孤岛: 引擎逻辑写好了却未接入主链路 chat()。
        现作为蓝图里的 DISPATCH/POLICY/TRUST 决策层，在 chat() 入口先裁决。
        """
        from meta_orchestrator.engine import MetaOrchestratorEngine
        self.meta_orchestrator = MetaOrchestratorEngine()
        logger.info("Meta-orchestrator (L3.5 dispatch) ready")

    def _init_mem0_store(self):
        """步骤: 真实语义记忆层 (Mem0, 长期/Graph-RAG)。

        四个行为引擎都缺的语义记忆层, 由真实 mem0.Memory 承担 (本地 chroma
        向量库 + Zhipu OpenAI 兼容 LLM/embedder)。库未装/无密钥时优雅降级到
        内存字典, 不阻断 AOS。
        """
        try:
            from core.memory.mem0_store import Mem0Store
            self.mem0_store = Mem0Store()
            backend = "mem0(real)" if self.mem0_store.available else "fallback(dict)"
            logger.info("Mem0 semantic memory ready (%s)", backend)
        except Exception as e:  # noqa: BLE001
            logger.warning("Mem0 store init failed (degraded): %s", e)
            self.mem0_store = None

    def _init_langfuse_tracer(self):
        """步骤: 可观测层 (Langfuse 真实接入)。

        在 chat/任务路径发 trace (input/output/metadata 含 meta 分层)。
        未配置密钥时静默禁用, 不阻断主流程。
        """
        try:
            from core.observability.langfuse_tracer import LangfuseTracer
            self.langfuse_tracer = LangfuseTracer()
            state = "enabled" if self.langfuse_tracer.enabled else "disabled(no-key)"
            logger.info("Langfuse observability ready (%s)", state)
        except Exception as e:  # noqa: BLE001
            logger.warning("Langfuse tracer init failed (degraded): %s", e)
            self.langfuse_tracer = None
    
    def get_init_status(self) -> dict:
        """获取初始化状态"""
        return {
            "status": "completed",
            "components": self.init_status.copy(),
            "total_components": len(self.init_status),
            "successful_components": sum(1 for status in self.init_status.values() if status == "success"),
            "failed_components": sum(1 for status in self.init_status.values() if status != "success"),
            "errors": self._initialization_errors.copy()
        }
    
    def is_component_ready(self, component: str) -> bool:
        """检查组件是否就绪"""
        return self.init_status.get(component) == "success"
    
    def _final_initialization_check(self):
        """最终初始化检查"""
        init_status = self.get_init_status()
        
        if init_status["failed_components"] > 0:
            logger.warning(f"⚠️ 初始化完成，但有 {init_status['failed_components']} 个组件失败:")
            for component, error in self._initialization_errors:
                logger.warning(f"  - {component}: {error}")
        else:
            logger.info("🎉 所有组件初始化成功！")

        # 12. LEMON Orchestrator - 学习型编排器
        try:
            from core.lemon_orchestrator import LEMONOrchestrator
            self.lemon_orchestrator = LEMONOrchestrator(brain=self)
            logger.info("LEMON Orchestrator ready (auto-generated orchestration specs)")
        except Exception as e:
            logger.warning("LEMON Orchestrator init failed: %s", e)

        # 13. SwarmFlow - 可控工作流编排引擎
        try:
            from core.swarm_flow import SwarmFlow
            self.swarm_flow = SwarmFlow(skill_registry=self.skill_registry, brain=self)
            logger.info("SwarmFlow ready (controllable workflow orchestration)")
        except Exception as e:
            logger.warning("SwarmFlow init failed: %s", e)

        # 14. Task Fingerprint - 记忆沉淀与复用系统
        try:
            from core.task_fingerprint import TaskFingerprint
            self.task_fingerprint = TaskFingerprint(memory_manager=self.memory)
            logger.info("Task Fingerprint ready (memory reuse + template matching)")
        except Exception as e:
            logger.warning("Task Fingerprint init failed: %s", e)

        # OpenClaw 接入已收敛到网关反向代理 (src/api/gateway.py -> :18789)
        # + Fabric OpenClawAdapter。不再在 brain 内自研实例化 core.open_claw
        # (违反铁律: 接入层须用真实开源 OpenClaw, 非自己写)。

        # 16. AgentCARD - 成本-精度优化策略 (初稿小模型→定稿大模型)
        try:
            from core.agent_card import AgentCARD
            self.agent_card = AgentCARD(brain=self)
            logger.info("AgentCARD ready (cost-precision optimization)")
        except Exception as e:
            logger.warning("AgentCARD init failed: %s", e)

        # 17. LightNegotiation - L3轻量协商机制 (主辅角色协作)
        try:
            from core.negotiation import LightNegotiation
            self.light_negotiation = LightNegotiation(skill_registry=self.skill_registry, brain=self)
            logger.info("LightNegotiation ready (L3 lightweight negotiation)")
        except Exception as e:
            logger.warning("LightNegotiation init failed: %s", e)

        # 18. FinalDeliverySystem - L4终审交付系统 (质量审核→打包→交付→存入记忆库)
        try:
            from core.negotiation import FinalDeliverySystem
            self.final_delivery = FinalDeliverySystem(
                task_fingerprint=self.task_fingerprint,
                memory_manager=self.memory,
            )
            logger.info("FinalDeliverySystem ready (L4 quality audit + packaging + delivery)")
        except Exception as e:
            logger.warning("FinalDeliverySystem init failed: %s", e)

        # 19. Register Agency Roles skills
        try:
            self._register_agency_roles()
        except Exception as e:
            logger.warning("Agency Roles registration failed: %s", e)

        logger.info("=== UnifiedBrain v5.0 FULLY initialized (L1-L5 routing + OpenClaw + MetaDebate + AgentCARD + LEMON + SwarmFlow + LightNegotiation + FinalDelivery + TaskFingerprint) ===")

    # ========================================================================
    #  REAL Hermes-Agent Integration (Nous Research v0.18.0)
    # ========================================================================
    def _init_real_hermes(self):
        """Initialize REAL Hermes-Agent from Nous Research.

        注意命名空间解冲突: hermes-agent 自带顶层 `utils` 包 (utils.py, 含
        base_url_hostname 等), 与 AOS 自身的 src/utils 包同名. AOS 启动时
        `utils` 已被加载进 sys.modules, 会遮蔽 hermes-agent 的 utils, 导致
        `from utils import base_url_hostname` 失败. 这里在加载 hermes 前暂存并
        移除 AOS 的 `utils*` 命名空间, 让 hermes-agent 加载自己的 utils, 加载
        完成后再还原 AOS 的 `utils`, 两者互不污染 (符合"薄缝集成"原则, 不改
        hermes-agent 内部).
        """
        import sys
        hermes_path = config.HERMES_SOURCE_PATH

        if hermes_path and os.path.exists(hermes_path):
            # --- 暂存并移除 AOS 的 utils* 命名空间, 避免遮蔽 hermes 的 utils ---
            _saved_utils = {
                k: sys.modules[k]
                for k in list(sys.modules)
                if k == "utils" or k.startswith("utils.")
            }
            for k in _saved_utils:
                del sys.modules[k]

            try:
                sys.path.insert(0, hermes_path)

                import os as _os
                _os.environ.setdefault("HERMES_HOME", str(Path(hermes_path) / "config" / "hermes"))
                _os.makedirs(_os.environ["HERMES_HOME"], exist_ok=True)

                from run_agent import AIAgent

                self.hermes = AIAgent(
                    base_url=config.ZHIPU_BASE_URL,
                    api_key=config.ZHIPU_API_KEY,
                    model=config.ZHIPU_MODEL,
                    verbose_logging=config.DEBUG,
                    quiet_mode=True,
                )

                logger.info(f"✅ REAL Hermes-Agent loaded from {hermes_path}")
                logger.info(f"   - Class: {type(self.hermes).__name__}")
                logger.info(f"   - Model: {config.ZHIPU_MODEL}")
                logger.info(f"   - Base URL: {config.ZHIPU_BASE_URL}")

                self.hermes.real_hermes = True
                return
            except Exception as e:
                logger.warning(f"⚠️ Failed to load REAL Hermes-Agent: {e}", exc_info=True)
            finally:
                if hermes_path in sys.path:
                    sys.path.remove(hermes_path)
                # 清理 hermes-agent 注入的 utils* 命名空间, 还原 AOS 的 utils
                for k in [k2 for k2 in list(sys.modules) if k2 == "utils" or k2.startswith("utils.")]:
                    if k not in _saved_utils:
                        del sys.modules[k]
                for k, v in _saved_utils.items():
                    sys.modules[k] = v

        logger.info("⚠️ Falling back to AOS Hermes implementation")
        from hermes.agent import HermesAgent
        self.hermes = HermesAgent()
        self.hermes.real_hermes = False

    # ========================================================================
    #  REAL DeerFlow Integration (ByteDance v2.1.0)
    # ========================================================================
    def _init_real_deerflow(self):
        """Initialize REAL DeerFlow by connecting to gateway on port 2026 (standard DeerFlow port)."""
        import requests
        
        try:
            response = requests.get("http://localhost:2026/health", timeout=3)
            if response.status_code == 200:
                logger.info("✅ DeerFlow gateway detected at http://localhost:2026")
                
                self.deerflow = DeerFlowGatewayClient(base_url="http://localhost:2026")
                logger.info(f"✅ REAL DeerFlow gateway client initialized")
                
                models = self.deerflow.list_models()
                # 统一接口契约处理：支持列表和字典两种格式
                if isinstance(models, dict):
                    model_list = models.get("models", [])
                elif isinstance(models, list):
                    model_list = models
                else:
                    logger.warning(f"未知的models响应格式: {type(models)}")
                    model_list = []
                
                model_names = [m.get("name", "") if isinstance(m, dict) else str(m) for m in model_list]
                logger.info(f"   - Available models: {model_names}")
                
                return
        except Exception as e:
            logger.warning(f"⚠️ DeerFlow gateway not available: {e}")
        
        logger.info("⚠️ Falling back to AOS DeerFlow implementation")
        from deerflow.scheduler import DeerFlowScheduler
        self.deerflow = DeerFlowScheduler(memory=self.memory)
        self.deerflow.real_deerflow = False

    # ========================================================================
    #  Execution Layer (执行层)
    # ========================================================================
    def _init_execution_layer(self):
        """Initialize execution layer with deep DeerFlow integration."""
        from execution.sandbox import SandboxManager
        from execution.tool_executor import ToolExecutor
        from execution.task_runner import TaskRunner
        from execution.workspace import WorkspaceManager
        
        self.sandbox = SandboxManager()
        self.tool_executor = ToolExecutor()
        self.task_runner = TaskRunner()
        self.workspace = WorkspaceManager()
        
        self._integrate_execution_with_deerflow()
        
        logger.info(f"✅ Execution Layer initialized with DeerFlow integration")
        logger.info(f"   - SandboxManager: {type(self.sandbox).__name__}")
        logger.info(f"   - ToolExecutor: {type(self.tool_executor).__name__}")
        logger.info(f"   - TaskRunner: {type(self.task_runner).__name__}")
        logger.info(f"   - WorkspaceManager: {type(self.workspace).__name__}")
    
    def _integrate_execution_with_deerflow(self):
        """Deep integration of execution layer with DeerFlow gateway."""
        
        def execute_sandbox_code(language, code, sandbox_id=None):
            if not sandbox_id:
                result = self.sandbox.create_sandbox()
                if not result["success"]:
                    return {"error": result["error"]}
                sandbox_id = result["sandbox"]["id"]
            
            return self.sandbox.execute_code(sandbox_id, code, language)
        
        def execute_bash(command):
            result = self.sandbox.create_sandbox()
            if not result["success"]:
                return {"error": result["error"]}
            sandbox_id = result["sandbox"]["id"]
            return self.sandbox.execute_code(sandbox_id, command, "bash")
        
        def read_file(file_path):
            workspace = self.workspace.list_workspaces()
            if workspace["workspaces"]:
                workspace_id = workspace["workspaces"][0]["id"]
                return self.workspace.read_file(workspace_id, file_path)
            return {"error": "No workspace found"}
        
        def write_file(file_path, content):
            workspace = self.workspace.list_workspaces()
            if not workspace["workspaces"]:
                result = self.workspace.create_workspace("default")
                workspace_id = result["workspace"]["id"]
            else:
                workspace_id = workspace["workspaces"][0]["id"]
            return self.workspace.write_file(workspace_id, file_path, content)
        
        def list_files(directory="."):
            workspace = self.workspace.list_workspaces()
            if workspace["workspaces"]:
                workspace_id = workspace["workspaces"][0]["id"]
                return self.workspace.list_files(workspace_id)
            return {"error": "No workspace found"}
        
        self.tool_executor.register_tool(
            name="execute_python",
            description="Execute Python code in a sandboxed environment",
            parameters={"code": {"type": "string", "description": "Python code to execute"},
                        "sandbox_id": {"type": "string", "description": "Optional sandbox ID"}},
            handler=lambda code, sandbox_id=None: execute_sandbox_code("python", code, sandbox_id)
        )
        
        self.tool_executor.register_tool(
            name="execute_bash",
            description="Execute bash commands in a sandboxed environment",
            parameters={"command": {"type": "string", "description": "Bash command to execute"}},
            handler=execute_bash
        )
        
        self.tool_executor.register_tool(
            name="read_file",
            description="Read file content from workspace",
            parameters={"file_path": {"type": "string", "description": "Path to file"}},
            handler=read_file
        )
        
        self.tool_executor.register_tool(
            name="write_file",
            description="Write content to file in workspace",
            parameters={"file_path": {"type": "string", "description": "Path to file"},
                        "content": {"type": "string", "description": "Content to write"}},
            handler=write_file
        )
        
        self.tool_executor.register_tool(
            name="list_files",
            description="List files in workspace directory",
            parameters={"directory": {"type": "string", "description": "Directory path"}},
            handler=list_files
        )
        
        self.deerflow.register_handler("execute_python", lambda code, **kwargs: execute_sandbox_code("python", code))
        self.deerflow.register_handler("execute_bash", execute_bash)
        self.deerflow.register_handler("read_file", read_file)
        self.deerflow.register_handler("write_file", write_file)
        
        logger.info("✅ Execution layer tools registered to DeerFlow")

    def _register_subagents(self, cfg):
        # OpenClaw 不再由自研 OpenClawSubAgent 注册 (DEPRECATED, 违反"用真实开源"
        # 铁律, 且其 detect_openclaw_path 实际返回 None 桥接悬空)。OpenClaw 统一由
        # Fabric OpenClawAdapter 经真实部署的 OpenClaw Gateway(:18789) 服务。
        if getattr(cfg, 'OPENCLAW_ENABLED', False):
            logger.info("OpenClaw 由 Fabric OpenClawAdapter (真实 Gateway) 提供服务, "
                        "跳过自研 OpenClawSubAgent 注册")

        try:
            if getattr(cfg, 'UITARS_ENABLED', False):
                ut = UITarsSubAgent(use_mcp=getattr(cfg, 'UITARS_USE_MCP', False),
                                    mcp_port=getattr(cfg, 'UITARS_MCP_PORT', 8090))
                self.subagents.register("uitars", ut.DESCRIPTION, ut.CAPABILITIES, ut.handle)
                self.deerflow.register_handler("gui_automation", ut.handle)
                logger.info("UI-TARS subagent registered")
        except Exception as e:
            logger.warning("UI-TARS subagent unavailable: %s", e)

        try:
            if getattr(cfg, 'UITARS_ENABLED', False):
                ut = UITarsSubAgent(use_mcp=getattr(cfg, 'UITARS_USE_MCP', False),
                                    mcp_port=getattr(cfg, 'UITARS_MCP_PORT', 8090))
                self.subagents.register("uitars", ut.DESCRIPTION, ut.CAPABILITIES, ut.handle)
                self.deerflow.register_handler("gui_automation", ut.handle)
                logger.info("UI-TARS subagent registered")
        except Exception as e:
            logger.warning("UI-TARS subagent unavailable: %s", e)

        try:
            if getattr(cfg, 'LOBSTER_ENABLED', False):
                lb = LobsterSubAgent(mode=getattr(cfg, 'LOBSTER_MODE', 'openclaw_bridge'),
                                     openclaw_command=getattr(cfg, 'OPENCLAW_COMMAND', 'npx'),
                                     lobster_port=getattr(cfg, 'LOBSTER_PORT', 8091))
                self.subagents.register("lobster", lb.DESCRIPTION, lb.CAPABILITIES, lb.handle)
                self.deerflow.register_handler("office_automation", lb.handle)
                logger.info("Lobster subagent registered")
        except Exception as e:
            logger.warning("Lobster subagent unavailable: %s", e)

        try:
            from subagents.vimax_agent import ViMaxSubagent
            vm = ViMaxSubagent()
            self.subagents.register("vimax", vm.DESCRIPTION, vm.CAPABILITIES, vm.handle)
            self.deerflow.register_handler("video_generation", vm.handle)
            logger.info("ViMax subagent registered")
        except Exception as e:
            logger.warning("ViMax subagent unavailable: %s", e)

        try:
            from subagents.ruflo_agent import RuFloSubagent
            rf = RuFloSubagent()
            self.subagents.register("ruflo", rf.DESCRIPTION, rf.CAPABILITIES, rf.handle)
            self.deerflow.register_handler("code_execution", rf.handle)
            logger.info("RuFlo subagent registered")
        except Exception as e:
            logger.warning("RuFlo subagent unavailable: %s", e)

        try:
            from subagents.pixelle_agent import PixelleVideoSubagent
            px = PixelleVideoSubagent()
            self.subagents.register("pixelle_video", px.DESCRIPTION, px.CAPABILITIES, px.handle)
            self.deerflow.register_handler("short_video_generation", px.handle)
            logger.info("Pixelle-Video subagent registered")
        except Exception as e:
            logger.warning("Pixelle-Video subagent unavailable: %s", e)

        try:
            from subagents.loop_engineering_agent import LoopEngineeringSubagent
            le = LoopEngineeringSubagent()
            self.subagents.register("loop_engineering", le.DESCRIPTION, le.CAPABILITIES, le.handle)
            self.deerflow.register_handler("loop_engineering", le.handle)
            logger.info("Loop Engineering subagent registered")
        except Exception as e:
            logger.warning("Loop Engineering subagent unavailable: %s", e)

        try:
            from subagents.skill_agent import register_skill_as_subagent

            skill_subagents = ["jina_reader", "codebase_memory", "codebase_memory_mcp", "searxng", "lightrag", "viitor_voice", "zvec", "llama_cpp", "comfyui", "agency_agents", "omni_route", "open_montage", "video_use", "cognee", "herdr", "design_md", "no_mistakes", "lingbot_map"]
            for skill_name in skill_subagents:
                register_skill_as_subagent(skill_name, self.skill_registry, self.subagents)
            logger.info(f"技能子智能体注册完成: {skill_subagents}")
        except Exception as e:
            logger.warning(f"技能子智能体注册失败: {e}")

        self.mcp.set_subagent_registry(self.subagents)

    def _register_agency_roles(self):
        """注册部门角色技能"""
        try:
            from skills.agency_roles import register_agency_roles as _register
            _register()
            logger.info("Agency Roles skills registered")
        except Exception as e:
            logger.warning(f"Agency Roles registration failed: {e}")

    # ========================================================================
    #  Unified Chat API - Five-Channel Routing
    # ========================================================================

    def chat(self, message: str, session_id: str = None,
             use_deerflow: bool = False, meta_decision: Optional[Dict[str, Any]] = None,
             **kwargs) -> Dict[str, Any]:
        """Unified chat with five-channel routing: L1-L5 task classification.

        meta_decision: 若调用方已算过 L3.5 意图分层决策(如 /api/chat 端点), 传入以
        复用, 避免重复调用 route_intent 导致 evolution_log 双写。为 None 时本方法自行计算。
        """
        
        import re
        date_patterns = ["今天几号", "今天日期", "日期", "几号", "几月几号", "几号了", "什么日子", "星期几"]
        if any(pattern in message for pattern in date_patterns):
            from datetime import datetime
            now = datetime.now()
            date_str = now.strftime("%Y年%m月%d日")
            weekday = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][now.weekday()]
            return {
                "session_id": session_id,
                "response": f"今天是 {date_str}，{weekday}。",
                "backend": "local",
                "success": True,
                "level": "L1",
                "channel": "直接对话",
            }

        classification = self.task_classifier.classify(message)
        level = classification.level
        channel = classification.channel

        # ---- 顶层元调度: meta_orchestrator 作为 DISPATCH/POLICY/TRUST 决策层 ----
        # 此前引擎是孤岛(未接入主链路); 现每个请求先过元调度裁决:
        #   - 命中 L3.5 (自修改/进化/元编排) -> 走 _route_l3_5 进化通道(安全门控)
        #   - 其余层 -> 仍由 task_classifier 的 L1-L5 路由处理
        # 引擎对 DB 写入 best-effort, 任何异常都回退到原有路由, 不阻断服务。
        mo = getattr(self, "meta_orchestrator", None)
        if meta_decision is None and mo is not None:
            try:
                meta_decision = mo.route_intent(
                    message,
                    user_id=kwargs.get("user_id", "hermes"),
                    project_id=kwargs.get("project_id", ""),
                    trace_id=kwargs.get("trace_id", ""),
                )
                if meta_decision.get("layer") == "L3.5":
                    return self._route_l3_5(message, session_id, meta_decision=meta_decision, **kwargs)
            except Exception as e:  # pragma: no cover - 元调度失败回退原有路由
                logger.warning("meta_orchestrator 路由失败, 回退 task_classifier: %s", e)

        logger.info(f"Task classified: {level.value} - {channel.value}")

        try:
            if level.value == "L1":
                return self._route_l1(message, session_id, **kwargs)
            elif level.value == "L2":
                return self._route_l2(message, session_id, **kwargs)
            elif level.value == "L3":
                return self._route_l3(message, session_id, **kwargs)
            elif level.value == "L4":
                return self._route_l4(message, session_id, **kwargs)
            elif level.value == "L5":
                return self._route_l5(message, session_id, **kwargs)
            else:
                return self._route_l1(message, session_id, **kwargs)
        except Exception as e:
            logger.error(f"Task routing failed: {e}", exc_info=True)
            return self._llm_cloud_fallback(message, session_id, level="L1", channel="路由失败-云端回落")

    def _llm_cloud_fallback(self, message: str, session_id: str = None,
                             level: str = "L1", channel: str = "云端LLM回落") -> Dict[str, Any]:
        """Hermes/本地模型不可用时, 回落到云端 LLMRouter(已配有效密钥)。

        这是'个人级开箱即用'的关键兜底: 即使本地 ollama 没装, 只要 .env 里有
        任意云端供应商密钥(ZHIPU/SILICONFLOW/BAIDU/XFYUN), 对话仍能正常出结果。
        """
        router = getattr(self, "router", None)
        if router is None:
            return {
                "success": False,
                "error": "无可用的LLM后端(Hermes 与 云端路由均未配置)",
                "level": level, "channel": channel,
            }
        try:
            out = router.chat([{"role": "user", "content": message}])
            return {
                "success": out.get("success", False),
                "response": out.get("content", ""),
                "provider": out.get("provider"),
                "model": out.get("model"),
                "level": level,
                "channel": channel,
                "backend": "cloud_router",
            }
        except Exception as e:
            logger.error("云端 LLM 回落也失败: %s", e, exc_info=True)
            return {"success": False, "error": f"LLM 调用失败: {e}", "level": level, "channel": channel}

    def _route_l1(self, message: str, session_id: str = None, **kwargs) -> Dict[str, Any]:
        """L1 - 直通通道: 优先 Hermes 直接回复, 失败/返回错误则回落云端 LLM"""
        try:
            result = self.hermes.chat(message, session_id=session_id, **kwargs)
        except Exception as e:
            logger.warning("L1 Hermes 异常, 回落云端 LLM: %s", e)
            return self._llm_cloud_fallback(message, session_id, level="L1")
        # Hermes 可能返回带 error 字段的 dict(即便 success=True), 或无内容 -> 回落云端
        if isinstance(result, dict) and (
            result.get("error") or not (result.get("response") or result.get("content"))
        ):
            logger.warning("L1 Hermes 返回错误/空内容, 回落云端 LLM: %s", result.get("error"))
            return self._llm_cloud_fallback(message, session_id, level="L1")
        result["level"] = "L1"
        result["channel"] = "直接对话"
        return result

    def _route_l2(self, message: str, session_id: str = None, **kwargs) -> Dict[str, Any]:
        """L2 - 快速通道: 选1个角色直接执行; 无匹配角色则回落 L1 对话"""
        similar = self.task_fingerprint.search_similar(message)
        if similar and similar[0].role_whitelist:
            role = similar[0].role_whitelist[0]
            logger.info(f"L2复用模板: {similar[0].fingerprint} -> {role}")
        else:
            role = self._find_best_single_role(message)

        if not role:
            logger.info("L2 无匹配角色, 回落 L1 对话")
            return self._route_l1(message, session_id, **kwargs)

        result = self.skill_registry.execute(role, {"task": message})
        result["level"] = "L2"
        result["channel"] = "快速通道"
        result["role"] = role
        return result

    def _route_l3(self, message: str, session_id: str = None, **kwargs) -> Dict[str, Any]:
        """L3 - 标准通道: 选1主+1辅角色，轻量协商; 无匹配则回落 L1"""
        similar = self.task_fingerprint.search_similar(message)
        if similar and similar[0].role_whitelist:
            roles = similar[0].role_whitelist[:2]
            logger.info(f"L3复用模板: {similar[0].fingerprint} -> {roles}")
        else:
            roles = self._find_main_and_support_roles(message)

        if not roles:
            logger.info("L3 无匹配角色, 回落 L1 对话")
            return self._route_l1(message, session_id, **kwargs)

        results = []
        for role in roles:
            result = self.skill_registry.execute(role, {"task": message})
            results.append({"role": role, "result": result})

        final_response = self._synthesize_results(results)
        return {
            "success": True,
            "level": "L3",
            "channel": "标准通道",
            "roles": roles,
            "response": final_response,
            "details": results,
        }

    def _route_l4(self, message: str, session_id: str = None, **kwargs) -> Dict[str, Any]:
        """L4 - 重型通道: 完整元辩论+投票+编排执行"""
        similar = self.task_fingerprint.search_similar(message, threshold=0.7)
        if similar:
            template = similar[0]
            logger.info(f"L4复用模板: {template.fingerprint}")
            spec_data = template.orchestration_spec
            role_whitelist = template.role_whitelist
        else:
            debate_result = self.meta_debate.run_full_debate(message)
            role_whitelist = debate_result.role_whitelist
            spec_data = None

            self.task_fingerprint.store_template(
                task=message,
                level="L4",
                role_whitelist=role_whitelist,
                model_strategy={k: v.value for k, v in debate_result.model_strategy.items()},
                cost_budget=debate_result.cost_budget,
            )

        spec = self.lemon_orchestrator.generate_spec(message, role_whitelist)
        spec = self.lemon_orchestrator.optimize_spec(spec)

        workflow_result = self.swarm_flow.execute_workflow(spec)

        self.task_fingerprint.update_template(
            self.task_fingerprint.generate_fingerprint(message),
            orchestration_spec=spec.to_dict(),
        )

        return {
            "success": workflow_result.status.value == "completed",
            "level": "L4",
            "channel": "重型通道",
            "workflow_id": workflow_result.workflow_id,
            "response": workflow_result.summary,
            "final_output": workflow_result.final_output,
            "step_results": [r.to_dict() for r in workflow_result.step_results],
        }

    def _route_l5(self, message: str, session_id: str = None, **kwargs) -> Dict[str, Any]:
        """L5 - 项目通道: 项目拆解+分层执行"""
        subtasks = self._decompose_project(message)
        results = []

        for subtask in subtasks:
            subtask_result = self.chat(subtask, session_id=session_id, **kwargs)
            results.append({
                "subtask": subtask,
                "level": subtask_result.get("level", "unknown"),
                "result": subtask_result,
            })

        project_summary = self._synthesize_project_results(results)

        self.task_fingerprint.store_template(
            task=message,
            level="L5",
            role_whitelist=[],
            orchestration_spec={"subtasks": subtasks},
        )

        return {
            "success": True,
            "level": "L5",
            "channel": "项目通道",
            "subtasks": subtasks,
            "response": project_summary,
            "subtask_results": results,
        }

    def _route_l3_5(self, message: str, session_id: str = None,
                    meta_decision: Dict[str, Any] = None, **kwargs) -> Dict[str, Any]:
        """L3.5 - 进化通道: 元调度捕获自修改/进化意图, 安全门控 + 人工审批。

        只生成受人工门控的提案 (不自动改代码/配置), 对齐蓝图 HUMANGATE。
        引擎已在 route_intent 内写入 evolution_log; 这里落 self_modification_proposals。
        """
        mo = getattr(self, "meta_orchestrator", None)
        proposal: Dict[str, Any] = {}
        if mo is not None:
            try:
                proposal = mo.propose_self_modification(message, meta_decision=meta_decision)
            except Exception as e:  # pragma: no cover - 提案落库失败不影响返回
                logger.warning("propose_self_modification 失败: %s", e)

        md = meta_decision or {}
        return {
            "success": True,
            "level": "L3.5",
            "channel": "进化通道",
            "layer": "L3.5",
            "workflow_id": md.get("workflow_id", "wf_meta_evolution_001"),
            "priority": md.get("priority", 9),
            "requires_human_approval": True,
            "proposal": proposal,
            "response": (
                "已捕获元进化意图，生成自修改提案并写入 evolution_log / "
                "self_modification_proposals，等待人工审批后执行。"
            ),
        }

    def _find_best_single_role(self, message: str) -> Optional[str]:
        """找到最适合任务的单个角色; 无匹配返回 None(由上层回落 L1)"""
        skills = self.skill_registry.search(message)
        if skills:
            return skills[0]["name"]
        return None

    def _find_main_and_support_roles(self, message: str) -> List[str]:
        """找到主角色和辅助角色; 无匹配返回空列表(由上层回落 L1)"""
        skills = self.skill_registry.search(message)
        if len(skills) >= 2:
            return [skills[0]["name"], skills[1]["name"]]
        elif skills:
            return [skills[0]["name"]]
        return []

    def _synthesize_results(self, results: List[Dict[str, Any]]) -> str:
        """综合多个角色的结果"""
        responses = []
        for r in results:
            result = r.get("result", {})
            if result.get("success"):
                data = result.get("data", {})
                if isinstance(data, dict):
                    responses.append(f"{r['role']}: {data.get('response', str(data))}")
                else:
                    responses.append(f"{r['role']}: {data}")

        if responses:
            return "\n\n".join(responses)
        return "任务执行完成"

    def _decompose_project(self, message: str) -> List[str]:
        """将复杂项目拆解为子任务"""
        prompt = f"""
请将以下复杂项目拆解为多个独立的子任务：

项目描述: {message}

要求:
1. 每个子任务应该独立可执行
2. 识别子任务之间的依赖关系
3. 每个子任务标注预计级别(L1-L4)

输出格式（JSON）：
{{
  "subtasks": [
    {{"task": "子任务1描述", "level": "L2"}},
    {{"task": "子任务2描述", "level": "L3"}}
  ],
  "dependencies": [["子任务1", "子任务2"]]
}}
"""
        try:
            result = self.hermes.chat(prompt, session_id="project_decomposition")
            import json
            response = result.get("response", "")
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(response[start:end])
                return [s["task"] for s in data.get("subtasks", [])]
        except Exception as e:
            logger.warning(f"项目拆解失败: {e}")

        return [message]

    def _synthesize_project_results(self, results: List[Dict[str, Any]]) -> str:
        """综合项目所有子任务的结果"""
        summaries = []
        for r in results:
            subtask = r.get("subtask", "")
            level = r.get("level", "unknown")
            result = r.get("result", {})
            response = result.get("response", "") or result.get("data", {}).get("response", "执行完成")
            summaries.append(f"【{level}】{subtask}\n{response}")

        if summaries:
            return "项目执行完成，以下是各子任务结果:\n\n" + "\n\n---\n\n".join(summaries)
        return "项目执行完成"

    def get_task_classification(self, message: str) -> Dict[str, Any]:
        """获取任务分级结果"""
        classification = self.task_classifier.classify(message)
        return classification.to_dict()

    def stream(self, message: str, session_id: str = None, **kwargs) -> Generator:
        """Stream a conversation turn through DeerFlow."""
        yield from self.deerflow.stream(message, thread_id=session_id, **kwargs)

    # ========================================================================
    #  Memory Bridge (unified)
    # ========================================================================

    def add_memory(self, content: str, category: str = "context",
                   confidence: float = 0.5) -> Dict[str, Any]:
        """Add memory to both AOS and DeerFlow."""
        # AOS side
        aos_result = self.hermes.add_knowledge(
            title=content[:80], content=content, source="unified_brain",
            tags=[category])
        # DeerFlow side
        try:
            self.deerflow.create_memory_fact(content, category=category,
                                             confidence=confidence)
        except Exception as e:
            logger.debug("DeerFlow memory sync skipped: %s", e)
        return aos_result

    def search_memory(self, query: str, search_type: str = "hybrid") -> Dict[str, Any]:
        """Search across unified memory."""
        return self.hermes.search_memory(query, search_type=search_type)

    # ---- Mem0 语义记忆委托 (真实接入) ----
    def semantic_memory_add(self, content: str, user_id: str = "aos", **kw) -> Dict[str, Any]:
        store = getattr(self, "mem0_store", None)
        if store is not None:
            return store.add(content, user_id=user_id, **kw)
        return {"ok": False, "backend": "none", "result": None}

    def semantic_memory_search(self, query: str, user_id: str = "aos",
                               limit: int = 5) -> Dict[str, Any]:
        store = getattr(self, "mem0_store", None)
        if store is not None:
            return store.search(query, user_id=user_id, limit=limit)
        return {"ok": False, "backend": "none", "results": []}

    def export_memory(self) -> Dict[str, Any]:
        """Export memory from both systems."""
        aos_mem = {"knowledge": len(self.memory.list_knowledge(limit=10000)),
                   "conversations": len(self.memory.list_tasks(limit=10000))}
        try:
            df_mem = self.deerflow.export_memory()
        except Exception:
            df_mem = {"status": "unavailable"}
        return {"aos": aos_mem, "deerflow": df_mem}

    # ========================================================================
    #  Health & Stats
    # ========================================================================

    def health_check(self) -> Dict[str, Any]:
        """Comprehensive health check across all components.

        与容错初始化一致: 任何组件初始化失败, 这里都不崩, 而是标记为
        unavailable / degraded, 并汇总到顶层 status。
        """
        from datetime import datetime as _dt

        def _safe(obj, method="get_stats", default=None):
            if obj is None:
                return {"status": "unavailable"}
            try:
                fn = getattr(obj, method, None)
                return fn() if callable(fn) else (default or {"status": "ok"})
            except Exception as e:  # pragma: no cover - 防御性
                return {"status": f"degraded: {e}"}

        identity = getattr(self, "identity", None)
        hermes = getattr(self, "hermes", None)
        deerflow = getattr(self, "deerflow", None)
        fabric = getattr(self, "fabric", None)

        components = {
            "hermes": (
                {"status": "ok", "real": True, "class": type(hermes).__name__}
                if getattr(hermes, "real_hermes", False)
                else _safe(hermes, method="get_stats")
            ),
            "deerflow": (
                {"status": "ok", "real": True, "class": type(deerflow).__name__}
                if getattr(deerflow, "real_deerflow", False)
                else _safe(deerflow, method="get_stats")
            ),
            "memory": _safe(getattr(self, "memory", None), method="get_stats"),
            "persistence": _safe(getattr(self, "persistence", None), method="get_stats"),
            "skills": {"count": len(getattr(getattr(self, "skill_registry", None), "_skills", {}))},
            "subagents": _safe(getattr(self, "subagents", None), method="get_stats"),
            "mcp": {"status": "ok" if getattr(self, "mcp", None) else "disabled"},
            "fabric": (
                {"adapters": len(getattr(fabric, "_adapters", {})),
                 "live": [e for e, a in getattr(fabric, "_adapters", {}).items() if a.health()]}
                if fabric is not None else {"status": "disabled"}
            ),
            "compliance": {
                "audit": _safe(getattr(self, "audit", None), method="get_stats"),
                "identity": _safe(getattr(self, "aid_gen", None), method="get_stats"),
                "tracer": _safe(getattr(self, "tracer", None), method="get_stats"),
            },
        }

        # hermes / deerflow deep 标志 (仅当对应对象存在时)
        if hermes is not None:
            components["hermes"]["deep"] = {
                "self_evolving_skills": getattr(self, "_deep_hermes_enabled", False),
                "nudge_engine": getattr(self, "_deep_hermes_enabled", False),
                "memory_lifecycle": getattr(self, "_deep_hermes_enabled", False),
                "context_engine": getattr(self, "_deep_hermes_enabled", False),
            }
        if deerflow is not None:
            components["deerflow"]["deep"] = {
                "runtime_journal": getattr(self, "_deep_deerflow_enabled", False),
                "tracing": getattr(self, "_deep_deerflow_enabled", False),
                "user_context": getattr(self, "_deep_deerflow_enabled", False),
                "middleware_chain": "14-layer onion model",
            }

        # hermes 快速自检 (失败仅降级, 不崩). REAL Hermes AIAgent 无此方法, 跳过.
        if hermes is not None and not getattr(hermes, "real_hermes", False):
            try:
                hermes.get_providers_status()
            except Exception as e:
                components["hermes"]["status"] = f"degraded: {e}"

        init_summary = self.get_init_status()
        status = "healthy" if init_summary["failed_components"] == 0 else "degraded"

        return {
            "status": status,
            "timestamp": _dt.now().isoformat(),
            "aid": getattr(identity, "aid", None),
            "init_summary": init_summary,
            "components": components,
        }

    def get_full_stats(self) -> Dict[str, Any]:
        """Aggregate stats from all components. Defensive: never raises."""
        from datetime import datetime as _dt

        def _stats(obj, method="get_stats"):
            if obj is None:
                return {"status": "unavailable"}
            try:
                fn = getattr(obj, method, None)
                return fn() if callable(fn) else {"status": "ok"}
            except Exception as e:
                return {"status": f"degraded: {e}"}

        hermes = getattr(self, "hermes", None)
        deerflow = getattr(self, "deerflow", None)

        stats: Dict[str, Any] = {
            "app": {
                "name": "AOS v5.0",
                "aid": getattr(getattr(self, "identity", None), "aid", None),
                "timestamp": _dt.now().isoformat(),
            },
            "hermes": _stats(hermes),
            "deerflow": _stats(deerflow),
            "subagents": _stats(getattr(self, "subagents", None)),
            "skills": _stats(hermes, method="list_skills"),
            "compliance": {
                "audit": _stats(getattr(self, "audit", None)),
                "identity": _stats(getattr(self, "aid_gen", None)),
                "tracing": _stats(getattr(self, "tracer", None)),
            },
            "persistence": _stats(getattr(self, "persistence", None)),
            "fabric": (
                {"adapters": len(getattr(getattr(self, "fabric", None), "_adapters", {}))}
                if getattr(self, "fabric", None) else {"status": "disabled"}
            ),
        }

        # DeerFlow deep (仅当真实 DeerFlow 网关且带 deep 属性时)
        if deerflow is not None and getattr(deerflow, "deep_deerflow", None) is not None:
            try:
                dd = deerflow.deep_deerflow
                stats["deerflow_deep"] = {
                    "sandbox_ready": getattr(deerflow, "_sandbox_bridge", None) is not None,
                    "guardrails_ready": getattr(deerflow, "_guardrails_bridge", None) is not None,
                    "agents_factory_ready": getattr(deerflow, "_agents_bridge", None) is not None,
                    "subagent_executor_ready": getattr(deerflow, "_subagent_bridge", None) is not None,
                    "journal_enabled": getattr(dd, "_journal", None) is not None,
                    "tracing_enabled": bool(getattr(dd, "_tracing_callbacks", []) or []),
                    "middleware_layers": len(getattr(dd, "MIDDLEWARE_CHAIN", []) or []),
                    "task_count": getattr(dd, "_task_counter", 0),
                    "active_user_contexts": len(getattr(dd, "_user_contexts", {}) or {}),
                }
            except Exception:
                stats["deerflow_deep"] = {"status": "unavailable"}
        else:
            stats["deerflow_deep"] = {"status": "unavailable"}

        # Deep Hermes (仅当真实 Hermes 且带 deep_hermes 时)
        if hermes is not None and getattr(hermes, "deep_hermes", None) is not None:
            try:
                dh = hermes.deep_hermes
                stats["deep_hermes"] = {
                    "self_evolving_skills": getattr(self, "_deep_hermes_enabled", False),
                    "nudge_engine": getattr(self, "_deep_hermes_enabled", False),
                    "memory_lifecycle": getattr(self, "_deep_hermes_enabled", False),
                    "context_engine": getattr(self, "_deep_hermes_enabled", False),
                    "skill_count": len(getattr(dh, "_skill_commands", []) or []),
                    "review_enabled": getattr(dh, "_review_enabled", False),
                    "context_status": getattr(hermes, "get_context_status", lambda: {})()
                    if hasattr(hermes, "get_context_status") else {},
                }
            except Exception:
                stats["deep_hermes"] = {"status": "unavailable"}
        else:
            stats["deep_hermes"] = {"status": "unavailable"}

        return stats

    # ========================================================================
    #  Session Management
    # ========================================================================

    def list_sessions(self) -> List[Dict[str, Any]]:
        return self.hermes.list_sessions()

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        return self.hermes.get_session_info(session_id)

    def list_threads(self, limit: int = 10) -> dict:
        return self.deerflow.list_threads(limit=limit)

    def get_thread(self, thread_id: str) -> dict:
        return self.deerflow.get_thread(thread_id)

    # ========================================================================
    #  Lifecycle
    # ========================================================================

    def shutdown(self):
        """Graceful shutdown of all components (deep integrations first)."""
        logger.info("Shutting down UnifiedBrain...")
        self.audit.log("system.shutdown", agent_id=self.identity.aid)
        self.audit.flush()
        self.tracer.shutdown()
        # Deep DeerFlow shutdown (clears user contexts, flushes journal)
        self.deerflow.shutdown(wait=True)
        # Deep Hermes shutdown (waits for review thread, syncs memory, closes providers)
        self.hermes.close()
        self.memory.close()
        self.persistence.close()
        logger.info("UnifiedBrain shutdown complete")


# ---- Singleton ----
_brain_instance: Optional[UnifiedBrain] = None


def get_brain() -> UnifiedBrain:
    """Get or create the singleton UnifiedBrain instance."""
    global _brain_instance
    if _brain_instance is None:
        _brain_instance = UnifiedBrain()
    return _brain_instance
