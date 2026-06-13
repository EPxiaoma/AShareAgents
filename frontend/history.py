"""扫描已有日志文件，管理分析历史记录。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def _results_dir() -> Path:
    """获取配置中的分析结果目录。"""
    from AShareAgents.config import DEFAULT_CONFIG
    return Path(DEFAULT_CONFIG["results_dir"])


def get_history() -> list[dict[str, str]]:
    """扫描已保存的分析日志，返回按日期倒序排列的列表。

    每条记录格式：{"ticker": "300750", "date": "2026-05-12", "path": "/abs/path/...json"}
    """
    root = _results_dir()
    if not root.exists():
        return []

    entries: list[dict[str, str]] = []
    for log_file in root.rglob("full_states_log_*.json"):
        match = re.search(r"full_states_log_(\d{4}-\d{2}-\d{2})\.json$", log_file.name)
        if not match:
            continue
        date = match.group(1)
        ticker = log_file.parent.parent.name
        entries.append({"ticker": ticker, "date": date, "path": str(log_file)})

    entries.sort(key=lambda e: e["date"], reverse=True)
    return entries


def load_analysis(path: str) -> dict[str, Any]:
    """加载已保存的分析 JSON 文件。"""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def extract_signal(state: dict[str, Any]) -> str:
    """从新旧格式的最终状态中提取五级交易评级。"""
    from AShareAgents.tools.rating import parse_rating

    candidates: list[Any] = [
        state.get("final_trade_decision"),
        (state.get("risk_debate_state") or {}).get("judge_decision")
        if isinstance(state.get("risk_debate_state"), dict) else None,
        state.get("trader_investment_decision"),
        state.get("investment_plan"),
        (state.get("investment_debate_state") or {}).get("judge_decision")
        if isinstance(state.get("investment_debate_state"), dict) else None,
    ]

    for text in candidates:
        if not text:
            continue
        cleaned = re.sub(r"<think>.*?</think>", "", str(text), flags=re.DOTALL)
        rating = parse_rating(cleaned, default="N/A")
        if rating != "N/A":
            return rating
    return "N/A"
