"""Agency 角色「带工具 Agent」共享基元（试点：短视频剪辑指导师）。

目的：让原本"纯 prompt 包装"的角色升级为真正能调用**确定性离线工具**的 Agent。
- 工具是普通 Python 函数，不依赖 LLM / 大脑，可独立运行、可单测。
- 与 AOS 大脑解耦：角色既保留 prompt→brain 的教练路径，也能在 `tool` 指定时走工具。

本模块刻意放在 `agency_roles/` 内、不污染 `skills/base.py`，以便作为试点验证；
若模式成熟，可上提到 `skills/` 公共层。
"""

from dataclasses import dataclass
from typing import Any, Callable, Dict, List


@dataclass
class Tool:
    """单个工具的描述与实现。"""

    name: str
    description: str
    func: Callable[..., Any]
    parameters: str = ""  # 人类可读参数说明


class ToolBox:
    """工具的注册与调用容器。"""

    def __init__(self) -> None:
        self._tools: Dict[str, Tool] = {}

    def register(
        self,
        name: str,
        description: str,
        func: Callable[..., Any],
        parameters: str = "",
    ) -> None:
        self._tools[name] = Tool(name=name, description=description, func=func, parameters=parameters)

    def has(self, name: str) -> bool:
        return name in self._tools

    def names(self) -> List[str]:
        return list(self._tools.keys())

    def describe(self) -> List[Dict[str, str]]:
        return [
            {"name": t.name, "description": t.description, "parameters": t.parameters}
            for t in self._tools.values()
        ]

    def call(self, name: str, **kwargs: Any) -> Any:
        if name not in self._tools:
            raise KeyError(f"未知工具: {name}，可用: {self.names()}")
        return self._tools[name].func(**kwargs)
