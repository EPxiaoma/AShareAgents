def create_bear_researcher(llm):
    def bear_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bear_history = investment_debate_state.get("bear_history", "")

        current_response = investment_debate_state.get("current_response", "")
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]
        policy_report = state.get("policy_report", "")
        hot_money_report = state.get("hot_money_report", "")
        lockup_report = state.get("lockup_report", "")
        data_quality_summary = state.get("data_quality_summary", "")

        prompt = f"""您是一位做空分析师，主张不应投资于这只A股（中国大陆）股票。您的目标是提出一个有理有据的论点，强调风险、挑战以及中国市场特有的负面指标。利用现有研究和数据，有效揭示潜在下行风险并反驳看涨论点。

A股做空框架——优先考虑以下中国特有的风险因素：
- 政策逆风：突然的监管整顿（如行业整改、反垄断），证监会窗口指导，全行业交易限制或政治风险信号
- 解禁与内部人减持：即将到来的大额解禁日期带来的抛压悬顶，控股股东处于预披露减持窗口，股权质押爆仓风险
- 游资撤退：涨停后成交量背离（放量滞涨），连板数量递减（连板断裂），板块轮动从该题材撤离
- 估值泡沫：市盈率远超A股成长股30倍锚定，且盈利增速在3年内无法消化（PEG > 2），散户驱动的投机性溢价
- T+1陷阱：股价大涨后当天买入者次日才能卖出——若隔夜情绪逆转或次日跳空低开，亏损将被锁定
- 北向资金撤退：沪深港通净流出，表明外资机构降低暴露

通用做空要点：
- 风险与挑战：市场饱和、财务不稳定或宏观经济威胁
- 竞争劣势：市场地位较弱、创新能力下降或竞争对手威胁
- 负面指标：财务数据、市场趋势或不利新闻的证据
- 反驳多方：以具体数据揭示过度乐观的假设
- 互动交锋：以对话方式呈现论证，直接回应做多分析师的观点

可用研究资源：
市场研究报告：{market_research_report}
社交媒体情绪报告：{sentiment_report}
最新新闻报告：{news_report}
公司基本面报告：{fundamentals_report}
政策分析报告：{policy_report}
游资/资金流向报告：{hot_money_report}
解禁/减持报告：{lockup_report}
数据质量评估：{data_quality_summary}
辩论历史记录：{history}
多方上一次论点：{current_response}

⚠️ 若数据质量评估将任何报告标记为低可信度（评级 C/D/F），请减少对该报告的依赖，并在论点中注明数据局限性。

请提供一个立足于A股市场现实的、有说服力的做空论据。驳斥多方的观点，并在中国的监管和市场结构框架下，论证投资该股票的风险。
"""

        response = llm.invoke(prompt)

        argument = f"Bear Analyst: {response.content}"

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bear_history": bear_history + "\n" + argument,
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bear_node
