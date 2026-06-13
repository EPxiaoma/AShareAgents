"""向 Agent 暴露公司新闻、全球新闻和内部人交易工具。"""

from langchain_core.tools import tool
from typing import Annotated
from AShareAgents.datasource.interface import route_to_vendor

@tool
def get_news(
    ticker: Annotated[str, "6位A股代码（如 600379）。必须是数字代码，不能是公司名称或中文"],
    start_date: Annotated[str, "开始日期，格式 yyyy-mm-dd"],
    end_date: Annotated[str, "结束日期，格式 yyyy-mm-dd"],
) -> str:
    """
    获取指定股票代码的新闻数据。
    使用已配置的 news_data 供应商。
    Args:
        ticker (str): 6位A股代码，如 600379、300750。必须是数字代码，不能是公司名称。
        start_date (str): 开始日期，格式 yyyy-mm-dd
        end_date (str): 结束日期，格式 yyyy-mm-dd
    Returns:
        str: 包含新闻数据的格式化字符串
    """
    return route_to_vendor("get_news", ticker, start_date, end_date)

@tool
def get_global_news(
    curr_date: Annotated[str, "当前日期，格式 yyyy-mm-dd"],
    look_back_days: Annotated[int, "回看天数"] = 7,
    limit: Annotated[int, "最多返回的文章数"] = 5,
) -> str:
    """
    获取全球新闻数据。
    使用已配置的 news_data 供应商。
    Args:
        curr_date (str): 当前日期，格式 yyyy-mm-dd
        look_back_days (int): 回看天数（默认 7）
        limit (int): 最多返回的文章数（默认 5）
    Returns:
        str: 包含全球新闻数据的格式化字符串
    """
    return route_to_vendor("get_global_news", curr_date, look_back_days, limit)

@tool
def get_insider_transactions(
    ticker: Annotated[str, "6位A股代码（如 600379）。必须是数字代码，不能是公司名称"],
) -> str:
    """
    获取公司的内部人交易信息。
    使用已配置的 news_data 供应商。
    Args:
        ticker (str): 6位A股代码，如 600379
    Returns:
        str: 内部人交易数据报告
    """
    return route_to_vendor("get_insider_transactions", ticker)
