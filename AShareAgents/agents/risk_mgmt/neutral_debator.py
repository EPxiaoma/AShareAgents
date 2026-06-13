"""创建中性风险观点节点，在收益机会与风险约束之间进行权衡。"""

def create_neutral_debator(llm):
    def neutral_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        neutral_history = risk_debate_state.get("neutral_history", "")

        current_aggressive_response = risk_debate_state.get("current_aggressive_response", "")
        current_conservative_response = risk_debate_state.get("current_conservative_response", "")

        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]
        policy_report = state.get("policy_report", "")
        hot_money_report = state.get("hot_money_report", "")
        lockup_report = state.get("lockup_report", "")

        trader_decision = state["trader_investment_plan"]

        prompt = f"""作为评估A股（中国大陆）股票的中性风险分析师，您的角色是提供一种平衡的视角，权衡潜在的收益和风险。充分考虑A股市场结构、更广泛的市场趋势和分散化策略。

A股中性框架——使用以下中国特有的平衡考虑因素：
- T+1作为双刃剑：T+1锁定亏损（保守方观点），但也防止恐慌性抛售并允许多日动能发展（激进方观点）。中性看法是：将仓位规模控制在单一隔夜跳空下跌是可承受的范围内。
- 政策信号敏感性校准：并非所有政策信号都具有同等分量。区分顶层国务院指令（高置信度）vs 地方政府激励措施（较低可靠性）vs 市场传闻（噪音）。据此调整风险评估权重。
- 北向资金作为聪明钱指标：通过沪深港通的外资机构资金流向比散户资金更具信息含量，但也更不稳定——他们比国内基金更快撤离。将其作为确认信号，而非投资主论据。
- 估值区间方法：与其僵化地认为"市盈率 > 30倍就是昂贵"或"成长股不必看市盈率"，不如提出一个估值区间——鉴于盈利增长轨迹，什么样的市盈率区间是可以接受的？将市盈率消化周期作为实用的锚定依据。
- 解禁时点评估：中性观点不应在解禁日期恐慌，而应监控实际的减持公告。风险是真实的，但时机是不确定的——在解禁窗口期附近逐步降低暴露，比二元化的全仓进出更为明智。
- 板块轮动敏感性：A股题材轮动速度快（通常2-4周）。中性的问题是：我们处于轮动周期的哪个阶段？轮动初期 = 仍有上涨空间；轮动末期 = 上行空间缩减而下行风险上升。
- 仓位管理优先于方向判断：在每日±10-20%涨跌幅限制和T+1结算的市场中，仓位管理比方向判断更为重要。中等仓位既可捕捉上行空间，又能限制锁定亏损的场景。

以下是交易员的方案：

{trader_decision}

同时挑战激进型和保守型分析师。指出在A股语境下，各方视角在何处过度乐观或过度谨慎。请使用以下数据源：

市场研究报告：{market_research_report}
社交媒体情绪报告：{sentiment_report}
最新新闻报告：{news_report}
公司基本面报告：{fundamentals_report}
政策分析报告：{policy_report}
游资/资金流向报告：{hot_money_report}
解禁/减持报告：{lockup_report}
辩论历史记录：{history} 激进方上一次论点：{current_aggressive_response} 保守方上一次论点：{current_conservative_response}。若尚无回复，请陈述您自己的观点。

倡导一种平衡的、以仓位管理为核心的方法，既捕捉A股上行空间，又尊重市场的结构性约束。以对话方式输出，无需特殊格式。"""

        response = llm.invoke(prompt)

        argument = f"Neutral Analyst: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "aggressive_history": risk_debate_state.get("aggressive_history", ""),
            "conservative_history": risk_debate_state.get("conservative_history", ""),
            "neutral_history": neutral_history + "\n" + argument,
            "latest_speaker": "Neutral",
            "current_aggressive_response": risk_debate_state.get(
                "current_aggressive_response", ""
            ),
            "current_conservative_response": risk_debate_state.get("current_conservative_response", ""),
            "current_neutral_response": argument,
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return neutral_node
