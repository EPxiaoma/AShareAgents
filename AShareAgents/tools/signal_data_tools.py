"""向 Agent 暴露 A 股题材、资金流向和事件信号工具。"""

from langchain_core.tools import tool
from typing import Annotated
from AShareAgents.datasource.interface import route_to_vendor


@tool
def get_profit_forecast(
    ticker: Annotated[str, "A股代码（如 688017）"],
) -> str:
    """
    获取一致预期 EPS 预测及前瞻估值指标。
    返回分析师覆盖数量、EPS 区间、前瞻 PE、PEG 和 PE 消化时间。
    使用已配置的 signal_data 供应商。
    Args:
        ticker (str): A股代码
    Returns:
        str: 包含估值指标的一致预期报告
    """
    return route_to_vendor("get_profit_forecast", ticker)


@tool
def get_hot_stocks(
    curr_date: Annotated[str, "日期，格式 YYYY-MM-DD，为空则取当日"] = "",
) -> str:
    """
    获取当日强势股票，附带题材归因标签。
    显示股票上涨的原因（如 '算力租赁+AI政务'），由同花顺编辑团队精选。
    包含题材频次分析。
    使用已配置的 signal_data 供应商。
    Args:
        curr_date (str): 日期，格式 YYYY-MM-DD，空字符串表示当日
    Returns:
        str: 强势股票列表，含原因标签和题材频次
    """
    return route_to_vendor("get_hot_stocks", curr_date)


@tool
def get_northbound_flow(
    curr_date: Annotated[str, "日期，格式 YYYY-MM-DD"],
    include_history: Annotated[
        bool, "是否包含历史每日数据（最近20个交易日）"
    ] = False,
) -> str:
    """
    获取北向资金流向（沪深股通）数据。
    实时：分钟级 HGT + SGT 累计净买入。
    历史（可选）：日级别数据用于趋势分析。
    使用已配置的 signal_data 供应商。
    Args:
        curr_date (str): 日期，格式 YYYY-MM-DD
        include_history (bool): 是否包含历史每日数据
    Returns:
        str: 北向资金流向报告，含多空信号
    """
    return route_to_vendor("get_northbound_flow", curr_date, include_history)


@tool
def get_concept_blocks(
    ticker: Annotated[str, "A股代码（如 688017）"],
) -> str:
    """
    获取股票所属的概念/板块/地区板块。
    显示行业（申万）、概念题材（如 机器人概念、减速器）和地区。
    每个板块包含当日涨跌幅。
    使用已配置的 signal_data 供应商。
    Args:
        ticker (str): A股代码
    Returns:
        str: 概念和板块归属，含每日涨跌幅
    """
    return route_to_vendor("get_concept_blocks", ticker)


@tool
def get_fund_flow(
    ticker: Annotated[str, "A股代码"],
    curr_date: Annotated[str, "日期，格式 YYYY-MM-DD"],
    include_history: Annotated[
        bool, "是否包含历史每日资金流向（最近20天）"
    ] = True,
) -> str:
    """
    获取个股资金流向（主力 vs 散户）。
    实时：分钟级超大/大/中/小单流向。
    历史：20个交易日按单量大小的每日净流入。
    使用已配置的 signal_data 供应商。
    Args:
        ticker (str): A股代码
        curr_date (str): 日期，格式 YYYY-MM-DD
        include_history (bool): 是否包含20日历史每日流向
    Returns:
        str: 资金流向报告，含主力信号
    """
    return route_to_vendor("get_fund_flow", ticker, curr_date, include_history)


@tool
def get_dragon_tiger_board(
    ticker: Annotated[str, "A股代码（如 000858）"],
    curr_date: Annotated[str, "日期，格式 YYYY-MM-DD"],
    look_back_days: Annotated[int, "回看天数（默认 30）"] = 30,
) -> str:
    """
    获取股票的龙虎榜数据。
    显示近期龙虎榜现身记录、买卖席位（营业部）Top 榜，
    以及机构参与情况。是追踪游资动向的关键信号。
    Args:
        ticker (str): A股代码
        curr_date (str): 日期，格式 YYYY-MM-DD
        look_back_days (int): 回看天数
    Returns:
        str: 龙虎榜现身记录，含席位详情和机构活跃度
    """
    return route_to_vendor("get_dragon_tiger_board", ticker, curr_date, look_back_days)


@tool
def get_lockup_expiry(
    ticker: Annotated[str, "A股代码（如 000858）"],
    curr_date: Annotated[str, "日期，格式 YYYY-MM-DD"],
    forward_days: Annotated[int, "向前查看的天数（默认 90）"] = 90,
) -> str:
    """
    获取股票的限售解禁日程。
    显示历史解禁记录和即将到期的解禁日历，
    含影响指标（解禁数量、市值占比）。
    Args:
        ticker (str): A股代码
        curr_date (str): 日期，格式 YYYY-MM-DD
        forward_days (int): 向前查看的天数
    Returns:
        str: 限售解禁日程及影响评估
    """
    return route_to_vendor("get_lockup_expiry", ticker, curr_date, forward_days)


@tool
def get_industry_comparison(
    ticker: Annotated[str, "A股代码（如 000858）"],
    curr_date: Annotated[str, "日期，格式 YYYY-MM-DD"],
) -> str:
    """
    获取行业板块横向对比（行业横向对比）。
    显示全部90个同花顺行业的涨跌幅排名，含换手率、
    净资金流向和领涨股。适用于板块轮动分析。
    Args:
        ticker (str): A股代码（用于识别相关行业）
        curr_date (str): 日期，格式 YYYY-MM-DD
    Returns:
        str: 行业表现排名及关键指标
    """
    return route_to_vendor("get_industry_comparison", ticker, curr_date)
