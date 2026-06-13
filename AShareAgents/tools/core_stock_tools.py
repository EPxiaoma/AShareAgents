from langchain_core.tools import tool
from typing import Annotated
from AShareAgents.datasource.interface import route_to_vendor


@tool
def get_stock_data(
    symbol: Annotated[str, "6位A股代码（如 600379）。必须是数字代码，不能是公司名称或中文"],
    start_date: Annotated[str, "开始日期，格式 yyyy-mm-dd"],
    end_date: Annotated[str, "结束日期，格式 yyyy-mm-dd"],
) -> str:
    """
    获取指定股票代码的股价数据（OHLCV）。
    使用已配置的 core_stock_apis 供应商。
    Args:
        symbol (str): 6位A股代码，如 600379、300750。必须是数字代码，不能是公司名称。
        start_date (str): 开始日期，格式 yyyy-mm-dd
        end_date (str): 结束日期，格式 yyyy-mm-dd
    Returns:
        str: 包含指定日期范围内股票价格数据的格式化 DataFrame。
    """
    return route_to_vendor("get_stock_data", symbol, start_date, end_date)
