"""扫描已有日志文件，管理分析历史记录。"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

_HISTORY_NAME_RE = re.compile(r"full_states_log_\d{4}-\d{2}-\d{2}\.json$")
_MAX_HISTORY_BYTES = 20 * 1024 * 1024


def _results_dir() -> Path:
    """获取配置中的分析结果目录。"""
    from AShareAgents.config import DEFAULT_CONFIG
    return Path(DEFAULT_CONFIG["results_dir"])


def get_history() -> list[dict[str, str]]:
    """扫描已保存的分析日志，返回按日期倒序排列的列表。

    每条记录包含股票代码、交易日期、分析时间和日志文件路径。
    """
    root = _results_dir()
    if not root.exists():
        return []

    entries: list[dict[str, str]] = []
    for log_file in root.rglob("full_states_log_*.json"):
        match = re.search(r"full_states_log_(\d{4}-\d{2}-\d{2})\.json$", log_file.name)
        if not match:
            continue
        try:
            safe_path = _resolve_history_path(log_file)
            modified_at = datetime.fromtimestamp(safe_path.stat().st_mtime)
        except (OSError, ValueError):
            continue
        date = match.group(1)
        ticker = log_file.parent.parent.name
        entries.append(
            {
                "ticker": ticker,
                "date": date,
                "time": modified_at.strftime("%H:%M:%S"),
                "path": str(safe_path),
            }
        )

    entries.sort(key=lambda e: (e["date"], e["time"]), reverse=True)
    return entries


def _resolve_history_path(path: str | Path) -> Path:
    """Resolve and validate a history file beneath the configured results root."""
    root = _results_dir().resolve()
    candidate = Path(path).resolve(strict=True)
    if not candidate.is_file() or not candidate.is_relative_to(root):
        raise ValueError("History file is outside the configured results directory")
    if not _HISTORY_NAME_RE.fullmatch(candidate.name):
        raise ValueError("Invalid history filename")
    if candidate.stat().st_size > _MAX_HISTORY_BYTES:
        raise ValueError("History file is too large")
    return candidate


def load_analysis(path: str) -> dict[str, Any]:
    """Load a validated saved analysis JSON object."""
    safe_path = _resolve_history_path(path)
    with safe_path.open(encoding="utf-8") as f:
        state = json.load(f)
    if not isinstance(state, dict):
        raise ValueError("History JSON must contain an object")
    return state


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
