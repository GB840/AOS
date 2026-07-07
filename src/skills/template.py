from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Union
from pathlib import Path
import json
import yaml
import logging

logger = logging.getLogger(__name__)

@dataclass
class StageSpec:
    name: str
    description: str
    required_inputs: List[str] = field(default_factory=list)
    expected_outputs: List[str] = field(default_factory=list)
    gate_questions: List[str] = field(default_factory=list)
    optional: bool = False

@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    required: bool = False

@dataclass
class TestCase:
    name: str
    input_context: Dict[str, Any] = field(default_factory=dict)
    expected_output: Dict[str, Any] = field(default_factory=dict)
    validation_rules: List[str] = field(default_factory=list)

@dataclass
class SkillTemplate:
    name: str
    description: str
    version: str = "1.0.0"
    author: str = "AOS"
    license: str = "MIT"
    category: str = "general"
    tags: List[str] = field(default_factory=list)
    capabilities: List[str] = field(default_factory=list)
    
    stages: List[StageSpec] = field(default_factory=list)
    tools: List[ToolSpec] = field(default_factory=list)
    test_cases: List[TestCase] = field(default_factory=list)
    
    execution_context: Dict[str, Any] = field(default_factory=dict)
    default_config: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def from_yaml(cls, yaml_content: str) -> "SkillTemplate":
        data = yaml.safe_load(yaml_content)
        stages = []
        for stage_data in data.get("stages", []):
            stages.append(StageSpec(**stage_data))
        
        tools = []
        for tool_data in data.get("tools", []):
            tools.append(ToolSpec(**tool_data))
        
        test_cases = []
        for tc_data in data.get("test_cases", []):
            test_cases.append(TestCase(**tc_data))
        
        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            version=data.get("version", "1.0.0"),
            author=data.get("author", "AOS"),
            license=data.get("license", "MIT"),
            category=data.get("category", "general"),
            tags=data.get("tags", []),
            capabilities=data.get("capabilities", []),
            stages=stages,
            tools=tools,
            test_cases=test_cases,
            execution_context=data.get("execution_context", {}),
            default_config=data.get("default_config", {}),
        )
    
    @classmethod
    def from_file(cls, filepath: Union[str, Path]) -> "SkillTemplate":
        filepath = Path(filepath)
        with open(filepath, "r", encoding="utf-8") as f:
            return cls.from_yaml(f.read())
    
    def to_yaml(self) -> str:
        data = {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "author": self.author,
            "license": self.license,
            "category": self.category,
            "tags": self.tags,
            "capabilities": self.capabilities,
            "stages": [stage.__dict__ for stage in self.stages],
            "tools": [tool.__dict__ for tool in self.tools],
            "test_cases": [tc.__dict__ for tc in self.test_cases],
            "execution_context": self.execution_context,
            "default_config": self.default_config,
        }
        return yaml.dump(data, default_flow_style=False, allow_unicode=True)
    
    def to_file(self, filepath: Union[str, Path]):
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(self.to_yaml())
    
    def validate(self) -> Dict[str, Any]:
        errors = []
        warnings = []
        
        if not self.name:
            errors.append("name is required")
        if not self.description:
            errors.append("description is required")
        
        for stage in self.stages:
            if not stage.name:
                errors.append(f"stage has no name")
        
        for tc in self.test_cases:
            if not tc.name:
                errors.append(f"test case has no name")
        
        if len(self.stages) == 0:
            warnings.append("no stages defined - skill will be simple execute-only")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "stage_count": len(self.stages),
            "tool_count": len(self.tools),
            "test_case_count": len(self.test_cases),
        }