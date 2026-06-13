def create_conservative_debator(llm):
    def conservative_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        conservative_history = risk_debate_state.get("conservative_history", "")

        current_aggressive_response = risk_debate_state.get("current_aggressive_response", "")
        current_neutral_response = risk_debate_state.get("current_neutral_response", "")

        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]
        policy_report = state.get("policy_report", "")
        hot_money_report = state.get("hot_money_report", "")
        lockup_report = state.get("lockup_report", "")

        trader_decision = state["trader_investment_plan"]

        prompt = f"""作为评估A股（中国大陆）股票的保守型风险分析师，您的首要目标是保护资产、最小化波动并确保稳定可靠的增值。严格审查交易员方案中的高风险要素，指出其可能使公司暴露于不当风险之处。

A股保守框架——强调以下中国特有的下行风险：
- T+1结算锁定：当日建立的任何仓位须等到次日才能退出。若股票开盘即跳空低开（例如隔夜政策新闻或全球抛售），亏损将被锁定且无法补救。这是A股市场最重要的结构性风险。
- 涨跌停板陷阱：若股票跌停（主板-10%，科创板/创业板-20%），卖单无法执行——您被锁定其中。连续多个跌停可导致灾难性损失而完全无法退出。
- 解禁抛压悬顶：大额限售解禁会产生巨大的潜在抛售压力。即使内部人尚未开始卖出，其卖出期权本身就足以压制市场情绪并限制上行空间。
- 政策逆转风险：A股是政策市。政府可以给予支持，也可以一夜之间收回——一条国务院指令就足以将行业支持转为行业整顿。
- 游资撤退风险：游资进出都极快。今天的涨停龙头就是明天的跌停牺牲品。当游资撤退时，散户总是最后一个知道。
- 估值纪律：市盈率 > 50倍且PEG > 2，无论增长叙事多么动听，都属于投机区域。应以30倍市盈率消化框架为锚——若需5年以上才能消化，该仓位即被高估。
- ST/退市风险：对于连续亏损的公司，ST标识将触发 ±5% 的涨跌幅限制和机构强制卖出。

以下是交易员的方案：

{trader_decision}

反驳激进型和中性分析师。指出他们的乐观情绪在何处忽视了A股的结构性风险。请使用以下数据源：

市场研究报告：{market_research_report}
社交媒体情绪报告：{sentiment_report}
最新新闻报告：{news_report}
公司基本面报告：{fundamentals_report}
政策分析报告：{policy_report}
游资/资金流向报告：{hot_money_report}
解禁/减持报告：{lockup_report}
辩论历史记录：{history} 激进方上一次论点：{current_aggressive_response} 中立方上一次论点：{current_neutral_response}。若尚无回复，请陈述您自己的观点。

论证为何保守立场是最安全的路径，尤其是在A股市场结构中，下行保护机制（止损、当日退出）严重受限的环境下。以对话方式输出，无需特殊格式。"""

        response = llm.invoke(prompt)

        argument = f"Conservative Analyst: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "aggressive_history": risk_debate_state.get("aggressive_history", ""),
            "conservative_history": conservative_history + "\n" + argument,
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": "Conservative",
            "current_aggressive_response": risk_debate_state.get(
                "current_aggressive_response", ""
            ),
            "current_conservative_response": argument,
            "current_neutral_response": risk_debate_state.get(
                "current_neutral_response", ""
            ),
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return conservative_node
