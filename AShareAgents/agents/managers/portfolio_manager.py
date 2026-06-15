"""投资组合经理：综合风险分析师辩论，形成最终投资决策。

利用 LangChain 的 ``with_structured_output`` 使 LLM 在一次调用中直接生成
类型化的 ``PortfolioDecision``。结果被渲染为 markdown 并存入
``final_trade_decision``，确保内存日志、CLI 显示和保存的报告
持续使用相同的格式。当模型提供商不支持结构化输出时，
该智能体会优雅降级为自由文本生成。
"""

from __future__ import annotations

from AShareAgents.models.agent_schemas import PortfolioDecision, render_pm_decision
from AShareAgents.tools.agent_utils import (
    build_instrument_context,
    get_language_instruction,
)
from AShareAgents.tools.structured import (
    bind_structured,
    invoke_structured_or_freetext,
)


def create_portfolio_manager(llm):
    structured_llm = bind_structured(llm, PortfolioDecision, "Portfolio Manager")

    def portfolio_manager_node(state) -> dict:
        instrument_context = build_instrument_context(state["company_of_interest"])

        history = state["risk_debate_state"]["history"]
        risk_debate_state = state["risk_debate_state"]
        research_plan = state["investment_plan"]
        trader_plan = state["trader_investment_plan"]

        past_context = state.get("past_context", "")
        lessons_line = (
            f"- 历史决策经验教训：\n{past_context}\n"
            if past_context
            else ""
        )

        prompt = f"""作为投资组合经理，请综合风控分析师的辩论，形成最终交易决策。

{instrument_context}

---

**A股交易限制**（决策时必须纳入考量）：
- T+1 结算：当日买入的股票需等到下一个交易日才能卖出
- 涨跌幅限制：主板 ±10%，科创板/创业板 ±20%，ST 股 ±5%
- 最小交易单位：主板 100 股（1 手）；科创板/创业板 200 股
- 交易时间：北京时间 09:30-11:30，13:00-15:00
- ST/退市风险：ST 或 *ST 状态代表监管警示，须纳入仓位管理考量
- 融资融券资格：并非所有 A 股均可融资融券；除非另有说明，默认按纯现金交易处理

---

**评级标准**（必须选择恰好一项）：
- **买入 (Buy)**：强烈看好，建议建仓或加仓
- **增持 (Overweight)**：前景乐观，逐步增加仓位
- **持有 (Hold)**：维持现有仓位，暂不操作
- **减持 (Underweight)**：降低仓位，部分获利了结
- **卖出 (Sell)**：清仓离场或避免入场

**背景信息：**
- 研究经理的投资计划：**{research_plan}**
- 交易员的交易方案：**{trader_plan}**
{lessons_line}
**风控分析师辩论记录：**
{history}

---

请果断决策，并将每项结论建立在分析师提供的具体证据之上。{get_language_instruction()}"""

        final_trade_decision = invoke_structured_or_freetext(
            structured_llm,
            llm,
            prompt,
            render_pm_decision,
            "Portfolio Manager",
        )

        new_risk_debate_state = {
            "judge_decision": final_trade_decision,
            "history": risk_debate_state["history"],
            "aggressive_history": risk_debate_state["aggressive_history"],
            "conservative_history": risk_debate_state["conservative_history"],
            "neutral_history": risk_debate_state["neutral_history"],
            "latest_speaker": "Judge",
            "current_aggressive_response": risk_debate_state["current_aggressive_response"],
            "current_conservative_response": risk_debate_state["current_conservative_response"],
            "current_neutral_response": risk_debate_state["current_neutral_response"],
            "count": risk_debate_state["count"],
        }

        return {
            "risk_debate_state": new_risk_debate_state,
            "final_trade_decision": final_trade_decision,
        }

    return portfolio_manager_node
