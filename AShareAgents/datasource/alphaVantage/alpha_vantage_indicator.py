"""Alpha Vantage 技术指标模块。

提供通过Alpha Vantage API获取各类技术分析指标的功能。
"""

import logging

from .alpha_vantage_common import _make_api_request

logger = logging.getLogger(__name__)

def get_indicator(
    symbol: str,
    indicator: str,
    curr_date: str,
    look_back_days: int,
    interval: str = "daily",
    time_period: int = 14,
    series_type: str = "close"
) -> str:
    """返回指定时间窗口内的Alpha Vantage技术指标值。

    Args:
        symbol: 公司股票代码
        indicator: 需要获取分析报告的技术指标
        curr_date: 当前交易日期，格式YYYY-MM-DD
        look_back_days: 回溯天数
        interval: 时间间隔（daily, weekly, monthly）
        time_period: 计算使用的数据点数
        series_type: 所需价格类型（close, open, high, low）

    Returns:
        包含指标值和描述的字符串
    """
    from datetime import datetime
    from dateutil.relativedelta import relativedelta

    supported_indicators = {
        "close_50_sma": ("50 SMA", "close"),
        "close_200_sma": ("200 SMA", "close"),
        "close_10_ema": ("10 EMA", "close"),
        "macd": ("MACD", "close"),
        "macds": ("MACD Signal", "close"),
        "macdh": ("MACD Histogram", "close"),
        "rsi": ("RSI", "close"),
        "boll": ("Bollinger Middle", "close"),
        "boll_ub": ("Bollinger Upper Band", "close"),
        "boll_lb": ("Bollinger Lower Band", "close"),
        "atr": ("ATR", None),
        "vwma": ("VWMA", "close")
    }

    indicator_descriptions = {
        "close_50_sma": "50 SMA：中期趋势指标。用法：识别趋势方向，作为动态支撑/阻力。提示：滞后于价格，需结合更快的指标获取及时信号。",
        "close_200_sma": "200 SMA：长期趋势基准。用法：确认整体市场趋势，识别金叉/死叉形态。提示：反应缓慢，更适合战略趋势确认而非频繁交易入场。",
        "close_10_ema": "10 EMA：灵敏的短期均线。用法：捕捉动量的快速转变和潜在入场点。提示：在震荡市场中易受噪声干扰，需结合更长周期的均线过滤假信号。",
        "macd": "MACD：通过EMA差值计算动量。用法：观察交叉和背离作为趋势变化的信号。提示：在低波动或横盘市场中需结合其他指标确认。",
        "macds": "MACD Signal：MACD线的EMA平滑值。用法：利用与MACD线的交叉触发交易。提示：应作为更广泛策略的一部分，避免误判。",
        "macdh": "MACD Histogram：展示MACD线与其信号线之间的差距。用法：直观显示动量强度，及早发现背离。提示：波动较大，在快速变动的市场中需辅以其他过滤手段。",
        "rsi": "RSI：衡量动量以标记超买/超卖状态。用法：使用70/30阈值并观察背离来信号反转。提示：在强趋势中RSI可能持续极端，务必结合趋势分析交叉验证。",
        "boll": "Bollinger Middle：作为布林带基准的20日SMA。用法：作为价格运动的动态基准。提示：结合上下轨有效识别突破或反转。",
        "boll_ub": "Bollinger Upper Band：通常为中线上方2个标准差。用法：信号潜在的过买状态和突破区域。提示：需结合其他工具确认信号；强势行情中价格可能持续沿上轨运行。",
        "boll_lb": "Bollinger Lower Band：通常为中线下下方2个标准差。用法：指示潜在的过卖状态。提示：需结合额外分析避免虚假反转信号。",
        "atr": "ATR：平均真实波幅，衡量波动率。用法：设定止损水平和基于当前市场波动率调整仓位规模。提示：为滞后指标，需作为更广泛风险管理策略的一部分使用。",
        "vwma": "VWMA：成交量加权的移动平均。用法：通过整合价格走势与成交量数据来确认趋势。提示：注意成交量突增导致的结果偏差，与其他成交量分析结合使用。"
    }

    if indicator not in supported_indicators:
        raise ValueError(
            f"指标 {indicator} 不受支持，请从以下指标中选择: {list(supported_indicators.keys())}"
        )

    curr_date_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    before = curr_date_dt - relativedelta(days=look_back_days)

    # 获取整个期间的数据，而非逐个调用
    _, required_series_type = supported_indicators[indicator]

    # 使用提供的series_type或回退到所需的
    if required_series_type:
        series_type = required_series_type

    try:
        # 获取期间的指标数据
        if indicator == "close_50_sma":
            data = _make_api_request("SMA", {
                "symbol": symbol,
                "interval": interval,
                "time_period": "50",
                "series_type": series_type,
                "datatype": "csv"
            })
        elif indicator == "close_200_sma":
            data = _make_api_request("SMA", {
                "symbol": symbol,
                "interval": interval,
                "time_period": "200",
                "series_type": series_type,
                "datatype": "csv"
            })
        elif indicator == "close_10_ema":
            data = _make_api_request("EMA", {
                "symbol": symbol,
                "interval": interval,
                "time_period": "10",
                "series_type": series_type,
                "datatype": "csv"
            })
        elif indicator == "macd":
            data = _make_api_request("MACD", {
                "symbol": symbol,
                "interval": interval,
                "series_type": series_type,
                "datatype": "csv"
            })
        elif indicator == "macds":
            data = _make_api_request("MACD", {
                "symbol": symbol,
                "interval": interval,
                "series_type": series_type,
                "datatype": "csv"
            })
        elif indicator == "macdh":
            data = _make_api_request("MACD", {
                "symbol": symbol,
                "interval": interval,
                "series_type": series_type,
                "datatype": "csv"
            })
        elif indicator == "rsi":
            data = _make_api_request("RSI", {
                "symbol": symbol,
                "interval": interval,
                "time_period": str(time_period),
                "series_type": series_type,
                "datatype": "csv"
            })
        elif indicator in ["boll", "boll_ub", "boll_lb"]:
            data = _make_api_request("BBANDS", {
                "symbol": symbol,
                "interval": interval,
                "time_period": "20",
                "series_type": series_type,
                "datatype": "csv"
            })
        elif indicator == "atr":
            data = _make_api_request("ATR", {
                "symbol": symbol,
                "interval": interval,
                "time_period": str(time_period),
                "datatype": "csv"
            })
        elif indicator == "vwma":
            # Alpha Vantage 没有直接提供VWMA，因此返回提示信息
            # 实际使用时需要从OHLCV数据计算
            return f"## {symbol} 的 VWMA (成交量加权移动平均线):\n\nVWMA 计算需要 OHLCV 数据，无法直接从 Alpha Vantage API 获取。\n该指标需通过原始股票数据使用成交量加权价格平均进行计算。\n\n{indicator_descriptions.get('vwma', '暂无描述信息。')}"
        else:
            return f"错误: 指标 {indicator} 尚未实现。"

        # 解析CSV数据，提取日期范围内的值
        lines = data.strip().split('\n')
        if len(lines) < 2:
            return f"错误: 指标 {indicator} 未返回数据"

        # 解析表头和数据
        header = [col.strip() for col in lines[0].split(',')]
        try:
            date_col_idx = header.index('time')
        except ValueError:
            return f"错误: 指标 {indicator} 的数据中未找到 'time' 列。可用列: {header}"

        # 将内部指标名映射到Alpha Vantage返回的CSV列名
        col_name_map = {
            "macd": "MACD", "macds": "MACD_Signal", "macdh": "MACD_Hist",
            "boll": "Real Middle Band", "boll_ub": "Real Upper Band", "boll_lb": "Real Lower Band",
            "rsi": "RSI", "atr": "ATR", "close_10_ema": "EMA",
            "close_50_sma": "SMA", "close_200_sma": "SMA"
        }

        target_col_name = col_name_map.get(indicator)

        if not target_col_name:
            # 如无特定映射，默认使用第二列
            value_col_idx = 1
        else:
            try:
                value_col_idx = header.index(target_col_name)
            except ValueError:
                return f"错误: 指标 '{indicator}' 的数据中未找到列 '{target_col_name}'。可用列: {header}"

        result_data = []
        for line in lines[1:]:
            if not line.strip():
                continue
            values = line.split(',')
            if len(values) > value_col_idx:
                try:
                    date_str = values[date_col_idx].strip()
                    # 解析日期
                    date_dt = datetime.strptime(date_str, "%Y-%m-%d")

                    # 检查日期是否在范围内
                    if before <= date_dt <= curr_date_dt:
                        value = values[value_col_idx].strip()
                        result_data.append((date_dt, value))
                except (ValueError, IndexError):
                    continue

        # 按日期排序并格式化输出
        result_data.sort(key=lambda x: x[0])

        ind_string = ""
        for date_dt, value in result_data:
            ind_string += f"{date_dt.strftime('%Y-%m-%d')}: {value}\n"

        if not ind_string:
            ind_string = "指定日期范围内无可用数据。\n"

        result_str = (
            f"## {indicator.upper()} 指标值（{before.strftime('%Y-%m-%d')} 至 {curr_date}）:\n\n"
            + ind_string
            + "\n\n"
            + indicator_descriptions.get(indicator, "暂无描述信息。")
        )

        return result_str

    except Exception as e:
        logger.warning("获取 Alpha Vantage 指标 %s 数据失败: %s", indicator, e)
        return f"获取 {indicator} 指标数据时出错: {str(e)}"
