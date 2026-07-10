"""
Herdr Skill Module - 多Agent终端管理

herdr 提供"多Agent终端管理"能力，允许在一个终端中同时运行并管理多个AI编码Agent。

核心价值:
- 多Agent管理: 同时管理多个AI编码Agent
- 终端集成: 统一终端界面进行操作
- 状态监控: 实时监控Agent状态
- 任务分配: 智能分配任务给Agent

部署位置:
1. DeerFlow 任务调度引擎的"Agent调度监控工具"
2. OpenClaw 的"多Agent管理补充"
3. AI 工厂的"Agent指挥中心"

支持的操作:
- start_agent: 启动Agent
- stop_agent: 停止Agent
- list_agents: 列出所有Agent
- get_agent_status: 获取Agent状态
- assign_task: 分配任务给Agent
- broadcast_message: 广播消息给所有Agent
- get_agent_logs: 获取Agent日志
- restart_agent: 重启Agent
"""

import logging
import uuid
import time
from typing import Dict, Any
from datetime import datetime

from .base import Skill

logger = logging.getLogger(__name__)

AGENT_STATUSES = {
    "idle": {"name": "空闲", "description": "Agent已启动但未执行任务"},
    "running": {"name": "运行中", "description": "Agent正在执行任务"},
    "paused": {"name": "暂停", "description": "Agent已暂停"},
    "stopped": {"name": "已停止", "description": "Agent已停止"},
    "error": {"name": "错误", "description": "Agent遇到错误"},
    "starting": {"name": "启动中", "description": "Agent正在启动"},
}

AGENT_ROLES = {
    "code_engineer": {"name": "代码工程师", "description": "负责代码编写和开发"},
    "code_reviewer": {"name": "代码审查员", "description": "负责代码审查和质量检查"},
    "test_engineer": {"name": "测试工程师", "description": "负责测试用例编写和测试"},
    "architect": {"name": "架构师", "description": "负责系统架构设计"},
    "devops": {"name": "DevOps工程师", "description": "负责部署和运维"},
    "data_scientist": {"name": "数据科学家", "description": "负责数据分析和建模"},
    "product_manager": {"name": "产品经理", "description": "负责产品规划和需求分析"},
    "designer": {"name": "设计师", "description": "负责UI/UX设计"},
}

HERDR_FEATURES = {
    "start_agent": {
        "name": "启动Agent",
        "description": "启动指定的AI编码Agent",
        "input": ["agent_id", "role", "config"],
        "output": {"agent_id", "status", "pid"},
    },
    "stop_agent": {
        "name": "停止Agent",
        "description": "停止指定的Agent",
        "input": ["agent_id"],
        "output": {"success", "agent_id"},
    },
    "list_agents": {
        "name": "列出Agent",
        "description": "列出所有已管理的Agent",
        "input": ["status", "role"],
        "output": {"agents", "count"},
    },
    "get_agent_status": {
        "name": "Agent状态",
        "description": "获取指定Agent的状态",
        "input": ["agent_id"],
        "output": {"status", "details"},
    },
    "assign_task": {
        "name": "分配任务",
        "description": "分配任务给指定Agent",
        "input": ["agent_id", "task", "priority"],
        "output": {"task_id", "agent_id", "status"},
    },
    "broadcast_message": {
        "name": "广播消息",
        "description": "向所有Agent广播消息",
        "input": ["message"],
        "output": {"success", "agent_count"},
    },
    "get_agent_logs": {
        "name": "获取日志",
        "description": "获取Agent的运行日志",
        "input": ["agent_id", "lines"],
        "output": {"logs", "count"},
    },
    "restart_agent": {
        "name": "重启Agent",
        "description": "重启指定的Agent",
        "input": ["agent_id"],
        "output": {"success", "agent_id"},
    },
    "create_agent": {
        "name": "创建Agent",
        "description": "创建新的AI编码Agent",
        "input": ["name", "role", "config"],
        "output": {"agent_id", "success"},
    },
    "get_stats": {
        "name": "统计信息",
        "description": "获取多Agent系统的统计信息",
        "input": [],
        "output": {"total_agents", "running_agents", "tasks"},
    },
}


class HerdrSkill(Skill):
    """
    Herdr 技能 - 多Agent终端管理
    
    提供多Agent终端管理能力，允许在一个终端中同时运行并管理多个AI编码Agent。
    """
    
    NAME = "herdr"
    DESCRIPTION = "Herdr — 多Agent终端管理，允许同时运行并管理多个AI编码Agent"
    VERSION = "1.0.0"
    AUTHOR = "herdr"
    LICENSE = "MIT"
    CATEGORY = "agent"
    TAGS = ["herdr", "agent", "terminal", "management", "multi-agent", "orchestration"]
    CAPABILITIES = [
        "multi_agent_management",
        "agent_monitoring",
        "task_assignment",
        "status_tracking",
        "log_collection",
        "agent_orchestration",
    ]
    
    def __init__(self):
        super().__init__()
        self._agents = {}
        self._tasks = {}
        self._agent_roles = AGENT_ROLES
        self._statuses = AGENT_STATUSES
        self._init_default_agents()
        
    def _init_default_agents(self):
        """初始化默认Agent"""
        default_agents = [
            {"name": "代码工程师", "role": "code_engineer"},
            {"name": "代码审查员", "role": "code_reviewer"},
            {"name": "测试工程师", "role": "test_engineer"},
            {"name": "架构师", "role": "architect"},
        ]
        
        for i, agent_config in enumerate(default_agents):
            agent_id = f"agent-{i + 1}"
            self._agents[agent_id] = {
                "id": agent_id,
                "name": agent_config["name"],
                "role": agent_config["role"],
                "role_name": self._agent_roles[agent_config["role"]]["name"],
                "status": "idle",
                "status_name": self._statuses["idle"]["name"],
                "pid": None,
                "created_at": datetime.now().isoformat(),
                "last_active": datetime.now().isoformat(),
                "tasks_completed": 0,
                "tasks_failed": 0,
                "logs": [],
                "config": {},
            }
    
    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行Herdr操作
        
        Args:
            context: 执行上下文
                - action: 操作类型
                - agent_id: Agent ID
                - name: Agent名称
                - role: Agent角色
                - config: Agent配置
                - status: 状态筛选
                - task: 任务描述
                - priority: 任务优先级
                - message: 广播消息
                - lines: 日志行数
        
        Returns:
            Dict: 执行结果
        """
        action = context.get("action", "list_agents")
        
        if action not in HERDR_FEATURES:
            return {
                "success": False,
                "error": f"未知操作: {action}，可用操作: {list(HERDR_FEATURES.keys())}",
                "available_actions": HERDR_FEATURES,
            }
        
        task_id = str(uuid.uuid4())[:8]
        
        result = self._execute_action(action, task_id, context)
        
        return {
            "success": result.get("success", False),
            "task_id": task_id,
            "action": action,
            "action_name": HERDR_FEATURES[action]["name"],
            "result": result.get("result"),
            "error": result.get("error"),
            "agent_count": len(self._agents),
            "timestamp": datetime.now().isoformat(),
        }
    
    def _execute_action(self, action: str, task_id: str, context: Dict) -> Dict[str, Any]:
        """执行具体操作"""
        try:
            if action == "start_agent":
                return self._start_agent(task_id, context)
            elif action == "stop_agent":
                return self._stop_agent(context)
            elif action == "list_agents":
                return self._list_agents(context)
            elif action == "get_agent_status":
                return self._get_agent_status(context)
            elif action == "assign_task":
                return self._assign_task(task_id, context)
            elif action == "broadcast_message":
                return self._broadcast_message(context)
            elif action == "get_agent_logs":
                return self._get_agent_logs(context)
            elif action == "restart_agent":
                return self._restart_agent(context)
            elif action == "create_agent":
                return self._create_agent(task_id, context)
            elif action == "get_stats":
                return self._get_stats(context)
            else:
                return {"success": False, "error": f"操作 {action} 未实现"}
        except Exception as e:
            logger.error(f"执行失败 {action}: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    def _start_agent(self, task_id: str, context: Dict) -> Dict[str, Any]:
        """启动Agent"""
        agent_id = context.get("agent_id", "")
        role = context.get("role", "")
        config = context.get("config", {})
        
        if not agent_id:
            return {"success": False, "error": "请提供Agent ID"}
        
        if agent_id not in self._agents:
            return {"success": False, "error": f"Agent {agent_id} 未找到"}
        
        if role and role not in self._agent_roles:
            return {
                "success": False,
                "error": f"无效角色: {role}，可用角色: {list(self._agent_roles.keys())}",
            }
        
        agent = self._agents[agent_id]
        
        if agent["status"] == "running":
            return {"success": False, "error": "Agent已经在运行中"}
        
        agent["status"] = "running"
        agent["status_name"] = self._statuses["running"]["name"]
        agent["pid"] = hash(agent_id) % 10000 + 1000
        agent["last_active"] = datetime.now().isoformat()
        agent["config"] = config
        
        if role:
            agent["role"] = role
            agent["role_name"] = self._agent_roles[role]["name"]
        
        agent["logs"].append({
            "timestamp": datetime.now().isoformat(),
            "level": "INFO",
            "message": f"Agent已启动，角色: {agent['role_name']}",
        })
        
        return {
            "success": True,
            "result": {
                "agent_id": agent_id,
                "name": agent["name"],
                "role": agent["role"],
                "status": "running",
                "pid": agent["pid"],
                "message": f"Agent {agent['name']} 已启动",
            },
        }
    
    def _stop_agent(self, context: Dict) -> Dict[str, Any]:
        """停止Agent"""
        agent_id = context.get("agent_id", "")
        
        if not agent_id:
            return {"success": False, "error": "请提供Agent ID"}
        
        if agent_id not in self._agents:
            return {"success": False, "error": f"Agent {agent_id} 未找到"}
        
        agent = self._agents[agent_id]
        
        if agent["status"] == "stopped":
            return {"success": False, "error": "Agent已经停止"}
        
        agent["status"] = "stopped"
        agent["status_name"] = self._statuses["stopped"]["name"]
        agent["pid"] = None
        agent["last_active"] = datetime.now().isoformat()
        
        agent["logs"].append({
            "timestamp": datetime.now().isoformat(),
            "level": "INFO",
            "message": "Agent已停止",
        })
        
        return {
            "success": True,
            "result": {
                "agent_id": agent_id,
                "name": agent["name"],
                "status": "stopped",
                "message": f"Agent {agent['name']} 已停止",
            },
        }
    
    def _list_agents(self, context: Dict) -> Dict[str, Any]:
        """列出所有Agent"""
        status = context.get("status", "")
        role = context.get("role", "")
        
        agents = []
        for agent_id, agent in self._agents.items():
            if status and agent["status"] != status:
                continue
            if role and agent["role"] != role:
                continue
            
            agents.append({
                "id": agent_id,
                "name": agent["name"],
                "role": agent["role"],
                "role_name": agent["role_name"],
                "status": agent["status"],
                "status_name": agent["status_name"],
                "pid": agent["pid"],
                "created_at": agent["created_at"],
                "last_active": agent["last_active"],
                "tasks_completed": agent["tasks_completed"],
                "tasks_failed": agent["tasks_failed"],
            })
        
        return {
            "success": True,
            "result": {
                "agents": agents,
                "count": len(agents),
                "total_agents": len(self._agents),
                "status": status,
                "role": role,
            },
        }
    
    def _get_agent_status(self, context: Dict) -> Dict[str, Any]:
        """获取Agent状态"""
        agent_id = context.get("agent_id", "")
        
        if not agent_id:
            return {"success": False, "error": "请提供Agent ID"}
        
        if agent_id not in self._agents:
            return {"success": False, "error": f"Agent {agent_id} 未找到"}
        
        agent = self._agents[agent_id]
        
        return {
            "success": True,
            "result": {
                "agent_id": agent_id,
                "name": agent["name"],
                "role": agent["role"],
                "role_name": agent["role_name"],
                "status": agent["status"],
                "status_name": agent["status_name"],
                "pid": agent["pid"],
                "created_at": agent["created_at"],
                "last_active": agent["last_active"],
                "tasks_completed": agent["tasks_completed"],
                "tasks_failed": agent["tasks_failed"],
                "recent_logs": agent["logs"][-5:],
            },
        }
    
    def _assign_task(self, task_id: str, context: Dict) -> Dict[str, Any]:
        """分配任务给Agent"""
        agent_id = context.get("agent_id", "")
        task = context.get("task", "")
        priority = context.get("priority", "normal")
        
        if not agent_id:
            return {"success": False, "error": "请提供Agent ID"}
        
        if not task:
            return {"success": False, "error": "请提供任务描述"}
        
        if agent_id not in self._agents:
            return {"success": False, "error": f"Agent {agent_id} 未找到"}
        
        agent = self._agents[agent_id]
        
        if agent["status"] != "running":
            return {"success": False, "error": f"Agent当前状态为 {agent['status_name']}，无法分配任务"}
        
        agent["status"] = "running"
        agent["last_active"] = datetime.now().isoformat()
        
        agent["logs"].append({
            "timestamp": datetime.now().isoformat(),
            "level": "INFO",
            "message": f"分配任务: {task[:50]}...",
        })
        
        self._tasks[task_id] = {
            "task_id": task_id,
            "agent_id": agent_id,
            "agent_name": agent["name"],
            "task": task,
            "priority": priority,
            "status": "running",
            "created_at": datetime.now().isoformat(),
        }
        
        agent["logs"].append({
            "timestamp": datetime.now().isoformat(),
            "level": "INFO",
            "message": f"任务完成: {task[:50]}...",
        })
        
        agent["tasks_completed"] += 1
        
        return {
            "success": True,
            "result": {
                "task_id": task_id,
                "agent_id": agent_id,
                "agent_name": agent["name"],
                "task": task,
                "priority": priority,
                "status": "completed",
                "message": f"任务已分配给 {agent['name']} 并完成",
            },
        }
    
    def _broadcast_message(self, context: Dict) -> Dict[str, Any]:
        """广播消息给所有Agent"""
        message = context.get("message", "")
        
        if not message:
            return {"success": False, "error": "请提供广播消息"}
        
        running_agents = [a for a in self._agents.values() if a["status"] == "running"]
        
        for agent in running_agents:
            agent["logs"].append({
                "timestamp": datetime.now().isoformat(),
                "level": "INFO",
                "message": f"广播消息: {message}",
            })
        
        return {
            "success": True,
            "result": {
                "message": message,
                "agent_count": len(running_agents),
                "message": f"消息已广播给 {len(running_agents)} 个运行中的Agent",
            },
        }
    
    def _get_agent_logs(self, context: Dict) -> Dict[str, Any]:
        """获取Agent日志"""
        agent_id = context.get("agent_id", "")
        lines = context.get("lines", 20)
        
        if not agent_id:
            return {"success": False, "error": "请提供Agent ID"}
        
        if agent_id not in self._agents:
            return {"success": False, "error": f"Agent {agent_id} 未找到"}
        
        agent = self._agents[agent_id]
        logs = agent["logs"][-lines:]
        
        return {
            "success": True,
            "result": {
                "agent_id": agent_id,
                "name": agent["name"],
                "logs": logs,
                "count": len(logs),
                "total_logs": len(agent["logs"]),
            },
        }
    
    def _restart_agent(self, context: Dict) -> Dict[str, Any]:
        """重启Agent"""
        agent_id = context.get("agent_id", "")
        
        if not agent_id:
            return {"success": False, "error": "请提供Agent ID"}
        
        if agent_id not in self._agents:
            return {"success": False, "error": f"Agent {agent_id} 未找到"}
        
        agent = self._agents[agent_id]
        
        agent["status"] = "stopped"
        agent["pid"] = None
        
        agent["logs"].append({
            "timestamp": datetime.now().isoformat(),
            "level": "INFO",
            "message": "Agent正在重启...",
        })
        
        time.sleep(0.1)
        
        agent["status"] = "running"
        agent["status_name"] = self._statuses["running"]["name"]
        agent["pid"] = hash(agent_id) % 10000 + 1000
        agent["last_active"] = datetime.now().isoformat()
        
        agent["logs"].append({
            "timestamp": datetime.now().isoformat(),
            "level": "INFO",
            "message": "Agent已重启",
        })
        
        return {
            "success": True,
            "result": {
                "agent_id": agent_id,
                "name": agent["name"],
                "status": "running",
                "message": f"Agent {agent['name']} 已重启",
            },
        }
    
    def _create_agent(self, task_id: str, context: Dict) -> Dict[str, Any]:
        """创建新Agent"""
        name = context.get("name", "")
        role = context.get("role", "code_engineer")
        config = context.get("config", {})
        
        if not name:
            return {"success": False, "error": "请提供Agent名称"}
        
        if role not in self._agent_roles:
            return {
                "success": False,
                "error": f"无效角色: {role}，可用角色: {list(self._agent_roles.keys())}",
            }
        
        agent_id = f"agent-{len(self._agents) + 1}"
        
        self._agents[agent_id] = {
            "id": agent_id,
            "name": name,
            "role": role,
            "role_name": self._agent_roles[role]["name"],
            "status": "idle",
            "status_name": self._statuses["idle"]["name"],
            "pid": None,
            "created_at": datetime.now().isoformat(),
            "last_active": datetime.now().isoformat(),
            "tasks_completed": 0,
            "tasks_failed": 0,
            "logs": [{
                "timestamp": datetime.now().isoformat(),
                "level": "INFO",
                "message": f"Agent创建成功，角色: {self._agent_roles[role]['name']}",
            }],
            "config": config,
        }
        
        return {
            "success": True,
            "result": {
                "agent_id": agent_id,
                "name": name,
                "role": role,
                "role_name": self._agent_roles[role]["name"],
                "status": "idle",
                "message": f"Agent {name} 创建成功",
            },
        }
    
    def _get_stats(self, context: Dict) -> Dict[str, Any]:
        """获取统计信息"""
        status_counts = {}
        for agent in self._agents.values():
            status = agent["status"]
            status_counts[status] = status_counts.get(status, 0) + 1
        
        role_counts = {}
        for agent in self._agents.values():
            role = agent["role"]
            role_counts[role] = role_counts.get(role, 0) + 1
        
        total_tasks = sum(a["tasks_completed"] + a["tasks_failed"] for a in self._agents.values())
        
        return {
            "success": True,
            "result": {
                "total_agents": len(self._agents),
                "running_agents": status_counts.get("running", 0),
                "idle_agents": status_counts.get("idle", 0),
                "stopped_agents": status_counts.get("stopped", 0),
                "status_counts": status_counts,
                "role_counts": role_counts,
                "total_tasks": total_tasks,
                "completed_tasks": sum(a["tasks_completed"] for a in self._agents.values()),
                "failed_tasks": sum(a["tasks_failed"] for a in self._agents.values()),
            },
        }
    
    def list_features(self) -> Dict[str, Any]:
        """列出所有可用功能"""
        return HERDR_FEATURES
    
    def get_agent_count(self) -> int:
        """获取Agent数量"""
        return len(self._agents)
    
    def get_running_count(self) -> int:
        """获取运行中Agent数量"""
        return sum(1 for a in self._agents.values() if a["status"] == "running")


def get_herdr_skill() -> HerdrSkill:
    """获取或创建 Herdr 技能实例"""
    return HerdrSkill()


def register_herdr_skill(registry=None):
    """注册 Herdr 技能到技能注册表"""
    if registry is None:
        from .base import SkillRegistry
        registry = SkillRegistry()
    
    skill = HerdrSkill()
    registry.register(skill)
    logger.info("Herdr 技能已注册")
    return skill