"""定义 LangGraph 工作流的条件路由规则。

该模块统一控制工具调用、多空辩论和风险讨论的节点流转。
"""

from AShareAgents.tools.agent_states import AgentState


class ConditionalLogic:
    """负责决定工作流图中条件分支和流转方向。"""

    def __init__(self, max_debate_rounds=1, max_risk_discuss_rounds=1):
        """使用配置参数初始化。

        Args:
            max_debate_rounds: 多空辩论的最大轮次
            max_risk_discuss_rounds: 风险分析讨论的最大轮次
        """
        self.max_debate_rounds = max_debate_rounds
        self.max_risk_discuss_rounds = max_risk_discuss_rounds

    def should_continue_market(self, state: AgentState):
        """判断市场分析是否应继续调用工具。

        Returns:
            有工具调用时返回 "tools_market"，否则返回 "Msg Clear Market"
        """
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            return "tools_market"
        return "Msg Clear Market"

    def should_continue_social(self, state: AgentState):
        """判断社交媒体分析是否应继续调用工具。

        Returns:
            有工具调用时返回 "tools_social"，否则返回 "Msg Clear Social"
        """
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            return "tools_social"
        return "Msg Clear Social"

    def should_continue_news(self, state: AgentState):
        """判断新闻分析是否应继续调用工具。

        Returns:
            有工具调用时返回 "tools_news"，否则返回 "Msg Clear News"
        """
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            return "tools_news"
        return "Msg Clear News"

    def should_continue_fundamentals(self, state: AgentState):
        """判断基本面分析是否应继续调用工具。

        Returns:
            有工具调用时返回 "tools_fundamentals"，否则返回 "Msg Clear Fundamentals"
        """
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            return "tools_fundamentals"
        return "Msg Clear Fundamentals"

    def should_continue_policy(self, state: AgentState):
        """判断政策分析是否应继续调用工具。

        Returns:
            有工具调用时返回 "tools_policy"，否则返回 "Msg Clear Policy"
        """
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            return "tools_policy"
        return "Msg Clear Policy"

    def should_continue_hot_money(self, state: AgentState):
        """判断热钱追踪是否应继续调用工具。

        Returns:
            有工具调用时返回 "tools_hot_money"，否则返回 "Msg Clear Hot_money"
        """
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            return "tools_hot_money"
        return "Msg Clear Hot_money"

    def should_continue_lockup(self, state: AgentState):
        """判断解禁/减持分析是否应继续调用工具。

        Returns:
            有工具调用时返回 "tools_lockup"，否则返回 "Msg Clear Lockup"
        """
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            return "tools_lockup"
        return "Msg Clear Lockup"

    def should_continue_debate(self, state: AgentState) -> str:
        """判断多空辩论是否应继续。

        根据辩论轮次计数和当前发言人决定下一节点。

        Returns:
            辩论未结束时返回发言方节点名，否则返回 "Research Manager"
        """
        if (
            state["investment_debate_state"]["count"] >= 2 * self.max_debate_rounds
        ):  # 两个智能体之间互辩3轮
            return "Research Manager"
        if state["investment_debate_state"]["current_response"].startswith("Bull"):
            return "Bear Researcher"
        return "Bull Researcher"

    def should_continue_risk_analysis(self, state: AgentState) -> str:
        """判断风险分析辩论是否应继续。

        根据风险辩论轮次计数和最新发言人决定下一节点。

        Returns:
            辩论未结束时返回下一位分析师节点名，否则返回 "Portfolio Manager"
        """
        if (
            state["risk_debate_state"]["count"] >= 3 * self.max_risk_discuss_rounds
        ):  # 三个智能体之间互辩3轮
            return "Portfolio Manager"
        if state["risk_debate_state"]["latest_speaker"].startswith("Aggressive"):
            return "Conservative Analyst"
        if state["risk_debate_state"]["latest_speaker"].startswith("Conservative"):
            return "Neutral Analyst"
        return "Aggressive Analyst"
