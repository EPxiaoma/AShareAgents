"""用于生成 Agent 结构化输出的 Pydantic 模式定义。

本框架的主要产物仍然是自然语言文本：每个 Agent 的自然语言推理
是用户在保存的 Markdown 报告中阅读的内容，也是下游 Agent 作为上下文
阅读的内容。结构化输出被叠加到三个决策型 Agent
（研究经理、交易员、投资组合经理）上，以便：

- 它们的输出在不同运行和供应商之间保持一致的章节标题
- 使用每个供应商的原生结构化输出模式（OpenAI/xAI 使用 json_schema，
  Gemini 使用 response_schema，Anthropic 使用 tool-use）
- Schema 字段描述成为模型的输出指令，使提示词正文
  可以专注于上下文和评级量表的指导
- 渲染辅助函数将解析后的 Pydantic 实例转换回系统其余部分
  已在消费的相同 Markdown 格式，因此展示、记忆日志和
  保存的报告继续无缝工作
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 共享评级类型
# ---------------------------------------------------------------------------


class PortfolioRating(str, Enum):
    """研究经理和投资组合经理使用的5级评级。"""

    BUY = "Buy"
    OVERWEIGHT = "Overweight"
    HOLD = "Hold"
    UNDERWEIGHT = "Underweight"
    SELL = "Sell"


class TraderAction(str, Enum):
    """交易员使用的3级交易方向枚举。

    交易员的职责是将研究经理的投资计划转化为具体的交易提案：
    本轮应执行买入、卖出还是持有。仓位规模和精细的
    Overweight / Underweight 决策在后续的投资组合经理阶段处理。
    """

    BUY = "Buy"
    HOLD = "Hold"
    SELL = "Sell"


# ---------------------------------------------------------------------------
# 研究经理
# ---------------------------------------------------------------------------


class ResearchPlan(BaseModel):
    """研究经理生成的结构化投资计划。

    交接给交易员：recommendation 确定了方向性观点，
    rationale 捕捉了多空辩论中哪一方的论点胜出，
    strategic_actions 将其转化为交易员可以执行的具体指令。
    """

    recommendation: PortfolioRating = Field(
        description=(
            "投资建议。精确取值为 Buy / Overweight / "
            "Hold / Underweight / Sell 之一。仅在多空双方证据"
            "真实均衡时保留 Hold；否则应选择论据更强的一方。"
        ),
    )
    rationale: str = Field(
        description=(
            "对辩论双方关键论点的对话式总结，以哪些论点"
            "导致了最终建议作为结尾。用自然的对话语气书写，如同告诉队友。"
        ),
    )
    strategic_actions: str = Field(
        description=(
            "交易员执行该建议的具体步骤，"
            "包括与评级一致的仓位规模指导。"
        ),
    )


def render_research_plan(plan: ResearchPlan) -> str:
    """将 ResearchPlan 渲染为 Markdown，供存储和交易员提示词上下文使用。"""
    return "\n".join([
        f"**Recommendation**: {plan.recommendation.value}",
        "",
        f"**Rationale**: {plan.rationale}",
        "",
        f"**Strategic Actions**: {plan.strategic_actions}",
    ])


# ---------------------------------------------------------------------------
# 交易员
# ---------------------------------------------------------------------------


class TraderProposal(BaseModel):
    """交易员生成的结构化交易提案。

    交易员阅读研究经理的投资计划和分析师报告，
    然后将其转化为具体交易：采取什么操作、支持该操作的推理、
    以及入场价、止损位和仓位规模的实际水平。
    """

    action: TraderAction = Field(
        description="交易方向。精确取值为 Buy / Hold / Sell 之一。",
    )
    reasoning: str = Field(
        description=(
            "基于分析师报告和研究计划的操作理由。"
            "两到四句话。"
        ),
    )
    entry_price: Optional[float] = Field(
        default=None,
        description="可选的入场目标价，以标的报价货币为单位。",
    )
    stop_loss: Optional[float] = Field(
        default=None,
        description="可选的止损价，以标的报价货币为单位。",
    )
    position_sizing: Optional[str] = Field(
        default=None,
        description="可选的仓位规模指导，例如 '投资组合的5%'。",
    )


def render_trader_proposal(proposal: TraderProposal) -> str:
    """将 TraderProposal 渲染为 Markdown。

    末尾的 ``FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL**`` 行
    保留用于向后兼容分析师的止损信号文本，以及任何
    通过 grep 搜索该行的外部代码。
    """
    parts = [
        f"**Action**: {proposal.action.value}",
        "",
        f"**Reasoning**: {proposal.reasoning}",
    ]
    if proposal.entry_price is not None:
        parts.extend(["", f"**Entry Price**: {proposal.entry_price}"])
    if proposal.stop_loss is not None:
        parts.extend(["", f"**Stop Loss**: {proposal.stop_loss}"])
    if proposal.position_sizing:
        parts.extend(["", f"**Position Sizing**: {proposal.position_sizing}"])
    parts.extend([
        "",
        f"FINAL TRANSACTION PROPOSAL: **{proposal.action.value.upper()}**",
    ])
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# 投资组合经理
# ---------------------------------------------------------------------------


class PortfolioDecision(BaseModel):
    """投资组合经理生成的结构化输出。

    模型在其主 LLM 调用中填充每个字段；无需单独的提取步骤。
    字段描述同时充当模型的输出指令，因此提示词正文
    只需传达上下文和评级量表的指导即可。
    """

    rating: PortfolioRating = Field(
        description=(
            "最终持仓评级。精确取值为 Buy / Overweight / Hold / "
            "Underweight / Sell 之一，基于分析师的辩论结果选择。"
        ),
    )
    executive_summary: str = Field(
        description=(
            "简洁的行动计划，涵盖入场策略、仓位规模、"
            "关键风险水平和时间周期。两到四句话。"
        ),
    )
    investment_thesis: str = Field(
        description=(
            "基于分析师辩论中具体证据的详细推理。"
            "如果提示词上下文中引用了历史经验，则将其纳入；"
            "否则仅依赖当前分析。"
        ),
    )
    price_target: Optional[float] = Field(
        default=None,
        description="可选的目标价，以标的报价货币为单位。",
    )
    time_horizon: Optional[str] = Field(
        default=None,
        description="可选的推荐持有周期，例如 '3-6个月'。",
    )


def render_pm_decision(decision: PortfolioDecision) -> str:
    """将 PortfolioDecision 渲染回系统其余部分期望的 Markdown 格式。

    记忆日志、CLI 展示和保存的报告文件都读取此 Markdown，
    因此渲染输出保留了下游解析器和报告编写器已处理的
    精确章节标题（``**Rating**``、``**Executive Summary**``、
    ``**Investment Thesis**``）。
    """
    parts = [
        f"**Rating**: {decision.rating.value}",
        "",
        f"**Executive Summary**: {decision.executive_summary}",
        "",
        f"**Investment Thesis**: {decision.investment_thesis}",
    ]
    if decision.price_target is not None:
        parts.extend(["", f"**Price Target**: {decision.price_target}"])
    if decision.time_horizon:
        parts.extend(["", f"**Time Horizon**: {decision.time_horizon}"])
    return "\n".join(parts)
