'''统一运行时守卫设施 (Runtime Resilience — L1 of the AOS stability system).

背景与动机
----------
本仓库历史上反复出现「某个外部依赖在 import / 初始化时卡死或崩溃，拖垮整条
import 链 (import kernel.wiring -> FabricHub -> 所有适配器) 甚至整个测试套件」：

  * ag2 / autogen 在某些环境 import 会**卡死**（阻塞、非异常，except 抓不住）；
  * litellm -> tokenizers、zvec -> rocksdb 原生扩展在沙箱负载下偶发卡死 / 崩溃；
  * 散落在各适配器的 `try: import / except` 只能防「导入报错」，防不住「导入卡死」。

本模块提供**单一、统一**的守卫原语，让任何一个依赖出问题都只影响自身、整系统
照常存活。它是「完整稳定系统」的 L1 基座。

原语
----
  * guarded_import(name, timeout): 超时线程守卫导入，卡死/失败返回 None；
  * SafeImport: 模块级懒加载描述符，首次访问才触发 guarded_import，永不阻塞；
  * degrade(name, reason): 统一降级标记（仅观测，便于看板）。

本模块**自身零依赖、零阻塞**：只用 stdlib，导入它不可能卡死。
'''
from __future__ import annotations

import importlib
import logging
import threading
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 20.0
# 分级超时：重型依赖（autogen/ag2 导入极慢，实测 80s+）给足时间，
# 其余按经验值设定。配合 prewarm() 后台预热，避免 health/初始化被卡死。
_MODULE_TIMEOUTS: dict = {
    "autogen": 180.0, "ag2": 180.0,
    "litellm": 30.0,
    "mem0ai": 40.0, "mem0": 40.0,
}
_PROBED: dict = {}  # name -> module | None (缓存，避免重复探测)
_WARMING: set = set()  # 正在后台预热中的模块名
# P2 并发修复：_PROBED / _WARMING 的 check-then-act 无锁，并发首调会各自
# 启动 daemon 线程跑 importlib（虽然 Python import 锁保证只执行一次模块体，
# 但 _PROBED 赋值仍可能被覆盖为 None 而非真实模块）。锁保护缓存写入。
_PROBE_LOCK = threading.Lock()


def guarded_import(name: str, timeout: Optional[float] = None) -> Optional[Any]:
    '''超时线程守卫导入。

    用 daemon 线程跑 ``importlib.import_module(name)``，主线程 ``join(timeout)``：
      * 线程在 timeout 内返回 -> 返回模块（import 异常视为不可用 -> None）；
      * 线程仍存活（卡死）-> 放弃，返回 None，**绝不阻塞调用方**；
      * 缓存结果，重复调用不再探测。

    超时取值优先级：显式参数 > 分级表 ``_MODULE_TIMEOUTS`` > ``_DEFAULT_TIMEOUT``。
    预热中（``_WARMING``）直接返回 None：避免与 prewarm 后台线程重复 import
    同一模块（Python import 锁会阻塞等待首个线程），让 health 如实标 dead，
    预热线程完成后再标 live，全程不卡调用方。
    '''
    # 快速路径：已探测过直接返回（读 dict 在 GIL 下原子）
    if name in _PROBED:
        return _PROBED[name]
    # 预热中：让 health 如实标 dead
    if name in _WARMING:
        return None
    to = timeout if timeout is not None else _MODULE_TIMEOUTS.get(name, _DEFAULT_TIMEOUT)
    box: dict = {}

    def _run() -> None:
        try:
            box['m'] = importlib.import_module(name)
        except Exception:  # noqa: BLE001 - 任一导入异常 = 该依赖不可用
            box['err'] = True

    th = threading.Thread(target=_run, daemon=True)
    th.start()
    th.join(to)
    if th.is_alive() or 'err' in box:
        logger.warning('guarded_import: %s unavailable (timeout=%.1fs)', name, to)
        with _PROBE_LOCK:
            _PROBED[name] = None
        return None
    mod = box.get('m')
    with _PROBE_LOCK:
        _PROBED[name] = mod
    return mod


class SafeImport:
    '''模块级懒加载描述符：访问属性才 guarded_import，永不阻塞。

    用法::

        class Foo:
            litellm = SafeImport('litellm')

        Foo().litellm   # 首次访问才导入；之后缓存；失败返回 None
    '''

    def __init__(self, module_name: str, timeout: float = _DEFAULT_TIMEOUT) -> None:
        self._name = module_name
        self._timeout = timeout
        self._attr: Optional[str] = None

    def __set_name__(self, owner: type, name: str) -> None:
        self._attr = name

    def __get__(self, instance: Any, owner: type) -> Optional[Any]:
        if instance is None:
            return self  # 类属性访问返回描述符自身，不影响类
        key = '_safeimport_' + (self._attr or '')
        cache = instance.__dict__
        if key not in cache:
            cache[key] = guarded_import(self._name, self._timeout)
        return cache[key]


_DEGRADED: dict = {}


def degrade(name: str, reason: str = '') -> None:
    '''统一降级标记（仅观测，不抛异常）。'''
    _DEGRADED[name] = reason or 'unavailable'
    logger.warning('degrade: %s -> %s', name, _DEGRADED[name])


def is_degraded(name: str) -> bool:
    return name in _DEGRADED


def prewarm(names: Iterable[str]) -> None:
    '''后台线程批量预热重依赖，结果缓存到 _PROBED。

    典型用途：FabricHub.__init__ 末尾 prewarm(["autogen","litellm","mem0ai"])
    让 autogen(80s)/litellm(22s) 在后台慢慢 import，不阻塞初始化与 health。
    预热期间 guarded_import 命中 _WARMING 直接返回 None（不重复 import 阻塞）。
    '''
    for name in names:
        if name in _PROBED or name in _WARMING:
            continue
        _WARMING.add(name)

        def _run(n: str = name) -> None:
            try:
                _PROBED[n] = importlib.import_module(n)
            except Exception:  # noqa: BLE001 - 预热失败 = 该依赖不可用
                _PROBED[n] = None
            finally:
                _WARMING.discard(n)

        threading.Thread(target=_run, daemon=True).start()


def is_warming(name: str) -> bool:
    '''模块是否正在后台预热中（尚未完成首次 import）。'''
    return name in _WARMING


def clear_caches() -> None:
    '''仅供测试隔离使用：清空探测与降级缓存。'''
    _PROBED.clear()
    _DEGRADED.clear()
    _WARMING.clear()
