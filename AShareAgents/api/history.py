"""Server-side access to saved analysis reports."""

from __future__ import annotations

import base64
import binascii
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from AShareAgents.config import DEFAULT_CONFIG

_HISTORY_NAME_RE = re.compile(r"full_states_log_(\d{4}-\d{2}-\d{2})\.json$")
_MAX_HISTORY_BYTES = 20 * 1024 * 1024


def _results_dir() -> Path:
    return Path(DEFAULT_CONFIG["results_dir"]).resolve()


def _history_id(ticker: str, trade_date: str) -> str:
    raw = f"{ticker}\0{trade_date}".encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_history_id(history_id: str) -> tuple[str, str]:
    try:
        padding = "=" * (-len(history_id) % 4)
        decoded = base64.urlsafe_b64decode(history_id + padding).decode("utf-8")
        ticker, trade_date = decoded.split("\0", 1)
    except (binascii.Error, ValueError, UnicodeDecodeError) as exc:
        raise ValueError("Invalid history id") from exc
    if not ticker or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", trade_date):
        raise ValueError("Invalid history id")
    return ticker, trade_date


def list_history() -> list[dict[str, str]]:
    root = _results_dir()
    if not root.exists():
        return []

    entries: list[dict[str, str]] = []
    for log_file in root.rglob("full_states_log_*.json"):
        match = _HISTORY_NAME_RE.fullmatch(log_file.name)
        if not match:
            continue
        try:
            safe_path = _validate_history_path(log_file)
            modified_at = datetime.fromtimestamp(safe_path.stat().st_mtime)
        except (OSError, ValueError):
            continue
        trade_date = match.group(1)
        ticker = safe_path.parent.parent.name
        entries.append(
            {
                "id": _history_id(ticker, trade_date),
                "ticker": ticker,
                "date": trade_date,
                "time": modified_at.strftime("%H:%M:%S"),
            }
        )

    entries.sort(key=lambda entry: (entry["date"], entry["time"]), reverse=True)
    return entries


def load_history(history_id: str) -> tuple[str, str, dict[str, Any]]:
    ticker, trade_date = _decode_history_id(history_id)
    candidate = (
        _results_dir()
        / ticker
        / "AShareAgentsStrategy_logs"
        / f"full_states_log_{trade_date}.json"
    )
    safe_path = _validate_history_path(candidate)
    with safe_path.open(encoding="utf-8") as handle:
        state = json.load(handle)
    if not isinstance(state, dict):
        raise ValueError("History JSON must contain an object")
    return ticker, trade_date, state


def extract_signal(state: dict[str, Any]) -> str:
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


def _validate_history_path(path: Path) -> Path:
    root = _results_dir()
    candidate = path.resolve(strict=True)
    if not candidate.is_file() or not candidate.is_relative_to(root):
        raise ValueError("History file is outside the configured results directory")
    if not _HISTORY_NAME_RE.fullmatch(candidate.name):
        raise ValueError("Invalid history filename")
    if candidate.stat().st_size > _MAX_HISTORY_BYTES:
        raise ValueError("History file is too large")
    return candidate
