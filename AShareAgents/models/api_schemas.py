"""Pydantic request and response models for the HTTP API."""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AnalysisConfig(BaseModel):
    """Client-selectable analysis options.

    Filesystem paths and other server-owned settings are intentionally omitted.
    """

    llm_provider: str = "minimax"
    deep_think_llm: str = "MiniMax-M2.7"
    quick_think_llm: str = "MiniMax-M2.7-highspeed"
    backend_url: str | None = None
    max_debate_rounds: int = Field(default=1, ge=1, le=10)
    max_risk_discuss_rounds: int = Field(default=1, ge=1, le=10)
    output_language: str = "Chinese"


class AnalysisCreateRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=64)
    trade_date: date
    config: AnalysisConfig = Field(default_factory=AnalysisConfig)


class AnalysisCreatedResponse(BaseModel):
    task_id: str
    status: TaskStatus


class StageSnapshot(BaseModel):
    id: str
    status: str


class AnalysisStats(BaseModel):
    llm_calls: int = 0
    tool_calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0


class AnalysisStatusResponse(BaseModel):
    task_id: str
    ticker: str
    trade_date: str
    status: TaskStatus
    current_stage: str = ""
    completed_stages: list[str] = Field(default_factory=list)
    stages: list[StageSnapshot] = Field(default_factory=list)
    stage_reports: dict[str, str] = Field(default_factory=dict)
    stats: AnalysisStats = Field(default_factory=AnalysisStats)
    elapsed: float = 0.0
    signal: str = ""
    error: str | None = None


class AnalysisResultResponse(BaseModel):
    task_id: str
    ticker: str
    trade_date: str
    signal: str
    elapsed: float
    final_state: dict[str, Any]


class HistoryEntry(BaseModel):
    id: str
    ticker: str
    date: str
    time: str


class HistoryResultResponse(BaseModel):
    id: str
    ticker: str
    trade_date: str
    signal: str
    final_state: dict[str, Any]


class TickerResolveRequest(BaseModel):
    query: str = Field(min_length=1, max_length=64)


class TickerResolveResponse(BaseModel):
    ticker: str


class HealthResponse(BaseModel):
    status: str = "ok"
