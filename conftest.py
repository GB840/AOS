"""
AOS 根 conftest —— 仅用于让 pytest 进程能干净退出。

问题背景：AOS 在 import / conftest 阶段会初始化一批重型 adapter
（MiniCPM 本地服务探活、MCP stdio 子进程、posthog telemetry 等），
这些组件会启动**非守护后台线程**。pytest 跑完所有测试进入退出阶段后，
Python 主线程会一直等待这些非守护线程结束，导致进程卡死、被 CI / 外层
`timeout` 杀掉；pytest-cov 的覆盖率报告与 .coverage 数据因此丢失。

关键点：pytest-cov 与 junitxml 都在 `sessionfinish` 阶段（进程仍存活时）
完成写盘。卡死发生在 `sessionfinish`**之后**的退出等待。因此只要在
`pytest_unconfigure`（sessionfinish 之后、进程退出之前）强制 `os._exit`，
cov 数据与报告都已落盘，且进程不再挂起。

默认关闭：仅当 `AOS_FORCE_EXIT=1` 时才强制退出，日常 `pytest` 不受影响。
"""
import os
import socket
import sys
import time
import urllib.request
import urllib.error

# 阻止 trio 导入：httpcore 会尝试 import trio（TrioBackend），而 trio 的
# import 扫描 sys.path 时会触发 _path_stat 命中沙箱限制路径，导致整个进程
# HANG。设 sys.modules['trio']=None 让 Python 认为 trio 不存在，httpcore
# 会优雅降级到 sync backend。
sys.modules.setdefault("trio", None)


def pytest_configure(config):
    # ── socket.create_connection 全局短超时 ──
    # Windows 上 socket.connect() 到不可达地址常忽略调用方传入的 timeout，
    # 导致 httpx / openai SDK / requests / urllib 全部 HANG（pytest-timeout 对
    # C 层阻塞无效）。在 socket.create_connection 层强制上限 3 秒，
    # 覆盖所有上层网络库（httpx、requests、urllib3、openai 等）。
    _orig_create_connection = socket.create_connection
    _SENTINEL = socket._GLOBAL_DEFAULT_TIMEOUT

    def _patched_create_connection(address, *args, **kwargs):
        # 提取当前 timeout（位置参数或关键字参数）
        if len(args) >= 1:
            t = args[0]
        else:
            t = kwargs.get("timeout", _SENTINEL)
        # 强制上限 3 秒：None / _GLOBAL_DEFAULT_TIMEOUT / >3 全部改成 3
        if t is None or t is _SENTINEL or (isinstance(t, (int, float)) and t > 3):
            if len(args) >= 1:
                args = (3,) + args[1:]
            else:
                kwargs["timeout"] = 3
        return _orig_create_connection(address, *args, **kwargs)

    socket.create_connection = _patched_create_connection

    # 测试环境无本地 GPU/服务（MiniCPM / OpenClaw / MCP 等），这些 adapter 的
    # health_detail 会对 localhost 发起 urlopen 探活。Windows 上 socket.connect
    # 到不可达端口常忽略 urlopen 的 timeout 参数而长时间 hang，拖垮整个 pytest
    # 套件（pytest-timeout 在 Windows 上对 C 层阻塞无效）。
    # 让 localhost 探活在测试环境立即失败，避免挂起（生产运行时不受影响）。
    _orig_urlopen = urllib.request.urlopen

    def _patched_urlopen(url, *args, **kwargs):
        target = url if isinstance(url, str) else getattr(url, "get_full_url", lambda: "")()
        if "localhost" in target or "127.0.0.1" in target:
            raise urllib.error.URLError("test-env: no local service")
        return _orig_urlopen(url, *args, **kwargs)

    urllib.request.urlopen = _patched_urlopen

    # 同理 patch requests.get / requests.post —— comfyui_adapter / ollama_gateway
    # 等适配器用 requests 库做 health 探活（走 urllib3 而非 urllib.request，
    # 上面的 urlopen patch 管不到）。mock.patch 仍然能正常工作：patch 保存的
    # "original" 是这里的 _patched_get，测试结束后会恢复回 _patched_get。
    try:
        import requests as _requests
        _orig_get = _requests.get
        _orig_post = _requests.post

        def _patched_get(url, *args, **kwargs):
            target = str(url) if url else ""
            if "localhost" in target or "127.0.0.1" in target:
                raise _requests.ConnectionError("test-env: no local service")
            return _orig_get(url, *args, **kwargs)

        def _patched_post(url, *args, **kwargs):
            target = str(url) if url else ""
            if "localhost" in target or "127.0.0.1" in target:
                raise _requests.ConnectionError("test-env: no local service")
            return _orig_post(url, *args, **kwargs)

        _requests.get = _patched_get
        _requests.post = _patched_post
    except ImportError:
        pass

    # 外部 SDK（OpenAI 等）在鉴权失败时会做指数退避 time.sleep，且 sleep 常发生在
    # 子线程里，pytest-timeout 在 Windows 上对跨线程阻塞无效，导致套件挂死。
    # 测试环境把超长 sleep 压缩到 20ms，让重试快速失败而非挂起。
    _orig_sleep = time.sleep

    def _fast_sleep(sec, *a, **k):
        try:
            s = float(sec)
        except (TypeError, ValueError):
            return _orig_sleep(sec, *a, **k)
        if s > 0.5:
            return _orig_sleep(0.02, *a, **k)
        return _orig_sleep(s, *a, **k)

    time.sleep = _fast_sleep


def pytest_unconfigure(config):
    if os.environ.get("AOS_FORCE_EXIT") == "1":
        # cov / junit 已在 sessionfinish 写盘，此处跳过等待后台线程直接退出。
        os._exit(0)
