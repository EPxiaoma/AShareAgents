"""从投资组合经理的决策中提取五级评级。

投资组合经理通过结构化输出生成 ``PortfolioDecision``，并渲染为始终包含
``**Rating**: X`` 标题的Markdown文本（参见
:func:`AShareAgents.models.schemas.render_pm_decision`）。
:mod:`AShareAgents.tools.rating` 中的确定性启发式方法足以提取该评级，
无需额外调用LLM。

本模块为兼容已有调用方而存在，它们期望 ``SignalProcessor.process_signal(text)`` 接口。
"""

from __future__ import annotations

from typing import Any

from AShareAgents.tools.rating import parse_rating


class SignalProcessor:
    """从投资组合经理的决策文本中提取五级评级。"""

    def __init__(self, quick_thinking_llm: Any = None):
        # LLM参数仅为向后兼容而保留，实际不再使用：
        # PM的结构化输出确保评级可从渲染的Markdown中解析，无需二次LLM调用。
        self.quick_thinking_llm = quick_thinking_llm

    def process_signal(self, full_signal: str) -> str:
        """返回 Buy / Overweight / Hold / Underweight / Sell 之一。

        Args:
            full_signal: 投资组合经理输出的完整决策文本

        Returns:
            五级评级字符串
        """
        return parse_rating(full_signal)
