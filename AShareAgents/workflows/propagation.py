"""构造工作流初始状态并执行图调用。

该模块集中管理辩论子状态、递归限制和运行时回调参数。
"""

from typing import Dict, Any, List, Optional
from AShareAgents.tools.agent_states import (
    AgentState,
    InvestDebateState,
    RiskDebateState,
)


class Propagator:
    """负责工作流图中的状态初始化和传播。"""

    def __init__(self, max_recur_limit=100):
        """使用配置参数初始化。

        Args:
            max_recur_limit: 图递归调用的最大次数限制
        """
        self.max_recur_limit = max_recur_limit

    def create_initial_state(
        self, company_name: str, trade_date: str, past_context: str = ""
    ) -> Dict[str, Any]:
        """创建智能体图的初始状态。

        Args:
            company_name: 目标公司名称/股票代码
            trade_date: 分析对应的交易日期
            past_context: 该股票的历史反思上下文

        Returns:
            包含所有初始字段的AgentState字典
        """
        return {
            "messages": [("human", company_name)],
            "company_of_interest": company_name,
            "trade_date": str(trade_date),
            "past_context": past_context,
            "investment_debate_state": InvestDebateState(
                {
                    "bull_history": "",
                    "bear_history": "",
                    "history": "",
                    "current_response": "",
                    "judge_decision": "",
                    "count": 0,
                }
            ),
            "risk_debate_state": RiskDebateState(
                {
                    "aggressive_history": "",
                    "conservative_history": "",
                    "neutral_history": "",
                    "history": "",
                    "latest_speaker": "",
                    "current_aggressive_response": "",
                    "current_conservative_response": "",
                    "current_neutral_response": "",
                    "judge_decision": "",
                    "count": 0,
                }
            ),
            "market_report": "",
            "fundamentals_report": "",
            "sentiment_report": "",
            "news_report": "",
            "policy_report": "",
            "hot_money_report": "",
            "lockup_report": "",
        }

    def get_graph_args(self, callbacks: Optional[List] = None) -> Dict[str, Any]:
        """获取图调用所需的参数。

        Args:
            callbacks: 可选的工具执行回调处理器列表。
                LLM回调单独通过LLM构造函数处理。

        Returns:
            包含stream_mode和config的参数字典
        """
        config = {"recursion_limit": self.max_recur_limit}
        if callbacks:
            config["callbacks"] = callbacks
        return {
            "stream_mode": "values",
            "config": config,
        }
