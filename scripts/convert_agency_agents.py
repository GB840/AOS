"""
Agency Agents 转 AOS Skills 转换器
===================================

将 agency-agents-zh 中的所有部门角色转换为 AOS Skill 类。
"""

import sys
import os
import re
from pathlib import Path
from typing import Dict, Any, List
from dataclasses import dataclass

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from src.skills.base import Skill, SkillMeta, SkillRegistry


@dataclass
class AgentDefinition:
    name: str
    description: str
    emoji: str
    color: str
    category: str
    identity: str
    mission: str
    rules: List[str]
    deliverables: str
    workflow: str
    expertise: str
    communication: str
    success_metrics: str
    filepath: Path


def sanitize_filename(name: str) -> str:
    result = name.lower()
    result = re.sub(r"[^\w\s-]", "", result)
    result = re.sub(r"[\s-]+", "_", result)
    result = result.strip("_")
    if not result:
        result = "unknown"
    return result


def generate_class_name(name: str) -> str:
    result = re.sub(r"[^\w\s]", "", name)
    words = result.split()
    class_name = "".join(word.capitalize() for word in words)
    if not class_name or class_name[0].isdigit():
        class_name = "Agent" + class_name
    return class_name + "Skill"


def parse_markdown_file(filepath: Path) -> AgentDefinition:
    content = filepath.read_text(encoding="utf-8")
    
    frontmatter_match = re.match(r"---\n(.*?)\n---", content, re.DOTALL)
    frontmatter = {}
    if frontmatter_match:
        for line in frontmatter_match.group(1).split("\n"):
            if ":" in line:
                key, value = line.split(":", 1)
                frontmatter[key.strip()] = value.strip().strip('"')
    
    name = frontmatter.get("name", filepath.stem.replace("-", " ").title())
    description = frontmatter.get("description", "")
    emoji = frontmatter.get("emoji", "🧠")
    color = frontmatter.get("color", "gray")
    
    body = content[frontmatter_match.end():] if frontmatter_match else content
    
    identity = extract_section(body, "身份与记忆") or extract_section(body, "你的身份与记忆") or ""
    mission = extract_section(body, "核心使命") or extract_section(body, "你的核心使命") or ""
    rules = extract_list_section(body, "关键规则") or extract_list_section(body, "你必须遵守的关键规则") or \
            extract_list_section(body, "必须遵守的规则") or []
    deliverables = extract_section(body, "技术交付物") or ""
    workflow = extract_section(body, "工作流程") or ""
    expertise = extract_section(body, "领域专长") or ""
    communication = extract_section(body, "沟通风格") or ""
    success_metrics = extract_section(body, "成功指标") or ""
    
    category = filepath.parent.name
    
    return AgentDefinition(
        name=name,
        description=description,
        emoji=emoji,
        color=color,
        category=category,
        identity=identity,
        mission=mission,
        rules=rules,
        deliverables=deliverables,
        workflow=workflow,
        expertise=expertise,
        communication=communication,
        success_metrics=success_metrics,
        filepath=filepath
    )


def remove_code_blocks(content: str) -> str:
    content = re.sub(r"```[\s\S]*?```", "", content)
    content = re.sub(r"`[^`]+`", "", content)
    return content


def extract_section(content: str, section_name: str) -> str:
    pattern = rf"##\s*{section_name}\s*\n(.*?)(?=\n##\s|$)"
    match = re.search(pattern, content, re.DOTALL)
    if match:
        content = match.group(1).strip()
        content = remove_code_blocks(content)
        return content
    return ""


def extract_list_section(content: str, section_name: str) -> List[str]:
    pattern = rf"##\s*{section_name}\s*\n(.*?)(?=\n##\s|$)"
    match = re.search(pattern, content, re.DOTALL)
    if match:
        content = match.group(1).strip()
        content = remove_code_blocks(content)
        lines = content.split("\n")
        rules = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith("###") and not line.startswith("####"):
                rule = re.sub(r"^[\d\.\-\*•]+\s*", "", line).strip()
                if rule:
                    rules.append(rule)
        return rules
    return []


def get_capabilities(category: str) -> List[str]:
    capabilities_map = {
        "engineering": ["code_generation", "system_design", "technical_analysis"],
        "finance": ["financial_analysis", "financial_modeling", "business_intelligence"],
        "sales": ["sales_strategy", "deal_analysis", "customer_interaction"],
        "marketing": ["marketing_strategy", "content_creation", "campaign_management"],
        "security": ["security_analysis", "threat_detection", "compliance"],
        "hr": ["employee_management", "recruitment", "performance"],
        "legal": ["legal_advice", "contract_review", "compliance"],
        "project-management": ["project_planning", "task_management", "team_coordination"],
        "testing": ["test_design", "quality_assurance", "bug_analysis"],
        "support": ["customer_support", "issue_resolution", "technical_support"],
        "product": ["product_design", "requirements_analysis", "user_research"],
        "paid-media": ["advertising", "media_buying", "performance_analysis"],
        "supply-chain": ["supply_chain_management", "logistics", "inventory"],
        "game-development": ["game_design", "game_development", "technical_art"],
        "gis": ["geospatial_analysis", "map_development", "location_intelligence"],
        "academic": ["research", "writing", "analysis"],
        "design": ["design", "ui_ux", "creative"],
        "specialized": ["consulting", "analysis", "strategy"],
        "spatial-computing": ["xr_development", "spatial_design", "immersive"],
    }
    return capabilities_map.get(category, ["consulting", "analysis", "strategy"])


def escape_string(s: str) -> str:
    s = s.replace('\\', '\\\\')
    s = s.replace('"', '\\"')
    s = s.replace("'", "\\'")
    s = s.replace('\n', '\\n')
    s = s.replace('\r', '\\r')
    return s


def generate_skill_class(agent: AgentDefinition) -> str:
    skill_name = sanitize_filename(agent.name)
    class_name = generate_class_name(agent.name)
    capabilities = get_capabilities(agent.category)
    capabilities_str = ", ".join(f'"{c}"' for c in capabilities)
    description = escape_string(agent.description)
    
    rules_str = "\n".join(f"- {rule}" for rule in agent.rules)
    
    identity_section = agent.identity
    mission_section = agent.mission
    rules_section = rules_str
    workflow_section = agent.workflow
    expertise_section = agent.expertise
    communication_section = agent.communication
    
    prompt_parts = []
    prompt_parts.append(f'你是{agent.emoji}【{agent.name}】。\n')
    
    if identity_section:
        prompt_parts.append(f'## 身份与记忆\n{identity_section}\n')
    if mission_section:
        prompt_parts.append(f'## 核心使命\n{mission_section}\n')
    if rules_section:
        prompt_parts.append(f'## 必须遵守的规则\n{rules_section}\n')
    if workflow_section:
        prompt_parts.append(f'## 工作流程\n{workflow_section}\n')
    if expertise_section:
        prompt_parts.append(f'## 领域专长\n{expertise_section}\n')
    if communication_section:
        prompt_parts.append(f'## 沟通风格\n{communication_section}\n')
    
    prompt_parts.append(f'---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。')
    
    full_prompt = "\n".join(prompt_parts)
    
    lines = []
    lines.append(f'"""')
    lines.append(f'{agent.emoji} {agent.name} - {agent.description}')
    lines.append(f'')
    lines.append(f'自动转换自 agency-agents-zh/{agent.category}/{agent.filepath.name}')
    lines.append(f'"""')
    lines.append(f'')
    lines.append(f'import logging')
    lines.append(f'from typing import Dict, Any')
    lines.append(f'')
    lines.append(f'from src.skills.base import Skill, SkillMeta')
    lines.append(f'')
    lines.append(f'logger = logging.getLogger(__name__)')
    lines.append(f'')
    lines.append(f'')
    lines.append(f'class {class_name}(Skill):')
    lines.append(f'    NAME = "{skill_name}"')
    lines.append(f'    DESCRIPTION = "{description}"')
    lines.append(f'    VERSION = "1.0.0"')
    lines.append(f'    AUTHOR = "AOS"')
    lines.append(f'    LICENSE = "MIT"')
    lines.append(f'    CATEGORY = "{agent.category}"')
    lines.append(f'    TAGS = ["{agent.category}", "consulting", "expert"]')
    lines.append(f'    CAPABILITIES = [{capabilities_str}]')
    lines.append(f'    PLATFORMS = ["python"]')
    lines.append(f'')
    lines.append(f'    def __init__(self):')
    lines.append(f'        super().__init__(SkillMeta(')
    lines.append(f'            name=self.NAME,')
    lines.append(f'            description=self.DESCRIPTION,')
    lines.append(f'            version=self.VERSION,')
    lines.append(f'            author=self.AUTHOR,')
    lines.append(f'            license=self.LICENSE,')
    lines.append(f'            category=self.CATEGORY,')
    lines.append(f'            tags=self.TAGS,')
    lines.append(f'            capabilities=self.CAPABILITIES,')
    lines.append(f'            platforms=self.PLATFORMS,')
    lines.append(f'        ))')
    lines.append(f'')
    lines.append(f'    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:')
    lines.append(f'        task = context.get("task", "")')
    lines.append(f'        inputs_data = context.get("inputs", "")')
    lines.append(f'')
    lines.append(f'        if not task:')
    lines.append(f'            return {{"success": False, "error": "缺少任务描述（task 参数）"}}')
    lines.append(f'')
    lines.append(f'        try:')
    lines.append(f'            from src.core import get_brain')
    lines.append(f'            brain = get_brain()')
    lines.append(f'')
    lines.append(f'            prompt = self._build_prompt(task)')
    lines.append(f'')
    lines.append(f'            if inputs_data:')
    lines.append(f'                prompt += "\\n\\n## 相关输入数据:\\n" + inputs_data')
    lines.append(f'')
    lines.append(f'            result = brain.chat(prompt, model="default")')
    lines.append(f'')
    lines.append(f'            if isinstance(result, str):')
    lines.append(f'                return {{"success": True, "skill": "{skill_name}", "data": {{"response": result}}}}')
    lines.append(f'            elif isinstance(result, dict) and "content" in result:')
    lines.append(f'                return {{"success": True, "skill": "{skill_name}", "data": {{"response": result["content"]}}}}')
    lines.append(f'            else:')
    lines.append(f'                return {{"success": True, "skill": "{skill_name}", "data": {{"response": str(result)}}}}')
    lines.append(f'')
    lines.append(f'        except Exception as e:')
    lines.append(f'            logger.error("{agent.name} 技能执行失败: %s", e, exc_info=True)')
    lines.append(f'            return {{"success": False, "skill": "{skill_name}", "error": str(e)}}')
    lines.append(f'')
    escaped_prompt = escape_string(full_prompt)
    lines.append(f'    def _build_prompt(self, task: str) -> str:')
    lines.append(f'        return "{escaped_prompt}".replace("%TASK_PLACEHOLDER%", task)')
    
    return "\n".join(lines)


def generate_init_file(agents: List[AgentDefinition]) -> str:
    imports = []
    registrations = []
    
    for agent in agents:
        skill_name = sanitize_filename(agent.name)
        class_name = generate_class_name(agent.name)
        imports.append(f"from .{skill_name} import {class_name}")
        registrations.append(f"    registry.register({class_name}())")
    
    lines = []
    lines.append('"""')
    lines.append('AOS Agency Roles Skills')
    lines.append('========================')
    lines.append('')
    lines.append(f'自动转换自 agency-agents-zh 的部门角色技能。')
    lines.append('')
    lines.append(f'包含 {len(agents)} 个专业角色技能，覆盖 {len(set(a.category for a in agents))} 个领域。')
    lines.append('"""')
    lines.append('')
    lines.append('import logging')
    lines.append('from src.skills.base import SkillRegistry')
    lines.append('')
    lines.append('registry = SkillRegistry()')
    lines.append('')
    lines.extend(imports)
    lines.append('')
    lines.append('def register_agency_roles():')
    lines.append('    """注册所有部门角色技能"""')
    lines.extend(registrations)
    lines.append('    logger.info(f"已注册 {{len(registry.list_all())}} 个部门角色技能")')
    lines.append('')
    lines.append('logger = logging.getLogger(__name__)')
    
    return "\n".join(lines)


def main():
    agency_dir = PROJECT_ROOT / "agency-agents-zh"
    output_dir = PROJECT_ROOT / "src" / "skills" / "agency_roles"
    
    print(f"读取 agency-agents-zh 目录: {agency_dir}")
    
    md_files = []
    exclude_dirs = {"scripts", "examples", "strategy", "coordination", "runbooks", "playbooks", ".github", "ISSUE_TEMPLATE", "PULL_REQUEST_TEMPLATE"}
    exclude_files = {"README.md", "README.md.zh-TW", "UPSTREAM.md", "QUICKSTART.md", "EXECUTIVE-BRIEF.md"}
    
    for root, dirs, files in os.walk(agency_dir):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for filename in files:
            if filename.endswith(".md") and not filename.startswith(".") and filename not in exclude_files:
                md_files.append(Path(root) / filename)
    
    print(f"找到 {len(md_files)} 个 agent 文件")
    
    agents = []
    output_dir.mkdir(parents=True, exist_ok=True)
    
    for old_file in output_dir.glob("*.py"):
        if old_file.name != "__init__.py":
            old_file.unlink()
    
    for filepath in md_files:
        try:
            agent = parse_markdown_file(filepath)
            agents.append(agent)
            
            skill_code = generate_skill_class(agent)
            skill_name = sanitize_filename(agent.name)
            skill_file = output_dir / f"{skill_name}.py"
            skill_file.write_text(skill_code, encoding="utf-8")
            
            print(f"  ✓ {agent.name} -> {skill_file.name}")
        except Exception as e:
            print(f"  ✗ {filepath}: {e}")
    
    init_code = generate_init_file(agents)
    (output_dir / "__init__.py").write_text(init_code, encoding="utf-8")
    
    print(f"\n共生成 {len(agents)} 个 Skill 文件")
    print(f"输出目录: {output_dir}")
    
    categories = {}
    for agent in agents:
        categories[agent.category] = categories.get(agent.category, 0) + 1
    
    print(f"\n分类统计:")
    for cat, count in sorted(categories.items()):
        print(f"  {cat}: {count} 个")


if __name__ == "__main__":
    main()
