"""FastAPI 后端负责的分析执行服务。"""

from __future__ import annotations

import re
import threading
from typing import Any

from AShareAgents.api.jobs import AnalysisJob, PIPELINE_STAGES

_REPORT_KEY_TO_STAGE = {
    "market_report": "market",
    "sentiment_report": "social",
    "news_report": "news",
    "fundamentals_report": "fundamentals",
    "policy_report": "policy",
    "hot_money_report": "hot_money",
    "lockup_report": "lockup",
}


def _strip_think_tags(text: str) -> str:
    return re.sub(r"<think>.*?</think>\s*", "", text, flags=re.DOTALL).strip()


def _detect_completed_stages(chunk: dict[str, Any], job: AnalysisJob) -> None:
    for report_key, stage_id in _REPORT_KEY_TO_STAGE.items():
        content = chunk.get(report_key, "")
        if content and job.stage_status(stage_id) != "done":
            job.mark_stage_done(stage_id, _strip_think_tags(str(content)))

    dqs = chunk.get("data_quality_summary", "")
    if dqs and job.stage_status("quality_gate") != "done":
        job.mark_stage_done("quality_gate", str(dqs))

    debate = chunk.get("investment_debate_state")
    if isinstance(debate, dict) and debate.get("judge_decision"):
        if job.stage_status("debate") != "done":
            job.mark_stage_done("debate", str(debate["judge_decision"]))

    trader_plan = chunk.get("trader_investment_plan", "")
    if trader_plan and job.stage_status("trader") != "done":
        job.mark_stage_done("trader", _strip_think_tags(str(trader_plan)))

    risk = chunk.get("risk_debate_state")
    if isinstance(risk, dict) and risk.get("judge_decision"):
        if job.stage_status("risk") != "done":
            job.mark_stage_done("risk", str(risk["judge_decision"]))

    final = chunk.get("final_trade_decision", "")
    if final and job.stage_status("pm") != "done":
        job.mark_stage_done("pm", _strip_think_tags(str(final)))


def _infer_active_stage(job: AnalysisJob) -> None:
    if job.current_stage and job.stage_status(job.current_stage) == "active":
        return
    for stage_id in PIPELINE_STAGES:
        if job.stage_status(stage_id) == "pending":
            job.mark_stage_active(stage_id)
            return


def run_analysis(job: AnalysisJob, config: dict[str, Any]) -> None:
    from AShareAgents.api.stats import StatsCallbackHandler
    from AShareAgents.workflows.trading_graph import AShareAgentsGraph

    job.mark_running()
    stats = StatsCallbackHandler()
    graph = AShareAgentsGraph(debug=True, config=config, callbacks=[stats])
    graph._resolve_pending_entries(job.ticker)
    past_context = graph.memory_log.get_past_context(job.ticker)
    init_state = graph.propagator.create_initial_state(
        job.ticker, job.trade_date, past_context=past_context
    )
    args = graph.propagator.get_graph_args(callbacks=[stats])
    last_chunk: dict[str, Any] = {}

    for chunk in graph.graph.stream(init_state, **args):
        last_chunk = chunk
        _detect_completed_stages(chunk, job)
        _infer_active_stage(job)
        values = stats.get_stats()
        job.update_stats(
            values["llm_calls"],
            values["tool_calls"],
            values["tokens_in"],
            values["tokens_out"],
        )

    signal = graph.process_signal(last_chunk.get("final_trade_decision", ""))
    graph.ticker = job.ticker
    graph._log_state(job.trade_date, last_chunk)
    final_state = graph.log_states_dict[str(job.trade_date)]

    final_decision = last_chunk.get("final_trade_decision", "")
    if final_decision:
        graph.memory_log.store_decision(job.ticker, job.trade_date, final_decision)

    job.mark_complete(final_state, signal)


def start_analysis(job: AnalysisJob, config: dict[str, Any]) -> threading.Thread:
    def _target() -> None:
        try:
            run_analysis(job, config)
        except Exception as exc:
            job.mark_error(str(exc))

    thread = threading.Thread(target=_target, daemon=True, name=f"analysis-{job.task_id}")
    thread.start()
    return thread
