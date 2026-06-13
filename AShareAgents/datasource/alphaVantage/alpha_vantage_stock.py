"""Alpha Vantage 股票行情数据模块。

提供每日调整后的OHLCV数据获取功能。
"""

from datetime import datetime
from .alpha_vantage_common import _make_api_request, _filter_csv_by_date_range

def get_stock(
    symbol: str,
    start_date: str,
    end_date: str
) -> str:
    """返回指定日期范围内的每日OHLCV数据、调整后收盘价以及历史拆股/分红事件。

    Args:
        symbol: 股票名称。示例：symbol=IBM
        start_date: 开始日期，格式YYYY-MM-DD
        end_date: 结束日期，格式YYYY-MM-DD

    Returns:
        按日期范围过滤后的每日调整时间序列CSV数据
    """
    # 解析日期以确定范围
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    today = datetime.now()

    # 根据请求范围是否在最近100天内选择outputsize
    # Compact返回最近100个数据点，检查start_date是否足够近
    days_from_today_to_start = (today - start_dt).days
    outputsize = "compact" if days_from_today_to_start < 100 else "full"

    params = {
        "symbol": symbol,
        "outputsize": outputsize,
        "datatype": "csv",
    }

    response = _make_api_request("TIME_SERIES_DAILY_ADJUSTED", params)

    return _filter_csv_by_date_range(response, start_date, end_date)
