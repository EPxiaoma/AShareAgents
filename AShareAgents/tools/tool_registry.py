"""暴露给 Agent 图节点使用的工具注册表。"""

from __future__ import annotations

from AShareAgents.rag.tools import (
    search_company_official_documents,
    search_policy_industry_knowledge,
)
from AShareAgents.tools.core_stock_tools import get_stock_data
from AShareAgents.tools.fundamental_data_tools import (
    get_balance_sheet,
    get_cashflow,
    get_fundamentals,
    get_income_statement,
)
from AShareAgents.tools.news_data_tools import (
    get_global_news,
    get_insider_transactions,
    get_news,
)
from AShareAgents.tools.signal_data_tools import (
    get_concept_blocks,
    get_dragon_tiger_board,
    get_fund_flow,
    get_hot_stocks,
    get_industry_comparison,
    get_lockup_expiry,
    get_northbound_flow,
    get_profit_forecast,
)
from AShareAgents.tools.technical_indicators_tools import get_indicators

__all__ = [
    "get_balance_sheet",
    "get_cashflow",
    "get_concept_blocks",
    "get_dragon_tiger_board",
    "get_fund_flow",
    "get_fundamentals",
    "get_global_news",
    "get_hot_stocks",
    "get_income_statement",
    "get_indicators",
    "get_industry_comparison",
    "get_insider_transactions",
    "get_lockup_expiry",
    "get_news",
    "get_northbound_flow",
    "get_profit_forecast",
    "get_stock_data",
    "search_company_official_documents",
    "search_policy_industry_knowledge",
]
