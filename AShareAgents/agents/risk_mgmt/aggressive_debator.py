"""创建激进风险观点节点，为高风险高收益策略提供论证。"""

def create_aggressive_debator(llm):
    def aggressive_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        aggressive_history = risk_debate_state.get("aggressive_history", "")

        current_conservative_response = risk_debate_state.get("current_conservative_response", "")
        current_neutral_response = risk_debate_state.get("current_neutral_response", "")

        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]
        policy_report = state.get("policy_report", "")
        hot_money_report = state.get("hot_money_report", "")
        lockup_report = state.get("lockup_report", "")

        trader_decision = state["trader_investment_plan"]

        prompt = f"""作为评估A股（中国大陆）股票的激进型风险分析师，您的角色是倡导高回报机会和大胆策略。聚焦于潜在上行空间、增长潜力和市场动能——即使这些伴随着较高风险。用基于数据的论据反驳保守型和中性分析师。

A股激进框架——利用以下中国特有的上行论点：
- 涨停板效应：在A股市场中，连续涨停会创造强大动能；T+1制度实际上有助于防止当日获利了结，从而实现多日连续拉升
- 政策驱动行业：当北京方面支持某一行业（如AI、芯片、新能源），政策托底是真实的——政府支持形成了一个在西方市场中不存在的底部
- 游资持仓信心：当顶级游资席位以明确的理由标签大举介入时，短期上行空间可能极具爆发力；错失这类行情本身也是一种风险
- 北向资金验证：若通过沪深港通的外资机构与国内资金同步净买入，这一双重确认是强烈的买入信号
- 市盈率扩张阶段：在A股牛市周期中，主线龙头市盈率常规可扩张至50-100倍；过早套用美股估值纪律意味着错失主升浪
- 散户情绪助力：A股市场80%为散户；当情绪转为积极时，羊群效应会放大收益，远超基本面自身所能解释的程度

以下是交易员的方案：

{trader_decision}

挑战保守型和中性观点。论证他们的谨慎为何可能错失机会。请使用以下数据源：

市场研究报告：{market_research_report}
社交媒体情绪报告：{sentiment_report}
最新新闻报告：{news_report}
公司基本面报告：{fundamentals_report}
政策分析报告：{policy_report}
游资/资金流向报告：{hot_money_report}
解禁/减持报告：{lockup_report}
辩论历史记录：{history} 保守方上一次论点：{current_conservative_response} 中立方上一次论点：{current_neutral_response}。若尚无回复，请陈述您自己的观点。

积极参与，有说服力地辩论，并论证为何激进型仓位配置是最适合这次A股机会的策略。以对话方式输出，无需特殊格式。"""

        response = llm.invoke(prompt)

        argument = f"Aggressive Analyst: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "aggressive_history": aggressive_history + "\n" + argument,
            "conservative_history": risk_debate_state.get("conservative_history", ""),
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": "Aggressive",
            "current_aggressive_response": argument,
            "current_conservative_response": risk_debate_state.get("current_conservative_response", ""),
            "current_neutral_response": risk_debate_state.get(
                "current_neutral_response", ""
            ),
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return aggressive_node
