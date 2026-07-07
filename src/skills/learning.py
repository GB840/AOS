from typing import Dict, List, Optional, Any
from datetime import datetime
import json
import logging
from pathlib import Path
from .base import Skill, SkillRegistry
from .template import SkillTemplate

logger = logging.getLogger(__name__)

class FeedbackRecord:
    def __init__(
        self,
        skill_name: str,
        rating: int,
        comment: str = "",
        context: Optional[Dict[str, Any]] = None,
        output: Optional[Any] = None,
        expected_output: Optional[Any] = None,
    ):
        self.skill_name = skill_name
        self.rating = rating
        self.comment = comment
        self.context = context or {}
        self.output = output
        self.expected_output = expected_output
        self.timestamp = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill_name": self.skill_name,
            "rating": self.rating,
            "comment": self.comment,
            "context": self.context,
            "output": self.output,
            "expected_output": self.expected_output,
            "timestamp": self.timestamp,
        }

class SkillImprovement:
    def __init__(
        self,
        skill_name: str,
        improvement_type: str,
        suggestion: str,
        priority: str = "medium",
    ):
        self.skill_name = skill_name
        self.improvement_type = improvement_type
        self.suggestion = suggestion
        self.priority = priority
        self.created_at = datetime.now().isoformat()
        self.applied = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill_name": self.skill_name,
            "improvement_type": self.improvement_type,
            "suggestion": self.suggestion,
            "priority": self.priority,
            "created_at": self.created_at,
            "applied": self.applied,
        }

class SkillLearningSystem:
    def __init__(self, storage_path: str = "outputs/skills/learning"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.feedbacks: List[FeedbackRecord] = []
        self.improvements: List[SkillImprovement] = []
        self.performance_history: Dict[str, List[Dict[str, Any]]] = {}
        self._load_data()
    
    def _load_data(self):
        feedbacks_file = self.storage_path / "feedbacks.json"
        improvements_file = self.storage_path / "improvements.json"
        performance_file = self.storage_path / "performance.json"
        
        if feedbacks_file.exists():
            try:
                with open(feedbacks_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.feedbacks = [FeedbackRecord(**item) for item in data]
            except:
                pass
        
        if improvements_file.exists():
            try:
                with open(improvements_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.improvements = [SkillImprovement(**item) for item in data]
            except:
                pass
        
        if performance_file.exists():
            try:
                with open(performance_file, "r", encoding="utf-8") as f:
                    self.performance_history = json.load(f)
            except:
                pass
    
    def _save_data(self):
        feedbacks_file = self.storage_path / "feedbacks.json"
        improvements_file = self.storage_path / "improvements.json"
        performance_file = self.storage_path / "performance.json"
        
        with open(feedbacks_file, "w", encoding="utf-8") as f:
            json.dump([f.to_dict() for f in self.feedbacks], f, ensure_ascii=False, indent=2)
        
        with open(improvements_file, "w", encoding="utf-8") as f:
            json.dump([i.to_dict() for i in self.improvements], f, ensure_ascii=False, indent=2)
        
        with open(performance_file, "w", encoding="utf-8") as f:
            json.dump(self.performance_history, f, ensure_ascii=False, indent=2)
    
    def submit_feedback(self, record: FeedbackRecord) -> bool:
        self.feedbacks.append(record)
        self._save_data()
        
        if record.rating <= 2:
            self._generate_improvement_suggestions(record)
        
        return True
    
    def log_performance(self, skill_name: str, duration_ms: float, success: bool, error: Optional[str] = None):
        if skill_name not in self.performance_history:
            self.performance_history[skill_name] = []
        
        self.performance_history[skill_name].append({
            "timestamp": datetime.now().isoformat(),
            "duration_ms": duration_ms,
            "success": success,
            "error": error,
        })
        
        if len(self.performance_history[skill_name]) > 1000:
            self.performance_history[skill_name] = self.performance_history[skill_name][-500:]
        
        self._save_data()
    
    def _generate_improvement_suggestions(self, feedback: FeedbackRecord):
        suggestions = []
        
        if feedback.rating <= 1:
            suggestions.append(SkillImprovement(
                skill_name=feedback.skill_name,
                improvement_type="critical",
                suggestion=f"Critical issue reported: {feedback.comment}",
                priority="high",
            ))
        
        if feedback.expected_output and feedback.output:
            suggestions.append(SkillImprovement(
                skill_name=feedback.skill_name,
                improvement_type="output_mismatch",
                suggestion=f"Output does not match expected. Expected: {str(feedback.expected_output)[:100]}, Got: {str(feedback.output)[:100]}",
                priority="medium",
            ))
        
        if feedback.comment:
            suggestions.append(SkillImprovement(
                skill_name=feedback.skill_name,
                improvement_type="user_feedback",
                suggestion=f"User feedback: {feedback.comment}",
                priority="medium",
            ))
        
        for suggestion in suggestions:
            self.improvements.append(suggestion)
        
        self._save_data()
    
    def analyze_skill_performance(self, skill_name: str) -> Dict[str, Any]:
        records = self.performance_history.get(skill_name, [])
        if not records:
            return {"skill_name": skill_name, "message": "No performance data"}
        
        total = len(records)
        success_count = sum(1 for r in records if r["success"])
        avg_duration = sum(r["duration_ms"] for r in records) / total
        error_count = total - success_count
        
        recent_records = records[-10:]
        recent_success = sum(1 for r in recent_records if r["success"]) / len(recent_records)
        
        return {
            "skill_name": skill_name,
            "total_executions": total,
            "success_rate": round(success_count / total, 2),
            "avg_duration_ms": round(avg_duration, 2),
            "error_count": error_count,
            "recent_success_rate": round(recent_success, 2),
        }
    
    def get_skill_feedbacks(self, skill_name: str) -> List[Dict[str, Any]]:
        return [f.to_dict() for f in self.feedbacks if f.skill_name == skill_name]
    
    def get_improvement_suggestions(self, skill_name: Optional[str] = None, priority: Optional[str] = None) -> List[Dict[str, Any]]:
        suggestions = self.improvements
        
        if skill_name:
            suggestions = [s for s in suggestions if s.skill_name == skill_name]
        
        if priority:
            suggestions = [s for s in suggestions if s.priority == priority]
        
        suggestions = [s for s in suggestions if not s.applied]
        
        return sorted(suggestions, key=lambda x: {"high": 0, "medium": 1, "low": 2}[x.priority])
    
    def apply_improvement(self, improvement_index: int) -> bool:
        if 0 <= improvement_index < len(self.improvements):
            self.improvements[improvement_index].applied = True
            self._save_data()
            return True
        return False
    
    def auto_optimize_skill(self, skill: Skill) -> Dict[str, Any]:
        feedbacks = self.get_skill_feedbacks(skill.name)
        if not feedbacks:
            return {"message": "No feedback available for optimization"}
        
        avg_rating = sum(f["rating"] for f in feedbacks) / len(feedbacks)
        
        suggestions = []
        
        if avg_rating < 3:
            suggestions.append("Consider improving the skill description and capabilities")
        
        performance = self.analyze_skill_performance(skill.name)
        if "success_rate" in performance and performance["success_rate"] < 0.7:
            suggestions.append("Skill has low success rate - need to review execution logic")
        
        if "avg_duration_ms" in performance and performance["avg_duration_ms"] > 10000:
            suggestions.append("Skill is slow - consider optimizing execution steps")
        
        return {
            "skill_name": skill.name,
            "avg_rating": round(avg_rating, 2),
            "feedback_count": len(feedbacks),
            "optimization_suggestions": suggestions,
            "performance": performance,
        }
    
    def get_overall_stats(self) -> Dict[str, Any]:
        total_feedbacks = len(self.feedbacks)
        total_improvements = len(self.improvements)
        applied_improvements = sum(1 for i in self.improvements if i.applied)
        
        skill_performance = {}
        for skill_name in self.performance_history:
            perf = self.analyze_skill_performance(skill_name)
            skill_performance[skill_name] = perf
        
        return {
            "total_feedbacks": total_feedbacks,
            "total_improvements": total_improvements,
            "applied_improvements": applied_improvements,
            "skill_performance": skill_performance,
        }

_default_learning_system = None

def get_learning_system() -> SkillLearningSystem:
    global _default_learning_system
    if _default_learning_system is None:
        _default_learning_system = SkillLearningSystem()
    return _default_learning_system