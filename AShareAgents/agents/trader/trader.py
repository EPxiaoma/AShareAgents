"""交易员：将研究经理的投资计划转化为具体的交易执行方案。"""

from __future__ import annotations

import functools

from langchain_core.messages import AIMessage

from AShareAgents.models.schemas import TraderProposal, render_trader_proposal
from AShareAgents.tools.agent_utils import build_instrument_context, get_language_instruction
from AShareAgents.tools.structured import (
    bind_structured,
    invoke_structured_or_freetext,
)


def create_trader(llm):
    structured_llm = bind_structured(llm, TraderProposal, "Trader")

    def trader_node(state, name):
        company_name = state["company_of_interest"]
        instrument_context = build_instrument_context(company_name)
        investment_plan = state["investment_plan"]

        # 收集A股专属分析师报告
        policy_report = state.get("policy_report", "")
        hot_money_report = state.get("hot_money_report", "")
        lockup_report = state.get("lockup_report", "")

        # 构建可选的A股上下文块
        astock_context_parts = []
        if policy_report:
            astock_context_parts.append(f"政策分析报告：\n{policy_report}")
        if hot_money_report:
            astock_context_parts.append(f"游资/资金流向报告：\n{hot_money_report}")
        if lockup_report:
            astock_context_parts.append(f"解禁/减持报告：\n{lockup_report}")
        astock_context = "\n\n".join(astock_context_parts)

        messages = [
            {
                "role": "system",
                "content": (
                    "你是一位专注于 A 股（中国大陆）股票的交易员。"
                    "请将研究经理的投资计划转化为具体、可执行的交易方案。决策时必须纳入 A 股交易限制：\n"
                    "- T+1 结算：当日买入的股票需等到下一个交易日才能卖出\n"
                    "- 涨跌幅限制：主板 ±10%，科创板/创业板 ±20%，ST 股 ±5%\n"
                    "- 最小交易单位：主板 100 股，科创板/创业板 200 股\n"
                    "- 交易时间：北京时间 09:30-11:30，13:00-15:00\n"
                    "请将推理建立在分析师报告和研究计划之上。"
                    "请明确给出入场价格、止损位和仓位规模。"
                    "（以上参数仅供技术研究参考，不构成投资建议）"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"基于分析师团队（包括技术、情绪、新闻、基本面、政策、资金流向和解禁/减持"
                    f"专家）的全面分析，以下是针对 {company_name} 的投资计划。\n\n"
                    f"{instrument_context}\n\n"
                    f"建议投资计划：\n{investment_plan}\n\n"
                    + (f"A股专属分析师补充背景：\n{astock_context}\n\n" if astock_context else "")
                    + "请利用这些洞察制定精确的交易方案。"
                    + get_language_instruction()
                ),
            },
        ]

        trader_plan = invoke_structured_or_freetext(
            structured_llm,
            llm,
            messages,
            render_trader_proposal,
            "Trader",
        )

        return {
            "messages": [AIMessage(content=trader_plan)],
            "trader_investment_plan": trader_plan,
            "sender": name,
        }

    return functools.partial(trader_node, name="Trader")
