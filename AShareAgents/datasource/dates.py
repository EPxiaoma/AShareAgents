"""数据源适配器共享的日期辅助函数。"""

from __future__ import annotations

from datetime import date, datetime, timedelta


def get_current_date() -> str:
    """返回 YYYY-MM-DD 格式的今天日期。"""
    return date.today().strftime("%Y-%m-%d")


def get_next_weekday(value):
    """当 ``value`` 落在周末时返回下一个工作日。"""
    if not isinstance(value, datetime):
        value = datetime.strptime(value, "%Y-%m-%d")

    if value.weekday() >= 5:
        return value + timedelta(days=7 - value.weekday())
    return value
