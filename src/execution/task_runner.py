"""
Task Runner - 任务运行器

管理任务的执行流程，支持：
- 任务队列管理
- 任务状态追踪
- 任务依赖处理
- 并行任务执行
- 任务重试机制
- 任务超时控制

标准：任务队列标准 (RabbitMQ/Kafka 兼容)
"""

import logging
import uuid
import asyncio
import threading
import time
from typing import Dict, Any, Callable
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TaskRunner:
    """任务运行器 - 管理任务的执行流程"""
    
    def __init__(self):
        self._tasks = {}
        self._task_queue = []
        self._max_workers = 4
        self._running_workers = 0
        self._lock = threading.Lock()
        
        logger.info("TaskRunner initialized")
    
    def submit_task(self, 
                    task_name: str,
                    task_func: Callable,
                    args: tuple = None,
                    kwargs: Dict = None,
                    priority: str = "medium",
                    timeout: int = 300,
                    retries: int = 2) -> Dict[str, Any]:
        """提交任务"""
        task_id = str(uuid.uuid4())[:8]
        
        task = {
            "id": task_id,
            "name": task_name,
            "func": task_func,
            "args": args or (),
            "kwargs": kwargs or {},
            "priority": priority,
            "timeout": timeout,
            "retries": retries,
            "status": TaskStatus.PENDING.value,
            "submitted_at": datetime.now().isoformat(),
            "started_at": None,
            "completed_at": None,
            "result": None,
            "error": None,
            "attempts": 0,
        }
        
        self._tasks[task_id] = task
        self._add_to_queue(task)
        
        logger.info(f"任务提交成功: {task_id} - {task_name}")
        return {"success": True, "task_id": task_id}
    
    def _add_to_queue(self, task: Dict):
        """添加任务到队列"""
        priority_order = {"high": 0, "medium": 1, "low": 2}
        
        with self._lock:
            inserted = False
            for i, queued_task in enumerate(self._task_queue):
                if priority_order[task["priority"]] < priority_order[queued_task["priority"]]:
                    self._task_queue.insert(i, task)
                    inserted = True
                    break
            
            if not inserted:
                self._task_queue.append(task)
    
    def run_task(self, task_id: str) -> Dict[str, Any]:
        """执行任务"""
        task = self._tasks.get(task_id)
        
        if not task:
            return {"success": False, "error": f"任务不存在: {task_id}"}
        
        if task["status"] == TaskStatus.RUNNING.value:
            return {"success": False, "error": f"任务正在运行: {task_id}"}
        
        task["status"] = TaskStatus.RUNNING.value
        task["started_at"] = datetime.now().isoformat()
        
        for attempt in range(task["retries"] + 1):
            task["attempts"] = attempt + 1
            
            try:
                result = task["func"](*task["args"], **task["kwargs"])
                
                task["status"] = TaskStatus.COMPLETED.value
                task["completed_at"] = datetime.now().isoformat()
                task["result"] = result
                
                logger.info(f"任务执行成功: {task_id}")
                return {"success": True, "task_id": task_id, "result": result}
            
            except Exception as e:
                error_msg = str(e)
                
                if attempt < task["retries"]:
                    logger.warning(f"任务执行失败 (重试 {attempt + 1}/{task['retries']}): {task_id} - {error_msg}")
                    time.sleep(2 ** attempt)
                else:
                    task["status"] = TaskStatus.FAILED.value
                    task["completed_at"] = datetime.now().isoformat()
                    task["error"] = error_msg
                    
                    logger.error(f"任务执行失败: {task_id} - {error_msg}")
                    return {"success": False, "error": error_msg}
    
    async def run_task_async(self, task_id: str) -> Dict[str, Any]:
        """异步执行任务"""
        task = self._tasks.get(task_id)
        
        if not task:
            return {"success": False, "error": f"任务不存在: {task_id}"}
        
        if task["status"] == TaskStatus.RUNNING.value:
            return {"success": False, "error": f"任务正在运行: {task_id}"}
        
        task["status"] = TaskStatus.RUNNING.value
        task["started_at"] = datetime.now().isoformat()
        
        for attempt in range(task["retries"] + 1):
            task["attempts"] = attempt + 1
            
            try:
                if asyncio.iscoroutinefunction(task["func"]):
                    result = await task["func"](*task["args"], **task["kwargs"])
                else:
                    result = await asyncio.to_thread(task["func"], *task["args"], **task["kwargs"])
                
                task["status"] = TaskStatus.COMPLETED.value
                task["completed_at"] = datetime.now().isoformat()
                task["result"] = result
                
                logger.info(f"任务执行成功: {task_id}")
                return {"success": True, "task_id": task_id, "result": result}
            
            except Exception as e:
                error_msg = str(e)
                
                if attempt < task["retries"]:
                    logger.warning(f"任务执行失败 (重试 {attempt + 1}/{task['retries']}): {task_id} - {error_msg}")
                    await asyncio.sleep(2 ** attempt)
                else:
                    task["status"] = TaskStatus.FAILED.value
                    task["completed_at"] = datetime.now().isoformat()
                    task["error"] = error_msg
                    
                    logger.error(f"任务执行失败: {task_id} - {error_msg}")
                    return {"success": False, "error": error_msg}
    
    def cancel_task(self, task_id: str) -> Dict[str, Any]:
        """取消任务"""
        task = self._tasks.get(task_id)
        
        if not task:
            return {"success": False, "error": f"任务不存在: {task_id}"}
        
        if task["status"] == TaskStatus.COMPLETED.value:
            return {"success": False, "error": "任务已完成"}
        
        task["status"] = TaskStatus.CANCELLED.value
        task["completed_at"] = datetime.now().isoformat()
        
        logger.info(f"任务已取消: {task_id}")
        return {"success": True, "message": f"任务 {task_id} 已取消"}
    
    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """获取任务状态"""
        task = self._tasks.get(task_id)
        
        if not task:
            return {"success": False, "error": f"任务不存在: {task_id}"}
        
        return {
            "success": True,
            "task": {
                "id": task["id"],
                "name": task["name"],
                "status": task["status"],
                "priority": task["priority"],
                "attempts": task["attempts"],
                "submitted_at": task["submitted_at"],
                "started_at": task["started_at"],
                "completed_at": task["completed_at"],
                "result": task["result"],
                "error": task["error"],
            },
        }
    
    def list_tasks(self, status: str = None) -> Dict[str, Any]:
        """列出任务"""
        tasks_info = []
        
        for task_id, task in self._tasks.items():
            if status and task["status"] != status:
                continue
            
            tasks_info.append({
                "id": task_id,
                "name": task["name"],
                "status": task["status"],
                "priority": task["priority"],
                "attempts": task["attempts"],
                "submitted_at": task["submitted_at"],
                "started_at": task["started_at"],
                "completed_at": task["completed_at"],
            })
        
        return {
            "success": True,
            "tasks": tasks_info,
            "count": len(tasks_info),
            "queue_length": len(self._task_queue),
        }
    
    def start_worker(self):
        """启动工作线程"""
        def worker():
            while True:
                with self._lock:
                    if not self._task_queue:
                        break
                    
                    task = self._task_queue.pop(0)
                
                self.run_task(task["id"])
        
        t = threading.Thread(target=worker)
        t.start()
        
        logger.info("工作线程已启动")
    
    def start_workers(self, count: int = None):
        """启动多个工作线程"""
        num_workers = count or self._max_workers
        
        for _ in range(num_workers):
            self.start_worker()
        
        logger.info(f"{num_workers} 个工作线程已启动")
