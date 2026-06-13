"""向 Agent 暴露技术指标查询工具。"""

from langchain_core.tools import tool
from typing import Annotated
from AShareAgents.datasource.interface import route_to_vendor

@tool
def get_indicators(
    symbol: Annotated[str, "6位A股代码（如 600379）。必须是数字代码，不能是公司名称或中文"],
    indicator: Annotated[str, "需要获取分析与报告的技术指标名称"],
    curr_date: Annotated[str, "当前交易日期，格式 YYYY-mm-dd"],
    look_back_days: Annotated[int, "回看天数"] = 30,
) -> str:
    """
    获取指定股票代码的单个技术指标。
    使用已配置的 technical_indicators 供应商。
    Args:
        symbol (str): 6位A股代码，如 600379、300750。必须是数字代码，不能是公司名称。
        indicator (str): 单个技术指标名称，如 'rsi'、'macd'。每次调用只传一个指标。
        curr_date (str): 当前交易日期，格式 YYYY-mm-dd
        look_back_days (int): 回看天数，默认 30
    Returns:
        str: 包含指定股票代码和指标的技术指标格式化 DataFrame。
    """
    # LLM 有时会把多个指标用逗号分隔传进来；
    # 将字符串拆分并逐个处理。
    indicators = [i.strip().lower() for i in indicator.split(",") if i.strip()]
    results = []
    for ind in indicators:
        try:
            results.append(route_to_vendor("get_indicators", symbol, ind, curr_date, look_back_days))
        except ValueError as e:
            results.append(str(e))
    return "\n\n".join(results)
