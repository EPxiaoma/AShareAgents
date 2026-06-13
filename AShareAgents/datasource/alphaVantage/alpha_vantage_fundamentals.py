"""Alpha Vantage 基本面数据模块。

提供公司概览、资产负债表、现金流量表和利润表的获取功能。
"""

from .alpha_vantage_common import _make_api_request


def _filter_reports_by_date(result, curr_date: str):
    """过滤年度/季度报告，排除curr_date之后的条目。

    通过移除会计期间结束日期在当前模拟日期之后的期间，
    防止前视偏差。
    """
    if not curr_date or not isinstance(result, dict):
        return result
    for key in ("annualReports", "quarterlyReports"):
        if key in result:
            result[key] = [
                r for r in result[key]
                if r.get("fiscalDateEnding", "") <= curr_date
            ]
    return result


def get_fundamentals(ticker: str, curr_date: str = None) -> str:
    """通过 Alpha Vantage 获取指定股票代码的全面基本面数据。

    Args:
        ticker: 公司股票代码
        curr_date: 当前交易日期，格式YYYY-MM-DD（Alpha Vantage不使用此参数）

    Returns:
        包含财务比率和关键指标的公司概览数据
    """
    params = {
        "symbol": ticker,
    }

    return _make_api_request("OVERVIEW", params)


def get_balance_sheet(ticker: str, freq: str = "quarterly", curr_date: str = None):
    """通过 Alpha Vantage 获取指定股票代码的资产负债表数据。"""
    result = _make_api_request("BALANCE_SHEET", {"symbol": ticker})
    return _filter_reports_by_date(result, curr_date)


def get_cashflow(ticker: str, freq: str = "quarterly", curr_date: str = None):
    """通过 Alpha Vantage 获取指定股票代码的现金流量表数据。"""
    result = _make_api_request("CASH_FLOW", {"symbol": ticker})
    return _filter_reports_by_date(result, curr_date)


def get_income_statement(ticker: str, freq: str = "quarterly", curr_date: str = None):
    """通过 Alpha Vantage 获取指定股票代码的利润表数据。"""
    result = _make_api_request("INCOME_STATEMENT", {"symbol": ticker})
    return _filter_reports_by_date(result, curr_date)
