"""研究经理：将多头/空头辩论转化为面向交易员的结构化投资计划。"""

from __future__ import annotations

from AShareAgents.models.schemas import ResearchPlan, render_research_plan
from AShareAgents.tools.agent_utils import build_instrument_context, get_language_instruction
from AShareAgents.tools.structured import (
    bind_structured,
    invoke_structured_or_freetext,
)


def create_research_manager(llm):
    structured_llm = bind_structured(llm, ResearchPlan, "Research Manager")

    def research_manager_node(state) -> dict:
        instrument_context = build_instrument_context(state["company_of_interest"])
        history = state["investment_debate_state"].get("history", "")

        investment_debate_state = state["investment_debate_state"]

        prompt = f"""作为研究经理和辩论主持人，你的职责是严格评估本轮多空辩论，为交易员提供清晰、可执行的投资计划。

{instrument_context}

注意：这是一只 A 股（中国大陆）股票。在综合辩论结果时，请充分考虑监管政策影响、游资/资金流向动态，以及解禁/减持风险。

---

**评级标准**（必须选择恰好一项）：
- **买入 (Buy)**：对多方论点有强烈信心；建议建仓或加仓
- **增持 (Overweight)**：偏乐观；建议逐步增加仓位
- **持有 (Hold)**：多空均衡；建议维持现有仓位
- **减持 (Underweight)**：偏谨慎；建议降低仓位
- **卖出 (Sell)**：对空方论点有强烈信心；建议清仓或规避

当辩论中某一方论据明显占优时，请给出明确立场；只有在多空双方证据确实旗鼓相当时，才使用「持有」评级。

---

**辩论记录：**
{history}""" + get_language_instruction()

        investment_plan = invoke_structured_or_freetext(
            structured_llm,
            llm,
            prompt,
            render_research_plan,
            "Research Manager",
        )

        new_investment_debate_state = {
            "judge_decision": investment_plan,
            "history": investment_debate_state.get("history", ""),
            "bear_history": investment_debate_state.get("bear_history", ""),
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": investment_plan,
            "count": investment_debate_state["count"],
        }

        return {
            "investment_debate_state": new_investment_debate_state,
            "investment_plan": investment_plan,
        }

    return research_manager_node
