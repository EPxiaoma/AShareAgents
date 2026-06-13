"""市场情绪分析师模块，通过分析新闻和舆论推断 A 股市场情绪方向、强度和可能的转折点。"""

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from AShareAgents.tools.agent_utils import build_instrument_context, get_language_instruction, get_news
from AShareAgents.datasource.config import get_config


def create_social_media_analyst(llm):
    def social_media_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = [
            get_news,
        ]

        system_message = (
            "你是一位专注于 A 股市场的市场情绪分析师。你的任务是通过分析公司相关新闻、市场讨论和公众情绪，判断市场对目标公司的整体态度和情绪走向。"
            "\n\n⚠️ A 股情绪分析框架："
            "\n- **散户情绪权重高**：A 股散户占比超过 60%，市场情绪对股价的短期影响远大于成熟市场。恐慌和贪婪的情绪波动更剧烈。"
            "\n- **舆论阵地**：东方财富股吧、雪球、同花顺社区是 A 股投资者最活跃的讨论平台。分析新闻时注意推断这些平台可能的情绪反应。"
            "\n- **情绪指标**：关注以下情绪信号 - 连续涨停后的追涨情绪、业绩暴雷后的恐慌抛售、机构调研后的预期变化、热门概念炒作的跟风程度。"
            "\n- **反向指标**：当市场情绪一致性过高（极度乐观或极度悲观）时，往往是反转信号。散户一致看多可能是阶段顶部。"
            "\n- **时间维度**：区分短期情绪波动（1-3 天，由单一事件驱动）和中期情绪趋势（1-4 周，由基本面变化驱动）。"
            "\n\n请使用 `get_news(query, start_date, end_date)` 工具获取公司相关新闻和市场讨论。从新闻内容中推断市场情绪方向、强度和可能的转折点。"
            "\n\n撰写详细的市场情绪分析报告，包含情绪评分（极度悲观/悲观/中性/乐观/极度乐观）和趋势判断。报告末尾附 Markdown 表格汇总情绪信号和结论。"
            "\n\n📋 必采清单 — 以下数据点必须出现在报告中，无法获取时标注 [数据缺失: xxx]："
            "\n1. 新闻检索条数和时间范围"
            "\n2. 正面/负面/中性新闻比例"
            "\n3. 排名前 3 的舆情主题"
            "\n4. 情绪评分（极度悲观/悲观/中性/乐观/极度乐观）"
            "\n5. 情绪趋势变化方向（升温/降温/平稳）"
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
            "sentiment_report": report,
        }

    return social_media_analyst_node
