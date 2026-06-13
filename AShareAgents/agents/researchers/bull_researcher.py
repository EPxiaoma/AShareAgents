"""创建多头研究节点，基于现有报告论证潜在投资价值。"""

def create_bull_researcher(llm):
    def bull_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bull_history = investment_debate_state.get("bull_history", "")

        current_response = investment_debate_state.get("current_response", "")
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]
        policy_report = state.get("policy_report", "")
        hot_money_report = state.get("hot_money_report", "")
        lockup_report = state.get("lockup_report", "")
        data_quality_summary = state.get("data_quality_summary", "")

        prompt = f"""您是一位做多分析师，力主投资于这只A股（中国大陆）股票。您的任务是构建一个强有力的、基于证据的论点，强调增长潜力、竞争优势和积极的市场指标。利用现有研究和数据，有效回应担忧并反驳看跌论点。

A股做多框架——优先考虑以下中国特有的看涨驱动因素：
- 政策顺风：政府补贴、产业支持政策（如"专精特新"、国家战略产业），证监会/国务院的有利监管信号
- 北向资金：沪深港通的持续净流入表明外资机构信心
- 游资接力：连续涨停且成交量确认，题材归属明确（理由标签），板块轮动刚刚启动
- 估值成长逻辑：使用前瞻市盈率(P/E)、PEG 和市盈率消化周期（A股成长股30倍锚定），论证当前溢价由盈利增长轨迹所支撑
- 解禁压力释放：若主要解禁期已过，或内部人未在减持，则消除了一个关键利空悬顶

通用做多要点：
- 增长潜力：市场机遇、营收预测和可扩展性
- 竞争优势：独特产品、主导市场地位或国内市场护城河
- 积极指标：财务健康、行业趋势和近期利好消息
- 反驳空方：以具体数据和合理推理，批判性分析空方论点
- 互动交锋：以对话方式呈现论证，直接回应做空分析师的观点

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
空方上一次论点：{current_response}

⚠️ 若数据质量评估将任何报告标记为低可信度（评级 C/D/F），请减少对该报告的依赖，并在论点中注明数据局限性。

请提供一个充分融入A股市场动态的、有说服力的做多论据。驳斥空方的疑虑，并论证在A股市场环境下您的做多立场为何更具优势。
"""

        response = llm.invoke(prompt)

        argument = f"Bull Analyst: {response.content}"

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bull_history": bull_history + "\n" + argument,
            "bear_history": investment_debate_state.get("bear_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bull_node
