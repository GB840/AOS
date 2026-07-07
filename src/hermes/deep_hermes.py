"""
Deep Hermes Integration - Complete self-evolving agent lifecycle.

Wires AOS into Hermes Agent's FULL capabilities:
1. Self-Evolving Skills: /learn command, automatic skill generation from tool calls > 5
2. Nudge/Reflection Engine: background_review after each turn (memory + skill updates)
3. Full Memory Lifecycle: prefetch, sync, session hooks, MEMORY.md/USER.md
4. Context Engine: context_compressor with token budget management
5. Skill Commands: scan, reload, build invocation messages
"""

import logging
import threading
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable

logger = logging.getLogger(__name__)

from utils.config import config

# ---- Hermes Agent 路径自动检测 ----
_HERMES_SRC = None

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
            return candidate
    return None

_HERMES_SRC = _detect_hermes_path()

if _HERMES_SRC and _HERMES_SRC not in sys.path:
    sys.path.insert(0, _HERMES_SRC)
    logger.info(f"DeepHermes: Hermes Agent 源码路径已添加: {_HERMES_SRC}")


class DeepHermesIntegration:
    """Complete Hermes Agent lifecycle integration for AOS.

    This class wraps the FULL Hermes Agent capabilities that were previously
    unused. It provides:

    1. Self-Evolving Skills: Skills auto-generated from complex tool use,
       skill library scanning, slash-command invocation, and hot-reload.

    2. Nudge/Reflection Engine: After each turn, a forked AIAgent reviews
       the conversation and autonomously updates memory and skills.

    3. Memory Lifecycle: Proper prefetch → turn → sync cycle with
       MEMORY.md/USER.md persistence, semantic recall, and context fencing.

    4. Context Engine: Real token tracking, compression threshold management,
       and context budget enforcement.

    Usage:
        deep = DeepHermesIntegration(agent)
        deep.on_turn_start(message, turn_number=1)
        response = agent.chat(message)
        deep.on_turn_end(message, response)
        deep.trigger_background_review()
    """

    def __init__(self, agent):
        """Initialize deep integration with a Hermes AIAgent instance.

        Args:
            agent: The real AIAgent from run_agent.py (NOT the AOS wrapper)
        """
        self._agent = agent
        self._turn_number = 0
        self._session_messages: List[Dict] = []
        self._review_enabled = True
        self._review_thread: Optional[threading.Thread] = None
        self._on_review_complete: Optional[Callable] = None

        # Memory store references
        self._memory_store = getattr(agent, "_memory_store", None)
        self._memory_enabled = getattr(agent, "_memory_enabled", True)
        self._user_profile_enabled = getattr(agent, "_user_profile_enabled", True)

        # Skill system
        self._skills_dir = None
        self._skill_commands = {}
        self._last_skill_scan = None

        # Context engine
        self._context_engine = getattr(agent, "_context_engine", None)
        self._context_compressor = getattr(agent, "_context_compressor", None)

        # Initialize skill scanning
        self._init_skills()

        logger.info(
            "DeepHermesIntegration initialized: "
            "skills=%d, memory=%s, review=%s, context=%s",
            len(self._skill_commands),
            "enabled" if self._memory_enabled else "disabled",
            "enabled" if self._review_enabled else "disabled",
            type(self._context_engine).__name__ if self._context_engine else "none",
        )

    # ================================================================
    # 1. SELF-EVOLVING SKILLS
    # ================================================================

    def _init_skills(self) -> None:
        """Scan and load the Hermes skill library."""
        try:
            from agent.skill_commands import scan_skill_commands, get_skill_commands
            self._skill_commands = scan_skill_commands()
            self._last_skill_scan = datetime.now()
            logger.info(
                "Scanned %d Hermes skills from %s",
                len(self._skill_commands),
                self._get_skills_dir(),
            )
        except Exception as e:
            logger.warning("Skill scan failed (non-fatal): %s", e)
            self._skill_commands = {}

    def _get_skills_dir(self) -> str:
        """Get the Hermes skills directory path."""
        if self._skills_dir:
            return self._skills_dir
        try:
            from tools.skills_tool import SKILLS_DIR
            self._skills_dir = str(SKILLS_DIR)
        except Exception:
            try:
                from hermes_constants import get_hermes_home
                self._skills_dir = str(get_hermes_home() / "skills")
            except Exception:
                self._skills_dir = os.path.expanduser("~/.hermes/skills")
        return self._skills_dir

    def reload_skills(self) -> Dict[str, Any]:
        """Hot-reload the skill library and return diff.

        Returns:
            Dict with 'added', 'removed', 'unchanged', 'total', 'commands'.
        """
        try:
            from agent.skill_commands import reload_skills
            diff = reload_skills()
            self._skill_commands = {}
            self._last_skill_scan = datetime.now()
            # Re-scan to refresh local cache
            self._init_skills()
            logger.info(
                "Skills reloaded: +%d added, -%d removed, %d total",
                len(diff.get("added", [])),
                len(diff.get("removed", [])),
                diff.get("total", 0),
            )
            return diff
        except Exception as e:
            logger.error("Skill reload failed: %s", e)
            return {"error": str(e)}

    def list_skills(self) -> Dict[str, Any]:
        """List all Hermes skills with details."""
        return {
            "skills": [
                {
                    "command": cmd,
                    "name": info.get("name", ""),
                    "description": info.get("description", ""),
                    "skill_dir": info.get("skill_dir", ""),
                }
                for cmd, info in self._skill_commands.items()
            ],
            "total": len(self._skill_commands),
            "skills_dir": self._get_skills_dir(),
            "last_scan": (
                self._last_skill_scan.isoformat()
                if self._last_skill_scan else None
            ),
        }

    def invoke_skill(self, skill_name: str, user_instruction: str = "") -> Optional[str]:
        """Build a skill invocation message for a /skill-name command.

        This is the equivalent of a user typing /skill-name in Hermes CLI.
        """
        try:
            from agent.skill_commands import build_skill_invocation_message
            cmd_key = "/" + skill_name.lower().replace("_", "-").lstrip("/")
            return build_skill_invocation_message(
                cmd_key,
                user_instruction=user_instruction,
                task_id=getattr(self._agent, "session_id", None),
            )
        except Exception as e:
            logger.warning("Skill invocation '%s' failed: %s", skill_name, e)
            return None

    def preload_skills(self, skill_names: List[str]) -> Dict[str, Any]:
        """Preload skills for a session (like --skill flag in CLI)."""
        try:
            from agent.skill_commands import build_preloaded_skills_prompt
            prompt, loaded, missing = build_preloaded_skills_prompt(skill_names)
            return {
                "prompt": prompt,
                "loaded": loaded,
                "missing": missing,
                "success": len(missing) == 0,
            }
        except Exception as e:
            logger.warning("Skill preload failed: %s", e)
            return {"error": str(e), "loaded": [], "missing": skill_names}

    def learn_from_experience(self, workflow_description: str) -> Dict[str, Any]:
        """Trigger the /learn command - distill a workflow into a reusable skill.

        This is Hermes' core self-evolution mechanism. When the agent has
        performed a complex task (>5 tool calls), it can auto-generate a
        SKILL.md from the experience.
        """
        learn_message = (
            f"[IMPORTANT: The user wants you to learn from this experience. "
            f"Distill the following workflow into a reusable skill:]\n\n"
            f"{workflow_description}\n\n"
            f"Create a SKILL.md with clear steps, pitfalls, and triggers. "
            f"Use the skill_manage tool to save it."
        )
        return {"message": learn_message, "action": "learn"}

    # ================================================================
    # 2. NUDGE / REFLECTION ENGINE
    # ================================================================

    def trigger_background_review(
        self,
        review_memory: bool = True,
        review_skills: bool = True,
        callback: Optional[Callable] = None,
    ) -> None:
        """Spawn a background review thread after a conversation turn.

        The review agent is a forked AIAgent that:
        - Reviews the conversation for memory-worthy facts
        - Updates skills based on user corrections and new techniques
        - Writes directly to MEMORY.md / USER.md and skill files
        - Surfaces a summary of actions taken

        Args:
            review_memory: Whether to review and update memory.
            review_skills: Whether to review and update skills.
            callback: Optional callback(review_summary) when review completes.
        """
        if not self._review_enabled:
            return

        messages_snapshot = list(self._session_messages)
        if not messages_snapshot:
            return

        self._on_review_complete = callback

        try:
            from agent.background_review import spawn_background_review_thread

            # Build review target and prompt
            target, prompt = spawn_background_review_thread(
                self._agent,
                messages_snapshot,
                review_memory=review_memory,
                review_skills=review_skills,
            )

            # Spawn daemon thread
            self._review_thread = threading.Thread(
                target=self._run_review_with_callback,
                args=(target, prompt),
                daemon=True,
                name="hermes-bg-review",
            )
            self._review_thread.start()
            logger.debug("Background review spawned (memory=%s, skills=%s)", review_memory, review_skills)

        except Exception as e:
            logger.warning("Background review spawn failed: %s", e)

    def _run_review_with_callback(self, target, prompt) -> None:
        """Run the review and trigger callback."""
        try:
            target()
        except Exception as e:
            logger.debug("Background review error (non-fatal): %s", e)
        finally:
            if self._on_review_complete:
                try:
                    self._on_review_complete()
                except Exception:
                    pass

    def enable_review(self, enabled: bool = True) -> None:
        """Enable or disable the background review engine."""
        self._review_enabled = enabled
        logger.info("Background review %s", "enabled" if enabled else "disabled")

    def set_review_callback(self, callback: Optional[Callable]) -> None:
        """Set a callback for review completion notifications."""
        self._on_review_complete = callback

    # ================================================================
    # 3. MEMORY LIFECYCLE
    # ================================================================

    def on_turn_start(self, message: str, turn_number: int = 0, **kwargs) -> str:
        """Run full memory prefetch before a conversation turn.

        This is the proper Hermes memory lifecycle:
        1. Prefetch semantic recall based on the user's message
        2. Notify memory providers of turn start
        3. Return prefetched context for injection into the conversation

        Returns:
            Prefetched memory context string (may be empty).
        """
        self._turn_number = turn_number

        memory_manager = getattr(self._agent, "_memory_manager", None)
        if not memory_manager:
            return ""

        # Notify providers of turn start
        try:
            memory_manager.on_turn_start(
                turn_number,
                message,
                remaining_tokens=kwargs.get("remaining_tokens", 0),
                model=kwargs.get("model", ""),
                platform=kwargs.get("platform", "aos"),
                tool_count=kwargs.get("tool_count", 0),
            )
        except Exception as e:
            logger.debug("on_turn_start failed: %s", e)

        # Prefetch context
        context = ""
        try:
            session_id = getattr(self._agent, "session_id", "")
            context = memory_manager.prefetch_all(message, session_id=session_id)
        except Exception as e:
            logger.debug("prefetch_all failed: %s", e)

        return context or ""

    def on_turn_end(self, user_message: str, assistant_response: str) -> None:
        """Sync memory after a conversation turn.

        This persists the turn to all memory providers and queues
        the next prefetch for faster subsequent recall.
        """
        memory_manager = getattr(self._agent, "_memory_manager", None)
        if not memory_manager:
            return

        try:
            session_id = getattr(self._agent, "session_id", "")
            memory_manager.sync_all(
                user_message,
                assistant_response,
                session_id=session_id,
                messages=list(self._session_messages),
            )
        except Exception as e:
            logger.debug("sync_all failed: %s", e)

        # Queue prefetch for next turn
        try:
            memory_manager.queue_prefetch_all(user_message, session_id=session_id)
        except Exception as e:
            logger.debug("queue_prefetch_all failed: %s", e)

    def on_session_end(self) -> None:
        """Notify memory providers of session end."""
        memory_manager = getattr(self._agent, "_memory_manager", None)
        if not memory_manager:
            return
        try:
            memory_manager.on_session_end(list(self._session_messages))
        except Exception as e:
            logger.debug("on_session_end failed: %s", e)

    def on_session_switch(self, new_session_id: str, **kwargs) -> None:
        """Notify memory providers of session rotation."""
        memory_manager = getattr(self._agent, "_memory_manager", None)
        if not memory_manager:
            return
        try:
            memory_manager.on_session_switch(new_session_id, **kwargs)
        except Exception as e:
            logger.debug("on_session_switch failed: %s", e)

    def get_memory_context(self, query: str = "") -> str:
        """Get prefetched memory context for the current state."""
        memory_manager = getattr(self._agent, "_memory_manager", None)
        if not memory_manager:
            return ""
        try:
            session_id = getattr(self._agent, "session_id", "")
            return memory_manager.prefetch_all(query or "current context", session_id=session_id)
        except Exception as e:
            logger.debug("get_memory_context failed: %s", e)
            return ""

    def get_memory_status(self) -> Dict[str, Any]:
        """Get memory system status."""
        memory_manager = getattr(self._agent, "_memory_manager", None)
        if not memory_manager:
            return {"enabled": False}

        providers = []
        for p in memory_manager.providers:
            providers.append({
                "name": p.name,
                "tools": len(p.get_tool_schemas()),
            })

        return {
            "enabled": True,
            "providers": providers,
            "total_tools": len(memory_manager.get_all_tool_names()),
            "memory_store": bool(self._memory_store),
            "user_profile_enabled": self._user_profile_enabled,
        }

    # ================================================================
    # 4. CONTEXT ENGINE
    # ================================================================

    def get_context_status(self) -> Dict[str, Any]:
        """Get context engine status for token management."""
        engine = self._context_engine or self._context_compressor
        if not engine:
            return {"engine": "none"}

        return {
            "engine": type(engine).__name__,
            "context_length": getattr(engine, "context_length", 0),
            "threshold_tokens": getattr(engine, "threshold_tokens", 0),
            "threshold_percent": getattr(engine, "threshold_percent", 0.75),
            "last_prompt_tokens": getattr(engine, "last_prompt_tokens", 0),
            "last_completion_tokens": getattr(engine, "last_completion_tokens", 0),
            "last_total_tokens": getattr(engine, "last_total_tokens", 0),
            "compression_count": getattr(engine, "compression_count", 0),
            "usage_percent": (
                min(100, getattr(engine, "last_prompt_tokens", 0) / getattr(engine, "context_length", 1) * 100)
                if getattr(engine, "context_length", 0) else 0
            ),
            "protect_first_n": getattr(engine, "protect_first_n", 3),
            "protect_last_n": getattr(engine, "protect_last_n", 6),
        }

    def should_compress(self) -> bool:
        """Check if context compression should fire."""
        engine = self._context_engine or self._context_compressor
        if not engine:
            return False
        try:
            return engine.should_compress()
        except Exception:
            return False

    def compress_context(self, focus_topic: str = "") -> Optional[List[Dict]]:
        """Trigger context compression.

        Returns the compacted message list, or None if compression wasn't needed.
        """
        engine = self._context_engine or self._context_compressor
        if not engine:
            return None
        try:
            if not engine.should_compress():
                return None
            return engine.compress(
                list(self._session_messages),
                focus_topic=focus_topic,
            )
        except Exception as e:
            logger.warning("Context compression failed: %s", e)
            return None

    # ================================================================
    # 5. INTEGRATED CONVERSATION TURN
    # ================================================================

    def full_conversation_turn(
        self,
        message: str,
        chat_fn: Callable,
        **kwargs,
    ) -> Dict[str, Any]:
        """Execute a complete conversation turn with full lifecycle.

        This is the "圆润如一" integration point. It runs:
        1. Memory prefetch (recall relevant context)
        2. Context compression check
        3. Conversation turn
        4. Memory sync (persist this turn)
        5. Background review (reflect and improve)

        Args:
            message: User's message.
            chat_fn: Function that takes a message and returns a response dict.
            **kwargs: Additional arguments passed to chat_fn.

        Returns:
            Response dict from chat_fn, enriched with lifecycle metadata.
        """
        # 1. Prefetch memory context
        memory_context = self.on_turn_start(message, turn_number=self._turn_number + 1)

        # 2. Check if context compression is needed
        if self.should_compress():
            compressed = self.compress_context()
            if compressed:
                self._session_messages = compressed
                logger.info("Context compressed: %d messages", len(compressed))

        # 3. Run the conversation turn
        # Inject memory context if available
        enriched_message = message
        if memory_context:
            from agent.memory_manager import build_memory_context_block
            enriched_message = (
                build_memory_context_block(memory_context) + "\n\n" + message
            )

        response = chat_fn(enriched_message, **kwargs)

        # 4. Sync memory
        response_text = response.get("response", "") if isinstance(response, dict) else str(response)
        self.on_turn_end(message, response_text)

        # 5. Trigger background review (non-blocking)
        if self._review_enabled:
            self.trigger_background_review(
                review_memory=True,
                review_skills=True,
            )

        # Enrich response with lifecycle metadata
        if isinstance(response, dict):
            response["_lifecycle"] = {
                "turn_number": self._turn_number,
                "memory_prefetched": bool(memory_context),
                "context_compressed": self.should_compress(),
                "review_spawned": self._review_enabled,
                "context_status": self.get_context_status(),
            }

        return response

    # ================================================================
    # 6. SHUTDOWN
    # ================================================================

    def shutdown(self) -> None:
        """Clean shutdown: wait for review, sync memory, close providers."""
        # Wait for background review to complete
        if self._review_thread and self._review_thread.is_alive():
            self._review_thread.join(timeout=30)

        # End session
        self.on_session_end()

        # Shutdown memory providers
        memory_manager = getattr(self._agent, "_memory_manager", None)
        if memory_manager:
            try:
                memory_manager.shutdown_all()
            except Exception as e:
                logger.debug("Memory shutdown failed: %s", e)

        logger.info("DeepHermesIntegration shutdown complete")


# ================================================================
# FACTORY
# ================================================================

def create_deep_hermes(agent) -> DeepHermesIntegration:
    """Create a DeepHermesIntegration for a Hermes AIAgent.

    Args:
        agent: The real AIAgent from run_agent.py.

    Returns:
        Configured DeepHermesIntegration instance.
    """
    return DeepHermesIntegration(agent)