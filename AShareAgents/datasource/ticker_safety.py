"""数据源缓存和文件路径使用的股票代码校验工具。"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_TICKER_PATH_RE = re.compile(r"^[A-Za-z0-9._\-\^]+$")
_HAS_CHINESE_RE = re.compile(r"[\u4e00-\u9fff]")


def safe_ticker_component(value: str, *, max_len: int = 32) -> str:
    """校验 ``value`` 是否能安全作为文件路径片段使用。"""
    if not isinstance(value, str) or not value:
        raise ValueError(f"股票代码必须是非空字符串，实际为 {value!r}")

    if _HAS_CHINESE_RE.search(value):
        from AShareAgents.datasource.astock.a_stock import resolve_ticker

        resolved = resolve_ticker(value)
        logger.info("已将中文股票名称 %r 解析为 %s", value, resolved)
        value = resolved

    if len(value) > max_len:
        raise ValueError(f"股票代码超过 {max_len} 个字符: {value!r}")
    if not _TICKER_PATH_RE.fullmatch(value):
        raise ValueError(f"股票代码包含文件路径不安全字符: {value!r}")
    if set(value) == {"."}:
        raise ValueError(f"股票代码不能只由点号组成: {value!r}")
    return value
