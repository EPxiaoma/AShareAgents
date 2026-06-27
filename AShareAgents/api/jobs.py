"""FastAPI 进程使用的内存分析任务注册表。"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from AShareAgents.models.api_schemas import (
    AnalysisStats,
    AnalysisStatusResponse,
    StageSnapshot,
    TaskStatus,
)


PIPELINE_STAGES: tuple[str, ...] = (
    "market",
    "social",
    "news",
    "fundamentals",
    "policy",
    "hot_money",
    "lockup",
    "quality_gate",
    "debate",
    "trader",
    "risk",
    "pm",
)


@dataclass
class AnalysisJob:
    ticker: str
    trade_date: str
    task_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    start_time: float = field(default_factory=time.time)
    end_time: float | None = None
    status: TaskStatus = TaskStatus.PENDING
    current_stage: str = ""
    completed_stages: list[str] = field(default_factory=list)
    stage_reports: dict[str, str] = field(default_factory=dict)
    final_state: dict[str, Any] = field(default_factory=dict)
    signal: str = ""
    error: str | None = None
    llm_calls: int = 0
    tool_calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    @property
    def elapsed(self) -> float:
        return (self.end_time or time.time()) - self.start_time

    def stage_status(self, stage_id: str) -> str:
        with self._lock:
            if stage_id in self.completed_stages:
                return "done"
            if stage_id == self.current_stage:
                return "active"
            return "pending"

    def mark_running(self) -> None:
        with self._lock:
            self.status = TaskStatus.RUNNING
            self.current_stage = "market"

    def mark_stage_active(self, stage_id: str) -> None:
        with self._lock:
            self.current_stage = stage_id

    def mark_stage_done(self, stage_id: str, report: str = "") -> None:
        with self._lock:
            if stage_id not in self.completed_stages:
                self.completed_stages.append(stage_id)
            if report:
                self.stage_reports[stage_id] = report
            if self.current_stage == stage_id:
                self.current_stage = ""

    def update_stats(self, llm: int, tool: int, tok_in: int, tok_out: int) -> None:
        with self._lock:
            self.llm_calls = llm
            self.tool_calls = tool
            self.tokens_in = tok_in
            self.tokens_out = tok_out

    def mark_complete(self, final_state: dict[str, Any], signal: str) -> None:
        with self._lock:
            self.final_state = final_state
            self.signal = signal
            self.current_stage = ""
            self.end_time = time.time()
            self.status = TaskStatus.COMPLETED

    def mark_error(self, error: str) -> None:
        with self._lock:
            self.error = error
            self.current_stage = ""
            self.end_time = time.time()
            self.status = TaskStatus.FAILED

    def snapshot(self) -> AnalysisStatusResponse:
        with self._lock:
            return AnalysisStatusResponse(
                task_id=self.task_id,
                ticker=self.ticker,
                trade_date=self.trade_date,
                status=self.status,
                current_stage=self.current_stage,
                completed_stages=list(self.completed_stages),
                stages=[
                    StageSnapshot(id=stage_id, status=self.stage_status(stage_id))
                    for stage_id in PIPELINE_STAGES
                ],
                stage_reports=dict(self.stage_reports),
                stats=AnalysisStats(
                    llm_calls=self.llm_calls,
                    tool_calls=self.tool_calls,
                    tokens_in=self.tokens_in,
                    tokens_out=self.tokens_out,
                ),
                elapsed=self.elapsed,
                signal=self.signal,
                error=self.error,
            )


class JobRegistry:
    def __init__(self, max_jobs: int = 100) -> None:
        self._jobs: dict[str, AnalysisJob] = {}
        self._max_jobs = max_jobs
        self._lock = threading.Lock()

    def create(self, ticker: str, trade_date: str) -> AnalysisJob:
        job = AnalysisJob(ticker=ticker, trade_date=trade_date)
        with self._lock:
            self._prune_locked()
            self._jobs[job.task_id] = job
        return job

    def get(self, task_id: str) -> AnalysisJob | None:
        with self._lock:
            return self._jobs.get(task_id)

    def _prune_locked(self) -> None:
        if len(self._jobs) < self._max_jobs:
            return
        finished = sorted(
            (
                job for job in self._jobs.values()
                if job.status in {TaskStatus.COMPLETED, TaskStatus.FAILED}
            ),
            key=lambda job: job.start_time,
        )
        for job in finished[: max(1, len(self._jobs) - self._max_jobs + 1)]:
            self._jobs.pop(job.task_id, None)


registry = JobRegistry()
