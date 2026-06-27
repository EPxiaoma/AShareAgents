"""A 股 OHLCV 行情数据和技术指标适配器。"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
import logging
import os

from dateutil.relativedelta import relativedelta
import pandas as pd

from ..mootdx import get_daily_bars as _get_mootdx_daily_bars
from ..sinaFinance import get_daily_kline as _sina_kline_fallback
from .errors import RECOVERABLE_DATA_SOURCE_ERRORS
from .symbols import _normalize_ticker

logger = logging.getLogger(__name__)

# 行情 OHLCV 数据优先从 mootdx 获取，并以 CSV 缓存。

def _load_ohlcv_astock(symbol: str, curr_date: str) -> pd.DataFrame:
    """通过 mootdx 获取 OHLCV，缓存至 CSV，按 curr_date 过滤。

    类似 yFinance.stockstats_tools.load_ohlcv，但使用 mootdx 替代 yfinance。

    Returns:
        包含以下列的 DataFrame：Date、Open、High、Low、Close、Volume。
    """
    from ..config import get_config

    code = _normalize_ticker(symbol)
    config = get_config()
    cache_dir = config.get(
        "data_cache_dir", os.path.expanduser("~/.ashareagents/cache")
    )
    os.makedirs(cache_dir, exist_ok=True)

    cache_file = os.path.join(cache_dir, f"{code}-astock-daily.csv")

    if os.path.exists(cache_file):
        mtime = datetime.fromtimestamp(os.path.getmtime(cache_file))
        if mtime.date() == datetime.now().date():
            data = pd.read_csv(cache_file, on_bad_lines="skip", encoding="utf-8")
            data["Date"] = pd.to_datetime(data["Date"])
            cutoff = pd.to_datetime(curr_date)
            return data[data["Date"] <= cutoff]

    # 从 mootdx 获取 800 根日K线（约3年交易日）
    try:
        df = _get_mootdx_daily_bars(code)
        if df.empty:
            raise ValueError(f"mootdx 未返回 {code} 的 OHLCV 数据")
    except RECOVERABLE_DATA_SOURCE_ERRORS as e:
        mootdx_error = e
        # 回退：新浪直连 HTTP API
        try:
            df = _sina_kline_fallback(code)
            if df.empty:
                raise ValueError(f"新浪未返回 {code} 的 OHLCV 数据")
            logger.info("行情数据源切换：%s 的 mootdx 数据不可用，已使用新浪财经", code)
        except RECOVERABLE_DATA_SOURCE_ERRORS as fallback_error:
            logger.warning(
                "OHLCV 获取 %s 失败：mootdx=%s；新浪=%s",
                code,
                mootdx_error,
                fallback_error,
            )
            raise ValueError(f"mootdx 和新浪均未返回 {code} 的 OHLCV 数据")

    # 缓存到磁盘
    df.to_csv(cache_file, index=False, encoding="utf-8")

    # 按 curr_date 过滤，防止前视偏差
    cutoff = pd.to_datetime(curr_date)
    return df[df["Date"] <= cutoff]


# 以下供应商方法必须与 interface.py 的 VENDOR_METHODS 签名保持一致。


# ---- 1. 获取行情数据（get_stock_data）----


def get_stock_data(
    symbol: Annotated[str, "A股代码（如 688017、SH688017）"],
    start_date: Annotated[str, "起始日期，格式 yyyy-mm-dd"],
    end_date: Annotated[str, "结束日期，格式 yyyy-mm-dd"],
) -> str:
    """获取 A 股 OHLCV 行情数据，复用 _load_ohlcv_astock 的缓存层。"""
    code = _normalize_ticker(symbol)

    try:
        df = _load_ohlcv_astock(code, end_date)
    except RECOVERABLE_DATA_SOURCE_ERRORS:
        return "K线数据获取失败：mootdx和新浪备用源均不可用，请检查网络连接"

    # 按日期范围过滤
    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)
    df = df[(df["Date"] >= start_dt) & (df["Date"] <= end_dt)]

    if df.empty:
        return f"在 {start_date} 至 {end_date} 期间未找到 A 股 '{code}' 的数据"

    for col in ["Open", "High", "Low", "Close"]:
        if col in df.columns:
            df[col] = df[col].round(2)

    df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")
    csv_out = df[["Date", "Open", "High", "Low", "Close", "Volume"]].to_csv(
        index=False
    )

    header = f"# {code} (A股) 行情数据，{start_date} 至 {end_date}\n"
    header += f"# 总记录数: {len(df)}\n"
    header += (
        f"# 数据获取时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    )

    return header + csv_out


# ---- 2. 获取技术指标（get_indicators）----

# 支持的技术指标及其说明
_INDICATOR_DESCRIPTIONS = {
    "close_50_sma": "50 日均线：中期趋势指标。",
    "close_200_sma": "200 日均线：长期趋势基准。",
    "close_10_ema": "10 日 EMA：灵敏的短期均线。",
    "macd": "MACD：通过 EMA 差值计算的动量指标。",
    "macds": "MACD 信号线：MACD 线的 EMA 平滑。",
    "macdh": "MACD 柱：MACD 与信号线之间的差值。",
    "rsi": "RSI：超买/超卖动量指标（阈值 70/30）。",
    "boll": "布林带中轨：20 日均线基准线。",
    "boll_ub": "布林带上轨：中轨上方 2 个标准差。",
    "boll_lb": "布林带下轨：中轨下方 2 个标准差。",
    "atr": "ATR：平均真实波幅，衡量波动率。",
    "vwma": "VWMA：成交量加权移动平均。",
    "mfi": "MFI：资金流量指数（成交量 + 价格动量）。",
}


def get_indicators(
    symbol: Annotated[str, "A股代码"],
    indicator: Annotated[
        str, "技术指标（如 rsi、macd、close_50_sma）"
    ],
    curr_date: Annotated[str, "当前交易日，格式 YYYY-mm-dd"],
    look_back_days: Annotated[int, "回顾多少天"],
) -> str:
    """基于 mootdx OHLCV 数据，使用 stockstats 计算技术指标。"""
    from stockstats import wrap

    code = _normalize_ticker(symbol)

    if indicator not in _INDICATOR_DESCRIPTIONS:
        raise ValueError(
            f"不支持的指标 {indicator}。"
            f"请从以下选项中选择：{list(_INDICATOR_DESCRIPTIONS.keys())}"
        )

    try:
        data = _load_ohlcv_astock(code, curr_date)
        df = wrap(data)
        df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")

        # 触发 stockstats 计算
        df[indicator]

        # 构建 日期 -> 指标值 的查找表
        ind_dict = {}
        for _, row in df.iterrows():
            d = row["Date"]
            v = row[indicator]
            ind_dict[d] = "N/A" if pd.isna(v) else str(round(float(v), 4))

        # 生成回顾窗口内的输出
        curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
        before = curr_dt - relativedelta(days=look_back_days)

        lines = []
        dt = curr_dt
        while dt >= before:
            ds = dt.strftime("%Y-%m-%d")
            val = ind_dict.get(ds, "N/A：非交易日（周末或节假日）")
            lines.append(f"{ds}: {val}")
            dt -= relativedelta(days=1)

        result = (
            f"## {code} 的 {indicator} 指标值 "
            f"（{before.strftime('%Y-%m-%d')} 至 {curr_date}）:\n\n"
            + "\n".join(lines)
            + "\n\n"
            + _INDICATOR_DESCRIPTIONS.get(indicator, "")
        )
        return result

    except RECOVERABLE_DATA_SOURCE_ERRORS as e:
        return f"计算 {code} 的 {indicator} 指标时出错：{str(e)}"
