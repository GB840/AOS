"""工作流数据模型 —— AOS Studio 的核心数据结构。

一个工作流 = 一组按顺序/并发执行的步骤。
和 OrchestrationChiplet 的 steps[] 格式兼容，可以直接运行。

设计原则：
- 兼容现有格式：和 OrchestrationChiplet.steps 一一对应
- 版本化：每次保存都是新版本，可回退
- 元数据丰富：标签、分类、作者、使用统计
"""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class WorkflowStep:
    """工作流中的一个步骤。"""
    id: str = ""
    name: str = ""
    capability: str = ""  # 能力标签，如 "web.search", "action.code_exec"
    in_from: str = "previous"  # previous / initial / parallel_group_xxx
    prompt: str = ""  # 可选：给这一步的额外提示
    payload: Dict[str, Any] = field(default_factory=dict)  # 固定参数
    timeout: int = 120  # 超时时间（秒）
    retry: int = 0  # 重试次数
    max_tokens: int = 0  # LLM 步骤的 token 上限（0=不限；Task 1: Cost Observability）
    description: str = ""

    def to_chiplet_step(self) -> Dict[str, Any]:
        """转换成 OrchestrationChiplet 能识别的 step 格式。"""
        step = {
            "capability": self.capability,
            "in_from": self.in_from,
        }
        if self.prompt:
            step["prompt"] = self.prompt
        if self.payload:
            step["payload"] = self.payload
        if self.name:
            step["name"] = self.name
        # Cost Observability: max_tokens > 0 时传给 LLM 步骤的 payload
        if self.max_tokens > 0:
            step.setdefault("payload", {})
            step["payload"]["max_tokens"] = self.max_tokens
        return step


@dataclass
class Workflow:
    """一个完整的工作流。"""
    id: str = ""
    name: str = ""
    description: str = ""
    category: str = "general"  # 分类：general / coding / marketing / data / ...
    tags: List[str] = field(default_factory=list)
    author: str = "system"
    version: str = "1.0.0"
    steps: List[WorkflowStep] = field(default_factory=list)
    variables: Dict[str, Any] = field(default_factory=dict)  # 全局变量
    created_at: str = ""
    updated_at: str = ""
    run_count: int = 0
    success_rate: float = 0.0
    avg_duration: float = 0.0
    is_template: bool = False  # 是否是模板（可被复用）
    is_public: bool = False  # 是否公开（在 Hub 里可见）
    published_to_hub: bool = False  # 是否已发布到 Hub

    @classmethod
    def create(cls, name: str, description: str = "", author: str = "user") -> "Workflow":
        now = datetime.now().isoformat()
        return cls(
            id=uuid.uuid4().hex[:12],
            name=name,
            description=description,
            author=author,
            created_at=now,
            updated_at=now,
        )

    def add_step(self, capability: str, name: str = "", in_from: str = "previous",
                 prompt: str = "", payload: Dict = None) -> WorkflowStep:
        """添加一个步骤。"""
        step = WorkflowStep(
            id=uuid.uuid4().hex[:8],
            name=name or capability,
            capability=capability,
            in_from=in_from,
            prompt=prompt,
            payload=payload or {},
        )
        self.steps.append(step)
        self._touch()
        return step

    def remove_step(self, step_id: str) -> bool:
        """删除一个步骤。"""
        for i, s in enumerate(self.steps):
            if s.id == step_id:
                self.steps.pop(i)
                self._touch()
                return True
        return False

    def move_step(self, step_id: str, to_index: int) -> bool:
        """移动步骤顺序。"""
        for i, s in enumerate(self.steps):
            if s.id == step_id:
                step = self.steps.pop(i)
                to_index = max(0, min(to_index, len(self.steps)))
                self.steps.insert(to_index, step)
                self._touch()
                return True
        return False

    def to_chiplet_steps(self) -> List[Dict[str, Any]]:
        """转换成 OrchestrationChiplet 能识别的 steps 列表。"""
        return [s.to_chiplet_step() for s in self.steps]

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["steps"] = [asdict(s) for s in self.steps]
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Workflow":
        steps_data = data.pop("steps", [])
        wf = cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
        wf.steps = [WorkflowStep(**s) for s in steps_data if s]
        return wf

    def _touch(self) -> None:
        self.updated_at = datetime.now().isoformat()


@dataclass
class WorkflowRun:
    """一次工作流运行记录。"""
    id: str = ""
    workflow_id: str = ""
    workflow_version: str = ""
    status: str = "pending"  # pending / running / success / failed
    started_at: str = ""
    ended_at: str = ""
    duration: float = 0.0
    input: Dict[str, Any] = field(default_factory=dict)
    output: Dict[str, Any] = field(default_factory=dict)
    steps: List[Dict[str, Any]] = field(default_factory=list)
    error: str = ""

    @classmethod
    def create(cls, workflow_id: str, workflow_version: str = "") -> "WorkflowRun":
        return cls(
            id=uuid.uuid4().hex[:12],
            workflow_id=workflow_id,
            workflow_version=workflow_version,
            started_at=datetime.now().isoformat(),
        )
