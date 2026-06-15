"""汇总 Agent 可调用工具并提供消息状态辅助函数。"""

from langchain_core.messages import HumanMessage, RemoveMessage

# 从各工具文件中导入工具函数
from AShareAgents.tools.core_stock_tools import (
    get_stock_data
)
from AShareAgents.tools.technical_indicators_tools import (
    get_indicators
)
from AShareAgents.tools.fundamental_data_tools import (
    get_fundamentals,
    get_balance_sheet,
    get_cashflow,
    get_income_statement
)
from AShareAgents.tools.news_data_tools import (
    get_news,
    get_insider_transactions,
    get_global_news
)
from AShareAgents.tools.signal_data_tools import (
    get_profit_forecast,
    get_hot_stocks,
    get_northbound_flow,
    get_concept_blocks,
    get_fund_flow,
    get_dragon_tiger_board,
    get_lockup_expiry,
    get_industry_comparison,
)
from AShareAgents.rag.tools import (
    search_company_official_documents,
    search_policy_industry_knowledge,
)


def get_language_instruction() -> str:
    """返回针对配置的输出语言的提示指令。

    当语言为英文（默认）时返回空字符串，不消耗额外 token。
    仅对面向用户的 agent（分析师、投资组合经理）生效。
    内部辩论 agent 保持英文以保证推理质量。
    """
    from AShareAgents.datasource.config import get_config
    lang = get_config().get("output_language", "English")
    if lang.strip().lower() == "english":
        return ""
    return f" Write your entire response in {lang}."


def build_instrument_context(ticker: str) -> str:
    """描述具体的交易标的，确保 agent 保留交易所限定的代码格式。"""
    return (
        f"The instrument to analyze is `{ticker}`. "
        "Use this exact ticker in every tool call, report, and recommendation, "
        "preserving any exchange suffix (e.g. `.TO`, `.L`, `.HK`, `.T`)."
    )

def create_msg_delete():
    def delete_messages(state):
        """清除消息并添加占位符，以兼容 Anthropic"""
        messages = state["messages"]

        # 移除所有消息
        removal_operations = [RemoveMessage(id=m.id) for m in messages]

        # 添加一条最小占位消息
        placeholder = HumanMessage(content="Continue")

        return {"messages": removal_operations + [placeholder]}

    return delete_messages



