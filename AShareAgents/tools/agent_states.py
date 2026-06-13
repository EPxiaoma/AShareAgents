from typing import Annotated
from typing_extensions import TypedDict
from langgraph.graph import MessagesState


# 研究员团队状态
class InvestDebateState(TypedDict):
    bull_history: Annotated[
        str, "多头对话历史"
    ]  # 多头对话历史
    bear_history: Annotated[
        str, "空头对话历史"
    ]  # 空头对话历史
    history: Annotated[str, "对话历史"]  # 对话历史
    current_response: Annotated[str, "最近一次回复"]  # 最近一次回复
    judge_decision: Annotated[str, "最终评判结果"]  # 最终评判结果
    count: Annotated[int, "当前对话轮数"]  # 对话轮数


# 风险管理团队状态
class RiskDebateState(TypedDict):
    aggressive_history: Annotated[
        str, "激进分析师的对话历史"
    ]  # 对话历史
    conservative_history: Annotated[
        str, "保守分析师的对话历史"
    ]  # 对话历史
    neutral_history: Annotated[
        str, "中立分析师的对话历史"
    ]  # 对话历史
    history: Annotated[str, "对话历史"]  # 对话历史
    latest_speaker: Annotated[str, "最近发言的分析师"]
    current_aggressive_response: Annotated[
        str, "激进分析师的最新回复"
    ]  # 最近一次回复
    current_conservative_response: Annotated[
        str, "保守分析师的最新回复"
    ]  # 最近一次回复
    current_neutral_response: Annotated[
        str, "中立分析师的最新回复"
    ]  # 最近一次回复
    judge_decision: Annotated[str, "评委的决定"]
    count: Annotated[int, "当前对话轮数"]  # 对话轮数


class AgentState(MessagesState):
    company_of_interest: Annotated[str, "当前交易关注的公司"]
    trade_date: Annotated[str, "当前交易日期"]

    sender: Annotated[str, "发送此消息的 Agent"]

    # 研究阶段
    market_report: Annotated[str, "市场分析师的报告"]
    sentiment_report: Annotated[str, "社交舆情分析师的报告"]
    news_report: Annotated[
        str, "新闻研究员关于当前全球事件的报告"
    ]
    fundamentals_report: Annotated[str, "基本面研究员的报告"]
    policy_report: Annotated[str, "政策分析师（A股专用）的报告"]
    hot_money_report: Annotated[str, "游资追踪师（A股专用）的报告"]
    lockup_report: Annotated[str, "限售解禁观察员（A股专用）的报告"]

    # 数据质量门槛
    data_quality_summary: Annotated[str, "所有分析师报告的质量把关评估（硬性检查+LLM复核）"]

    # 研究员团队讨论阶段
    investment_debate_state: Annotated[
        InvestDebateState, "关于是否投资的辩论当前状态"
    ]
    investment_plan: Annotated[str, "分析师制定的投资方案"]

    trader_investment_plan: Annotated[str, "交易员制定的投资方案"]

    # 风险管理团队讨论阶段
    risk_debate_state: Annotated[
        RiskDebateState, "风险评估辩论的当前状态"
    ]
    final_trade_decision: Annotated[str, "风险分析师做出的最终决策"]
    past_context: Annotated[str, "运行启动时注入的记忆日志上下文（同标的决策+跨标的经验）"]
