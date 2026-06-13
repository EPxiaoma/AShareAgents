"""Alpha Vantage 新闻与内部交易数据模块。

提供市场新闻情感分析数据和内部交易数据的获取功能。
"""

from .alpha_vantage_common import _make_api_request, format_datetime_for_api

def get_news(ticker, start_date, end_date) -> dict[str, str] | str:
    """获取来自全球知名新闻机构的市场新闻与情感数据。

    涵盖股票、加密货币、外汇以及财政政策、并购、IPO等主题。

    Args:
        ticker: 股票代码
        start_date: 新闻搜索开始日期
        end_date: 新闻搜索结束日期

    Returns:
        包含新闻情感数据的字典或JSON字符串
    """

    params = {
        "tickers": ticker,
        "time_from": format_datetime_for_api(start_date),
        "time_to": format_datetime_for_api(end_date),
    }

    return _make_api_request("NEWS_SENTIMENT", params)

def get_global_news(curr_date, look_back_days: int = 7, limit: int = 50) -> dict[str, str] | str:
    """获取全球市场新闻与情感数据（不限定特定股票代码）。

    涵盖金融市场、经济等广泛市场主题。

    Args:
        curr_date: 当前日期，格式YYYY-MM-DD
        look_back_days: 回溯天数（默认7天）
        limit: 最多返回文章数（默认50）

    Returns:
        包含全球新闻情感数据的字典或JSON字符串
    """
    from datetime import datetime, timedelta

    # 计算开始日期
    curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_dt = curr_dt - timedelta(days=look_back_days)
    start_date = start_dt.strftime("%Y-%m-%d")

    params = {
        "topics": "financial_markets,economy_macro,economy_monetary",
        "time_from": format_datetime_for_api(start_date),
        "time_to": format_datetime_for_api(curr_date),
        "limit": str(limit),
    }

    return _make_api_request("NEWS_SENTIMENT", params)


def get_insider_transactions(symbol: str) -> dict[str, str] | str:
    """获取主要利益相关者的最新和历史内部交易数据。

    涵盖创始人、高管、董事会成员等的交易记录。

    Args:
        symbol: 股票代码。示例："IBM"

    Returns:
        包含内部交易数据的字典或JSON字符串
    """

    params = {
        "symbol": symbol,
    }

    return _make_api_request("INSIDER_TRANSACTIONS", params)
