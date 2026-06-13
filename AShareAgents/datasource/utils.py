"""数据源通用工具模块。

提供股票代码安全校验、数据保存、日期处理等工具函数。
"""

import os
import re
import json
import logging
import pandas as pd
from datetime import date, timedelta, datetime
from typing import Annotated

logger = logging.getLogger(__name__)

SavePathType = Annotated[str, "数据保存路径。为 None 时不保存。"]

# 股票代码可包含字母、数字、点号、破折号、下划线和尖号
# （用于指数代码如 ^GSPC）。其余字符将被拒绝，
# 防止在路径拼接时跳出目标目录。
_TICKER_PATH_RE = re.compile(r"^[A-Za-z0-9._\-\^]+$")
_HAS_CHINESE_RE = re.compile(r"[一-鿿]")


def safe_ticker_component(value: str, *, max_len: int = 32) -> str:
    """校验 ``value`` 是否可安全用于文件系统路径拼接。

    如果值包含中文字符（常见于LLM返回股票名称而非代码时），
    会通过 ``resolve_ticker`` 自动解析为6位A股代码后再校验。

    Args:
        value: 待校验的股票代码或名称
        max_len: 最大允许字符数

    Returns:
        校验通过的原始值

    Raises:
        ValueError: 值不符合安全规则时抛出
    """
    if not isinstance(value, str) or not value:
        raise ValueError(f"股票代码必须是非空字符串，实际为 {value!r}")

    if _HAS_CHINESE_RE.search(value):
        from AShareAgents.datasource.astock.a_stock import resolve_ticker
        resolved = resolve_ticker(value)
        logger.info("自动解析中文股票名称 %r -> %s", value, resolved)
        value = resolved

    if len(value) > max_len:
        raise ValueError(f"股票代码超过 {max_len} 个字符: {value!r}")
    if not _TICKER_PATH_RE.fullmatch(value):
        raise ValueError(
            f"股票代码包含文件系统路径中不允许的字符: {value!r}"
        )
    if set(value) == {"."}:
        raise ValueError(f"股票代码不能仅由点号组成: {value!r}")
    return value


def save_output(data: pd.DataFrame, tag: str, save_path: SavePathType = None) -> None:
    """将DataFrame保存到CSV文件。"""
    if save_path:
        data.to_csv(save_path, encoding="utf-8")
        logger.debug("%s 已保存至 %s", tag, save_path)


def get_current_date():
    """获取当前日期字符串，格式为YYYY-MM-DD。"""
    return date.today().strftime("%Y-%m-%d")


def decorate_all_methods(decorator):
    """装饰器：将类中所有可调用方法应用指定装饰器。"""
    def class_decorator(cls):
        for attr_name, attr_value in cls.__dict__.items():
            if callable(attr_value):
                setattr(cls, attr_name, decorator(attr_value))
        return cls

    return class_decorator


def get_next_weekday(date):
    """若给定日期为周末，则返回下一个工作日；否则返回原日期。"""
    if not isinstance(date, datetime):
        date = datetime.strptime(date, "%Y-%m-%d")

    if date.weekday() >= 5:
        days_to_add = 7 - date.weekday()
        next_weekday = date + timedelta(days=days_to_add)
        return next_weekday
    else:
        return date
