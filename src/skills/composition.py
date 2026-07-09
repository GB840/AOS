from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
import logging
from .base import Skill, SkillRegistry
from .template import SkillTemplate

logger = logging.getLogger(__name__)

class CombinationStrategy(Enum):
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    CONDITIONAL = "conditional"
    LOOP = "loop"

class SkillLink:
    def __init__(self, from_skill: str, to_skill: str, condition: Optional[str] = None, data_mapping: Optional[Dict[str, str]] = None):
        self.from_skill = from_skill
        self.to_skill = to_skill
        self.condition = condition
        self.data_mapping = data_mapping or {}
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "from_skill": self.from_skill,
            "to_skill": self.to_skill,
            "condition": self.condition,
            "data_mapping": self.data_mapping,
        }

class SkillPipeline:
    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self.skills: List[str] = []
        self.links: List[SkillLink] = []
        self.strategy: CombinationStrategy = CombinationStrategy.SEQUENTIAL
        self.input_schema: Dict[str, Any] = {}
        self.output_schema: Dict[str, Any] = {}
    
    def add_skill(self, skill_name: str):
        if skill_name not in self.skills:
            self.skills.append(skill_name)
    
    def add_link(self, from_skill: str, to_skill: str, condition: Optional[str] = None, data_mapping: Optional[Dict[str, str]] = None):
        link = SkillLink(from_skill, to_skill, condition, data_mapping)
        self.links.append(link)
    
    def set_strategy(self, strategy: CombinationStrategy):
        self.strategy = strategy
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "skills": self.skills,
            "links": [link.to_dict() for link in self.links],
            "strategy": self.strategy.value,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
        }

def _safe_eval_condition(condition: str, context: Dict[str, Any], results: Dict[str, Any]) -> bool:
    from .safe_eval import safe_eval_expr

    safe_vars = {"context": context, "results": results}
    # 用受限 AST 求值器替代 eval: 仅允许 context/results[...] 比较 / 布尔 / len() / None 判定,
    # 杜绝 eval 代码注入 (无属性访问 / 无导入 / 无任意调用)。
    return safe_eval_expr(condition, safe_vars)

class SkillCompositionEngine:
    def __init__(self, registry: Optional[SkillRegistry] = None):
        self.registry = registry or SkillRegistry()
        self.pipelines: Dict[str, SkillPipeline] = {}
    
    def create_pipeline(self, name: str, description: str = "") -> SkillPipeline:
        pipeline = SkillPipeline(name, description)
        self.pipelines[name] = pipeline
        return pipeline
    
    def get_pipeline(self, name: str) -> Optional[SkillPipeline]:
        return self.pipelines.get(name)
    
    def delete_pipeline(self, name: str) -> bool:
        if name in self.pipelines:
            del self.pipelines[name]
            return True
        return False
    
    def list_pipelines(self) -> List[Dict[str, Any]]:
        return [pipeline.to_dict() for pipeline in self.pipelines.values()]
    
    def compose_skills(self, skill_names: List[str], strategy: CombinationStrategy = CombinationStrategy.SEQUENTIAL) -> SkillPipeline:
        pipeline_name = "_".join(skill_names)
        pipeline = self.create_pipeline(pipeline_name, f"Composed pipeline: {', '.join(skill_names)}")
        
        for skill_name in skill_names:
            pipeline.add_skill(skill_name)
        
        pipeline.set_strategy(strategy)
        
        for i in range(len(skill_names) - 1):
            pipeline.add_link(skill_names[i], skill_names[i + 1])
        
        return pipeline
    
    def execute_pipeline(self, pipeline_name: str, context: Dict[str, Any]) -> Dict[str, Any]:
        pipeline = self.pipelines.get(pipeline_name)
        if not pipeline:
            return {"success": False, "error": f"Pipeline '{pipeline_name}' not found"}
        
        results = {}
        current_context = context.copy()
        
        if pipeline.strategy == CombinationStrategy.SEQUENTIAL:
            results = self._execute_sequential(pipeline, current_context)
        elif pipeline.strategy == CombinationStrategy.PARALLEL:
            results = self._execute_parallel(pipeline, current_context)
        elif pipeline.strategy == CombinationStrategy.CONDITIONAL:
            results = self._execute_conditional(pipeline, current_context)
        elif pipeline.strategy == CombinationStrategy.LOOP:
            results = self._execute_loop(pipeline, current_context)
        
        return {
            "success": True,
            "pipeline": pipeline_name,
            "results": results,
            "strategy": pipeline.strategy.value,
        }
    
    def _execute_sequential(self, pipeline: SkillPipeline, context: Dict[str, Any]) -> Dict[str, Any]:
        results = {}
        current_data = context.copy()
        
        for skill_name in pipeline.skills:
            skill = self.registry.find_by_name(skill_name)
            if not skill:
                logger.warning(f"Skill '{skill_name}' not found in registry")
                continue
            
            for link in pipeline.links:
                if link.from_skill == skill_name:
                    for target_key, source_key in link.data_mapping.items():
                        if source_key in current_data:
                            current_data[target_key] = current_data[source_key]
            
            result = skill.execute(current_data)
            results[skill_name] = result
            
            if "output" in result:
                current_data["previous_output"] = result["output"]
            if "result" in result:
                current_data["previous_result"] = result["result"]
        
        return results
    
    def _execute_parallel(self, pipeline: SkillPipeline, context: Dict[str, Any]) -> Dict[str, Any]:
        import concurrent.futures
        
        results = {}
        
        def execute_skill(skill_name):
            skill = self.registry.find_by_name(skill_name)
            if skill:
                return skill_name, skill.execute(context.copy())
            return skill_name, {"success": False, "error": "Skill not found"}
        
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = {executor.submit(execute_skill, name): name for name in pipeline.skills}
            for future in concurrent.futures.as_completed(futures):
                skill_name, result = future.result()
                results[skill_name] = result
        
        return results
    
    def _execute_conditional(self, pipeline: SkillPipeline, context: Dict[str, Any]) -> Dict[str, Any]:
        results = {}
        current_data = context.copy()
        
        for skill_name in pipeline.skills:
            skill = self.registry.find_by_name(skill_name)
            if not skill:
                continue
            
            should_execute = True
            for link in pipeline.links:
                if link.from_skill == skill_name and link.condition:
                    should_execute = _safe_eval_condition(link.condition, current_data, results)
            
            if should_execute:
                result = skill.execute(current_data)
                results[skill_name] = result
        
        return results
    
    def _execute_loop(self, pipeline: SkillPipeline, context: Dict[str, Any]) -> Dict[str, Any]:
        results = {}
        max_iterations = context.get("max_iterations", 5)
        iteration = 0
        
        while iteration < max_iterations:
            iteration_results = {}
            
            for skill_name in pipeline.skills:
                skill = self.registry.find_by_name(skill_name)
                if skill:
                    result = skill.execute(context.copy())
                    iteration_results[skill_name] = result
            
            results[f"iteration_{iteration}"] = iteration_results
            
            if context.get("break_condition"):
                if _safe_eval_condition(context["break_condition"], context, iteration_results):
                    break
            
            iteration += 1
        
        return results
    
    def suggest_composition(self, task_description: str) -> List[Dict[str, Any]]:
        all_skills = self.registry.list_all()
        suggestions = []
        
        for skill in all_skills:
            skill_name = skill.name
            description = skill.meta.description
            capabilities = skill.meta.capabilities
            
            score = 0
            if skill_name.lower() in task_description.lower():
                score += 3
            if any(cap.lower() in task_description.lower() for cap in capabilities):
                score += 2
            if description.lower() in task_description.lower():
                score += 1
            
            if score > 0:
                suggestions.append({
                    "skill_name": skill_name,
                    "score": score,
                    "capabilities": capabilities,
                    "description": description,
                })
        
        return sorted(suggestions, key=lambda x: x["score"], reverse=True)[:5]
    
    def analyze_pipeline(self, pipeline_name: str) -> Dict[str, Any]:
        pipeline = self.pipelines.get(pipeline_name)
        if not pipeline:
            return {"error": f"Pipeline '{pipeline_name}' not found"}
        
        skill_details = []
        for skill_name in pipeline.skills:
            skill = self.registry.find_by_name(skill_name)
            if skill:
                skill_details.append({
                    "name": skill.name,
                    "version": skill.meta.version,
                    "capabilities": skill.meta.capabilities,
                    "category": skill.meta.category,
                })
            else:
                skill_details.append({
                    "name": skill_name,
                    "error": "Skill not found in registry",
                })
        
        return {
            "pipeline": pipeline_name,
            "strategy": pipeline.strategy.value,
            "skill_count": len(pipeline.skills),
            "link_count": len(pipeline.links),
            "skills": skill_details,
        }