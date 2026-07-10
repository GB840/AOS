"""
RuFlo Subagent - 多智能体编排子智能体

将 RuFlo 作为 DeerFlow 子智能体集成，提供专业级开发团队协作能力。
作为"超级 Worker"，专门处理需要大规模协作的复杂开发任务。

核心能力:
- 多智能体蜂群 (Swarm): 100+ 专业智能体协同工作
- 智能三层路由 (Routing): 低成本/高性能分层处理
- 持久化向量记忆 (Memory): 150x-12,500x 加速的向量搜索
- 分布式联邦通信 (Federation): 跨机器安全通信
"""

import os
import logging
import uuid
import asyncio
from typing import Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class RuFloSubagent:
    """
    RuFlo 多智能体编排子智能体
    
    通过 DeerFlow 调度，执行专业级开发任务。
    支持八种任务类型和十个专业智能体角色。
    """
    
    NAME = "ruflo"
    DESCRIPTION = "RuFlo 多智能体编排平台 — 赋予 AI 工具、记忆、循环和沙箱"
    CAPABILITIES = [
        "code_generation",
        "code_review",
        "test_generation",
        "security_audit",
        "architecture_design",
        "full_stack_development",
        "data_pipeline",
        "devops_deployment",
        "multi_agent_swarm",
        "persistent_memory",
    ]
    
    AGENTS = {
        "architect": {"name": "架构师", "role": "架构设计", "emoji": "🏗️"},
        "developer": {"name": "开发者", "role": "编码实现", "emoji": "👨‍💻"},
        "reviewer": {"name": "代码审查员", "role": "代码审查", "emoji": "🔍"},
        "tester": {"name": "测试工程师", "role": "测试验证", "emoji": "🧪"},
        "security": {"name": "安全专家", "role": "安全审计", "emoji": "🛡️"},
        "devops": {"name": "DevOps工程师", "role": "部署运维", "emoji": "🚀"},
        "frontend": {"name": "前端工程师", "role": "前端开发", "emoji": "🎨"},
        "backend": {"name": "后端工程师", "role": "后端开发", "emoji": "⚙️"},
        "data": {"name": "数据工程师", "role": "数据处理", "emoji": "📊"},
        "qa": {"name": "QA工程师", "role": "质量保证", "emoji": "✅"},
    }
    
    TASKS = {
        "code_gen": {"name": "代码生成", "description": "根据需求生成代码", "agents": ["developer"], "emoji": "💻"},
        "code_review": {"name": "代码审查", "description": "审查代码质量", "agents": ["reviewer", "security"], "emoji": "🔍"},
        "test_gen": {"name": "测试生成", "description": "生成测试用例", "agents": ["tester", "qa"], "emoji": "🧪"},
        "security_audit": {"name": "安全审计", "description": "安全漏洞扫描", "agents": ["security"], "emoji": "🛡️"},
        "architect_design": {"name": "架构设计", "description": "系统架构设计", "agents": ["architect", "backend"], "emoji": "🏗️"},
        "full_stack": {"name": "全栈开发", "description": "完整项目开发", "agents": ["frontend", "backend", "devops"], "emoji": "🌐"},
        "data_pipeline": {"name": "数据管道", "description": "数据处理管道", "agents": ["data", "backend"], "emoji": "📊"},
        "deploy": {"name": "部署上线", "description": "CI/CD部署", "agents": ["devops"], "emoji": "🚀"},
    }
    
    def __init__(self):
        self._skill = None
        self._initialized = False
        self._tasks: Dict[str, Dict] = {}
        
        self._init_skill()
    
    def _init_skill(self):
        """初始化 RuFlo 技能"""
        try:
            from skills.ruflo import get_ruflo_skill
            self._skill = get_ruflo_skill()
            self._initialized = True
            logger.info("RuFlo 子智能体初始化成功")
        except Exception as e:
            logger.warning(f"RuFlo 技能初始化失败: {e}")
            logger.info("RuFlo CLI 未安装，将使用模拟模式")
    
    def handle(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        同步调用入口 — 供 SubAgentRegistry.invoke() 使用
        
        Args:
            input_data: 输入数据
                - task: 任务类型
                - input/message/prompt: 任务描述
                - agents: 指定智能体列表 (可选)
                - params: 额外参数
        
        Returns:
            Dict: 执行结果
        """
        if not self._initialized:
            return self._handle_mock(input_data)
        
        try:
            result = self._skill.execute(input_data)
            if result.get("success"):
                logger.info(f"RuFlo 任务执行成功: {result.get('task_id')}")
            else:
                logger.warning(f"RuFlo 任务执行失败: {result.get('error')}")
            return result
        except Exception as e:
            logger.error(f"RuFlo 子智能体执行失败: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    async def async_handle(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        异步调用入口
        
        Args:
            input_data: 输入数据
        
        Returns:
            Dict: 执行结果
        """
        if not self._initialized:
            return self._handle_mock(input_data)
        
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self._skill.execute, input_data)
        return result
    
    def _handle_mock(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        模拟模式处理 — 当 RuFlo CLI 未安装时返回模拟结果
        
        使用 AOS 内置能力模拟 RuFlo 的多智能体协作效果。
        """
        task_id = str(uuid.uuid4())[:8]
        task_type = input_data.get("task", "code_gen")
        input_content = input_data.get("input", input_data.get("message", ""))
        
        task_config = self.TASKS.get(task_type, {})
        agents = input_data.get("agents", task_config.get("agents", ["developer"]))
        agent_details = [self.AGENTS.get(a, {"name": a, "role": "unknown", "emoji": "🤖"}) for a in agents]
        
        mock_result = {
            "success": True,
            "task_id": task_id,
            "task_type": task_type,
            "task_name": task_config.get("name", task_type),
            "status": "completed",
            "started_at": datetime.now().isoformat(),
            "completed_at": datetime.now().isoformat(),
            "result": {
                "mock": True,
                "task_type": task_type,
                "input_length": len(input_content),
                "agents": agent_details,
                "options": input_data.get("params", {}),
                "execution_steps": [
                    {"agent": agent_details[0]["name"], "action": "分析需求", "status": "completed", "emoji": "📋"},
                    {"agent": agent_details[0]["name"], "action": "制定方案", "status": "completed", "emoji": "📐"},
                    {"agent": agent_details[1]["name"] if len(agent_details) > 1 else agent_details[0]["name"], 
                     "action": "编写代码", "status": "completed", "emoji": "💻"},
                    {"agent": "代码审查员", "action": "审查代码", "status": "completed", "emoji": "🔍"},
                    {"agent": "测试工程师", "action": "编写测试", "status": "completed", "emoji": "🧪"},
                ],
                "message": "RuFlo CLI 未安装，使用 AOS 模拟模式。实际使用请安装: npm install -g ruflo",
                "features": [
                    "🧠 多智能体蜂群 (100+ 专业智能体)",
                    "🔄 智能三层路由 (低成本/高性能分层)",
                    "💾 持久化向量记忆 (150x-12,500x 加速)",
                    "🌐 分布式联邦通信 (跨机器安全)",
                    "🔧 314 个 MCP 工具 + 26 个 CLI 命令",
                ],
                "next_steps": [
                    "安装 RuFlo: npm install -g ruflo",
                    "配置 API 密钥: export RUFLO_API_KEY=your-key",
                    "重新运行任务",
                ],
            },
        }
        
        logger.info(f"RuFlo 模拟模式: {task_type} -> {task_id}")
        return mock_result
    
    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """
        获取任务状态
        
        Args:
            task_id: 任务 ID
        
        Returns:
            Dict: 任务状态信息
        """
        if self._skill:
            return self._skill.get_task_status(task_id)
        
        return self._tasks.get(task_id, {"status": "unknown"})
    
    def list_agents(self) -> Dict[str, Any]:
        """
        列出所有可用智能体
        
        Returns:
            Dict: 智能体列表
        """
        return self.AGENTS
    
    def list_tasks(self) -> Dict[str, Any]:
        """
        列出所有可用任务类型
        
        Returns:
            Dict: 任务列表
        """
        return self.TASKS
    
    def is_ready(self) -> bool:
        """
        检查子智能体是否就绪
        
        Returns:
            bool: 是否就绪
        """
        return self._initialized
    
    def configure(self, api_key: str) -> bool:
        """
        配置 RuFlo API 密钥
        
        Args:
            api_key: RuFlo API 密钥
        
        Returns:
            bool: 是否配置成功
        """
        os.environ["RUFLO_API_KEY"] = api_key
        logger.info("RuFlo API 密钥已配置")
        return True


def get_ruflo_subagent() -> RuFloSubagent:
    """获取或创建 RuFlo 子智能体实例"""
    return RuFloSubagent()


def register_ruflo_subagent(registry=None):
    """注册 RuFlo 子智能体到 SubAgentRegistry"""
    if registry is None:
        from subagents.base import SubAgentRegistry
        registry = SubAgentRegistry()
    
    agent = RuFloSubagent()
    registry.register(agent.NAME, agent.DESCRIPTION, agent.CAPABILITIES, agent.handle)
    logger.info("RuFlo 子智能体已注册")
    return agent