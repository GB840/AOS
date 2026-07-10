"""v1.0 UI 层：抽象 UI 接口 + 三个 UI 面（可换皮）。

这是 v1.0 物种思维中"UI 层（可换皮）"的默认实现。
提供了抽象 UILayer(ABC) 接口，使得 UI 是可替换的（今天 Web UI，明天 CLI /
桌面 / 移动端）而内核不改。三 UI 面分别对应结构图中的对话面板、Agent 工作台、
应用商店。

每个 UI 面用 UISurface 描述符表示，UILayer 实现决定如何渲染。
默认的 WebUILayer 返回三个 surface；CLI 实现可返回同样三个 surface 以文本渲染。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ─── UI 表面描述符（框架无关） ───────────────────────────────────

class SurfaceKind:
    """UI 面类型命名空间。"""
    CHAT_PANEL = "chat_panel"
    AGENT_WORKBENCH = "agent_workbench"
    APP_STORE = "app_store"


@dataclass
class UISurface:
    """框架无关的 UI 面描述符。

    id / title / kind 是必选元数据。
    routes 是 Web UI 的路由提示（CLI 可忽略）。
    capabilities 声明该表面的交互能力（streaming / file-upload / etc）。
    """
    id: str
    title: str
    kind: str
    description: str = ""
    routes: List[str] = field(default_factory=list)
    capabilities: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class UIRender:
    """UILayer.render() 的返回：一个表面的渲染描述。"""
    surface_id: str
    kind: str
    title: str
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


# ─── UI 层抽象接口 ───────────────────────────────────────────────

class UILayer(ABC):
    """抽象 UI 层。实现可以是 WebUI / CLI / Desktop / Mobile — 内核依赖此
    接口，不依赖具体 UI 框架。"""

    @abstractmethod
    def list_surfaces(self) -> List[UISurface]:
        """列出当前 UI 层的所有表面（对话面板 / Agent 工作台 / 应用商店）。"""
        ...

    @abstractmethod
    def render(self, surface_id: str, context: Dict[str, Any] | None = None) -> UIRender:
        """渲染一个 UI 面。context 含 caller_agent / current_task 等运行时信息。"""
        ...

    @abstractmethod
    def platform(self) -> str:
        """返回 UI 平台标识：'web' / 'cli' / 'desktop' / 'mobile'。"""
        ...


# ─── 默认 Web UI 实现 ────────────────────────────────────────────

class WebUILayer(UILayer):
    """Web UI 层默认实现。

    暴露 v1.0 结构图的三个 UI 面：对话面板、Agent 工作台、应用商店。
    返回框架无关的 UISurface 描述符，由具体 Web 框架（Streamlit / FastAPI
    渲染器）负责 HTML 产出。兼容现有 web/app.py 的升级路径。
    """

    def __init__(self, base_url: str = "http://localhost:8000") -> None:
        self.base_url = base_url

    def list_surfaces(self) -> List[UISurface]:
        return [
            UISurface(
                id="chat_panel",
                title="对话面板",
                kind=SurfaceKind.CHAT_PANEL,
                description="与 Agent 实时对话，支持流式输出",
                routes=["/chat", "/api/chat", "/ws/chat"],
                capabilities=["streaming", "markdown", "file-upload"],
            ),
            UISurface(
                id="agent_workbench",
                title="Agent 工作台",
                kind=SurfaceKind.AGENT_WORKBENCH,
                description="管理 Agent 实例、编排任务、监控运行时状态",
                routes=["/agents", "/api/agents"],
                capabilities=["dashboard", "workflow-builder", "status-monitor"],
            ),
            UISurface(
                id="app_store",
                title="应用商店",
                kind=SurfaceKind.APP_STORE,
                description="一键安装社区技能、Agent 模板、新模型适配器",
                routes=["/store", "/api/store"],
                capabilities=["browse", "install", "publish"],
            ),
        ]

    def render(self, surface_id: str,
               context: Dict[str, Any] | None = None) -> UIRender:
        ctx = context or {}
        for s in self.list_surfaces():
            if s.id == surface_id:
                return UIRender(
                    surface_id=s.id, kind=s.kind, title=s.title,
                    data={"surface": s, "context": ctx,
                          "base_url": self.base_url},
                )
        return UIRender(surface_id=surface_id, kind="unknown", title="Not Found",
                        error=f"surface {surface_id!r} not found")

    def platform(self) -> str:
        return "web"


# ─── CLI UI 实现（示例：证明"可换皮"） ───────────────────────────

class CLIUILayer(UILayer):
    """CLI 终端 UI 层。

    证明 UILayer 是可替换的：同一套 AOS 系统，换 WebUILayer → CLI 终端输出。
    """

    def list_surfaces(self) -> List[UISurface]:
        return [
            UISurface(id="chat_panel", title="对话面板",
                      kind=SurfaceKind.CHAT_PANEL,
                      description="终端对话，逐行输入"),
            UISurface(id="agent_workbench", title="Agent 工作台",
                      kind=SurfaceKind.AGENT_WORKBENCH,
                      capabilities=["dashboard", "status-monitor"]),
            UISurface(id="app_store", title="应用商店",
                      kind=SurfaceKind.APP_STORE,
                      capabilities=["browse", "install"]),
        ]

    def render(self, surface_id: str,
               context: Dict[str, Any] | None = None) -> UIRender:
        ctx = context or {}
        for s in self.list_surfaces():
            if s.id == surface_id:
                return UIRender(
                    surface_id=s.id, kind="cli-" + s.kind, title=s.title,
                    data={"surface": s, "context": ctx,
                          "output_mode": "text"},
                )
        return UIRender(surface_id=surface_id, kind="unknown", title="Not Found",
                        error=f"CLI surface {surface_id!r} not found")

    def platform(self) -> str:
        return "cli"
