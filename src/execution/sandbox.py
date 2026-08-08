"""
Sandbox Manager - 防手滑执行护栏（非安全沙箱边界）

诚实边界声明：本模块是 **defense-in-depth 的护栏层**，用于拦截明显的破坏性 /
危险命令（rm -rf、格式化、fork bomb、os.system / subprocess 派生外壳等），
降低「手滑误执行」与「低成熟度代码随意派生进程」的风险。

它 **不是** 安全沙箱边界：
- POSIX 下经 setrlimit 做 RLIMIT_AS / RLIMIT_CPU 资源限额，但仍是 best-effort，
  不提供真正的文件系统隔离或网络访问控制；
- Windows 下无 rlimit（_HAS_RLIMIT=False），仅能降优先级 + 限制 CPU 亲和，
  硬内存上限需 Job Object，当前未实现，资源隔离基本无保证。

不要把本模块当作「能安全执行不可信代码」的边界来用——不可信代码仍需在
独立容器 / 虚拟机 / 专用沙箱服务中运行。

支持的执行后端（护栏在上述边界内生效）：
- 本地子进程（Python / JavaScript / Bash）
- 预留对接：Docker/K8s、E2B、Firecrawl 等外部沙箱服务

核心护栏能力：
- 危险命令黑名单 + AST 调用级检查（只拦实际派生进程/外壳/执行任意代码，不拦 import 本身）；覆盖 5 类间接引用（模块别名 / from-import / __import__ / importlib·builtins 动态加载 / 变量别名转手 / sys.modules 动态获取）
- 总超时硬闸（防止传入过大 timeout 卡死）
- 资源限额（POSIX 真实强制；Windows best-effort）
"""

import os
import sys
import ast
import logging
import uuid
import tempfile
import subprocess
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


def _safe_decode(raw) -> str:
    """把子进程输出字节安全地解码为 str（消灭 UnicodeDecodeError）。

    中文 Windows 子进程（cmd / pip / ffmpeg / dir 等）按系统活动代码页
    cp936(GBK) 输出，若按 UTF-8 解码会在 subprocess 读取线程里抛
    UnicodeDecodeError、导致该步拿不到真实 stdout。策略：utf-8 → cp936/gbk
    回落，最后 errors='replace' 兜底，绝不抛异常、且尽量保留中文。
    """
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    for enc in ("utf-8", "cp936", "gbk"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")

# ── 安全边界：危险命令黑名单 ──────────────────────────────────────────────────
# 匹配这些模式的代码/命令将被拒绝执行，防止破坏性操作。
# 这是 defense-in-depth 的一层；上层 API 还有命令白名单。
_DANGEROUS_PATTERNS = [
    "rm -rf",
    "rm -fr",
    "format ",
    "format\t",
    "del /",
    "deltree",
    "shutdown",
    "reboot",
    "halt ",
    "poweroff",
    "mkfs",
    "dd if=",
    ":(){ :|:& };:",   # fork bomb
    "chmod -R 777 /",
    "> /dev/sda",
    "wget|sh",
    "curl|sh",
    "eval(base64",
]

# ── 危险模块 → 危险属性/调用集合（用于 AST 调用级检查）─────────────────────────
# 设计原则：不拦 import 本身（os.path / sys.argv / subprocess 配置等常用且安全），
# 只拦「实际派生进程/外壳」的危险调用。__import__ 直接调用也拦（可加载任意模块）。
# sys 仅登记、无危险属性 → import 与调用均放行。
_DANGER_MODULE_ATTRS = {
    "os": {
        "system", "popen",
        "spawnl", "spawnv", "spawnve", "spawnlpe", "spawnvpe",
        "execv", "execve", "execl", "execlp", "execlpe", "execvp", "execvpe",
        "posix_spawn", "posix_spawnp",
    },
    "subprocess": {
        "Popen", "call", "run", "check_call", "check_output",
        "check_run", "getoutput", "getstatusoutput",
    },
    # 间接引用族：动态加载/获取任意模块对象，可绕过 import 语句派生进程或执行代码
    "importlib": {"import_module"},          # importlib.import_module("os").system(...)
    "builtins": {"__import__"},              # builtins.__import__("os").system(...)
    "sys": {"modules"},                       # sys.modules["os"].system(...)（由 Subscript 检测拦截）
}

# 任意代码执行内置函数（直接调用即危险，不区分参数）
_CODE_EXEC_BUILTINS = ("eval", "exec", "compile")

# ── 资源限额 ────────────────────────────────────────────────────────────────
# 硬上限：防止单次执行卡死。安装/下载类任务需要更长，故放宽到 600s
# （autopilot 的大包下载自带 300s 子超时，这里只是总闸）。
_HARD_TIMEOUT_CAP = 600
_DEFAULT_MEM_LIMIT_MB = 512
_DEFAULT_CPU_SECONDS = 30

# POSIX 下用 resource.setrlimit 做真实的 AS/CPU 限额；Windows 走 best-effort。
try:
    import resource as _resource  # type: ignore
    _HAS_RLIMIT = sys.platform != "win32"
except Exception:  # pragma: no cover - 仅极老平台缺 resource 模块
    _resource = None
    _HAS_RLIMIT = False


def _attr_base(node) -> "str | None":
    """展开 a.b.c 属性链，返回最底层 Name 的 id（如 a.b.c -> 'a'）；非 Name 开头返回 None。"""
    cur = node
    while isinstance(cur, ast.Attribute):
        cur = cur.value
    if isinstance(cur, ast.Name):
        return cur.id
    return None


def _is_sys_modules(node) -> bool:
    """判断 Subscript 是否为 sys.modules[...] 动态模块获取。"""
    v = node.value  # type: ignore[attr-defined]
    return (isinstance(v, ast.Attribute) and isinstance(v.value, ast.Name)
            and v.value.id == "sys" and v.attr == "modules")


def _track_alias_assign(node, danger_mod: dict, danger_names: dict) -> None:
    """记录别名转手 t = os.system / t = mod.danger_attr，使后续 t(...) 也命中危险规则。"""
    if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
        return
    val = node.value
    if not isinstance(val, ast.Attribute):
        return
    base = _attr_base(val)
    if base in _DANGER_MODULE_ATTRS and val.attr in _DANGER_MODULE_ATTRS[base]:
        danger_names[node.targets[0].id] = base
    elif base in danger_mod and val.attr in _DANGER_MODULE_ATTRS[danger_mod[base]]:
        danger_names[node.targets[0].id] = danger_mod[base]


def _check_dangerous_patterns(code: str) -> str | None:
    """检查代码是否包含危险模式。返回匹配的模式字符串，或 None 表示安全。

    护栏范围（defense-in-depth，**非安全边界**）：
    - 黑名单字符串匹配（删库 / 格式化 / fork bomb 等）
    - AST 调用级检查：不拦 import 本身，只拦「实际派生进程 / 外壳 / 执行任意代码」的调用。
      覆盖 5 类间接引用绕过方式：模块别名、from-import 别名、__import__ 直接调用、
      importlib / builtins 动态加载、变量别名转手、sys.modules 动态获取。

    注意：纯 Python 内的删文件 / 偷密钥 / 打网络 / 吃内存载荷本层仍不防护；
    这只是提高手滑门槛，不可信代码必须进容器 / VM / 专用沙箱服务。
    """
    # 黑名单
    code_lower = code.lower()
    for pattern in _DANGEROUS_PATTERNS:
        if pattern.lower() in code_lower:
            return pattern

    try:
        tree = ast.parse(code)
        # 记录导入的「危险模块别名 → 真实模块名」
        danger_mod: dict = {}
        danger_names: dict = {}  # from X import func 或别名转手 → 模块名
        # 第一遍：收集 import 别名 + 变量别名转手（赋值）
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    base = alias.name.split('.')[0]
                    if base in _DANGER_MODULE_ATTRS:
                        danger_mod[alias.asname or base] = base
            elif isinstance(node, ast.ImportFrom):
                mod = (node.module or '').split('.')[0]
                if mod in _DANGER_MODULE_ATTRS:
                    for alias in node.names:
                        if alias.name in _DANGER_MODULE_ATTRS[mod]:
                            danger_names[alias.asname or alias.name] = mod
                        else:
                            danger_mod[alias.asname or alias.name] = mod
            elif isinstance(node, ast.Assign):
                _track_alias_assign(node, danger_mod, danger_names)
        # 第二遍：检查动态模块获取 + 危险调用
        for node in ast.walk(tree):
            # sys.modules[...] 动态获取模块对象（间接引用族）
            if isinstance(node, ast.Subscript) and _is_sys_modules(node):
                return "sys.modules[] dynamic module access"
            if isinstance(node, ast.Call):
                f = node.func
                if isinstance(f, ast.Name):
                    # eval / exec / compile 任意代码执行内置
                    if f.id in _CODE_EXEC_BUILTINS:
                        return f"call {f.id}()"
                    # from os import system; system(...) 或别名转手 f = os.system; f(...)
                    if f.id in danger_names:
                        return f"call {f.id}()"
                    # __import__(...) 直接调用（可加载任意模块并执行任意代码）
                    if f.id == "__import__":
                        return "__import__ call"
                # 模块属性调用：os.system / subprocess.Popen / builtins.__import__ /
                # importlib.import_module（这些直接调用即危险，不等后续 .system()）
                elif isinstance(f, ast.Attribute):
                    base = _attr_base(f)
                    if base in _DANGER_MODULE_ATTRS and f.attr in _DANGER_MODULE_ATTRS[base]:
                        return f"call {base}.{f.attr}()"
                    mod = danger_mod.get(base)
                    if mod and f.attr in _DANGER_MODULE_ATTRS[mod]:
                        return f"call {base}.{f.attr}()"
    except SyntaxError:
        # 非 Python 代码（bash / JS / 纯命令）不能也不该被 ast 解析；
        # 字符串黑名单已足够覆盖危险模式，不把 SyntaxError 当危险误杀。
        pass

    return None


class SandboxManager:
    """沙箱管理器 - 提供安全的代码执行环境"""
    
    def __init__(self):
        self._sandboxes = {}
        self._max_sandboxes = 10
        self._default_timeout = 30
        self._default_memory_limit = "512m"
        self._default_memory_limit_mb = _DEFAULT_MEM_LIMIT_MB
        self._default_cpu_seconds = _DEFAULT_CPU_SECONDS

        logger.info("SandboxManager initialized")

    def create_sandbox(self,
                       name: str = None,
                       timeout: int = None,
                       memory_limit: str = None,
                       memory_limit_mb: int = None,
                       cpu_seconds: int = None,
                       network_access: bool = True) -> Dict[str, Any]:
        """创建新沙箱

        memory_limit_mb: 真实内存上限（MB），POSIX 下经 setrlimit 强制；
                         Windows 下为预留字段（best-effort，见 _apply_win_limits）。
        cpu_seconds:     CPU 时间硬上限（秒），POSIX 下经 setrlimit 强制。
        """
        sandbox_id = str(uuid.uuid4())[:8]
        sandbox_name = name or f"sandbox_{sandbox_id}"

        if len(self._sandboxes) >= self._max_sandboxes:
            return {"success": False, "error": "沙箱数量已达上限"}

        sandbox = {
            "id": sandbox_id,
            "name": sandbox_name,
            "timeout": timeout or self._default_timeout,
            "memory_limit": memory_limit or self._default_memory_limit,
            "memory_limit_mb": memory_limit_mb or self._default_memory_limit_mb,
            "cpu_seconds": cpu_seconds or self._default_cpu_seconds,
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

        # 总闸：不超硬上限，避免请求方传入过大 timeout 卡死
        exec_timeout = min(timeout or sandbox["timeout"], _HARD_TIMEOUT_CAP)
        mem_mb = sandbox.get("memory_limit_mb") or self._default_memory_limit_mb
        cpu_sec = sandbox.get("cpu_seconds") or self._default_cpu_seconds

        try:
            if language.lower() == "python":
                result = self._execute_python(code, exec_timeout, mem_mb, cpu_sec)
            elif language.lower() == "javascript":
                result = self._execute_javascript(code, exec_timeout, mem_mb, cpu_sec)
            elif language.lower() == "bash":
                result = self._execute_bash(code, exec_timeout, mem_mb, cpu_sec)
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
    
    # ── 带资源限额的子进程运行器 ──────────────────────────────────────────────

    def _run_limited(self, cmd, timeout, mem_limit_mb=None, cpu_seconds=None,
                     shell=False):
        """带资源限额运行子进程。

        - POSIX：经 preexec_fn 调 setrlimit 强制 RLIMIT_AS / RLIMIT_CPU（真实限额）
        - Windows：best-effort，启动后用 psutil 降优先级 + 限制 CPU 亲和（见
          _apply_win_limits）；硬内存上限在 Windows 需 Job Object，暂未实现。

        返回 (returncode, stdout, stderr)；returncode 为 None 表示进程根本起不来。
        """
        preexec = None
        if _HAS_RLIMIT:
            def _pre():
                # P4-4 安全修复：原 except: pass 完全静默，若 setrlimit 失败
                # 沙箱限制（内存/CPU）可能没生效但无人知晓。改为记录到 stderr
                # （preexec 在子进程内，不能用主进程 logger；用 os.write 避免异常）。
                try:
                    mb = int(mem_limit_mb or 0)
                    if mb > 0:
                        b = mb * 1024 * 1024
                        _resource.setrlimit(_resource.RLIMIT_AS, (b, b))
                    cs = int(cpu_seconds or 0)
                    if cs > 0:
                        _resource.setrlimit(_resource.RLIMIT_CPU, (cs, cs))
                except Exception as e:
                    # preexec_fn 在子进程执行，不能用主进程 logger。
                    # 写 stderr 让父进程 communicate() 能捕获到告警。
                    import sys as _sys
                    try:
                        _sys.stderr.write(
                            f"[sandbox] WARNING: setrlimit 失败，沙箱限制可能未生效: {e}\n"
                        )
                        _sys.stderr.flush()
                    except Exception:
                        pass  # 连 stderr 都写不了，只能放弃记录
            preexec = _pre

        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                shell=shell, preexec_fn=preexec,
            )
        except (FileNotFoundError, OSError) as e:
            return None, "", str(e)

        if sys.platform == "win32":
            self._apply_win_limits(proc, cpu_seconds)

        try:
            out_b, err_b = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            out_b, err_b = proc.communicate()
            return proc.returncode, _safe_decode(out_b), f"执行超时（>{timeout}s）: " + _safe_decode(err_b)
        return proc.returncode, _safe_decode(out_b), _safe_decode(err_b)

    def _apply_win_limits(self, proc, cpu_seconds) -> None:
        """Windows best-effort 限制：降优先级 + 限制可用核心数（不强制内存上限）。"""
        try:
            import psutil
            p = psutil.Process(proc.pid)
            try:
                p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
            except Exception:
                pass
            try:
                cores = list(range(os.cpu_count() or 1))
                if len(cores) > 1:
                    # 只用约一半核心，避免单任务占满整机
                    p.cpu_affinity(cores[:max(1, len(cores) // 2)])
            except Exception:
                pass
        except Exception:
            pass

    def _execute_python(self, code: str, timeout: int,
                        mem_limit_mb=None, cpu_seconds=None) -> Dict[str, Any]:
        """执行Python代码"""
        import time

        # 安全边界：危险模式黑名单检查
        matched = _check_dangerous_patterns(code)
        if matched:
            logger.warning("sandbox 拒绝危险 Python 代码: pattern=%r, code=%.120s", matched, code)
            return {"success": False, "error": f"Blocked: code contains dangerous pattern '{matched}'"}

        logger.info("sandbox 执行 Python 代码: timeout=%ds, mem=%sMB, code=%.200s",
                    timeout, mem_limit_mb, code)

        start_time = time.time()

        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False,
                                          encoding='utf-8') as f:
            f.write(code)
            temp_file = f.name

        try:
            rc, out, err = self._run_limited(
                [sys.executable, temp_file], timeout, mem_limit_mb, cpu_seconds)
            if rc is None:
                return {"success": False, "error": err, "duration": round(time.time() - start_time, 2)}
            duration = time.time() - start_time
            if rc == 0:
                return {"success": True, "output": out, "duration": round(duration, 2)}
            return {"success": False, "error": err, "duration": round(duration, 2)}
        finally:
            os.unlink(temp_file)
    
    def _execute_javascript(self, code: str, timeout: int,
                             mem_limit_mb=None, cpu_seconds=None) -> Dict[str, Any]:
        """执行JavaScript代码"""
        import time

        # 安全边界：危险模式黑名单检查
        matched = _check_dangerous_patterns(code)
        if matched:
            logger.warning("sandbox 拒绝危险 JavaScript 代码: pattern=%r, code=%.120s", matched, code)
            return {"success": False, "error": f"Blocked: code contains dangerous pattern '{matched}'"}

        logger.info("sandbox 执行 JavaScript 代码: timeout=%ds, mem=%sMB, code=%.200s",
                    timeout, mem_limit_mb, code)

        start_time = time.time()

        with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False,
                                          encoding='utf-8') as f:
            f.write(code)
            temp_file = f.name

        try:
            rc, out, err = self._run_limited(
                ["node", temp_file], timeout, mem_limit_mb, cpu_seconds)
            if rc is None:
                return {"success": False, "error": err, "duration": round(time.time() - start_time, 2)}
            duration = time.time() - start_time
            if rc == 0:
                return {"success": True, "output": out, "duration": round(duration, 2)}
            return {"success": False, "error": err, "duration": round(duration, 2)}
        finally:
            os.unlink(temp_file)
    
    def _execute_bash(self, code: str, timeout: int,
                      mem_limit_mb=None, cpu_seconds=None) -> Dict[str, Any]:
        """执行Bash命令"""
        import time

        # 安全边界：危险模式黑名单检查
        matched = _check_dangerous_patterns(code)
        if matched:
            logger.warning("sandbox 拒绝危险 Bash 命令: pattern=%r, code=%.120s", matched, code)
            return {"success": False, "error": f"Blocked: code contains dangerous pattern '{matched}'"}

        logger.info("sandbox 执行 Bash 命令: timeout=%ds, mem=%sMB, code=%.200s",
                    timeout, mem_limit_mb, code)

        start_time = time.time()

        if sys.platform == "win32":
            # cmd /c 优先：winget / choco / pip / npm 等是 Windows 原生命令，
            # cmd 能正确解析 Windows App Execution Alias（如 WindowsApps 里的
            # winget.exe）；而 Git Bash / WSL 不解析这些别名，会报
            # "command not found"。仅当 cmd 报「命令未找到」类错误（疑似真正的
            # unix shell 命令）时才回落 bash -c。
            last = None  # (rc, out, err)
            for args in (["cmd", "/c", code], ["bash", "-c", code]):
                rc, out, err = self._run_limited(args, timeout, mem_limit_mb, cpu_seconds)
                if rc is None:
                    last = (1, "", err)
                    continue
                if rc == 0:
                    last = (rc, out, err)
                    break
                e = (err or "").lower()
                # 命令未找到 → 换解释器再试；其余真实错误（权限/参数/网络）不再重试
                if "not recognized" in e or "command not found" in e or "no such file" in e:
                    last = (rc, out, err)
                    continue
                last = (rc, out, err)
                break
            if last is None or last[0] is None:
                return {"success": False,
                        "error": "没有可用的 shell 执行器（cmd / bash 均不可用）",
                        "duration": round(time.time() - start_time, 2)}
            rc, out, err = last
        else:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False,
                                              encoding='utf-8') as f:
                f.write(code)
                temp_file = f.name
            try:
                os.chmod(temp_file, 0o755)
                rc, out, err = self._run_limited(
                    [temp_file], timeout, mem_limit_mb, cpu_seconds)
            finally:
                try:
                    os.unlink(temp_file)
                except OSError:
                    pass
            if rc is None:
                return {"success": False, "error": err,
                        "duration": round(time.time() - start_time, 2)}

        duration = time.time() - start_time
        if rc == 0:
            return {"success": True, "output": out, "duration": round(duration, 2)}
        return {"success": False,
                "error": (err or out or "命令执行失败，无 stderr 输出"),
                "duration": round(duration, 2)}
    
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
