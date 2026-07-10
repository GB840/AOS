"""
Design.md — UI/UX设计标准化规范知识库。
让AI直接读取并生成符合规范的UI，为前端代码生成提供设计指导。
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from .base import Skill, SkillMeta

logger = logging.getLogger(__name__)

DESIGN_SPEC_TEMPLATES = {
    "mobile": {
        "name": "mobile-design",
        "description": "移动端设计规范",
        "spacing": {"xs": 4, "sm": 8, "md": 16, "lg": 24, "xl": 32},
        "typography": {
            "h1": {"size": 34, "weight": 700, "line_height": 1.2},
            "h2": {"size": 28, "weight": 600, "line_height": 1.3},
            "body": {"size": 16, "weight": 400, "line_height": 1.5},
            "caption": {"size": 12, "weight": 400, "line_height": 1.4},
        },
        "colors": {
            "primary": "#6366f1",
            "secondary": "#8b5cf6",
            "success": "#22c55e",
            "warning": "#f59e0b",
            "error": "#ef4444",
            "background": "#ffffff",
            "surface": "#f8fafc",
            "text": "#1e293b",
            "text_secondary": "#64748b",
        },
        "components": ["button", "card", "input", "list", "navigation"],
    },
    "desktop": {
        "name": "desktop-design",
        "description": "桌面端设计规范",
        "spacing": {"xs": 4, "sm": 8, "md": 16, "lg": 24, "xl": 32, "2xl": 48},
        "typography": {
            "h1": {"size": 48, "weight": 700, "line_height": 1.1},
            "h2": {"size": 36, "weight": 600, "line_height": 1.2},
            "h3": {"size": 24, "weight": 600, "line_height": 1.3},
            "body": {"size": 16, "weight": 400, "line_height": 1.6},
            "small": {"size": 14, "weight": 400, "line_height": 1.5},
        },
        "colors": {
            "primary": "#3b82f6",
            "secondary": "#8b5cf6",
            "success": "#10b981",
            "warning": "#f59e0b",
            "error": "#ef4444",
            "background": "#ffffff",
            "surface": "#f1f5f9",
            "text": "#0f172a",
            "text_secondary": "#64748b",
        },
        "components": ["button", "card", "input", "table", "sidebar", "modal"],
    },
    "dark": {
        "name": "dark-design",
        "description": "深色模式设计规范",
        "colors": {
            "primary": "#818cf8",
            "secondary": "#a78bfa",
            "background": "#0f172a",
            "surface": "#1e293b",
            "text": "#f1f5f9",
            "text_secondary": "#94a3b8",
        },
    },
}

COMPONENT_PATTERNS = {
    "button": {
        "variants": ["primary", "secondary", "outline", "ghost", "danger"],
        "sizes": ["sm", "md", "lg"],
        "states": ["default", "hover", "active", "disabled"],
    },
    "card": {
        "variants": ["default", "elevated", "outlined"],
        "sections": ["header", "body", "footer", "media"],
    },
    "input": {
        "types": ["text", "email", "password", "number", "textarea", "select"],
        "states": ["default", "focus", "error", "disabled"],
    },
    "navigation": {
        "types": ["navbar", "sidebar", "breadcrumb", "tabs"],
    },
}


class DesignMdSkill(Skill):
    NAME = "design_md"
    DESCRIPTION = "Design.md — UI/UX设计标准化规范知识库，让AI生成符合设计规范的前端代码"
    CAPABILITIES = [
        "design_spec_retrieval",
        "component_patterns",
        "theme_generation",
        "style_guides",
        "design_validation",
        "spec_export",
    ]
    CATEGORY = "design"
    TAGS = ["design", "ui", "ux", "components", "style-guide", "design-system"]

    def __init__(self):
        meta = SkillMeta(
            name=self.NAME,
            description=self.DESCRIPTION,
            version="1.0.0",
            author="AOS",
            license="MIT",
            tags=self.TAGS,
            capabilities=self.CAPABILITIES,
            category=self.CATEGORY,
        )
        super().__init__(meta)
        self._specs = DESIGN_SPEC_TEMPLATES
        self._component_patterns = COMPONENT_PATTERNS
        self._custom_specs: Dict[str, Dict] = {}
        self._load_custom_specs()

    def _load_custom_specs(self):
        specs_dir = Path("outputs/design_specs")
        specs_dir.mkdir(parents=True, exist_ok=True)
        for spec_file in specs_dir.glob("*.json"):
            try:
                with open(spec_file, "r", encoding="utf-8") as f:
                    spec = json.load(f)
                    self._custom_specs[spec["name"]] = spec
                logger.info(f"加载自定义设计规范: {spec['name']}")
            except Exception as e:
                logger.warning(f"加载设计规范失败: {spec_file} - {e}")

    def _get_spec(self, spec_name: str) -> Optional[Dict]:
        if spec_name in self._custom_specs:
            return self._custom_specs[spec_name]
        if spec_name in self._specs:
            return self._specs[spec_name]
        return None

    def _validate_design(self, design_data: Dict, spec_name: str) -> Dict[str, Any]:
        spec = self._get_spec(spec_name)
        if not spec:
            return {"valid": False, "errors": [f"设计规范 {spec_name} 不存在"]}

        errors = []
        warnings = []

        if "colors" in design_data:
            for color_name, color_value in design_data["colors"].items():
                if not color_value.startswith("#") or len(color_value) not in (7, 9):
                    errors.append(f"颜色值格式错误: {color_name} = {color_value}")

        if "typography" in design_data:
            for style_name, style_data in design_data["typography"].items():
                if "size" in style_data and (style_data["size"] < 8 or style_data["size"] > 120):
                    warnings.append(f"字体大小异常: {style_name} = {style_data['size']}px")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "spec_used": spec_name,
        }

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        action = context.get("action", "get_spec")

        try:
            if action == "get_spec":
                spec_name = context.get("spec_name", "mobile")
                spec = self._get_spec(spec_name)
                if spec:
                    return {"success": True, "result": spec}
                return {"success": False, "error": f"设计规范 {spec_name} 不存在"}

            elif action == "list_specs":
                all_specs = list(self._specs.keys()) + list(self._custom_specs.keys())
                return {"success": True, "result": {"specs": all_specs}}

            elif action == "get_component_pattern":
                component = context.get("component", "")
                if component in self._component_patterns:
                    return {"success": True, "result": self._component_patterns[component]}
                return {"success": False, "error": f"组件模式 {component} 不存在"}

            elif action == "list_components":
                return {"success": True, "result": {"components": self._component_patterns}}

            elif action == "generate_theme":
                base_spec = context.get("base_spec", context.get("spec_name", "mobile"))
                primary_color = context.get("primary_color", "#6366f1")
                accent_color = context.get("accent_color", "#8b5cf6")

                spec = self._get_spec(base_spec)
                if not spec:
                    return {"success": False, "error": f"基础规范 {base_spec} 不存在"}

                theme = spec.copy()
                if "colors" in theme:
                    theme["colors"]["primary"] = primary_color
                    theme["colors"]["secondary"] = accent_color
                theme["name"] = f"custom-theme-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
                theme["customized_at"] = datetime.now().isoformat()

                return {"success": True, "result": theme}

            elif action == "save_spec":
                spec_data = context.get("spec_data", {})
                if not spec_data.get("name"):
                    return {"success": False, "error": "设计规范名称不能为空"}

                self._custom_specs[spec_data["name"]] = spec_data
                specs_dir = Path("outputs/design_specs")
                specs_dir.mkdir(parents=True, exist_ok=True)
                spec_file = specs_dir / f"{spec_data['name']}.json"
                with open(spec_file, "w", encoding="utf-8") as f:
                    json.dump(spec_data, f, ensure_ascii=False, indent=2)

                return {"success": True, "result": {"saved": True, "file": str(spec_file)}}

            elif action == "validate_design":
                design_data = context.get("design_data", {})
                spec_name = context.get("spec_name", "mobile")
                validation = self._validate_design(design_data, spec_name)
                return {"success": True, "result": validation}

            elif action == "export_spec":
                spec_name = context.get("spec_name", "mobile")
                format_type = context.get("format", "json")
                spec = self._get_spec(spec_name)
                if not spec:
                    return {"success": False, "error": f"设计规范 {spec_name} 不存在"}

                if format_type == "css":
                    colors = spec.get("colors", {})
                    css = ":root {\n"
                    for key, value in colors.items():
                        css += f"  --color-{key}: {value};\n"
                    css += "}\n"
                    return {"success": True, "result": {"format": "css", "content": css}}

                elif format_type == "tailwind":
                    tailwind = {"theme": {"extend": spec}}
                    return {"success": True, "result": {"format": "tailwind", "content": json.dumps(tailwind, indent=2, ensure_ascii=False)}}

                return {"success": True, "result": {"format": "json", "content": json.dumps(spec, indent=2, ensure_ascii=False)}}

            elif action == "生成主题":
                spec_name = context.get("spec_name", "mobile")
                primary_color = context.get("primary_color", "#6366f1")
                accent_color = context.get("accent_color", "#8b5cf6")
                return self.execute({
                    "action": "generate_theme",
                    "base_spec": spec_name,
                    "primary_color": primary_color,
                    "accent_color": accent_color,
                })

            elif action == "导出规范":
                spec_name = context.get("spec_name", "mobile")
                format_type = context.get("format", "json")
                return self.execute({
                    "action": "export_spec",
                    "spec_name": spec_name,
                    "format": format_type,
                })

            elif action == "验证设计":
                design_data = context.get("design_data", {})
                spec_name = context.get("spec_name", "mobile")
                return self.execute({
                    "action": "validate_design",
                    "design_data": design_data,
                    "spec_name": spec_name,
                })

            elif action == "列出组件":
                return self.execute({"action": "list_components"})

            else:
                return {"success": False, "error": f"未知动作: {action}"}

        except Exception as e:
            logger.error(f"Design.md 执行失败: {e}", exc_info=True)
            return {"success": False, "error": str(e)}


def get_design_md_skill() -> DesignMdSkill:
    return DesignMdSkill()


def register_design_md_skill(registry=None):
    if registry is None:
        from .base import SkillRegistry
        registry = SkillRegistry()
    skill = DesignMdSkill()
    registry.register(skill)
    logger.info("Design.md 技能已注册")
    return skill