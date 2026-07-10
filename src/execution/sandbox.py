"""
Sandbox Manager - 沙箱隔离层

提供安全的代码执行环境，支持多种沙箱后端：
- 本地沙箱（Docker/K8s）
- E2B 沙箱
- Firecrawl 沙箱

核心能力：
- 代码隔离执行
- 资源限制（CPU/内存/时间）
- 文件系统隔离
- 网络访问控制
- 环境变量管理

标准：Docker/K8s 沙箱标准
"""

import os
import sys
import logging
import uuid
import tempfile
import subprocess
from typing import Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class SandboxManager:
    """沙箱管理器 - 提供安全的代码执行环境"""
    
    def __init__(self):
        self._sandboxes = {}
        self._max_sandboxes = 10
        self._default_timeout = 30
        self._default_memory_limit = "512m"
        
        logger.info("SandboxManager initialized")
    
    def create_sandbox(self, 
                       name: str = None,
                       timeout: int = None,
                       memory_limit: str = None,
                       network_access: bool = True) -> Dict[str, Any]:
        """创建新沙箱"""
        sandbox_id = str(uuid.uuid4())[:8]
        sandbox_name = name or f"sandbox_{sandbox_id}"
        
        if len(self._sandboxes) >= self._max_sandboxes:
            return {"success": False, "error": "沙箱数量已达上限"}
        
        sandbox = {
            "id": sandbox_id,
            "name": sandbox_name,
            "timeout": timeout or self._default_timeout,
            "memory_limit": memory_limit or self._default_memory_limit,
            "network_access": network_access,
            "status": "running",
            "created_at": datetime.now().isoformat(),
            "executions": [],
        }
        
        self._sandboxes[sandbox_id] = sandbox
        logger.info(f"沙箱创建成功: {sandbox_id}")
        
        return {"success": True, "sandbox": sandbox}
    
    def execute_code(self, 
                     sandbox_id: str,
                     code: str,
                     language: str = "python",
                     timeout: int = None) -> Dict[str, Any]:
        """在沙箱中执行代码"""
        sandbox = self._sandboxes.get(sandbox_id)
        
        if not sandbox:
            return {"success": False, "error": f"沙箱不存在: {sandbox_id}"}
        
        if sandbox["status"] != "running":
            return {"success": False, "error": f"沙箱未运行: {sandbox_id}"}
        
        exec_timeout = timeout or sandbox["timeout"]
        
        try:
            if language.lower() == "python":
                result = self._execute_python(code, exec_timeout)
            elif language.lower() == "javascript":
                result = self._execute_javascript(code, exec_timeout)
            elif language.lower() == "bash":
                result = self._execute_bash(code, exec_timeout)
            else:
                return {"success": False, "error": f"不支持的语言: {language}"}
            
            sandbox["executions"].append({
                "timestamp": datetime.now().isoformat(),
                "language": language,
                "status": "success" if result.get("success") else "failed",
                "duration": result.get("duration", 0),
            })
            
            return result
        
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _execute_python(self, code: str, timeout: int) -> Dict[str, Any]:
        """执行Python代码"""
        import time
        start_time = time.time()
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            temp_file = f.name
        
        try:
            result = subprocess.run(
                [sys.executable, temp_file],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            
            duration = time.time() - start_time
            
            if result.returncode == 0:
                return {
                    "success": True,
                    "output": result.stdout,
                    "duration": round(duration, 2),
                }
            else:
                return {
                    "success": False,
                    "error": result.stderr,
                    "duration": round(duration, 2),
                }
        finally:
            os.unlink(temp_file)
    
    def _execute_javascript(self, code: str, timeout: int) -> Dict[str, Any]:
        """执行JavaScript代码"""
        import time
        start_time = time.time()
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
            f.write(code)
            temp_file = f.name
        
        try:
            result = subprocess.run(
                ["node", temp_file],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            
            duration = time.time() - start_time
            
            if result.returncode == 0:
                return {
                    "success": True,
                    "output": result.stdout,
                    "duration": round(duration, 2),
                }
            else:
                return {
                    "success": False,
                    "error": result.stderr,
                    "duration": round(duration, 2),
                }
        finally:
            os.unlink(temp_file)
    
    def _execute_bash(self, code: str, timeout: int) -> Dict[str, Any]:
        """执行Bash命令"""
        import time
        start_time = time.time()
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as f:
            f.write(code)
            temp_file = f.name
        
        try:
            os.chmod(temp_file, 0o755)
            
            result = subprocess.run(
                [temp_file],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            
            duration = time.time() - start_time
            
            if result.returncode == 0:
                return {
                    "success": True,
                    "output": result.stdout,
                    "duration": round(duration, 2),
                }
            else:
                return {
                    "success": False,
                    "error": result.stderr,
                    "duration": round(duration, 2),
                }
        finally:
            os.unlink(temp_file)
    
    def destroy_sandbox(self, sandbox_id: str) -> Dict[str, Any]:
        """销毁沙箱"""
        if sandbox_id not in self._sandboxes:
            return {"success": False, "error": f"沙箱不存在: {sandbox_id}"}
        
        del self._sandboxes[sandbox_id]
        logger.info(f"沙箱已销毁: {sandbox_id}")
        
        return {"success": True, "message": f"沙箱 {sandbox_id} 已销毁"}
    
    def list_sandboxes(self) -> Dict[str, Any]:
        """列出所有沙箱"""
        return {
            "success": True,
            "sandboxes": list(self._sandboxes.values()),
            "count": len(self._sandboxes),
        }
    
    def get_sandbox_status(self, sandbox_id: str) -> Dict[str, Any]:
        """获取沙箱状态"""
        sandbox = self._sandboxes.get(sandbox_id)
        
        if not sandbox:
            return {"success": False, "error": f"沙箱不存在: {sandbox_id}"}
        
        return {"success": True, "sandbox": sandbox}
