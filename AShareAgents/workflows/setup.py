# 图构建与配置模块：负责组装和管理A股智能分析工作流图。
# 提供GraphSetup类，根据选定的分析师类型动态创建节点和边，
# 串联分析师分析、多空辩论、交易决策和风险评估的全流程。

from typing import Any, Dict
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from AShareAgents.agents import *
from AShareAgents.tools.agent_states import AgentState

from .conditional_logic import ConditionalLogic


class GraphSetup:
    """负责智能体图的构建和配置。"""

    def __init__(
        self,
        quick_thinking_llm: Any,
        deep_thinking_llm: Any,
        tool_nodes: Dict[str, ToolNode],
        conditional_logic: ConditionalLogic,
    ):
        """初始化所需的组件依赖。

        Args:
            quick_thinking_llm: 快速思考LLM实例
            deep_thinking_llm: 深度思考LLM实例
            tool_nodes: 分析师类型到ToolNode的映射字典
            conditional_logic: 条件路由逻辑实例
        """
        self.quick_thinking_llm = quick_thinking_llm
        self.deep_thinking_llm = deep_thinking_llm
        self.tool_nodes = tool_nodes
        self.conditional_logic = conditional_logic

    def setup_graph(
        self, selected_analysts=["market", "social", "news", "fundamentals", "policy", "hot_money", "lockup"]
    ):
        """构建并编译智能体工作流图。

        Args:
            selected_analysts: 需要启用的分析师类型列表，可选：
                - "market": 市场分析师（技术分析）
                - "social": 社交媒体/情绪分析师
                - "news": 新闻分析师
                - "fundamentals": 基本面分析师
                - "policy": 政策分析师（A股专用）
                - "hot_money": 热钱/资金流向追踪（A股专用）
                - "lockup": 解禁/减持监控（A股专用）

        Returns:
            配置完成的StateGraph工作流实例

        Raises:
            ValueError: 未选择任何分析师时抛出
        """
        if len(selected_analysts) == 0:
            raise ValueError("A股智能分析图配置错误：未选择任何分析师！")

        # 创建分析师节点
        analyst_nodes = {}
        delete_nodes = {}
        tool_nodes = {}

        if "market" in selected_analysts:
            analyst_nodes["market"] = create_market_analyst(
                self.quick_thinking_llm
            )
            delete_nodes["market"] = create_msg_delete()
            tool_nodes["market"] = self.tool_nodes["market"]

        if "social" in selected_analysts:
            analyst_nodes["social"] = create_social_media_analyst(
                self.quick_thinking_llm
            )
            delete_nodes["social"] = create_msg_delete()
            tool_nodes["social"] = self.tool_nodes["social"]

        if "news" in selected_analysts:
            analyst_nodes["news"] = create_news_analyst(
                self.quick_thinking_llm
            )
            delete_nodes["news"] = create_msg_delete()
            tool_nodes["news"] = self.tool_nodes["news"]

        if "fundamentals" in selected_analysts:
            analyst_nodes["fundamentals"] = create_fundamentals_analyst(
                self.quick_thinking_llm
            )
            delete_nodes["fundamentals"] = create_msg_delete()
            tool_nodes["fundamentals"] = self.tool_nodes["fundamentals"]

        if "policy" in selected_analysts:
            analyst_nodes["policy"] = create_policy_analyst(
                self.quick_thinking_llm
            )
            delete_nodes["policy"] = create_msg_delete()
            tool_nodes["policy"] = self.tool_nodes["policy"]

        if "hot_money" in selected_analysts:
            analyst_nodes["hot_money"] = create_hot_money_tracker(
                self.quick_thinking_llm
            )
            delete_nodes["hot_money"] = create_msg_delete()
            tool_nodes["hot_money"] = self.tool_nodes["hot_money"]

        if "lockup" in selected_analysts:
            analyst_nodes["lockup"] = create_lockup_watcher(
                self.quick_thinking_llm
            )
            delete_nodes["lockup"] = create_msg_delete()
            tool_nodes["lockup"] = self.tool_nodes["lockup"]

        # 创建质量门控节点
        quality_gate_node = create_quality_gate(self.quick_thinking_llm)

        # 创建研究员和管理员节点
        bull_researcher_node = create_bull_researcher(self.quick_thinking_llm)
        bear_researcher_node = create_bear_researcher(self.quick_thinking_llm)
        research_manager_node = create_research_manager(self.deep_thinking_llm)
        trader_node = create_trader(self.quick_thinking_llm)

        # 创建风险分析节点
        aggressive_analyst = create_aggressive_debator(self.quick_thinking_llm)
        neutral_analyst = create_neutral_debator(self.quick_thinking_llm)
        conservative_analyst = create_conservative_debator(self.quick_thinking_llm)
        portfolio_manager_node = create_portfolio_manager(self.deep_thinking_llm)

        # 创建工作流
        workflow = StateGraph(AgentState)

        # 将分析师节点添加到图中
        for analyst_type, node in analyst_nodes.items():
            workflow.add_node(f"{analyst_type.capitalize()} Analyst", node)
            workflow.add_node(
                f"Msg Clear {analyst_type.capitalize()}", delete_nodes[analyst_type]
            )
            workflow.add_node(f"tools_{analyst_type}", tool_nodes[analyst_type])

        # 添加质量门控及其他节点
        workflow.add_node("Quality Gate", quality_gate_node)
        workflow.add_node("Bull Researcher", bull_researcher_node)
        workflow.add_node("Bear Researcher", bear_researcher_node)
        workflow.add_node("Research Manager", research_manager_node)
        workflow.add_node("Trader", trader_node)
        workflow.add_node("Aggressive Analyst", aggressive_analyst)
        workflow.add_node("Neutral Analyst", neutral_analyst)
        workflow.add_node("Conservative Analyst", conservative_analyst)
        workflow.add_node("Portfolio Manager", portfolio_manager_node)

        # 定义边
        # 从第一个分析师开始
        first_analyst = selected_analysts[0]
        workflow.add_edge(START, f"{first_analyst.capitalize()} Analyst")

        # 按顺序连接各分析师
        for i, analyst_type in enumerate(selected_analysts):
            current_analyst = f"{analyst_type.capitalize()} Analyst"
            current_tools = f"tools_{analyst_type}"
            current_clear = f"Msg Clear {analyst_type.capitalize()}"

            # 为当前分析师添加条件边
            workflow.add_conditional_edges(
                current_analyst,
                getattr(self.conditional_logic, f"should_continue_{analyst_type}"),
                [current_tools, current_clear],
            )
            workflow.add_edge(current_tools, current_analyst)

            # 连接到下一个分析师，若是最后一个则连接到质量门控
            if i < len(selected_analysts) - 1:
                next_analyst = f"{selected_analysts[i+1].capitalize()} Analyst"
                workflow.add_edge(current_clear, next_analyst)
            else:
                workflow.add_edge(current_clear, "Quality Gate")

        workflow.add_edge("Quality Gate", "Bull Researcher")

        # 添加其余边
        workflow.add_conditional_edges(
            "Bull Researcher",
            self.conditional_logic.should_continue_debate,
            {
                "Bear Researcher": "Bear Researcher",
                "Research Manager": "Research Manager",
            },
        )
        workflow.add_conditional_edges(
            "Bear Researcher",
            self.conditional_logic.should_continue_debate,
            {
                "Bull Researcher": "Bull Researcher",
                "Research Manager": "Research Manager",
            },
        )
        workflow.add_edge("Research Manager", "Trader")
        workflow.add_edge("Trader", "Aggressive Analyst")
        workflow.add_conditional_edges(
            "Aggressive Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {
                "Conservative Analyst": "Conservative Analyst",
                "Portfolio Manager": "Portfolio Manager",
            },
        )
        workflow.add_conditional_edges(
            "Conservative Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {
                "Neutral Analyst": "Neutral Analyst",
                "Portfolio Manager": "Portfolio Manager",
            },
        )
        workflow.add_conditional_edges(
            "Neutral Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {
                "Aggressive Analyst": "Aggressive Analyst",
                "Portfolio Manager": "Portfolio Manager",
            },
        )

        workflow.add_edge("Portfolio Manager", END)

        return workflow
