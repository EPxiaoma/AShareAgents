"""A 股数据源适配器门面。

具体实现已按业务能力拆分，便于行情、基本面、新闻、信号和事件适配器独立维护。
"""

from __future__ import annotations

from typing import Annotated

from .cache import _cached, _clear_runtime_cache, _warning_once
from .events import (
    get_dragon_tiger_board as _get_dragon_tiger_board,
    get_industry_comparison as _get_industry_comparison,
    get_lockup_expiry as _get_lockup_expiry,
)
from .fundamentals import (
    get_balance_sheet,
    get_cashflow,
    get_fundamentals,
    get_income_statement,
    get_insider_transactions,
)
from .market import get_indicators, get_stock_data
from .news import (
    fetch_eastmoney_company_news as _news_fetch_eastmoney,
    fetch_sina_company_news as _news_fetch_sina,
    get_company_news as _get_company_news,
    get_global_news as _aggregate_global_news,
)
from .signals import (
    get_concept_blocks,
    get_fund_flow,
    get_hot_stocks,
    get_northbound_flow,
    get_profit_forecast,
)
from .symbols import _normalize_ticker, resolve_ticker


def _fetch_news_eastmoney(code: str, page_size: int = 20) -> list[dict]:
    """东方财富新闻适配器的兼容包装。"""
    return _news_fetch_eastmoney(code, page_size)


def _fetch_news_sina(code: str, page_size: int = 20) -> list[dict]:
    """新浪新闻适配器的兼容包装。"""
    return _news_fetch_sina(code, page_size)


def get_news(
    ticker: Annotated[str, "A 股代码"],
    start_date: Annotated[str, "起始日期，格式 yyyy-mm-dd"],
    end_date: Annotated[str, "结束日期，格式 yyyy-mm-dd"],
) -> str:
    """规范化 A 股代码后返回公司新闻。"""
    return _get_company_news(_normalize_ticker(ticker), start_date, end_date)


def get_global_news(
    curr_date: Annotated[str, "当前日期，格式 yyyy-mm-dd"],
    look_back_days: Annotated[int, "回看天数"] = 7,
    limit: Annotated[int, "最多文章数"] = 10,
) -> str:
    """使用共享运行期缓存返回全球财经新闻。"""
    return _cached(
        f"global_news:{curr_date}:{look_back_days}:{limit}",
        _get_global_news_impl,
        curr_date,
        look_back_days,
        limit,
    )


def _get_global_news_impl(curr_date: str, look_back_days: int, limit: int) -> str:
    """执行不带缓存的全球新闻聚合。"""
    return _aggregate_global_news(
        curr_date,
        look_back_days,
        limit,
        warning_once=_warning_once,
    )


def get_dragon_tiger_board(
    ticker: str,
    trade_date: str,
    look_back_days: int = 30,
) -> str:
    """返回近期龙虎榜记录、席位明细和机构动向。"""
    return _cached(
        f"dragon-tiger:{ticker}:{trade_date}:{look_back_days}",
        _get_dragon_tiger_board,
        ticker,
        trade_date,
        look_back_days,
    )


def get_lockup_expiry(
    ticker: str,
    trade_date: str,
    forward_days: int = 90,
) -> str:
    """返回历史和未来限售解禁安排。"""
    return _cached(
        f"lockup:{ticker}:{trade_date}:{forward_days}",
        _get_lockup_expiry,
        ticker,
        trade_date,
        forward_days,
    )


def get_industry_comparison(
    ticker: str,
    trade_date: str,
    top_n: int = 20,
) -> str:
    """返回东方财富行业表现排名。"""
    return _cached(
        f"industry:{ticker}:{trade_date}:{top_n}",
        _get_industry_comparison,
        ticker,
        trade_date,
        top_n,
    )


__all__ = [
    "_clear_runtime_cache",
    "_fetch_news_eastmoney",
    "_fetch_news_sina",
    "resolve_ticker",
    "get_stock_data",
    "get_indicators",
    "get_fundamentals",
    "get_balance_sheet",
    "get_cashflow",
    "get_income_statement",
    "get_news",
    "get_global_news",
    "get_insider_transactions",
    "get_profit_forecast",
    "get_hot_stocks",
    "get_northbound_flow",
    "get_concept_blocks",
    "get_fund_flow",
    "get_dragon_tiger_board",
    "get_lockup_expiry",
    "get_industry_comparison",
]
