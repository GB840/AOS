from typing import Dict, List, Optional, Any
import ast
import subprocess
import tempfile
import os
import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

# 传给沙箱子进程的"安全环境变量"白名单: 仅保留运行 python/node/bash 所需的最小系统变量,
# 彻底剔除 AOS 自身密钥 (API_KEY / JWT 私钥 / 数据库口令 / *SECRET* / *TOKEN* 等),
# 使沙箱内用户代码无法通过 os.environ 读取平台机密。
_SANDBOX_SAFE_ENV_KEYS = {
    "PATH", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "TEMP", "TMP", "TMPDIR",
    "LANG", "LC_ALL", "PYTHONIOENCODING", "PYTHONUNBUFFERED",
    "HOME", "USERPROFILE", "COMSPEC", "PATHEXT", "OS",
    "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE", "PROCESSOR_IDENTIFIER",
}

class SandboxConfig:
    def __init__(
        self,
        allowed_modules: Optional[List[str]] = None,
        disallowed_modules: Optional[List[str]] = None,
        max_memory_mb: int = 256,
        max_cpu_time_seconds: int = 60,
        max_output_size: int = 1024 * 1024,
        allowed_paths: Optional[List[str]] = None,
        disallowed_paths: Optional[List[str]] = None,
    ):
        self.allowed_modules = allowed_modules or []
        self.disallowed_modules = disallowed_modules or []
        self.max_memory_mb = max_memory_mb
        self.max_cpu_time_seconds = max_cpu_time_seconds
        self.max_output_size = max_output_size
        self.allowed_paths = allowed_paths or []
        self.disallowed_paths = disallowed_paths or []
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed_modules": self.allowed_modules,
            "disallowed_modules": self.disallowed_modules,
            "max_memory_mb": self.max_memory_mb,
            "max_cpu_time_seconds": self.max_cpu_time_seconds,
            "max_output_size": self.max_output_size,
            "allowed_paths": self.allowed_paths,
            "disallowed_paths": self.disallowed_paths,
        }

class SandboxResult:
    def __init__(
        self,
        success: bool,
        output: Optional[str] = None,
        error: Optional[str] = None,
        duration_ms: float = 0,
        memory_used_mb: float = 0,
    ):
        self.success = success
        self.output = output
        self.error = error
        self.duration_ms = duration_ms
        self.memory_used_mb = memory_used_mb
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "memory_used_mb": self.memory_used_mb,
        }

class SkillSandbox:
    def __init__(self, config: Optional[SandboxConfig] = None):
        self.config = config or SandboxConfig()
        self._setup_sandbox_env()
    
    def _setup_sandbox_env(self):
        self.sandbox_dir = Path(tempfile.mkdtemp(prefix="aos-sandbox-"))
        os.chmod(self.sandbox_dir, 0o755)
    
    def _cleanup(self):
        if hasattr(self, 'sandbox_dir') and self.sandbox_dir.exists():
            try:
                shutil.rmtree(self.sandbox_dir)
            except Exception as e:
                logger.warning("沙箱目录清理失败: %s", e)

    def _safe_env(self) -> Dict[str, str]:
        """构造不含任何 AOS 密钥的最小环境, 供沙箱子进程使用 (防机密泄露)。"""
        env: Dict[str, str] = {}
        for k in _SANDBOX_SAFE_ENV_KEYS:
            if k in os.environ:
                env[k] = os.environ[k]
        # 仅把沙箱目录加入 PYTHONPATH, 不让子进程 import AOS 内部模块。
        env["PYTHONPATH"] = str(self.sandbox_dir)
        env["PYTHONIOENCODING"] = "utf-8"
        return env

    def _check_imports(self, code: str) -> Optional[str]:
        """AST 静态校验 import, 落实 SandboxConfig 的 allow/deny。

        阻断 os/subprocess/socket 等高危模块 (含 __import__ / importlib.import_module 动态导入),
        防止沙箱内用户代码逃逸到宿主机。返回错误描述或 None。
        """
        allowed = set(self.config.allowed_modules or [])
        denied = set(self.config.disallowed_modules or [])
        if not allowed and not denied:
            return None
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return f"syntax error: {e}"
        for node in ast.walk(tree):
            mod: Optional[str] = None
            if isinstance(node, ast.Import):
                for n in node.names:
                    mod = n.name.split(".")[0]
                    if self._import_blocked(mod, allowed, denied):
                        return f"import 被禁止: {mod}"
            elif isinstance(node, ast.ImportFrom):
                mod = (node.module or "").split(".")[0]
                if mod and self._import_blocked(mod, allowed, denied):
                    return f"import 被禁止: {mod}"
            elif isinstance(node, ast.Call):
                # 拦截 __import__('os') / importlib.import_module('os')
                func = node.func
                name = getattr(func, "attr", None) or getattr(func, "id", None)
                if name in ("import_module", "import_", "__import__") and node.args:
                    arg = node.args[0]
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        mod = arg.value.split(".")[0]
                        if self._import_blocked(mod, allowed, denied):
                            return f"动态导入被禁止: {mod}"
        return None

    @staticmethod
    def _import_blocked(mod: str, allowed: set, denied: set) -> bool:
        if denied and mod in denied:
            return True
        if allowed and mod not in allowed:
            return True
        return False
    
    def execute_code(self, code: str, language: str = "python") -> SandboxResult:
        if language == "python":
            return self._execute_python(code)
        elif language == "javascript":
            return self._execute_javascript(code)
        elif language == "bash":
            return self._execute_bash(code)
        else:
            return SandboxResult(success=False, error=f"Unsupported language: {language}")
    
    def _execute_python(self, code: str) -> SandboxResult:
        import time
        
        # 静态校验 import: 命中禁止/白名单则直接拒绝, 不启动子进程 (fail-fast)。
        bad = self._check_imports(code)
        if bad:
            return SandboxResult(success=False, error=f"security: {bad}")
        
        executor_path = self.sandbox_dir / "executor.py"
        user_code_path = self.sandbox_dir / "user_code.py"
        result_path = self.sandbox_dir / "result.json"
        
        sandbox_code = self._wrap_python_code(code)
        
        with open(user_code_path, "w", encoding="utf-8") as f:
            f.write(code)
        
        with open(executor_path, "w", encoding="utf-8") as f:
            f.write(sandbox_code)
        
        start_time = time.time()
        
        try:
            # 仅传不含密钥的最小安全环境, 防止沙箱读取平台机密。
            env = self._safe_env()
            
            proc = subprocess.run(
                ["python", str(executor_path)],
                cwd=self.sandbox_dir,
                env=env,
                capture_output=True,
                text=True,
                timeout=self.config.max_cpu_time_seconds,
            )
            
            duration_ms = (time.time() - start_time) * 1000
            
            if result_path.exists():
                with open(result_path, "r", encoding="utf-8") as f:
                    import json
                    try:
                        result_data = json.load(f)
                        return SandboxResult(
                            success=result_data.get("success", False),
                            output=result_data.get("output"),
                            error=result_data.get("error"),
                            duration_ms=duration_ms,
                            memory_used_mb=result_data.get("memory_used", 0),
                        )
                    except Exception as e:
                        logger.warning("沙箱结果 JSON 解析失败: %s", e)
            
            if proc.returncode == 0:
                output = proc.stdout[:self.config.max_output_size]
                return SandboxResult(
                    success=True,
                    output=output,
                    duration_ms=duration_ms,
                )
            else:
                error = proc.stderr[:self.config.max_output_size]
                return SandboxResult(
                    success=False,
                    error=error,
                    duration_ms=duration_ms,
                )
        
        except subprocess.TimeoutExpired:
            duration_ms = (time.time() - start_time) * 1000
            return SandboxResult(
                success=False,
                error=f"Timeout after {self.config.max_cpu_time_seconds} seconds",
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return SandboxResult(
                success=False,
                error=str(e),
                duration_ms=duration_ms,
            )
    
    def _wrap_python_code(self, code: str) -> str:
        return """
import sys
import os
import json
import tracemalloc
import time

result = {
    "success": False,
    "output": "",
    "error": "",
    "memory_used": 0,
}

tracemalloc.start()
start_time = time.time()

old_stdout = sys.stdout
old_stderr = sys.stderr
output_buffer = []

class OutputCatcher:
    def write(self, text):
        output_buffer.append(text)
    def flush(self):
        pass

sys.stdout = OutputCatcher()
sys.stderr = OutputCatcher()

try:
    code_file = os.path.join(os.path.dirname(__file__), "user_code.py")
    with open(code_file, "r", encoding="utf-8") as f:
        user_code = f.read()
    exec(user_code)
    result["success"] = True
except Exception as e:
    result["error"] = str(e)
finally:
    sys.stdout = old_stdout
    sys.stderr = old_stderr
    end_time = time.time()

snapshot = tracemalloc.take_snapshot()
top_stats = snapshot.statistics("lineno")
memory_used = sum(stat.size for stat in top_stats) / (1024 * 1024)

result["output"] = "".join(output_buffer)
result["memory_used"] = round(memory_used, 2)

result_path = os.path.join(os.path.dirname(__file__), "result.json")
with open(result_path, "w", encoding="utf-8") as f:
    json.dump(result, f)
"""
    
    def _execute_javascript(self, code: str) -> SandboxResult:
        import time
        
        code_path = self.sandbox_dir / "executor.js"
        result_path = self.sandbox_dir / "result.json"
        
        with open(code_path, "w", encoding="utf-8") as f:
            f.write(code)
        
        start_time = time.time()
        
        try:
            # 仅传不含密钥的最小安全环境。
            env = self._safe_env()
            proc = subprocess.run(
                ["node", str(code_path)],
                cwd=self.sandbox_dir,
                env=env,
                capture_output=True,
                text=True,
                timeout=self.config.max_cpu_time_seconds,
            )
            
            duration_ms = (time.time() - start_time) * 1000
            
            if proc.returncode == 0:
                output = proc.stdout[:self.config.max_output_size]
                return SandboxResult(
                    success=True,
                    output=output,
                    duration_ms=duration_ms,
                )
            else:
                error = proc.stderr[:self.config.max_output_size]
                return SandboxResult(
                    success=False,
                    error=error,
                    duration_ms=duration_ms,
                )
        
        except subprocess.TimeoutExpired:
            duration_ms = (time.time() - start_time) * 1000
            return SandboxResult(
                success=False,
                error=f"Timeout after {self.config.max_cpu_time_seconds} seconds",
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return SandboxResult(
                success=False,
                error=str(e),
                duration_ms=duration_ms,
            )
    
    def _execute_bash(self, code: str) -> SandboxResult:
        import time
        
        code_path = self.sandbox_dir / "executor.sh"
        
        with open(code_path, "w", encoding="utf-8") as f:
            f.write(code)
        
        os.chmod(code_path, 0o755)
        
        start_time = time.time()
        
        try:
            # 仅传不含密钥的最小安全环境。
            env = self._safe_env()
            proc = subprocess.run(
                ["bash", str(code_path)],
                cwd=self.sandbox_dir,
                env=env,
                capture_output=True,
                text=True,
                timeout=self.config.max_cpu_time_seconds,
            )
            
            duration_ms = (time.time() - start_time) * 1000
            
            if proc.returncode == 0:
                output = proc.stdout[:self.config.max_output_size]
                return SandboxResult(
                    success=True,
                    output=output,
                    duration_ms=duration_ms,
                )
            else:
                error = proc.stderr[:self.config.max_output_size]
                return SandboxResult(
                    success=False,
                    error=error,
                    duration_ms=duration_ms,
                )
        
        except subprocess.TimeoutExpired:
            duration_ms = (time.time() - start_time) * 1000
            return SandboxResult(
                success=False,
                error=f"Timeout after {self.config.max_cpu_time_seconds} seconds",
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return SandboxResult(
                success=False,
                error=str(e),
                duration_ms=duration_ms,
            )
    
    def execute_skill_safely(self, skill_name: str, context: Dict[str, Any]) -> SandboxResult:
        from .base import SkillRegistry
        
        registry = SkillRegistry()
        skill = registry.find_by_name(skill_name)
        
        if not skill:
            return SandboxResult(success=False, error=f"Skill '{skill_name}' not found")
        
        try:
            # 防模板注入
            safe_name = skill_name.replace('"', '\\"').replace('\n', '')
            safe_context = str(context).replace('"', '\\"').replace('\n', '')
            code_to_execute = """
from skills.base import SkillRegistry
registry = SkillRegistry()
skill = registry.find_by_name("{name}")
if skill:
    result = skill.execute({ctx})
    print(result)
""".format(name=safe_name, ctx=safe_context)
            return self.execute_code(code_to_execute, language="python")
        except Exception as e:
            return SandboxResult(success=False, error=str(e))
    
    def validate_code(self, code: str, language: str = "python") -> Dict[str, Any]:
        issues = []
        
        dangerous_patterns = [
            ("os.system", "Potential command injection"),
            ("subprocess", "Potential command injection"),
            ("eval(", "Potential code injection"),
            ("exec(", "Potential code injection"),
            ("__import__", "Potential module abuse"),
            ("pickle.loads", "Potential deserialization attack"),
            ("yaml.load", "Potential deserialization attack"),
            ("socket.socket", "Potential network access"),
            ("urllib.request", "Potential external access"),
            ("requests.", "Potential external access"),
        ]
        
        for pattern, description in dangerous_patterns:
            if pattern in code:
                issues.append({
                    "type": "security",
                    "pattern": pattern,
                    "description": description,
                })
        
        if language == "python":
            try:
                compile(code, "<string>", "exec")
                issues.append({"type": "syntax", "status": "valid", "description": "Python syntax is valid"})
            except SyntaxError as e:
                issues.append({"type": "syntax", "status": "invalid", "description": f"Syntax error: {e}"})
        
        return {
            "valid": len([i for i in issues if i["type"] == "security"]) == 0,
            "issues": issues,
        }
    
    def cleanup(self):
        self._cleanup()

_default_sandbox = None

def get_sandbox() -> SkillSandbox:
    global _default_sandbox
    if _default_sandbox is None:
        config = SandboxConfig(
            disallowed_modules=[
                "os", "subprocess", "socket", "urllib", "requests",
                "pickle", "yaml", "marshal", "ctypes", "threading",
                "multiprocessing", "shutil", "tempfile", "glob",
            ],
            max_memory_mb=256,
            max_cpu_time_seconds=30,
        )
        _default_sandbox = SkillSandbox(config)
    return _default_sandbox