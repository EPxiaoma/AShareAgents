"""基于 stockstats 的技术指标计算工具模块。

提供OHLCV数据加载、缓存、技术指标计算和yfinance重试机制等底层支持。
"""

import time
import logging

import pandas as pd
import yfinance as yf
from yfinance.exceptions import YFRateLimitError
from stockstats import wrap
from typing import Annotated
import os
from ..config import get_config
from ..utils import safe_ticker_component

logger = logging.getLogger(__name__)


def yf_retry(func, max_retries=3, base_delay=2.0):
    """执行 yfinance 调用，遇到限流时使用指数退避重试。

    yfinance 在收到 HTTP 429 响应时抛出 YFRateLimitError 但不会内部重试。
    此包装器专门为限流错误添加重试逻辑，其他异常立即传播。
    """
    for attempt in range(max_retries + 1):
        try:
            return func()
        except YFRateLimitError:
            if attempt < max_retries:
                delay = base_delay * (2 ** attempt)
                logger.warning(f"Yahoo Finance 请求频率受限，{delay:.0f}秒后重试 (第 {attempt + 1}/{max_retries} 次)")
                time.sleep(delay)
            else:
                raise


def _clean_dataframe(data: pd.DataFrame) -> pd.DataFrame:
    """规范化股票DataFrame：解析日期、删除无效行、填充价格缺失值。"""
    data["Date"] = pd.to_datetime(data["Date"], errors="coerce")
    data = data.dropna(subset=["Date"])

    price_cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in data.columns]
    data[price_cols] = data[price_cols].apply(pd.to_numeric, errors="coerce")
    data = data.dropna(subset=["Close"])
    data[price_cols] = data[price_cols].ffill().bfill()

    return data


def load_ohlcv(symbol: str, curr_date: str) -> pd.DataFrame:
    """加载带缓存的OHLCV数据，过滤未来数据以防止前视偏差。

    下载最近5年的数据并按代码缓存。后续调用直接复用缓存。
    curr_date 之后的行情行会被过滤掉，确保回测不会看到未来价格。

    Args:
        symbol: 股票代码
        curr_date: 当前日期，格式YYYY-MM-DD

    Returns:
        pd.DataFrame: 过滤后的OHLCV数据
    """
    # 拒绝可能通过缓存文件名逃逸目标目录的代码值
    safe_symbol = safe_ticker_component(symbol)

    config = get_config()
    curr_date_dt = pd.to_datetime(curr_date)

    # 缓存使用固定窗口（5年至今天），每个代码对应一个文件
    today_date = pd.Timestamp.today()
    start_date = today_date - pd.DateOffset(years=5)
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = today_date.strftime("%Y-%m-%d")

    os.makedirs(config["data_cache_dir"], exist_ok=True)
    data_file = os.path.join(
        config["data_cache_dir"],
        f"{safe_symbol}-YFin-data-{start_str}-{end_str}.csv",
    )

    if os.path.exists(data_file):
        data = pd.read_csv(data_file, on_bad_lines="skip", encoding="utf-8")
    else:
        data = yf_retry(lambda: yf.download(
            symbol,
            start=start_str,
            end=end_str,
            multi_level_index=False,
            progress=False,
            auto_adjust=True,
        ))
        data = data.reset_index()
        data.to_csv(data_file, index=False, encoding="utf-8")

    data = _clean_dataframe(data)

    # 过滤到curr_date以防止回测中的前视偏差
    data = data[data["Date"] <= curr_date_dt]

    return data


def filter_financials_by_date(data: pd.DataFrame, curr_date: str) -> pd.DataFrame:
    """删除curr_date之后的财务报表列（会计期间时间戳）。

    yfinance的财务报表使用会计期间结束日期作为列名。
    代表未来数据的列将被移除，以防止前视偏差。
    """
    if not curr_date or data.empty:
        return data
    cutoff = pd.Timestamp(curr_date)
    mask = pd.to_datetime(data.columns, errors="coerce") <= cutoff
    return data.loc[:, mask]


class StockstatsUtils:
    @staticmethod
    def get_stock_stats(
        symbol: Annotated[str, "公司股票代码"],
        indicator: Annotated[
            str, "基于股票数据的量化分析指标"
        ],
        curr_date: Annotated[
            str, "当前日期，格式YYYY-MM-DD"
        ],
    ):
        """获取指定日期的技术指标值。"""
        data = load_ohlcv(symbol, curr_date)
        df = wrap(data)
        df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")
        curr_date_str = pd.to_datetime(curr_date).strftime("%Y-%m-%d")

        df[indicator]  # 触发 stockstats 计算指标
        matching_rows = df[df["Date"].str.startswith(curr_date_str)]

        if not matching_rows.empty:
            indicator_value = matching_rows[indicator].values[0]
            return indicator_value
        else:
            return "不适用: 非交易日 (周末或节假日)"
