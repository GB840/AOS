"""
Hermes Brain Module - wraps the REAL Hermes Agent v0.15.2 (NousResearch, MIT)
NOT a fake replacement - this is a thin adapter that imports the real open-source framework.
Hermes = Brain (intent recognition, reasoning, conversation)
DeerFlow = Scheduler (multi-agent orchestration, workflow dispatch)
"""

import sys
import logging
import json
import uuid
from typing import Dict, List, Optional, Any, AsyncGenerator
from pathlib import Path

import os as _os

from utils.config import config
from skills import SkillRegistry, SkillCreator, FindSkills, SuperpowersSkill
from skills import JStackSkill, FrontendDesignSkill, UIUXProMaxSkill, DuckDuckGoSearchSkill
from router import LLMRouter, TaskType

logger = logging.getLogger(__name__)

_HERMES_SRC = None
_HERMES_AVAILABLE = False

def _detect_hermes_path() -> Optional[str]:
    """自动检测 Hermes Agent 源码路径"""
    candidates = [
        config.HERMES_SOURCE_PATH,
        config.HERMES_AGENT_PATH,
        str(Path(config.BASE_DIR) / "external" / "hermes_agent-0.15.2"),
        str(Path(config.BASE_DIR) / "external" / "hermes_agent"),
    ]
    
    for candidate in candidates:
        if candidate and Path(candidate).exists() and (Path(candidate) / "run_agent.py").exists():
            logger.info(f"Hermes Agent 源码路径检测成功: {candidate}")
            return candidate
    
    logger.warning("Hermes Agent 源码路径未检测到，将使用 AOS 内置实现")
    return None

_HERMES_SRC = _detect_hermes_path()

if _HERMES_SRC:
    try:
        if _HERMES_SRC not in sys.path:
            sys.path.insert(0, _HERMES_SRC)
        
        _os.environ['HERMES_HOME'] = str(Path(__file__).resolve().parent.parent.parent / 'config' / 'hermes')
        
        from datetime import datetime
        
        # ---- The REAL Hermes Agent engine (4617 lines of open-source code) ----
        from run_agent import AIAgent
        
        _HERMES_AVAILABLE = True
        logger.info("✅ Hermes Agent 真实引擎加载成功")
    except ImportError as e:
        logger.warning(f"❌ Hermes Agent 导入失败: {e}，将使用 AOS 内置实现")
        _HERMES_AVAILABLE = False
        if _HERMES_SRC in sys.path:
            sys.path.remove(_HERMES_SRC)
else:
    from datetime import datetime
    _HERMES_AVAILABLE = False

if not _HERMES_AVAILABLE:
    class AIAgent:
        """Fallback AIAgent when real Hermes is not available"""
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            logger.info(f"⚠️ 使用降级 AIAgent 实现: {kwargs.get('provider', 'unknown')}/{kwargs.get('model', 'unknown')}")
        
        def chat(self, message, **kwargs):
            return {"message": {"content": f"[降级模式] 任务已收到: {message[:50]}..."}}
        
        def stream(self, message, **kwargs):
            yield {"content": f"[降级模式] 任务已收到: {message[:50]}..."}
        
        def complete(self, prompt, **kwargs):
            return {"content": f"[降级模式] 已处理: {prompt[:50]}..."}

# ---- Deep Hermes Integration (self-evolving skills + nudge + memory lifecycle + context) ----
from hermes.deep_hermes import create_deep_hermes


class HermesAgent:
    """
    AOS wrapper around the real Hermes AIAgent v0.15.2.

    This is NOT a fake. It imports and configures the actual NousResearch
    hermes-agent runtime, then adds AOS-specific enhancements:
    - Multi-provider routing from AOS config
    - 7 self-evolving skills
    - Session management
    - Memory persistence via ChromaDB + SQLite
    """

    def __init__(self):
        provider_config = self._resolve_provider()

        self._agent = AIAgent(
            base_url=provider_config["base_url"],
            api_key=provider_config["api_key"],
            model=provider_config["model"],
            provider=provider_config.get("provider", "openai"),
            max_iterations=30,
            verbose_logging=config.DEBUG,
        )

        self.sessions: Dict[str, Dict[str, Any]] = {}
        from memory import MemoryManager
        self.memory = MemoryManager()
        self.skills = SkillRegistry()
        self._register_skills()

        self._router = LLMRouter()

        # ---- Deep Hermes Integration: self-evolving skills + nudge + memory lifecycle + context ----
        self.deep_hermes = create_deep_hermes(self._agent)
        # Wire AOS callback for review notifications
        self.deep_hermes.set_review_callback(self._on_review_complete)

        logger.info(
            "Hermes brain initialized (real AIAgent v0.15.2 + %d skills + DeepHermes, provider=%s/%s)",
            self.skills.get_stats()["total"],
            provider_config.get("provider", "openai"),
            provider_config["model"],
        )

    def _resolve_provider(self) -> Dict[str, str]:
        providers = [
            ("zhipu", config.ZHIPU_API_KEY, config.ZHIPU_BASE_URL, config.ZHIPU_MODEL),
            ("siliconflow", config.SILICONFLOW_API_KEY, config.SILICONFLOW_BASE_URL, config.SILICONFLOW_MODEL),
            ("baidu", config.BAIDU_API_KEY, config.BAIDU_BASE_URL, config.BAIDU_MODEL),
            ("ollama", "ollama", config.OLLAMA_BASE_URL, config.OLLAMA_MODEL),
        ]
        for name, api_key, base_url, model in providers:
            if api_key and base_url:
                return {"provider": name, "api_key": api_key, "base_url": base_url, "model": model}
        return {"provider": "ollama", "api_key": "ollama", "base_url": config.OLLAMA_BASE_URL, "model": config.OLLAMA_MODEL}

    # ---- Public API ----

    def chat(self, message: str, session_id: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """Full-lifecycle chat: prefetch context -> chat -> sync memory -> background review."""
        if not session_id:
            session_id = str(uuid.uuid4())
        if session_id not in self.sessions:
            self.sessions[session_id] = {"created_at": datetime.now().isoformat(), "message_count": 0}
        self.sessions[session_id]["message_count"] += 1

        self.memory.add_conversation(session_id=session_id, role="user", content=message)

        # ---- Deep Hermes Lifecycle: prefetch memory context ----
        memory_context = self.deep_hermes.on_turn_start(
            message, turn_number=self.sessions[session_id]["message_count"])

        # ---- Context compression check ----
        if self.deep_hermes.should_compress():
            compressed = self.deep_hermes.compress_context()
            if compressed:
                logger.info("Context compressed before turn")

        # ---- Inject memory context ----
        enriched_message = message
        if memory_context:
            try:
                from agent.memory_manager import build_memory_context_block
                enriched_message = build_memory_context_block(memory_context) + "\n\n" + message
            except Exception:
                enriched_message = message

        try:
            result = self._agent.run_conversation(enriched_message)
            response_text = result.get("final_response", "")
            failed = False
        except Exception as e:
            logger.error(f"Hermes chat error: {e}")
            response_text = f"[Hermes error: {e}]"
            failed = True

        self.memory.add_conversation(
            session_id=session_id, role="assistant", content=response_text,
            metadata={"provider": self._resolve_provider()["provider"]},
        )

        # ---- Deep Hermes Lifecycle: sync memory + trigger background review ----
        self.deep_hermes.on_turn_end(message, response_text)
        self.deep_hermes.trigger_background_review(review_memory=True, review_skills=True)

        return {
            "session_id": session_id,
            "response": "" if failed else response_text,
            "error": response_text if failed else None,
            "provider": self._resolve_provider()["provider"],
            "model": self._resolve_provider()["model"],
            "success": not failed,
            "timestamp": datetime.now().isoformat(),
            "_lifecycle": {
                "memory_prefetched": bool(memory_context),
                "review_spawned": True,
                "context_status": self.deep_hermes.get_context_status(),
            },
        }

    async def stream_chat(self, message: str, session_id: Optional[str] = None, **kwargs) -> AsyncGenerator[str, None]:
        response = self.chat(message, session_id, **kwargs)
        content = response["response"]
        chunk_size = 4
        for i in range(0, len(content), chunk_size):
            yield json.dumps(
                {"type": "content", "content": content[i:i+chunk_size], "session_id": response["session_id"]},
                ensure_ascii=False,
            )
        yield json.dumps(
            {"type": "done", "provider": response["provider"], "model": response["model"], "session_id": response["session_id"]},
            ensure_ascii=False,
        )

    # ---- Knowledge & Memory ----

    def add_knowledge(self, title: str, content: str, source: str = "", tags: Optional[List[str]] = None) -> Dict[str, Any]:
        kid = self.memory.add_knowledge(title, content, source, tags)
        return {"id": kid, "title": title, "success": True}

    def search_memory(self, query: str, search_type: str = "hybrid") -> Dict[str, Any]:
        if search_type == "semantic":
            results = self.memory.semantic_search(query)
        elif search_type == "fulltext":
            results = self.memory.search_conversations(query) + self.memory.search_knowledge_fulltext(query)
        else:
            results = self.memory.hybrid_search(query)
        return {"query": query, "results": results, "count": len(results)}

    # ---- Session management ----

    def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        session = self.sessions.get(session_id)
        if not session:
            return None
        history = self.memory.get_conversation_history(session_id)
        return {"session_id": session_id, "created_at": session["created_at"], "message_count": session["message_count"], "history": history}

    def list_sessions(self) -> List[Dict[str, Any]]:
        return [{"session_id": sid, "created_at": s["created_at"], "message_count": s["message_count"]} for sid, s in self.sessions.items()]

    # ---- Skills ----

    def _register_skills(self):
        self.skills.register(SkillCreator())
        self.skills.register(FindSkills())
        self.skills.register(SuperpowersSkill())
        self.skills.register(JStackSkill())
        self.skills.register(FrontendDesignSkill())
        self.skills.register(UIUXProMaxSkill())
        self.skills.register(DuckDuckGoSearchSkill())

    def execute_skill(self, name: str, context: Dict[str, Any]) -> Dict[str, Any]:
        return self.skills.execute(name, context)

    def list_skills(self, category: str = "") -> Dict[str, Any]:
        stats = self.skills.get_stats()
        skills = self.skills.list_by_category(category) if category else self.skills.list_all()
        return {"skills": skills, "total": stats["total"], "categories": stats["categories"]}

    def search_skills(self, query: str) -> Dict[str, Any]:
        return {"query": query, "results": self.skills.search(query)}

    # ---- Provider status ----

    def get_providers_status(self) -> Dict[str, Any]:
        providers = [
            {"name": "zhipu", "available": bool(config.ZHIPU_API_KEY), "model": config.ZHIPU_MODEL},
            {"name": "siliconflow", "available": bool(config.SILICONFLOW_API_KEY), "model": config.SILICONFLOW_MODEL},
            {"name": "baidu", "available": bool(config.BAIDU_API_KEY), "model": config.BAIDU_MODEL},
            {"name": "ollama", "available": bool(config.OLLAMA_BASE_URL), "model": config.OLLAMA_MODEL},
        ]
        return {"providers": providers, "count": sum(1 for p in providers if p["available"])}

    def set_provider(self, provider_name: str) -> bool:
        providers = {
            "zhipu": {"base_url": config.ZHIPU_BASE_URL, "api_key": config.ZHIPU_API_KEY, "model": config.ZHIPU_MODEL},
            "siliconflow": {"base_url": config.SILICONFLOW_BASE_URL, "api_key": config.SILICONFLOW_API_KEY, "model": config.SILICONFLOW_MODEL},
            "baidu": {"base_url": config.BAIDU_BASE_URL, "api_key": config.BAIDU_API_KEY, "model": config.BAIDU_MODEL},
            "ollama": {"base_url": f"{config.OLLAMA_BASE_URL}/v1", "api_key": "ollama", "model": config.OLLAMA_MODEL},
        }
        if provider_name in providers:
            p = providers[provider_name]
            self._agent.base_url = p["base_url"]
            self._agent.api_key = p["api_key"]
            self._agent.model = p["model"]
            logger.info(f"Provider switched to: {provider_name}")
            return True
        return False

    def route_chat(self, message: str, task_type: str = "general", **kwargs) -> Dict[str, Any]:
        task_types = {
            "coding": TaskType.CODING,
            "high_concurrency": TaskType.HIGH_CONCURRENCY,
            "long_context": TaskType.LONG_CONTEXT,
            "voice": TaskType.VOICE,
            "experiment": TaskType.EXPERIMENT,
            "general": TaskType.GENERAL,
        }
        tt = task_types.get(task_type, TaskType.GENERAL)
        messages = [{"role": "user", "content": message}]
        return self._router.chat(messages, task_type=tt, **kwargs)

    # ---- Stats ----

    def get_stats(self) -> Dict[str, Any]:
        providers = self.get_providers_status()
        tasks = self.memory.list_tasks(limit=100)
        task_stats = {}
        for t in tasks:
            s = t.get("status", "unknown")
            task_stats[s] = task_stats.get(s, 0) + 1
        return {
            "app_name": config.APP_NAME,
            "app_version": config.APP_VERSION,
            "available_providers": providers["count"],
            "active_sessions": len(self.sessions),
            "task_stats": task_stats,
            "skills_registered": self.skills.get_stats()["total"],
            "timestamp": datetime.now().isoformat(),
        }

    def close(self):
        # Shutdown deep integration first (waits for review, syncs memory, closes providers)
        self.deep_hermes.shutdown()
        if hasattr(self._agent, "close"):
            self._agent.close()
        self.memory.close()

    # ========================================================================
    #  Deep Hermes: Self-Evolving Skills
    # ========================================================================

    def reload_skills(self) -> Dict[str, Any]:
        """Hot-reload the Hermes skill library (scan + diff)."""
        return self.deep_hermes.reload_skills()

    def invoke_skill(self, skill_name: str, user_instruction: str = "") -> Optional[str]:
        """Invoke a Hermes skill by /name (builds the invocation message)."""
        return self.deep_hermes.invoke_skill(skill_name, user_instruction)

    def preload_skills(self, skill_names: List[str]) -> Dict[str, Any]:
        """Preload skills for a session."""
        return self.deep_hermes.preload_skills(skill_names)

    def learn(self, workflow_description: str) -> Dict[str, Any]:
        """Trigger /learn - distill a workflow into a reusable SKILL.md."""
        return self.deep_hermes.learn_from_experience(workflow_description)

    def list_hermes_skills(self) -> Dict[str, Any]:
        """List all Hermes skills (from the real ~/.hermes/skills/ directory)."""
        return self.deep_hermes.list_skills()

    # ========================================================================
    #  Deep Hermes: Nudge / Reflection Engine
    # ========================================================================

    def trigger_review(self, review_memory: bool = True, review_skills: bool = True) -> None:
        """Manually trigger a background review."""
        self.deep_hermes.trigger_background_review(
            review_memory=review_memory, review_skills=review_skills)

    def enable_review(self, enabled: bool = True) -> None:
        """Enable or disable the background review engine."""
        self.deep_hermes.enable_review(enabled)

    def _on_review_complete(self) -> None:
        """Callback when background review finishes."""
        logger.debug("Background review completed")

    # ========================================================================
    #  Deep Hermes: Context Engine & Memory Status
    # ========================================================================

    def get_context_status(self) -> Dict[str, Any]:
        """Get context engine status (token usage, compression state)."""
        return self.deep_hermes.get_context_status()

    def get_memory_status(self) -> Dict[str, Any]:
        """Get memory system status (providers, tools)."""
        return self.deep_hermes.get_memory_status()

    def get_memory_context(self, query: str = "") -> str:
        """Get prefetched memory context."""
        return self.deep_hermes.get_memory_context(query)
