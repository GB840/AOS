"""
AOS v5.0 — 通知服务 (Notify)

对标蓝图 NOTIFY(站内/Webhook/WS)。满足蓝图节点: NOTIFY。
设计原则 (严谨 + 开放 + 灵活):
  - 通道可插拔: 内置 in_app(写 Notification ORM 表) 与 webhook(需 requests, 自动探测)。
  - WS 通道暴露 send_ws 接口 (由上层 websocket 服务注入回调), 无 WS 服务时优雅降级。
  - 任何通道失败都不阻断其他通道; send() 返回每个通道的结果清单。
"""

import json
import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class NotificationService:
    def __init__(self):
        self._channels: Dict[str, Callable[[str, Dict[str, Any]], Any]] = {}
        self._ws_sender: Optional[Callable[[str, Dict[str, Any]], Any]] = None
        self._register_builtins()

    def _register_builtins(self) -> None:
        self.register("in_app", self._send_in_app)
        self.register("webhook", self._send_webhook)
        self.register("ws", self._send_ws)

    # ---- 公共 API ----
    def register(self, name: str, sender: Callable[[str, Dict[str, Any]], Any]) -> None:
        self._channels[name] = sender

    def set_ws_sender(self, fn: Callable[[str, Dict[str, Any]], Any]) -> None:
        """注入 WS 发送回调 (由 websocket 服务在启动时设置)。"""
        self._ws_sender = fn

    def send(self, agent_id: str, payload: Dict[str, Any],
             channels: Optional[List[str]] = None) -> Dict[str, Any]:
        """向指定 agent 发送通知。返回 {channel: result/error}。"""
        want = channels or list(self._channels.keys())
        results: Dict[str, Any] = {}
        for ch in want:
            sender = self._channels.get(ch)
            if sender is None:
                results[ch] = {"ok": False, "error": "unknown channel"}
                continue
            try:
                results[ch] = {"ok": True, "result": sender(agent_id, payload)}
            except Exception as e:  # pragma: no cover - 单通道失败不影响其他
                logger.warning("notify channel %s failed: %s", ch, e)
                results[ch] = {"ok": False, "error": str(e)}
        return results

    # ---- 通道实现 ----
    def _send_in_app(self, agent_id: str, payload: Dict[str, Any]) -> Any:
        try:
            from core.database import session_scope
            from core.database.models import Notification

            with session_scope() as s:
                s.add(Notification(
                    agent_id=agent_id,
                    channel="in_app",
                    payload_json=json.dumps(payload, ensure_ascii=False),
                    read=False,
                ))
                s.commit()
            return {"stored": True}
        except Exception as e:  # pragma: no cover - DB 不可用时降级
            logger.debug("in_app 通知落库失败 (忽略): %s", e)
            return {"stored": False, "error": str(e)}

    def _send_webhook(self, agent_id: str, payload: Dict[str, Any]) -> Any:
        try:
            import requests  # 可选依赖
        except Exception as e:
            logger.warning("requests library not available for webhook: %s", e)
            return {"sent": False, "error": "requests not installed"}
        url = payload.get("webhook_url")
        if not url:
            return {"sent": False, "error": "no webhook_url"}
        try:
            resp = requests.post(url, json=payload, timeout=5)
            return {"sent": True, "status": resp.status_code}
        except Exception as e:  # pragma: no cover
            logger.warning("Webhook POST failed: %s", e)
            return {"sent": False, "error": str(e)}

    def _send_ws(self, agent_id: str, payload: Dict[str, Any]) -> Any:
        if self._ws_sender is None:
            return {"sent": False, "error": "ws sender not configured"}
        try:
            self._ws_sender(agent_id, payload)
            return {"sent": True}
        except Exception as e:  # pragma: no cover
            logger.warning("WS notification failed: %s", e)
            return {"sent": False, "error": str(e)}
