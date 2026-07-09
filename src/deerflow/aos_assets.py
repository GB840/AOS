"""
AOS 开源资产归位目录 (Asset Placement Catalog)
================================================

把 AOS 仓库内所有**开源可复用构件**（subagents / skills / agency_roles）
映射到正确的器官 / 基建平面，并生成可直接喂给 DeerFlow 子智能体 /
技能系统的注册清单。

归位原则（用户决策 2026-07-08）：
- 8 个 sub-agents      → DeerFlow 子智能体（每个封装一个真实开源工具 / agent）
- ~50 个 skills        → DeerFlow 技能，按领域归到对应基建平面
                          记忆 / 知识类  → Mem0 平面
                          UI 自动化类   → browser-use 平面
                          搜索 / 媒体 / 工程 / 语音 / LLM 基础设施 → DeerFlow 技能
                          元技能         → fabric 自举能力（skill 自举）
- 271 个 agency_roles  → DeerFlow 子智能体「角色模板」(role-template subagents)
                          也可作 OpenClaw 人设技能，默认归 DeerFlow 角色模板

所有解析走静态 AST / 正则，**不执行任何资产模块**（避免 import 副作用或崩溃）。
真实注册在 DeerFlow 源码可导入时由 register_all() 一键执行；不可导入时
只产出注册清单（不假成功）。
"""

import ast
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

AOS_ROOT = Path(__file__).resolve().parents[2]  # src/deerflow -> repo root
SUBAGENTS_DIR = AOS_ROOT / "src" / "subagents"
SKILLS_DIR = AOS_ROOT / "src" / "skills"
ROLES_DIR = SKILLS_DIR / "agency_roles"

# 不是真实桥接的 sub-agent（自管注册表 / 已废弃走真实 OpenClaw）
SUBAGENT_EXCLUDE = {"__init__", "registry"}
# skills 里的框架 / 元文件，不是领域技能
SKILL_FRAMEWORK = {
    "__init__", "base", "adapter", "factory", "composition",
    "template", "agency_agents", "find_skills", "marketplace",
}
# agency_roles 里的非角色文件
ROLE_EXCLUDE = {"__init__", "__pycache__", "agent_list", "catalog", "contributing"}


# ---------------------------------------------------------------------------
# 静态解析工具（AST，不执行）
# ---------------------------------------------------------------------------

def _module_doc(path: Path) -> str:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        logger.warning("解析失败 %s: %s", path, e)
        return ""
    if (d := ast.get_docstring(tree)) :
        return d.strip().splitlines()[0] if d.strip() else ""
    return ""


def _class_attrs(path: Path, names: List[str]) -> Dict[str, Optional[str]]:
    """提取模块里第一个类的若干类属性（NAME/DESCRIPTION/CATEGORY/TAGS 等）。"""
    out: Dict[str, Optional[str]] = {n: None for n in names}
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        logger.warning("解析失败 %s: %s", path, e)
        return out
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for stmt in node.body:
                if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
                    tgt = stmt.targets[0]
                    if isinstance(tgt, ast.Name) and tgt.id in names:
                        if isinstance(stmt.value, ast.Constant):
                            out[tgt.id] = str(stmt.value.value)
                        elif isinstance(stmt.value, (ast.List, ast.Tuple)):
                            items = []
                            for elt in stmt.value.elts:
                                if isinstance(elt, ast.Constant):
                                    items.append(str(elt.value))
                            out[tgt.id] = ",".join(items)
            break  # 只看第一个类
    return out


# ---------------------------------------------------------------------------
# 归位判定
# ---------------------------------------------------------------------------

def _classify_skill(name: str, category: str, tags: str, description: str) -> str:
    """返回目标位置键。"""
    text = f"{name} {category} {tags} {description}".lower()
    if any(k in text for k in ["memory", "knowledge", "rag", "cognee", "lightrag",
                               "codebase_memory", "向量", "embedding", "zvec"]):
        return "plane:mem0"          # 记忆 / 知识 → Mem0 平面
    if any(k in text for k in ["ui", "uitars", "gui", "browser", "自动化", "automation"]):
        return "plane:browser-use"   # UI 自动化 → browser-use 平面
    if any(k in text for k in ["search", "duckduckgo", "jina", "searxng", "reader", "搜索"]):
        return "deerflow:skill"      # 搜索 → DeerFlow 技能
    if any(k in text for k in ["video", "comfyui", "pixelle", "montage", "image",
                               "design", "frontend", "ui_ux", "媒体", "图像"]):
        return "deerflow:skill"      # 媒体 / 设计 → DeerFlow 技能
    if any(k in text for k in ["voice", "tts", "asr", "audio", "语音"]):
        return "deerflow:skill"      # 语音 → DeerFlow 技能
    if any(k in text for k in ["ollama", "llama", "llm", "herdr", "omni", "lingbot", "模型"]):
        return "deerflow:skill"      # LLM 基础设施 → DeerFlow 技能
    if any(k in text for k in ["engineering", "version", "monitor", "sandbox",
                               "loop", "no_mistakes", "工程", "版本"]):
        return "deerflow:skill"      # 工程 → DeerFlow 技能
    if any(k in text for k in ["skill_creator", "learning", "superpowers", "meta", "agency", "自举"]):
        return "fabric:capability"   # 元技能 → fabric 自举能力
    return "deerflow:skill"


# ---------------------------------------------------------------------------
# 发现
# ---------------------------------------------------------------------------

@dataclass
class Asset:
    name: str
    target: str
    source: str
    note: str = ""


def discover_subagents() -> List[Asset]:
    out: List[Asset] = []
    if not SUBAGENTS_DIR.exists():
        return out
    for p in sorted(SUBAGENTS_DIR.glob("*.py")):
        stem = p.stem
        if stem in SUBAGENT_EXCLUDE:
            continue
        doc = _module_doc(p)
        out.append(Asset(
            name=stem,
            target="deerflow:subagent",
            source=f"src/subagents/{p.name}",
            note=doc,
        ))
    return out


def discover_skills() -> List[Asset]:
    out: List[Asset] = []
    if not SKILLS_DIR.exists():
        return out
    for p in sorted(SKILLS_DIR.glob("*.py")):
        stem = p.stem
        if stem in SKILL_FRAMEWORK:
            continue
        attrs = _class_attrs(p, ["NAME", "DESCRIPTION", "CATEGORY", "TAGS"])
        name = (attrs.get("NAME") or stem)
        cat = attrs.get("CATEGORY") or ""
        tags = attrs.get("TAGS") or ""
        desc = attrs.get("DESCRIPTION") or _module_doc(p)
        out.append(Asset(
            name=name,
            target=_classify_skill(name, cat, tags, desc),
            source=f"src/skills/{p.name}",
            note=f"[{cat or '?'}] {desc[:60]}",
        ))
    return out


def discover_roles() -> List[Asset]:
    out: List[Asset] = []
    if not ROLES_DIR.exists():
        return out
    for p in sorted(ROLES_DIR.glob("*.py")):
        stem = p.stem
        if stem in ROLE_EXCLUDE:
            continue
        attrs = _class_attrs(p, ["NAME", "DESCRIPTION", "CATEGORY", "TAGS"])
        name = (attrs.get("NAME") or stem)
        cat = attrs.get("CATEGORY") or ""
        desc = attrs.get("DESCRIPTION") or _module_doc(p)
        out.append(Asset(
            name=name,
            target="deerflow:role_template",
            source=f"src/skills/agency_roles/{p.name}",
            note=f"[{cat or '?'}] {desc[:50]}",
        ))
    return out


# ---------------------------------------------------------------------------
# 目录构建
# ---------------------------------------------------------------------------

def build_catalog() -> Dict[str, Any]:
    subagents = discover_subagents()
    skills = discover_skills()
    roles = discover_roles()

    # 按 target 聚合技能
    by_target: Dict[str, List[Asset]] = {}
    for a in skills:
        by_target.setdefault(a.target, []).append(a)

    return {
        "subagents": subagents,
        "skills": skills,
        "roles": roles,
        "skills_by_target": by_target,
        "summary": {
            "subagents": len(subagents),
            "skills": len(skills),
            "roles": len(roles),
            "deerflow_skills": len(by_target.get("deerflow:skill", [])),
            "mem0_plane": len(by_target.get("plane:mem0", [])),
            "browser_use_plane": len(by_target.get("plane:browser-use", [])),
            "fabric_capability": len(by_target.get("fabric:capability", [])),
        },
    }


# ---------------------------------------------------------------------------
# 生成 DeerFlow 注册清单（喂给 AOSSubagentBridge.register_subagent）
# ---------------------------------------------------------------------------

def to_deerflow_registrations(catalog: Dict[str, Any]) -> List[Dict[str, Any]]:
    """把 subagents + roles 展开为 DeerFlow 子智能体注册项。"""
    regs: List[Dict[str, Any]] = []
    for a in catalog["subagents"]:
        regs.append({
            "name": a.name,
            "description": a.note or f"{a.name} 子智能体",
            "system_prompt": a.note,
            "skills": None,
            "model": "inherit",
        })
    for a in catalog["roles"]:
        regs.append({
            "name": a.name,
            "description": a.note or f"{a.name} 角色模板",
            "system_prompt": a.note,
            "skills": None,
            "model": "inherit",
        })
    return regs


# ---------------------------------------------------------------------------
# 真实注册（DeerFlow 可导入时执行；否则只返回计划）
# ---------------------------------------------------------------------------

def register_all(bridge=None) -> Dict[str, Any]:
    """把目录里的 subagents + roles 注册进 DeerFlow。

    返回 {
        "deerflow_available": bool,
        "registered": int,
        "plan": [ ...注册项... ],
        "error": str|None,
    }
    """
    catalog = build_catalog()
    plan = to_deerflow_registrations(catalog)

    if bridge is None:
        try:
            from src.deerflow.subagent_executor import AOSSubagentBridge
            bridge = AOSSubagentBridge()
        except Exception as e:  # noqa: BLE001
            logger.warning("DeerFlow 桥接不可导入，只产出注册计划: %s", e)
            return {"deerflow_available": False, "registered": 0,
                    "plan": plan, "error": str(e)}

    registered = 0
    for r in plan:
        try:
            bridge.register_subagent(
                r["name"], r["description"],
                system_prompt=r["system_prompt"],
                skills=r["skills"], model=r["model"],
            )
            registered += 1
        except Exception as e:  # noqa: BLE001
            logger.warning("注册 %s 失败: %s", r["name"], e)
    return {"deerflow_available": True, "registered": registered,
            "plan": plan, "error": None}


if __name__ == "__main__":
    cat = build_catalog()
    s = cat["summary"]
    print(f"subagents : {s['subagents']}")
    print(f"skills    : {s['skills']}  (deerflow={s['deerflow_skills']}, "
          f"mem0={s['mem0_plane']}, browser-use={s['browser_use_plane']}, "
          f"fabric={s['fabric_capability']})")
    print(f"roles     : {s['roles']}")
    print(f"deerflow 子智能体注册项(含 roles): {len(to_deerflow_registrations(cat))}")
