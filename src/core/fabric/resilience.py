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
from typing import Any, Optional

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 8.0
_PROBED: dict = {}  # name -> module | None (缓存，避免重复探测)


def guarded_import(name: str, timeout: float = _DEFAULT_TIMEOUT) -> Optional[Any]:
    '''超时线程守卫导入。

    用 daemon 线程跑 ``importlib.import_module(name)``，主线程 ``join(timeout)``：
      * 线程在 timeout 内返回 -> 返回模块（import 异常视为不可用 -> None）；
      * 线程仍存活（卡死）-> 放弃，返回 None，**绝不阻塞调用方**；
      * 缓存结果，重复调用不再探测。

    这是「卡死抓不住」问题的唯一可靠解法：except 抓不住阻塞，但 join 超时能。
    '''
    if name in _PROBED:
        return _PROBED[name]
    box: dict = {}

    def _run() -> None:
        try:
            box['m'] = importlib.import_module(name)
        except Exception:  # noqa: BLE001 - 任一导入异常 = 该依赖不可用
            box['err'] = True

    th = threading.Thread(target=_run, daemon=True)
    th.start()
    th.join(timeout)
    if th.is_alive() or 'err' in box:
        logger.warning('guarded_import: %s unavailable (timeout=%.1fs)', name, timeout)
        _PROBED[name] = None
        return None
    _PROBED[name] = box.get('m')
    return _PROBED[name]


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


def clear_caches() -> None:
    '''仅供测试隔离使用：清空探测与降级缓存。'''
    _PROBED.clear()
    _DEGRADED.clear()
