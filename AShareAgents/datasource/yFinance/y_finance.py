"""基于 yfinance 的股票数据获取模块。

提供股票OHLCV数据、技术指标、基本面数据、财务报表和内部交易数据的获取功能。
"""

from typing import Annotated
from datetime import datetime
from dateutil.relativedelta import relativedelta
import logging
import pandas as pd
import yfinance as yf
import os

logger = logging.getLogger(__name__)

from .stockstats_utils import StockstatsUtils, _clean_dataframe, yf_retry, load_ohlcv, filter_financials_by_date

def get_YFin_data_online(
    symbol: Annotated[str, "公司股票代码"],
    start_date: Annotated[str, "开始日期，格式YYYY-MM-DD"],
    end_date: Annotated[str, "结束日期，格式YYYY-MM-DD"],
):

    datetime.strptime(start_date, "%Y-%m-%d")
    datetime.strptime(end_date, "%Y-%m-%d")

    # 创建股票代码对象
    ticker = yf.Ticker(symbol.upper())

    # 获取指定日期范围的历史数据
    data = yf_retry(lambda: ticker.history(start=start_date, end=end_date))

    # 检查数据是否为空
    if data.empty:
        return (
            f"在 {start_date} 至 {end_date} 期间未找到股票代码 '{symbol}' 的数据"
        )

    # 移除索引中的时区信息，以便更清晰地展示
    if data.index.tz is not None:
        data.index = data.index.tz_localize(None)

    # 将数值列舍入到2位小数，便于显示
    numeric_columns = ["Open", "High", "Low", "Close", "Adj Close"]
    for col in numeric_columns:
        if col in data.columns:
            data[col] = data[col].round(2)

    # 将DataFrame转换为CSV字符串
    csv_string = data.to_csv()

    # 添加头部信息
    header = f"# {symbol.upper()} 股票数据 ({start_date} 至 {end_date})\n"
    header += f"# 总记录数: {len(data)}\n"
    header += f"# 数据获取时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

    return header + csv_string

def get_stock_stats_indicators_window(
    symbol: Annotated[str, "公司股票代码"],
    indicator: Annotated[str, "需要获取分析报告的技术指标"],
    curr_date: Annotated[
        str, "当前交易日期，格式YYYY-MM-DD"
    ],
    look_back_days: Annotated[int, "回溯天数"],
) -> str:

    best_ind_params = {
        # 移动平均线
        "close_50_sma": (
            "50 SMA：中期趋势指标。"
            "用法：识别趋势方向，作为动态支撑/阻力。"
            "提示：滞后于价格，需结合更快的指标获取及时信号。"
        ),
        "close_200_sma": (
            "200 SMA：长期趋势基准。"
            "用法：确认整体市场趋势，识别金叉/死叉形态。"
            "提示：反应缓慢，更适合战略趋势确认而非频繁交易入场。"
        ),
        "close_10_ema": (
            "10 EMA：灵敏的短期均线。"
            "用法：捕捉动量的快速转变和潜在入场点。"
            "提示：在震荡市场中易受噪声干扰，需结合更长周期的均线过滤假信号。"
        ),
        # MACD 相关
        "macd": (
            "MACD：通过EMA差值计算动量。"
            "用法：观察交叉和背离作为趋势变化的信号。"
            "提示：在低波动或横盘市场中需结合其他指标确认。"
        ),
        "macds": (
            "MACD Signal：MACD线的EMA平滑值。"
            "用法：利用与MACD线的交叉触发交易。"
            "提示：应作为更广泛策略的一部分，避免误判。"
        ),
        "macdh": (
            "MACD Histogram：展示MACD线与其信号线之间的差距。"
            "用法：直观显示动量强度，及早发现背离。"
            "提示：波动较大，在快速变动的市场中需辅以其他过滤手段。"
        ),
        # 动量指标
        "rsi": (
            "RSI：衡量动量以标记超买/超卖状态。"
            "用法：使用70/30阈值并观察背离来信号反转。"
            "提示：在强趋势中RSI可能持续极端，务必结合趋势分析交叉验证。"
        ),
        # 波动率指标
        "boll": (
            "Bollinger Middle：作为布林带基准的20日SMA。"
            "用法：作为价格运动的动态基准。"
            "提示：结合上下轨有效识别突破或反转。"
        ),
        "boll_ub": (
            "Bollinger Upper Band：通常为中线上方2个标准差。"
            "用法：信号潜在的过买状态和突破区域。"
            "提示：需结合其他工具确认信号；强势行情中价格可能持续沿上轨运行。"
        ),
        "boll_lb": (
            "Bollinger Lower Band：通常为中线下下方2个标准差。"
            "用法：指示潜在的过卖状态。"
            "提示：需结合额外分析避免虚假反转信号。"
        ),
        "atr": (
            "ATR：平均真实波幅，衡量波动率。"
            "用法：设定止损水平和基于当前市场波动率调整仓位规模。"
            "提示：为滞后指标，需作为更广泛风险管理策略的一部分使用。"
        ),
        # 成交量相关指标
        "vwma": (
            "VWMA：成交量加权的移动平均。"
            "用法：通过整合价格走势与成交量数据来确认趋势。"
            "提示：注意成交量突增导致的结果偏差，与其他成交量分析结合使用。"
        ),
        "mfi": (
            "MFI：资金流量指数是一种同时使用价格和成交量来衡量买卖压力的动量指标。"
            "用法：识别超买(>80)或超卖(<20)状态，确认趋势或反转的强度。"
            "提示：与RSI或MACD结合使用以确认信号；价格与MFI之间的背离可预示潜在反转。"
        ),
    }

    if indicator not in best_ind_params:
        raise ValueError(
            f"指标 {indicator} 不受支持，请从以下指标中选择: {list(best_ind_params.keys())}"
        )

    end_date = curr_date
    curr_date_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    before = curr_date_dt - relativedelta(days=look_back_days)

    # 优化：一次获取股票数据，计算所有日期的指标
    try:
        indicator_data = _get_stock_stats_bulk(symbol, indicator, curr_date)

        # 生成所需的日期范围
        current_dt = curr_date_dt
        date_values = []

        while current_dt >= before:
            date_str = current_dt.strftime('%Y-%m-%d')

            # 查找该日期的指标值
            if date_str in indicator_data:
                indicator_value = indicator_data[date_str]
            else:
                indicator_value = "不适用: 非交易日 (周末或节假日)"

            date_values.append((date_str, indicator_value))
            current_dt = current_dt - relativedelta(days=1)

        # 构建结果字符串
        ind_string = ""
        for date_str, value in date_values:
            ind_string += f"{date_str}: {value}\n"

    except Exception as e:
        logger.warning("批量获取 stockstats 数据失败: %s", e)
        # 批量方法失败时回退到原始实现
        ind_string = ""
        curr_date_dt = datetime.strptime(curr_date, "%Y-%m-%d")
        while curr_date_dt >= before:
            indicator_value = get_stockstats_indicator(
                symbol, indicator, curr_date_dt.strftime("%Y-%m-%d")
            )
            ind_string += f"{curr_date_dt.strftime('%Y-%m-%d')}: {indicator_value}\n"
            curr_date_dt = curr_date_dt - relativedelta(days=1)

    result_str = (
        f"## {indicator} values from {before.strftime('%Y-%m-%d')} to {end_date}:\n\n"
        + ind_string
        + "\n\n"
        + best_ind_params.get(indicator, "暂无描述信息。")
    )

    return result_str


def _get_stock_stats_bulk(
    symbol: Annotated[str, "公司股票代码"],
    indicator: Annotated[str, "需要计算的技术指标"],
    curr_date: Annotated[str, "参考当前日期"]
) -> dict:
    """批量计算stockstats技术指标（优化版）。

    一次性获取数据，为所有可用日期计算指标值。

    Args:
        symbol: 公司股票代码
        indicator: 需要计算的技术指标
        curr_date: 参考当前日期

    Returns:
        dict: 日期字符串到指标值的映射
    """
    from stockstats import wrap

    data = load_ohlcv(symbol, curr_date)
    df = wrap(data)
    df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")

    # 一次性计算所有行的指标
    df[indicator]  # 触发 stockstats 计算指标

    # 创建日期字符串到指标值的映射字典
    result_dict = {}
    for _, row in df.iterrows():
        date_str = row["Date"]
        indicator_value = row[indicator]

        # 处理 NaN/None 值
        if pd.isna(indicator_value):
            result_dict[date_str] = "不适用"
        else:
            result_dict[date_str] = str(indicator_value)

    return result_dict


def get_stockstats_indicator(
    symbol: Annotated[str, "公司股票代码"],
    indicator: Annotated[str, "需要获取分析报告的技术指标"],
    curr_date: Annotated[
        str, "当前交易日期，格式YYYY-MM-DD"
    ],
) -> str:

    curr_date_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    curr_date = curr_date_dt.strftime("%Y-%m-%d")

    try:
        indicator_value = StockstatsUtils.get_stock_stats(
            symbol,
            indicator,
            curr_date,
        )
    except Exception as e:
        logger.warning(
            "获取指标 %s 于 %s 的数据失败: %s",
            indicator, curr_date, e
        )
        return ""

    return str(indicator_value)


def get_fundamentals(
    ticker: Annotated[str, "公司股票代码"],
    curr_date: Annotated[str, "当前日期（yfinance不使用此参数）"] = None
):
    """通过 yfinance 获取公司基本面概览数据。"""
    try:
        ticker_obj = yf.Ticker(ticker.upper())
        info = yf_retry(lambda: ticker_obj.info)

        if not info:
            return f"未找到股票代码 '{ticker}' 的基本面数据"

        fields = [
            ("Name", info.get("longName")),
            ("Sector", info.get("sector")),
            ("Industry", info.get("industry")),
            ("Market Cap", info.get("marketCap")),
            ("PE Ratio (TTM)", info.get("trailingPE")),
            ("Forward PE", info.get("forwardPE")),
            ("PEG Ratio", info.get("pegRatio")),
            ("Price to Book", info.get("priceToBook")),
            ("EPS (TTM)", info.get("trailingEps")),
            ("Forward EPS", info.get("forwardEps")),
            ("Dividend Yield", info.get("dividendYield")),
            ("Beta", info.get("beta")),
            ("52 Week High", info.get("fiftyTwoWeekHigh")),
            ("52 Week Low", info.get("fiftyTwoWeekLow")),
            ("50 Day Average", info.get("fiftyDayAverage")),
            ("200 Day Average", info.get("twoHundredDayAverage")),
            ("Revenue (TTM)", info.get("totalRevenue")),
            ("Gross Profit", info.get("grossProfits")),
            ("EBITDA", info.get("ebitda")),
            ("Net Income", info.get("netIncomeToCommon")),
            ("Profit Margin", info.get("profitMargins")),
            ("Operating Margin", info.get("operatingMargins")),
            ("Return on Equity", info.get("returnOnEquity")),
            ("Return on Assets", info.get("returnOnAssets")),
            ("Debt to Equity", info.get("debtToEquity")),
            ("Current Ratio", info.get("currentRatio")),
            ("Book Value", info.get("bookValue")),
            ("Free Cash Flow", info.get("freeCashflow")),
        ]

        lines = []
        for label, value in fields:
            if value is not None:
                lines.append(f"{label}: {value}")

        header = f"# {ticker.upper()} 公司基本面数据\n"
        header += f"# 数据获取时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + "\n".join(lines)

    except Exception as e:
        return f"获取 {ticker} 基本面数据时出错: {str(e)}"


def get_balance_sheet(
    ticker: Annotated[str, "公司股票代码"],
    freq: Annotated[str, "数据频率：'annual'（年度）或 'quarterly'（季度）"] = "quarterly",
    curr_date: Annotated[str, "当前日期，格式YYYY-MM-DD"] = None
):
    """通过 yfinance 获取资产负债表数据。"""
    try:
        ticker_obj = yf.Ticker(ticker.upper())

        if freq.lower() == "quarterly":
            data = yf_retry(lambda: ticker_obj.quarterly_balance_sheet)
        else:
            data = yf_retry(lambda: ticker_obj.balance_sheet)

        data = filter_financials_by_date(data, curr_date)

        if data.empty:
            return f"未找到股票代码 '{ticker}' 的资产负债表数据"

        # 转换为CSV字符串以保持与其他函数一致
        csv_string = data.to_csv()

        # 添加头部信息
        header = f"# {ticker.upper()} 资产负债表数据 ({freq})\n"
        header += f"# 数据获取时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + csv_string

    except Exception as e:
        return f"获取 {ticker} 资产负债表数据时出错: {str(e)}"


def get_cashflow(
    ticker: Annotated[str, "公司股票代码"],
    freq: Annotated[str, "数据频率：'annual'（年度）或 'quarterly'（季度）"] = "quarterly",
    curr_date: Annotated[str, "当前日期，格式YYYY-MM-DD"] = None
):
    """通过 yfinance 获取现金流量表数据。"""
    try:
        ticker_obj = yf.Ticker(ticker.upper())

        if freq.lower() == "quarterly":
            data = yf_retry(lambda: ticker_obj.quarterly_cashflow)
        else:
            data = yf_retry(lambda: ticker_obj.cashflow)

        data = filter_financials_by_date(data, curr_date)

        if data.empty:
            return f"未找到股票代码 '{ticker}' 的现金流量表数据"

        # 转换为CSV字符串以保持与其他函数一致
        csv_string = data.to_csv()

        # 添加头部信息
        header = f"# {ticker.upper()} 现金流量表数据 ({freq})\n"
        header += f"# 数据获取时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + csv_string

    except Exception as e:
        return f"获取 {ticker} 现金流量表数据时出错: {str(e)}"


def get_income_statement(
    ticker: Annotated[str, "公司股票代码"],
    freq: Annotated[str, "数据频率：'annual'（年度）或 'quarterly'（季度）"] = "quarterly",
    curr_date: Annotated[str, "当前日期，格式YYYY-MM-DD"] = None
):
    """通过 yfinance 获取利润表数据。"""
    try:
        ticker_obj = yf.Ticker(ticker.upper())

        if freq.lower() == "quarterly":
            data = yf_retry(lambda: ticker_obj.quarterly_income_stmt)
        else:
            data = yf_retry(lambda: ticker_obj.income_stmt)

        data = filter_financials_by_date(data, curr_date)

        if data.empty:
            return f"未找到股票代码 '{ticker}' 的利润表数据"

        # 转换为CSV字符串以保持与其他函数一致
        csv_string = data.to_csv()

        # 添加头部信息
        header = f"# {ticker.upper()} 利润表数据 ({freq})\n"
        header += f"# 数据获取时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + csv_string

    except Exception as e:
        return f"获取 {ticker} 利润表数据时出错: {str(e)}"


def get_insider_transactions(
    ticker: Annotated[str, "公司股票代码"]
):
    """通过 yfinance 获取内部交易数据。"""
    try:
        ticker_obj = yf.Ticker(ticker.upper())
        data = yf_retry(lambda: ticker_obj.insider_transactions)

        if data is None or data.empty:
            return f"未找到股票代码 '{ticker}' 的内部交易数据"

        # 转换为CSV字符串以保持与其他函数一致
        csv_string = data.to_csv()

        # 添加头部信息
        header = f"# {ticker.upper()} 内部交易数据\n"
        header += f"# 数据获取时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + csv_string

    except Exception as e:
        return f"获取 {ticker} 内部交易数据时出错: {str(e)}"
