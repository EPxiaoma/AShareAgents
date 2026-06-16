"""新闻分析师模块，收集和分析 A 股市场新闻动态，评估政策、行业和公司层面消息对股价的影响。"""

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from AShareAgents.tools.agent_helpers import (
    build_instrument_context,
    get_language_instruction,
)
from AShareAgents.tools.tool_registry import (
    get_global_news,
    get_news,
)
from AShareAgents.datasource.config import get_config


def create_news_analyst(llm):
    def news_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = [
            get_news,
            get_global_news,
        ]

        system_message = (
            "你是一位专注于 A 股市场的新闻与政策分析师。你的任务是分析近期新闻动态，评估其对目标公司和 A 股市场的影响。"
            "\n\n⚠️ A 股新闻分析框架："
            "\n- **政策敏感度**：A 股是典型的「政策市」，国务院/证监会/央行/发改委的政策发布对市场影响巨大。重点关注：货币政策（降准降息）、产业政策（扶持/限制）、监管政策（IPO 节奏、再融资、减持新规）。"
            "\n- **消息来源权重**：财联社快讯（最快）> 新华财经/证券时报（权威）> 东方财富/同花顺（广泛）。注意区分官方消息与市场传闻。"
            "\n- **行业轮动**：A 股板块轮动特征明显，一个行业利好政策可能带动整个板块，分析时需关注产业链上下游联动。"
            "\n- **事件驱动**：关注财报预告/业绩快报、股东大会决议、重大合同公告、机构调研记录等公司层面事件。"
            "\n\n请使用以下工具："
            "\n- `get_news(query, start_date, end_date)`：获取公司相关的个股新闻"
            "\n- `get_global_news(curr_date, look_back_days, limit)`：获取宏观经济和市场整体新闻"
            "\n\n撰写全面的新闻分析报告，区分利好/利空/中性消息，评估影响程度和持续时间。报告末尾附 Markdown 表格汇总关键新闻事件及其影响评级。"
            "\n\n📋 必采清单 — 以下数据点必须出现在报告中，无法获取时标注 [数据缺失: xxx]："
            "\n1. 个股新闻条数和时间范围"
            "\n2. 宏观新闻条数和时间范围"
            "\n3. 关键事件时间线（至少列出 3 个重要事件及日期）"
            "\n4. 利好/利空/中性事件分类统计"
            "\n5. 风险事件清单（如有）"
            + get_language_instruction()
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你是一个乐于助人的 AI 助手，与其他助手协作完成任务。"
                    " 使用提供的工具推进问题的解答。"
                    " 如果你无法完全回答，没关系；其他拥有不同工具的助手"
                    " 会在你停下的地方继续。尽你所能推动进展。"
                    " 如果你或其他助手得到了最终交易建议：**买入/持有/卖出** 或可交付成果，"
                    " 请在回复前加上 最终交易建议：**买入/持有/卖出**，以便团队知道可以停止。"
                    " 你可以使用以下工具：{tool_names}。\n{system_message}"
                    "供你参考，当前日期是 {current_date}。{instrument_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        chain = prompt | llm.bind_tools(tools)
        result = chain.invoke(state["messages"])

        report = ""

        if len(result.tool_calls) == 0:
            report = result.content

        return {
            "messages": [result],
            "news_report": report,
        }

    return news_analyst_node
