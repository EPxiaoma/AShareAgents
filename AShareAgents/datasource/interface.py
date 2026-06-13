"""数据源统一接口模块。

定义工具分类、供应商映射和路由逻辑，根据配置将方法调用路由到对应供应商实现。
"""

from typing import Annotated

# 从各供应商模块导入具体实现
from .yFinance.y_finance import (
    get_YFin_data_online,
    get_stock_stats_indicators_window,
    get_fundamentals as get_yfinance_fundamentals,
    get_balance_sheet as get_yfinance_balance_sheet,
    get_cashflow as get_yfinance_cashflow,
    get_income_statement as get_yfinance_income_statement,
    get_insider_transactions as get_yfinance_insider_transactions,
)
from .yFinance.yfinance_news import get_news_yfinance, get_global_news_yfinance
from .alphaVantage.alpha_vantage import (
    get_stock as get_alpha_vantage_stock,
    get_indicator as get_alpha_vantage_indicator,
    get_fundamentals as get_alpha_vantage_fundamentals,
    get_balance_sheet as get_alpha_vantage_balance_sheet,
    get_cashflow as get_alpha_vantage_cashflow,
    get_income_statement as get_alpha_vantage_income_statement,
    get_insider_transactions as get_alpha_vantage_insider_transactions,
    get_news as get_alpha_vantage_news,
    get_global_news as get_alpha_vantage_global_news,
)
from .alphaVantage.alpha_vantage_common import AlphaVantageRateLimitError
from .astock.a_stock import (
    resolve_ticker,
    get_stock_data as get_astock_stock_data,
    get_indicators as get_astock_indicators,
    get_fundamentals as get_astock_fundamentals,
    get_balance_sheet as get_astock_balance_sheet,
    get_cashflow as get_astock_cashflow,
    get_income_statement as get_astock_income_statement,
    get_news as get_astock_news,
    get_global_news as get_astock_global_news,
    get_insider_transactions as get_astock_insider_transactions,
    get_profit_forecast as get_astock_profit_forecast,
    get_hot_stocks as get_astock_hot_stocks,
    get_northbound_flow as get_astock_northbound_flow,
    get_concept_blocks as get_astock_concept_blocks,
    get_fund_flow as get_astock_fund_flow,
    get_dragon_tiger_board as get_astock_dragon_tiger_board,
    get_lockup_expiry as get_astock_lockup_expiry,
    get_industry_comparison as get_astock_industry_comparison,
)

# 配置与路由逻辑
from .config import get_config

# 按类别组织的工具定义
TOOLS_CATEGORIES = {
    "core_stock_apis": {
        "description": "OHLCV股票价格数据",
        "tools": [
            "get_stock_data"
        ]
    },
    "technical_indicators": {
        "description": "技术分析指标",
        "tools": [
            "get_indicators"
        ]
    },
    "fundamental_data": {
        "description": "公司基本面数据",
        "tools": [
            "get_fundamentals",
            "get_balance_sheet",
            "get_cashflow",
            "get_income_statement"
        ]
    },
    "news_data": {
        "description": "新闻与内部交易数据",
        "tools": [
            "get_news",
            "get_global_news",
            "get_insider_transactions",
        ]
    },
    "signal_data": {
        "description": "A股信号层数据（题材归属、资金流向、一致性预测）",
        "tools": [
            "get_profit_forecast",
            "get_hot_stocks",
            "get_northbound_flow",
            "get_concept_blocks",
            "get_fund_flow",
            "get_dragon_tiger_board",
            "get_lockup_expiry",
            "get_industry_comparison",
        ]
    }
}

VENDOR_LIST = [
    "a_stock",
    "yfinance",
    "alpha_vantage",
]

# 方法到供应商实现的映射
VENDOR_METHODS = {
    # core_stock_apis
    "get_stock_data": {
        "a_stock": get_astock_stock_data,
        "alpha_vantage": get_alpha_vantage_stock,
        "yfinance": get_YFin_data_online,
    },
    # technical_indicators
    "get_indicators": {
        "a_stock": get_astock_indicators,
        "alpha_vantage": get_alpha_vantage_indicator,
        "yfinance": get_stock_stats_indicators_window,
    },
    # fundamental_data
    "get_fundamentals": {
        "a_stock": get_astock_fundamentals,
        "alpha_vantage": get_alpha_vantage_fundamentals,
        "yfinance": get_yfinance_fundamentals,
    },
    "get_balance_sheet": {
        "a_stock": get_astock_balance_sheet,
        "alpha_vantage": get_alpha_vantage_balance_sheet,
        "yfinance": get_yfinance_balance_sheet,
    },
    "get_cashflow": {
        "a_stock": get_astock_cashflow,
        "alpha_vantage": get_alpha_vantage_cashflow,
        "yfinance": get_yfinance_cashflow,
    },
    "get_income_statement": {
        "a_stock": get_astock_income_statement,
        "alpha_vantage": get_alpha_vantage_income_statement,
        "yfinance": get_yfinance_income_statement,
    },
    # news_data
    "get_news": {
        "a_stock": get_astock_news,
        "alpha_vantage": get_alpha_vantage_news,
        "yfinance": get_news_yfinance,
    },
    "get_global_news": {
        "a_stock": get_astock_global_news,
        "yfinance": get_global_news_yfinance,
        "alpha_vantage": get_alpha_vantage_global_news,
    },
    "get_insider_transactions": {
        "a_stock": get_astock_insider_transactions,
        "alpha_vantage": get_alpha_vantage_insider_transactions,
        "yfinance": get_yfinance_insider_transactions,
    },
    # signal_data（仅A股）
    "get_profit_forecast": {
        "a_stock": get_astock_profit_forecast,
    },
    "get_hot_stocks": {
        "a_stock": get_astock_hot_stocks,
    },
    "get_northbound_flow": {
        "a_stock": get_astock_northbound_flow,
    },
    "get_concept_blocks": {
        "a_stock": get_astock_concept_blocks,
    },
    "get_fund_flow": {
        "a_stock": get_astock_fund_flow,
    },
    "get_dragon_tiger_board": {
        "a_stock": get_astock_dragon_tiger_board,
    },
    "get_lockup_expiry": {
        "a_stock": get_astock_lockup_expiry,
    },
    "get_industry_comparison": {
        "a_stock": get_astock_industry_comparison,
    },
}

def get_category_for_method(method: str) -> str:
    """获取指定方法所属的类别。"""
    for category, info in TOOLS_CATEGORIES.items():
        if method in info["tools"]:
            return category
    raise ValueError(f"方法 '{method}' 未在任何类别中找到")

def get_vendor(category: str, method: str = None) -> str:
    """获取数据类别或具体工具方法配置的供应商。

    工具级别的配置优先于类别级别。
    """
    config = get_config()

    # 先检查工具级别配置（如果提供了 method）
    if method:
        tool_vendors = config.get("tool_vendors", {})
        if method in tool_vendors:
            return tool_vendors[method]

    # 回退到类别级别配置
    return config.get("data_vendors", {}).get(category, "default")

def route_to_vendor(method: str, *args, **kwargs):
    """将方法调用路由到对应的供应商实现，支持失败回退。"""
    category = get_category_for_method(method)
    vendor_config = get_vendor(category, method)
    primary_vendors = [v.strip() for v in vendor_config.split(',')]

    if method not in VENDOR_METHODS:
        raise ValueError(f"方法 '{method}' 不受支持")

    # 构建回退链：主供应商优先，其余可用供应商依次排列
    all_available_vendors = list(VENDOR_METHODS[method].keys())
    fallback_vendors = primary_vendors.copy()
    for vendor in all_available_vendors:
        if vendor not in fallback_vendors:
            fallback_vendors.append(vendor)

    for vendor in fallback_vendors:
        if vendor not in VENDOR_METHODS[method]:
            continue

        vendor_impl = VENDOR_METHODS[method][vendor]
        impl_func = vendor_impl[0] if isinstance(vendor_impl, list) else vendor_impl

        try:
            return impl_func(*args, **kwargs)
        except AlphaVantageRateLimitError:
            continue  # 仅在限流时触发回退

    raise RuntimeError(f"方法 '{method}' 没有可用的供应商")
