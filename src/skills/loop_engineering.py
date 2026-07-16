"""
Loop Engineering Skill Module - 循环工程框架

核心定义:
Loop Engineering（循环工程）：通过设计闭环机制，让AI在设定目标和验收标准后，
自主完成任务迭代、试错、复盘，无需人工逐轮干预。

核心公式: Agent = Model + Harness + Loop

五大核心组件:
1. 定时任务 (Scheduled Tasks) - 自动启动循环
2. 工作树隔离 (Worktree Isolation) - 多Agent并行执行互不干扰
3. 项目知识体系 (Project Knowledge) - 保存项目背景信息
4. 连接器 (Connectors) - 对接外部工具
5. 子Agent机制 (Sub-Agent Mechanism) - 任务拆分与验收分离

行业演进:
- Prompt Engineering → Context Engineering → Harness Engineering → Loop Engineering
"""

import logging
import uuid
import asyncio
from typing import Dict, List, Any
from datetime import datetime

from .base import Skill

logger = logging.getLogger(__name__)


def _safe_async_run(coro):
    """安全地在同步上下文中运行协程：如果已有事件循环在运行则创建新循环在线程中执行。"""
    import concurrent.futures
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        # 已在事件循环中（如 asyncio.to_thread），在新线程中创建独立循环
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(asyncio.run, coro)
            return future.result()
    else:
        return asyncio.run(coro)


LOOP_COMPONENTS = {
    "scheduler": {
        "name": "定时任务",
        "description": "自动启动循环，无需人工触发",
        "features": ["定时触发", "条件触发", "事件触发"],
    },
    "worktree": {
        "name": "工作树隔离",
        "description": "多Agent并行执行互不干扰",
        "features": ["独立上下文", "资源隔离", "并行执行"],
    },
    "knowledge": {
        "name": "项目知识体系",
        "description": "保存项目背景信息，避免失忆",
        "features": ["持久化记忆", "上下文恢复", "知识沉淀"],
    },
    "connector": {
        "name": "连接器",
        "description": "对接外部工具（GitHub、数据库等）",
        "features": ["API对接", "数据库连接", "文件系统"],
    },
    "subagent": {
        "name": "子Agent机制",
        "description": "任务拆分与验收分离，避免自审自判",
        "features": ["任务拆分", "独立验收", "质量保证"],
    },
}

LOOP_STAGES = {
    "define": {"name": "目标定义", "description": "将模糊意图转化为可衡量的硬指标"},
    "execute": {"name": "执行", "description": "AI自主完成任务"},
    "verify": {"name": "验收", "description": "验证是否满足验收标准"},
    "review": {"name": "复盘", "description": "记录经验教训，避免重复试错"},
    "optimize": {"name": "优化", "description": "基于复盘结果优化下次迭代"},
}

LOOP_TEMPLATES = {
    "code_gen": {
        "name": "代码生成循环",
        "description": "从需求到可运行代码的完整循环",
        "goal": "生成完整、可运行的代码",
        "criteria": ["代码可执行", "包含测试", "代码审查通过"],
        "max_iterations": 5,
        "timeout": 300,
    },
    "content_gen": {
        "name": "内容生成循环",
        "description": "从创意到成品内容的完整循环",
        "goal": "生成高质量内容",
        "criteria": ["内容完整", "逻辑清晰", "格式正确"],
        "max_iterations": 3,
        "timeout": 180,
    },
    "problem_solving": {
        "name": "问题解决循环",
        "description": "从问题描述到解决方案的完整循环",
        "goal": "提供可行的解决方案",
        "criteria": ["方案可行", "有步骤说明", "有验证方法"],
        "max_iterations": 5,
        "timeout": 600,
    },
    "research": {
        "name": "研究循环",
        "description": "从问题到深度分析的完整循环",
        "goal": "提供深度分析报告",
        "criteria": ["信息准确", "引用来源", "分析深入"],
        "max_iterations": 3,
        "timeout": 600,
    },
}


class Loop:
    """
    单个循环实例
    
    包含完整的循环生命周期：定义 → 执行 → 验收 → 复盘 → 优化
    """
    
    def __init__(self, loop_id: str, template: str, goal: str, criteria: List[str], 
                 max_iterations: int = 5, timeout: int = 300):
        self.id = loop_id
        self.template = template
        self.goal = goal
        self.criteria = criteria
        self.max_iterations = max_iterations
        self.timeout = timeout
        
        self.iterations: List[Dict] = []
        self.status = "running"
        self.current_iteration = 0
        self.started_at = datetime.now()
        self.completed_at = None
        self.final_result = None
        
        self._brain = None
    
    async def run(self, input_data: str) -> Dict[str, Any]:
        """
        运行完整循环
        
        Args:
            input_data: 输入数据
            
        Returns:
            Dict: 循环执行结果
        """
        try:
            from core import get_brain
            self._brain = get_brain()
            
            for iteration in range(1, self.max_iterations + 1):
                self.current_iteration = iteration
                
                iteration_result = await self._run_iteration(input_data, iteration)
                self.iterations.append(iteration_result)
                
                if iteration_result.get("verified"):
                    self.status = "completed"
                    self.final_result = iteration_result.get("result")
                    break
                
                if iteration == self.max_iterations:
                    self.status = "exhausted"
                    self.final_result = iteration_result.get("result")
            
            self.completed_at = datetime.now()
            
            return {
                "loop_id": self.id,
                "template": self.template,
                "goal": self.goal,
                "status": self.status,
                "iterations": self.iterations,
                "total_iterations": len(self.iterations),
                "final_result": self.final_result,
                "started_at": self.started_at.isoformat(),
                "completed_at": self.completed_at.isoformat(),
                "duration": (self.completed_at - self.started_at).total_seconds(),
            }
        
        except Exception as e:
            logger.error(f"循环执行失败: {e}", exc_info=True)
            self.status = "failed"
            return {
                "loop_id": self.id,
                "status": "failed",
                "error": str(e),
                "iterations": self.iterations,
            }
    
    async def _run_iteration(self, input_data: str, iteration: int) -> Dict[str, Any]:
        """
        运行单次迭代
        
        Args:
            input_data: 输入数据
            iteration: 当前迭代次数
            
        Returns:
            Dict: 迭代结果
        """
        start_time = datetime.now()
        
        execution_result = await self._execute(input_data, iteration)
        
        verification_result = await self._verify(execution_result, iteration)
        
        review_result = await self._review(execution_result, verification_result, iteration)
        
        end_time = datetime.now()
        
        return {
            "iteration": iteration,
            "execution": execution_result,
            "verification": verification_result,
            "review": review_result,
            "verified": verification_result.get("passed", False),
            "result": execution_result.get("result"),
            "duration": (end_time - start_time).total_seconds(),
            "timestamp": datetime.now().isoformat(),
        }
    
    async def _execute(self, input_data: str, iteration: int) -> Dict[str, Any]:
        """执行阶段"""
        prompt = f"""你正在执行一个循环任务的第 {iteration}/{self.max_iterations} 次迭代。

目标: {self.goal}

验收标准:
{chr(10).join([f"- {c}" for c in self.criteria])}

当前输入: {input_data}

请完成任务并返回结果。确保结果满足所有验收标准。"""
        
        result = self._brain.chat(message=prompt, session_id=f"loop-execute-{self.id}")
        return {"result": result.get("response", ""), "success": True}
    
    async def _verify(self, execution_result: Dict, iteration: int) -> Dict[str, Any]:
        """验收阶段"""
        result = execution_result.get("result", "")
        
        prompt = f"""你是一个独立的验收专家。请验证以下结果是否满足所有验收标准。

目标: {self.goal}

验收标准:
{chr(10).join([f"- {c}" for c in self.criteria])}

待验证结果:
{result}

请逐条验证，并给出最终结论（通过或不通过）。"""
        
        verify_result = self._brain.chat(message=prompt, session_id=f"loop-verify-{self.id}")
        
        passed = "通过" in verify_result.get("response", "") or "满足" in verify_result.get("response", "")
        
        return {
            "passed": passed,
            "verification": verify_result.get("response", ""),
            "criteria": self.criteria,
        }
    
    async def _review(self, execution_result: Dict, verification_result: Dict, iteration: int) -> Dict[str, Any]:
        """复盘阶段"""
        result = execution_result.get("result", "")
        verified = verification_result.get("passed", False)
        
        if verified:
            return {"message": "任务已通过，无需复盘"}
        
        prompt = f"""你是一个复盘专家。请分析以下迭代失败的原因，并提供改进建议。

迭代次数: {iteration}/{self.max_iterations}
目标: {self.goal}
结果: {result[:500]}
验收结果: 未通过

请分析:
1. 失败的原因
2. 下一次迭代的改进建议
3. 需要调整的策略"""
        
        review_result = self._brain.chat(message=prompt, session_id=f"loop-review-{self.id}")
        
        return {
            "review": review_result.get("response", ""),
            "iteration": iteration,
            "verified": verified,
        }


class LoopEngineeringSkill(Skill):
    """
    Loop Engineering 技能
    
    实现完整的循环工程框架，支持：
    1. 创建和管理循环
    2. 定义目标和验收标准
    3. 自动迭代执行
    4. 独立验收和复盘
    5. 知识沉淀和优化
    """
    
    NAME = "loop_engineering"
    DESCRIPTION = "Loop Engineering — 循环工程，支持创建、运行、监控自动化循环，包含代码生成、内容生成、问题解决、研究四种模板"
    VERSION = "1.0.0"
    AUTHOR = "AOS"
    LICENSE = "MIT"
    CATEGORY = "automation"
    TAGS = ["loop", "automation", "iteration", "engineering", "workflow"]
    CAPABILITIES = ["loop_creation", "loop_execution", "loop_monitoring", "code_generation", "content_generation", "problem_solving", "research"]
    
    def __init__(self):
        super().__init__()
        self._loops: Dict[str, Loop] = {}
        self._project_knowledge: Dict[str, Dict] = {}
        self._templates = LOOP_TEMPLATES
    
    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行 Loop Engineering 任务
        
        Args:
            context: 执行上下文
                - action: 操作类型 (create/run/status/list)
                - template: 循环模板 (code_gen/content_gen/problem_solving/research)
                - goal: 目标描述
                - criteria: 验收标准列表
                - input: 输入数据
                - loop_id: 循环ID（用于status操作）
        
        Returns:
            Dict: 执行结果
        """
        action = context.get("action", "run")
        
        if action == "create":
            return self._create_loop(context)
        elif action == "run":
            return self._run_loop(context)
        elif action == "status":
            return self._get_loop_status(context)
        elif action == "list":
            return self._list_loops(context)
        elif action == "stop":
            return self._stop_loop(context)
        else:
            return {"success": False, "error": f"未知操作: {action}"}
    
    def _create_loop(self, context: Dict) -> Dict[str, Any]:
        """创建循环"""
        template = context.get("template", "code_gen")
        goal = context.get("goal", "")
        criteria = context.get("criteria", [])
        max_iterations = context.get("max_iterations", 5)
        timeout = context.get("timeout", 300)
        
        if not goal:
            template_info = self._templates.get(template, {})
            goal = template_info.get("goal", "完成任务")
            criteria = template_info.get("criteria", ["完成"])
        
        loop_id = str(uuid.uuid4())[:8]
        
        loop = Loop(
            loop_id=loop_id,
            template=template,
            goal=goal,
            criteria=criteria,
            max_iterations=max_iterations,
            timeout=timeout,
        )
        
        self._loops[loop_id] = loop
        
        return {
            "success": True,
            "loop_id": loop_id,
            "template": template,
            "goal": goal,
            "criteria": criteria,
            "max_iterations": max_iterations,
            "timeout": timeout,
            "status": "created",
        }
    
    def _run_loop(self, context: Dict) -> Dict[str, Any]:
        """运行循环"""
        loop_id = context.get("loop_id")
        input_data = context.get("input", context.get("message", ""))
        
        if not loop_id:
            template = context.get("template", "code_gen")
            create_result = self._create_loop(context)
            loop_id = create_result.get("loop_id")
        
        loop = self._loops.get(loop_id)
        if not loop:
            return {"success": False, "error": f"循环不存在: {loop_id}"}
        
        if not input_data:
            return {"success": False, "error": "缺少输入数据"}
        
        # 使用 _safe_async_run 避免在已有事件循环中调用 asyncio.run() 导致 RuntimeError
        result = _safe_async_run(loop.run(input_data))
        
        return {
            "success": True,
            **result,
        }
    
    def _get_loop_status(self, context: Dict) -> Dict[str, Any]:
        """获取循环状态"""
        loop_id = context.get("loop_id")
        if not loop_id:
            return {"success": False, "error": "缺少 loop_id"}
        
        loop = self._loops.get(loop_id)
        if not loop:
            return {"success": False, "error": f"循环不存在: {loop_id}"}
        
        return {
            "success": True,
            "loop_id": loop.id,
            "template": loop.template,
            "goal": loop.goal,
            "status": loop.status,
            "current_iteration": loop.current_iteration,
            "max_iterations": loop.max_iterations,
            "total_iterations": len(loop.iterations),
            "started_at": loop.started_at.isoformat() if loop.started_at else None,
            "completed_at": loop.completed_at.isoformat() if loop.completed_at else None,
        }
    
    def _list_loops(self, context: Dict) -> Dict[str, Any]:
        """列出所有循环"""
        loops_info = []
        for loop_id, loop in self._loops.items():
            loops_info.append({
                "loop_id": loop.id,
                "template": loop.template,
                "goal": loop.goal,
                "status": loop.status,
                "iterations": len(loop.iterations),
                "max_iterations": loop.max_iterations,
            })
        
        return {
            "success": True,
            "loops": loops_info,
            "count": len(loops_info),
        }
    
    def _stop_loop(self, context: Dict) -> Dict[str, Any]:
        """停止循环"""
        loop_id = context.get("loop_id")
        if not loop_id:
            return {"success": False, "error": "缺少 loop_id"}
        
        loop = self._loops.get(loop_id)
        if not loop:
            return {"success": False, "error": f"循环不存在: {loop_id}"}
        
        loop.status = "stopped"
        loop.completed_at = datetime.now()
        
        return {
            "success": True,
            "loop_id": loop_id,
            "status": "stopped",
        }
    
    def add_project_knowledge(self, project_id: str, knowledge: Dict[str, Any]):
        """添加项目知识"""
        if project_id not in self._project_knowledge:
            self._project_knowledge[project_id] = {}
        
        self._project_knowledge[project_id].update(knowledge)
        logger.info(f"项目知识已更新: {project_id}")
    
    def get_project_knowledge(self, project_id: str) -> Dict[str, Any]:
        """获取项目知识"""
        return self._project_knowledge.get(project_id, {})
    
    def list_templates(self) -> Dict[str, Any]:
        """列出所有循环模板"""
        return self._templates
    
    def list_components(self) -> Dict[str, Any]:
        """列出所有核心组件"""
        return LOOP_COMPONENTS


def get_loop_skill() -> LoopEngineeringSkill:
    """获取或创建 Loop Engineering 技能实例"""
    return LoopEngineeringSkill()


def register_loop_skill(registry=None):
    """注册 Loop Engineering 技能到技能注册表"""
    if registry is None:
        from .base import SkillRegistry
        registry = SkillRegistry()
    
    skill = LoopEngineeringSkill()
    registry.register(skill)
    logger.info("Loop Engineering 技能已注册")
    return skill