"""A 股数据源适配器使用的进程内运行期缓存。"""

from __future__ import annotations

from collections import OrderedDict
import logging
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

_RUN_CACHE_TTL_SECONDS = 300.0
_RUN_CACHE_MAX_ENTRIES = 128
_run_cache: OrderedDict[str, tuple[float, Any]] = OrderedDict()
_run_cache_lock = threading.RLock()
_cache_key_locks: dict[str, threading.Lock] = {}
_warning_keys: set[str] = set()


def _cached(key: str, factory, *args) -> Any:
    """为昂贵的外部请求返回短生命周期缓存结果。"""
    now = time.monotonic()
    with _run_cache_lock:
        cached = _run_cache.get(key)
        if cached is not None:
            created_at, value = cached
            if now - created_at < _RUN_CACHE_TTL_SECONDS:
                _run_cache.move_to_end(key)
                return value
            del _run_cache[key]
        key_lock = _cache_key_locks.setdefault(key, threading.Lock())

    # 仅串行化相同 key 的请求，互不相关的数据源仍可并行执行。
    with key_lock:
        now = time.monotonic()
        with _run_cache_lock:
            cached = _run_cache.get(key)
            if cached is not None:
                created_at, value = cached
                if now - created_at < _RUN_CACHE_TTL_SECONDS:
                    _run_cache.move_to_end(key)
                    return value
                del _run_cache[key]

        value = factory(*args)
        with _run_cache_lock:
            _run_cache[key] = (time.monotonic(), value)
            _run_cache.move_to_end(key)
            while len(_run_cache) > _RUN_CACHE_MAX_ENTRIES:
                _run_cache.popitem(last=False)
        return value


def _clear_runtime_cache() -> None:
    """清理进程内缓存，主要用于确定性测试。"""
    with _run_cache_lock:
        _run_cache.clear()
        _cache_key_locks.clear()


def _warning_once(key: str, message: str, *args) -> None:
    """同类外部数据源故障只告警一次，后续保留在 debug 日志。"""
    with _run_cache_lock:
        if key in _warning_keys:
            logger.debug(message, *args)
            return
        _warning_keys.add(key)
    logger.warning(message, *args)


def _info_once(key: str, message: str, *args) -> None:
    """成功回退日志只记录一次，重复信息降级为 debug。"""
    with _run_cache_lock:
        if key in _warning_keys:
            logger.debug(message, *args)
            return
        _warning_keys.add(key)
    logger.info(message, *args)
