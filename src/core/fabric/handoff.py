"""
结构化交接信封 (HandoffEnvelope) —— AOS 多 Agent / 多会话结构化交接链

设计原则（遵循 Ponytail 阶梯 + AGENTS.md §10 极简优先）：
- 仅一个 dataclass：HandoffEnvelope，承载一次交接包的全部事实与边界
- store_handoff()：把信封序列化为 Markdown 存入 IMA 知识库
  （IMA 写路径已于 2026-07-15 真跑验证：openapi/note/v1/import_doc 返回 note_id）
- review_handoff()：纯只读审查，不写任何东西，输出缺口清单

刻意不做（偏重，当前不需要）：五权限模型、独立审查芯粒、复杂状态机。
信封字段 + 只读 review 步骤已覆盖「不丢上下文 / 可审计 / 可撤回」三件事。
"""
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any


@dataclass
class HandoffEnvelope:
    """结构化交接信封 —— 一次交接包的全部事实与边界"""
    task_id: str
    title: str
    summary: str                                      # 一句话结论
    confirmed_facts: List[str] = field(default_factory=list)   # 已确认事实
    assumptions: List[str] = field(default_factory=list)       # 假设（未验证前提）
    risk_boundary: List[str] = field(default_factory=list)    # 风险边界 / 禁忌
    open_questions: List[str] = field(default_factory=list)   # 未决问题
    handoff_to: str = ""                               # 交接给谁（agent / 人 / 会话）
    source: str = ""                                   # 来源（上一手）
    created_at: str = ""
    tags: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_markdown(self) -> str:
        """序列化为 IMA 笔记 Markdown（标题即首个 '# 行'）"""
        lines: List[str] = [f"# 交接: {self.title}", ""]
        lines.append(f"- task_id: `{self.task_id}`")
        lines.append(f"- 来源: {self.source or '—'}")
        lines.append(f"- 交接给: {self.handoff_to or '—'}")
        lines.append(f"- 创建: {self.created_at}")
        if self.tags:
            lines.append(f"- 标签: {', '.join(self.tags)}")
        lines.append("")
        lines.append(f"## 结论\n{self.summary}")
        lines.append("")
        lines.append("## 已确认事实")
        lines += [f"- {x}" for x in self.confirmed_facts] or ["- （无）"]
        lines.append("")
        lines.append("## 假设（未验证前提）")
        lines += [f"- {x}" for x in self.assumptions] or ["- （无）"]
        lines.append("")
        lines.append("## 风险边界 / 禁忌")
        lines += [f"- {x}" for x in self.risk_boundary] or ["- （无）"]
        lines.append("")
        lines.append("## 未决问题")
        lines += [f"- {x}" for x in self.open_questions] or ["- （无）"]
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def review_handoff(envelope: "HandoffEnvelope") -> Dict[str, Any]:
    """只读审查：不写任何东西，返回缺口清单（哪些关键字段空）"""
    gaps: List[str] = []
    if not envelope.confirmed_facts:
        gaps.append("缺少已确认事实")
    if not envelope.assumptions:
        gaps.append("未列假设（未验证前提）")
    if not envelope.risk_boundary:
        gaps.append("未标风险边界")
    if not envelope.handoff_to:
        gaps.append("未指定交接对象")
    return {
        "task_id": envelope.task_id,
        "title": envelope.title,
        "gap_count": len(gaps),
        "gaps": gaps,
        "ready": len(gaps) == 0,
    }


def store_handoff(envelope: "HandoffEnvelope", skill=None) -> Dict[str, Any]:
    """把交接信封存入 IMA 知识库（写路径 2026-07-15 实跑通过）"""
    if skill is None:
        from skills.ima import IMASkill
        skill = IMASkill()
    if not skill.is_configured():
        return {"success": False, "configured": False,
                "error": "IMA 未配置 API Key，无法存储交接信封"}
    return skill.execute({
        "operation": "create_note",
        "title": f"交接: {envelope.title}",
        "content": envelope.to_markdown(),
        "content_format": 1,
    })
