from typing import Any, Callable, Dict, List, Optional, Union
from pathlib import Path
import logging
from .base import Skill, SkillMeta, SkillRegistry
from .template import SkillTemplate, StageSpec, TestCase

logger = logging.getLogger(__name__)

class TemplateSkill(Skill):
    def __init__(self, template: SkillTemplate):
        meta = SkillMeta(
            name=template.name,
            description=template.description,
            version=template.version,
            author=template.author,
            license=template.license,
            tags=template.tags,
            capabilities=template.capabilities,
            category=template.category,
        )
        super().__init__(meta)
        self.template = template
        self._stage_handlers: Dict[str, Callable] = {}
        self._register_default_handlers()
    
    def _register_default_handlers(self):
        for stage in self.template.stages:
            self._stage_handlers[stage.name] = self._default_stage_handler
    
    def _default_stage_handler(self, stage: StageSpec, context: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "success": True,
            "stage": stage.name,
            "description": stage.description,
            "gate_questions": stage.gate_questions,
            "required_inputs": stage.required_inputs,
            "expected_outputs": stage.expected_outputs,
        }
    
    def register_stage_handler(self, stage_name: str, handler: Callable):
        self._stage_handlers[stage_name] = handler
        logger.info(f"Registered handler for stage '{stage_name}' in skill '{self.name}'")
    
    def execute_stage(self, stage_name: str, context: Dict[str, Any]) -> Dict[str, Any]:
        stage = next((s for s in self.template.stages if s.name == stage_name), None)
        if not stage:
            return {"success": False, "error": f"Stage '{stage_name}' not found"}
        
        handler = self._stage_handlers.get(stage_name, self._default_stage_handler)
        return handler(stage, context)
    
    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        stage_name = context.get("stage")
        
        if stage_name:
            return self.execute_stage(stage_name, context)
        
        return self.run_pipeline(context)
    
    def run_pipeline(self, context: Dict[str, Any]) -> Dict[str, Any]:
        results = {}
        task = context.get("task", context.get("message", ""))
        
        for stage in self.template.stages:
            stage_context = {**context, "task": task, "previous_results": results}
            result = self.execute_stage(stage.name, stage_context)
            
            if not result.get("success", True):
                return {
                    "success": False,
                    "stage": stage.name,
                    "error": result.get("error", "Stage execution failed"),
                    "results": results,
                }
            
            results[stage.name] = result
        
        return {
            "success": True,
            "results": results,
            "stage_count": len(self.template.stages),
        }
    
    def run_tests(self) -> Dict[str, Any]:
        results = {"passed": [], "failed": [], "skipped": []}
        
        for tc in self.template.test_cases:
            try:
                result = self.execute(tc.input_context)
                
                if self._validate_test_result(result, tc):
                    results["passed"].append(tc.name)
                else:
                    results["failed"].append({
                        "name": tc.name,
                        "expected": tc.expected_output,
                        "actual": result,
                    })
            except Exception as e:
                results["failed"].append({
                    "name": tc.name,
                    "error": str(e),
                })
        
        return {
            **results,
            "total": len(self.template.test_cases),
            "pass_rate": len(results["passed"]) / max(len(self.template.test_cases), 1),
        }
    
    def _validate_test_result(self, result: Dict[str, Any], tc: TestCase) -> bool:
        if not result.get("success"):
            return False
        
        for key, expected in tc.expected_output.items():
            if key in result and result[key] != expected:
                return False
        
        for rule in tc.validation_rules:
            if not self._apply_validation_rule(rule, result):
                return False
        
        return True
    
    def _apply_validation_rule(self, rule: str, result: Dict[str, Any]) -> bool:
        import re
        
        safe_vars = {"result": result}
        allowed_patterns = [
            r'^result\["[^"]+"\]\s*(==|!=|<|>|<=|>=)\s*["\w]+$',
            r'^result\["[^"]+"\]\s*and\s*result\["[^"]+"\]$',
            r'^result\["[^"]+"\]\s*or\s*result\["[^"]+"\]$',
            r'^not\s+result\["[^"]+"\]$',
            r'^len\(result\["[^"]+"\]\)\s*(==|!=|<|>|<=|>=)\s*\d+$',
            r'^result\["[^"]+"\]\s*is\s+(None|not\s+None)$',
        ]
        
        for pattern in allowed_patterns:
            if re.match(pattern, rule):
                try:
                    return bool(eval(rule, {}, safe_vars))
                except Exception:
                    return False
        
        return False

class SkillFactory:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._templates: Dict[str, SkillTemplate] = {}
            cls._instance._registry = SkillRegistry()
        return cls._instance
    
    def register_template(self, template: SkillTemplate):
        self._templates[template.name] = template
        logger.info(f"Registered skill template: {template.name}")
    
    def get_template(self, name: str) -> Optional[SkillTemplate]:
        return self._templates.get(name)
    
    def list_templates(self) -> List[Dict[str, Any]]:
        return [self._template_to_dict(t) for t in self._templates.values()]
    
    def _template_to_dict(self, template: SkillTemplate) -> Dict[str, Any]:
        return {
            "name": template.name,
            "description": template.description,
            "version": template.version,
            "category": template.category,
            "stage_count": len(template.stages),
            "tool_count": len(template.tools),
            "test_case_count": len(template.test_cases),
            "tags": template.tags,
        }
    
    def create_skill(self, template_name: str, custom_handlers: Optional[Dict[str, Callable]] = None) -> Optional[Skill]:
        template = self._templates.get(template_name)
        if not template:
            logger.error(f"Template '{template_name}' not found")
            return None
        
        skill = TemplateSkill(template)
        
        if custom_handlers:
            for stage_name, handler in custom_handlers.items():
                skill.register_stage_handler(stage_name, handler)
        
        return skill
    
    def create_and_register(self, template_name: str, custom_handlers: Optional[Dict[str, Callable]] = None) -> bool:
        skill = self.create_skill(template_name, custom_handlers)
        if skill:
            self._registry.register(skill)
            logger.info(f"Created and registered skill: {skill.name}")
            return True
        return False
    
    def validate_template(self, template_name: str) -> Dict[str, Any]:
        template = self._templates.get(template_name)
        if not template:
            return {"valid": False, "error": f"Template '{template_name}' not found"}
        return template.validate()
    
    def load_template_from_file(self, filepath: Union[str, Path]) -> bool:
        try:
            template = SkillTemplate.from_file(filepath)
            self.register_template(template)
            logger.info(f"Loaded template from file: {filepath}")
            return True
        except Exception as e:
            logger.error(f"Failed to load template from file {filepath}: {e}")
            return False
    
    def load_templates_from_directory(self, directory: Union[str, Path]) -> int:
        directory = Path(directory)
        count = 0
        
        for filepath in directory.glob("*.yaml"):
            if self.load_template_from_file(filepath):
                count += 1
        
        for filepath in directory.glob("*.yml"):
            if self.load_template_from_file(filepath):
                count += 1
        
        logger.info(f"Loaded {count} templates from directory: {directory}")
        return count
    
    def get_registry(self) -> SkillRegistry:
        return self._registry
    
    def get_stats(self) -> Dict[str, Any]:
        return {
            "templates": len(self._templates),
            "skills": self._registry.get_stats(),
        }