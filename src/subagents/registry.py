"""子智能体注册中心 - 统一管理 OpenClaw / UI-TARS / LobsterAI 子智能体."""

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class SubAgentInfo:
    """子智能体元信息."""

    name: str
    description: str
    capabilities: List[str] = field(default_factory=list)
    handler: Optional[Callable] = None
    status: str = "idle"
    last_invoked: Optional[str] = None
    invoke_count: int = 0
    error_message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "capabilities": self.capabilities,
            "status": self.status,
            "last_invoked": self.last_invoked,
            "invoke_count": self.invoke_count,
            "error_message": self.error_message,
        }


class SubAgentRegistry:
    """子智能体注册中心 - 注册、发现、调用."""

    def __init__(self) -> None:
        self._agents: Dict[str, SubAgentInfo] = {}
        logger.info("SubAgentRegistry 初始化完成")

    def register(self, name: str, description: str, capabilities: List[str], handler: Callable) -> None:
        if name in self._agents:
            logger.warning(f"子智能体 {name} 已存在，将被覆盖")
        self._agents[name] = SubAgentInfo(
            name=name, description=description, capabilities=capabilities, handler=handler,
        )
        logger.info(f"子智能体已注册: {name} ({len(capabilities)} 项能力)")

    def unregister(self, name: str) -> bool:
        if name in self._agents:
            del self._agents[name]
            logger.info(f"子智能体已注销: {name}")
            return True
        return False

    def get(self, name: str) -> Optional[SubAgentInfo]:
        return self._agents.get(name)

    def list_agents(self) -> List[Dict[str, Any]]:
        return [info.to_dict() for info in self._agents.values()]

    def has(self, name: str) -> bool:
        return name in self._agents

    def invoke(self, name: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
        info = self._agents.get(name)
        if not info:
            return {"success": False, "error": f"子智能体 {name} 未注册"}
        if info.handler is None:
            return {"success": False, "error": f"子智能体 {name} 没有处理器"}
        info.status = "busy"
        try:
            result = info.handler(input_data)
            info.invoke_count += 1
            info.last_invoked = datetime.now().isoformat()
            info.status = "idle"
            info.error_message = ""
            return {"success": True, "agent": name, "data": result}
        except Exception as exc:
            info.status = "error"
            info.error_message = str(exc)
            logger.error(f"子智能体 {name} 调用失败: {exc}", exc_info=True)
            return {"success": False, "agent": name, "error": str(exc)}

    def get_stats(self) -> Dict[str, Any]:
        total = len(self._agents)
        return {
            "total": total,
            "idle": sum(1 for a in self._agents.values() if a.status == "idle"),
            "busy": sum(1 for a in self._agents.values() if a.status == "busy"),
            "error": sum(1 for a in self._agents.values() if a.status == "error"),
            "agents": list(self._agents.keys()),
        }
