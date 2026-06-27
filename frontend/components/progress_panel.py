"""分析流水线的实时进度展示组件。"""

from __future__ import annotations

import html

import streamlit as st

from frontend.progress import PIPELINE_STAGES, ProgressTracker


_STATUS_META = {
    "done": ("已完成", "#22c55e"),
    "active": ("运行中", "#f59e0b"),
    "pending": ("等待中", "#657386"),
}


def _format_time(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"


def _stage_card(index: int, stage: dict[str, str], status: str) -> str:
    label, color = _STATUS_META.get(status, _STATUS_META["pending"])
    border = color if status == "active" else "#16202b"
    background = "rgba(245, 158, 11, 0.08)" if status == "active" else "#0b1016"
    return f"""
    <div style="background:{background}; border:1px solid {border}; border-radius:8px; padding:0.72rem; min-height:84px;">
        <div style="display:flex; align-items:center; justify-content:space-between; gap:0.5rem;">
            <span style="color:#8b98a8; font-size:0.72rem; font-weight:800;">{index:02d}</span>
            <span style="color:{color}; font-size:0.72rem; font-weight:700;">{label}</span>
        </div>
        <div style="color:#f4f7fb; font-size:0.92rem; font-weight:750; margin-top:0.42rem;">{html.escape(stage['name'])}</div>
        <div style="color:#657386; font-size:0.72rem; margin-top:0.34rem;">{html.escape(stage.get('report_key', ''))}</div>
    </div>
    """


def render_progress(tracker: ProgressTracker) -> None:
    """渲染流水线进度面板。"""

    completed = len(tracker.completed_stages)
    total = len(PIPELINE_STAGES)
    pct = completed / total if total else 0
    current_stage = next(
        (stage["name"] for stage in PIPELINE_STAGES if stage["id"] == tracker.current_stage),
        "任务排队中",
    )

    st.html(
        f"""
        <div class="as-topbar">
            <div>
                <div class="as-kicker">LIVE RESEARCH PIPELINE</div>
                <div class="as-title">{html.escape(tracker.ticker)} 分析进行中</div>
                <div class="as-subtitle">当前阶段：{html.escape(current_stage)} · 分析日期：{html.escape(tracker.trade_date)}</div>
            </div>
            <div class="as-session">
                <div class="as-pill">完成 {completed}/{total}</div>
                <div class="as-pill">耗时 {_format_time(tracker.elapsed)}</div>
                <div class="as-pill">实时轮询</div>
            </div>
        </div>
        """
    )

    st.progress(pct, text=f"{completed}/{total} 阶段完成 · {_format_time(tracker.elapsed)}")

    stage_html = "\n".join(
        _stage_card(index, stage, tracker.stage_status(stage["id"]))
        for index, stage in enumerate(PIPELINE_STAGES, start=1)
    )
    st.html(
        f"""
        <div class="as-panel" style="margin-top:1rem;">
            <div class="as-panel-title">
                <span>多智能体调度链路</span>
                <span class="as-muted">分析师 → 质量门控 → 辩论 → 风控 → 决策</span>
            </div>
            <div class="as-pipeline">{stage_html}</div>
        </div>
        """
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("LLM 调用", tracker.llm_calls)
    c2.metric("工具调用", tracker.tool_calls)
    c3.metric("输入 Tokens", f"{tracker.tokens_in:,}")
    c4.metric("输出 Tokens", f"{tracker.tokens_out:,}")

    if tracker.error:
        st.error(f"错误: {tracker.error}")

    completed_reports = [
        (stage["name"], stage["icon"], tracker.stage_reports[stage["id"]])
        for stage in PIPELINE_STAGES
        if stage["id"] in tracker.stage_reports
    ]

    if completed_reports:
        st.markdown("### 阶段报告")
        for name, icon, report in reversed(completed_reports):
            is_latest = name == completed_reports[-1][0]
            with st.expander(f"{icon} {name}", expanded=is_latest):
                st.markdown(report[:3000])
