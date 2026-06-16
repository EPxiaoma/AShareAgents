"""处理 FastAPI 后端历史数据的前端辅助函数。"""

from __future__ import annotations

import re
from typing import Any


def get_history() -> list[dict[str, str]]:
    from AShareAgents.api.client import get_api_client

    return get_api_client().get_history()


def load_analysis(history_id: str) -> dict[str, Any]:
    return load_history(history_id)["final_state"]


def load_history(history_id: str) -> dict[str, Any]:
    from AShareAgents.api.client import get_api_client

    return get_api_client().get_history_result(history_id)


def extract_signal(state: dict[str, Any]) -> str:
    """从分析状态中提取五档组合评级。"""
    from AShareAgents.tools.rating import parse_rating

    candidates: list[Any] = [
        state.get("final_trade_decision"),
        (state.get("risk_debate_state") or {}).get("judge_decision")
        if isinstance(state.get("risk_debate_state"), dict)
        else None,
        state.get("trader_investment_decision"),
        state.get("investment_plan"),
        (state.get("investment_debate_state") or {}).get("judge_decision")
        if isinstance(state.get("investment_debate_state"), dict)
        else None,
    ]

    for text in candidates:
        if not text:
            continue
        cleaned = re.sub(r"<think>.*?</think>", "", str(text), flags=re.DOTALL)
        rating = parse_rating(cleaned, default="N/A")
        if rating != "N/A":
            return rating
    return "N/A"
