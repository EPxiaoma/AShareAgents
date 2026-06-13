from langchain_core.tools import tool
from typing import Annotated
from AShareAgents.datasource.interface import route_to_vendor


@tool
def get_fundamentals(
    ticker: Annotated[str, "6位A股代码（如 600379）。必须是数字代码，不能是公司名称"],
    curr_date: Annotated[str, "当前交易日期，格式 yyyy-mm-dd"],
) -> str:
    """
    获取指定股票代码的全面基本面数据。
    使用已配置的 fundamental_data 供应商。
    Args:
        ticker (str): 公司股票代码
        curr_date (str): 当前交易日期，格式 yyyy-mm-dd
    Returns:
        str: 包含全面基本面数据的格式化报告
    """
    return route_to_vendor("get_fundamentals", ticker, curr_date)


@tool
def get_balance_sheet(
    ticker: Annotated[str, "6位A股代码（如 600379）。必须是数字代码，不能是公司名称"],
    freq: Annotated[str, "报告频率：annual/quarterly"] = "quarterly",
    curr_date: Annotated[str, "当前交易日期，格式 yyyy-mm-dd"] = None,
) -> str:
    """
    获取指定股票代码的资产负债表数据。
    使用已配置的 fundamental_data 供应商。
    Args:
        ticker (str): 公司股票代码
        freq (str): 报告频率：annual/quarterly（默认 quarterly）
        curr_date (str): 当前交易日期，格式 yyyy-mm-dd
    Returns:
        str: 包含资产负债表数据的格式化报告
    """
    return route_to_vendor("get_balance_sheet", ticker, freq, curr_date)


@tool
def get_cashflow(
    ticker: Annotated[str, "6位A股代码（如 600379）。必须是数字代码，不能是公司名称"],
    freq: Annotated[str, "报告频率：annual/quarterly"] = "quarterly",
    curr_date: Annotated[str, "当前交易日期，格式 yyyy-mm-dd"] = None,
) -> str:
    """
    获取指定股票代码的现金流量表数据。
    使用已配置的 fundamental_data 供应商。
    Args:
        ticker (str): 公司股票代码
        freq (str): 报告频率：annual/quarterly（默认 quarterly）
        curr_date (str): 当前交易日期，格式 yyyy-mm-dd
    Returns:
        str: 包含现金流量表数据的格式化报告
    """
    return route_to_vendor("get_cashflow", ticker, freq, curr_date)


@tool
def get_income_statement(
    ticker: Annotated[str, "6位A股代码（如 600379）。必须是数字代码，不能是公司名称"],
    freq: Annotated[str, "报告频率：annual/quarterly"] = "quarterly",
    curr_date: Annotated[str, "当前交易日期，格式 yyyy-mm-dd"] = None,
) -> str:
    """
    获取指定股票代码的利润表数据。
    使用已配置的 fundamental_data 供应商。
    Args:
        ticker (str): 公司股票代码
        freq (str): 报告频率：annual/quarterly（默认 quarterly）
        curr_date (str): 当前交易日期，格式 yyyy-mm-dd
    Returns:
        str: 包含利润表数据的格式化报告
    """
    return route_to_vendor("get_income_statement", ticker, freq, curr_date)
