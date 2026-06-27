"""AShareAgents A股分析 — Streamlit Web 界面。"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from AShareAgents.logging_config import setup_logging

setup_logging()

import streamlit as st
from dotenv import load_dotenv

load_dotenv(_PROJECT_ROOT / ".env")

from AShareAgents.api.client import APIError, get_api_client  # noqa: E402

from frontend.components.progress_panel import render_progress  # noqa: E402
from frontend.components.report_viewer import render_report  # noqa: E402
from frontend.components.sidebar import render_sidebar  # noqa: E402
from frontend.history import load_history  # noqa: E402
from frontend.progress import ProgressTracker  # noqa: E402

st.set_page_config(
    page_title="AShareAgents A股分析",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    :root {
        --bg: #080b0f;
        --panel: #0d1218;
        --panel-2: #111821;
        --line: #1d2835;
        --line-soft: #16202b;
        --text: #f4f7fb;
        --muted: #8b98a8;
        --muted-2: #657386;
        --amber: #f59e0b;
        --amber-2: #d97706;
        --green: #22c55e;
        --red: #ef4444;
        --yellow: #eab308;
    }

    #MainMenu,
    footer,
    div[data-testid="stDecoration"],
    div[data-testid="stStatusWidget"],
    div[data-testid="stToolbarActions"],
    div[data-testid="stAppDeployButton"],
    span[data-testid="stMainMenu"] { display: none !important; }
    header[data-testid="stHeader"] {
        background: transparent !important;
        box-shadow: none !important;
    }
    button[data-testid="stExpandSidebarButton"],
    button[data-testid="stSidebarCollapseButton"],
    button[data-testid="collapsedControl"],
    [data-testid="stSidebarCollapsedControl"] {
        display: flex !important;
        visibility: visible !important;
        opacity: 1 !important;
    }

    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    .stApp {
        background:
            radial-gradient(circle at 20% 0%, rgba(245, 158, 11, 0.08), transparent 28rem),
            linear-gradient(180deg, #0a0d12 0%, var(--bg) 42%, #07090d 100%);
        color: var(--text);
    }
    .block-container {
        padding-top: 2rem !important;
        padding-bottom: 2rem !important;
        max-width: 1400px;
    }
    section[data-testid="stSidebar"] {
        background: #0a0e13;
        border-right: 1px solid var(--line);
    }
    section[data-testid="stSidebar"] > div { padding-top: 1.4rem; }
    h1, h2, h3, h4, h5, h6 { letter-spacing: 0 !important; color: var(--text) !important; }
    p, li, label, .stMarkdown { color: #d9e1eb; }
    .stMetric label { color: var(--muted) !important; font-size: 0.78rem !important; }
    .stMetric [data-testid="stMetricValue"] {
        color: var(--text) !important;
        font-weight: 750 !important;
        font-size: 1.45rem !important;
    }
    div[data-testid="stMetric"] {
        background: var(--panel);
        border: 1px solid var(--line-soft);
        border-radius: 8px;
        padding: 0.85rem 0.95rem;
    }
    .stProgress > div > div > div {
        background: linear-gradient(90deg, var(--amber), #fbbf24) !important;
    }
    button[kind="primary"] {
        background: linear-gradient(135deg, var(--amber), var(--amber-2)) !important;
        border: none !important;
        color: #111827 !important;
        font-weight: 800 !important;
        letter-spacing: 0 !important;
        box-shadow: 0 10px 26px rgba(245, 158, 11, 0.18) !important;
        transition: all 0.2s ease !important;
        border-radius: 8px !important;
    }
    button[kind="primary"]:hover {
        background: linear-gradient(135deg, #fbbf24, var(--amber)) !important;
        box-shadow: 0 12px 32px rgba(245, 158, 11, 0.24) !important;
        transform: translateY(-1px) !important;
    }
    button[kind="secondary"] {
        background: #0f151d !important;
        border: 1px solid var(--line-soft) !important;
        color: #dbe3ed !important;
        transition: all 0.2s ease !important;
        border-radius: 8px !important;
    }
    button[kind="secondary"]:hover {
        background: #131b25 !important;
        border-color: rgba(245, 158, 11, 0.6) !important;
        color: #fbbf24 !important;
    }
    .stExpander {
        background: var(--panel) !important;
        border: 1px solid var(--line-soft) !important;
        border-radius: 8px !important;
    }
    .stTabs [data-baseweb="tab"] { color: var(--muted) !important; }
    .stTabs [aria-selected="true"] {
        color: #fbbf24 !important;
        border-bottom-color: var(--amber) !important;
    }
    div[data-testid="stDownloadButton"] button {
        background: #0f151d !important;
        border: 1px solid rgba(245, 158, 11, 0.5) !important;
        color: #fbbf24 !important;
    }
    input[data-testid="stTextInputRootElement"] input,
    .stTextInput input,
    .stDateInput input {
        background: #0f151d !important;
        border-color: var(--line) !important;
        color: var(--text) !important;
        border-radius: 8px !important;
    }
    .stTextInput input:focus {
        border-color: var(--amber) !important;
        box-shadow: 0 0 0 1px var(--amber) !important;
    }
    div[data-baseweb="select"] > div {
        background: #0f151d !important;
        border-color: var(--line) !important;
        border-radius: 8px !important;
    }
    .as-topbar {
        display: flex;
        justify-content: space-between;
        align-items: flex-end;
        gap: 1.5rem;
        padding: 0.25rem 0 1.15rem;
        border-bottom: 1px solid var(--line);
        margin-bottom: 1.1rem;
    }
    .as-kicker {
        color: var(--amber);
        font-size: 0.74rem;
        font-weight: 800;
        letter-spacing: 0.08em;
        text-transform: uppercase;
    }
    .as-title {
        margin-top: 0.25rem;
        color: var(--text);
        font-size: 1.65rem;
        line-height: 1.2;
        font-weight: 800;
    }
    .as-subtitle { color: var(--muted); font-size: 0.9rem; margin-top: 0.35rem; }
    .as-session { display: flex; gap: 0.55rem; flex-wrap: wrap; justify-content: flex-end; }
    .as-pill {
        border: 1px solid var(--line);
        background: rgba(17, 24, 33, 0.76);
        color: #cfd8e3;
        border-radius: 999px;
        padding: 0.42rem 0.68rem;
        font-size: 0.78rem;
        white-space: nowrap;
    }
    .as-grid { display: grid; grid-template-columns: minmax(0, 1.35fr) minmax(320px, 0.65fr); gap: 1rem; align-items: stretch; }
    .as-panel {
        background: rgba(13, 18, 24, 0.92);
        border: 1px solid var(--line-soft);
        border-radius: 8px;
        padding: 1.05rem;
    }
    .as-panel-title { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.85rem; color: var(--text); font-weight: 750; }
    .as-muted { color: var(--muted); font-size: 0.86rem; }
    .as-pipeline { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 0.55rem; }
    .as-stage { min-height: 72px; background: #0b1016; border: 1px solid var(--line-soft); border-radius: 8px; padding: 0.68rem; }
    .as-stage-index { color: var(--amber); font-size: 0.7rem; font-weight: 800; margin-bottom: 0.35rem; }
    .as-stage-name { color: var(--text); font-weight: 700; font-size: 0.88rem; }
    .as-stage-meta { color: var(--muted-2); font-size: 0.74rem; margin-top: 0.32rem; }
    .as-empty-actions { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0.75rem; margin-top: 1rem; }
    .as-action { border-top: 1px solid var(--line); padding-top: 0.8rem; }
    .as-action strong { display: block; color: var(--text); font-size: 0.92rem; margin-bottom: 0.22rem; }
    .as-decision { display: grid; gap: 0.75rem; }
    .as-signal-box { border: 1px solid rgba(245, 158, 11, 0.28); background: linear-gradient(180deg, rgba(245, 158, 11, 0.08), rgba(13, 18, 24, 0.4)); border-radius: 8px; padding: 1rem; }
    .as-signal { color: var(--amber); font-size: 2.1rem; font-weight: 800; line-height: 1; }
    .as-row { display: flex; justify-content: space-between; gap: 1rem; padding: 0.62rem 0; border-bottom: 1px solid var(--line-soft); color: #dbe3ed; font-size: 0.86rem; }
    .as-row span:last-child { color: var(--muted); text-align: right; }
    .as-risk { margin-top: 1rem; padding: 0.8rem 1rem; border: 1px solid rgba(245, 158, 11, 0.2); border-radius: 8px; color: #b7c2d0; font-size: 0.8rem; line-height: 1.7; background: rgba(245, 158, 11, 0.04); }
    @media (max-width: 900px) {
        .as-topbar { align-items: flex-start; flex-direction: column; }
        .as-session { justify-content: flex-start; }
        .as-grid { grid-template-columns: 1fr; }
        .as-pipeline { grid-template-columns: repeat(2, minmax(0, 1fr)); }
        .as-empty-actions { grid-template-columns: 1fr; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def _build_config() -> dict:
    config: dict[str, object] = {}
    config["llm_provider"] = st.session_state.get("llm_provider", "minimax")
    config["deep_think_llm"] = st.session_state.get("deep_think_llm", "MiniMax-M2.7")
    config["quick_think_llm"] = st.session_state.get("quick_think_llm", "MiniMax-M2.7-highspeed")
    backend_url = (st.session_state.get("llm_base_url") or os.getenv("BACKEND_URL") or "").strip()
    config["backend_url"] = backend_url or None
    config["max_debate_rounds"] = 1
    config["max_risk_discuss_rounds"] = 1
    config["output_language"] = "Chinese"
    return config


with st.sidebar:
    render_sidebar()

start_req = st.session_state.pop("start_analysis", None)
if start_req:
    tracker = ProgressTracker(
        ticker=start_req["ticker"],
        trade_date=start_req["trade_date"],
    )
    st.session_state["tracker"] = tracker
    try:
        tracker.task_id = get_api_client().start_analysis(
            ticker=start_req["ticker"],
            trade_date=start_req["trade_date"],
            config=_build_config(),
        )
        tracker.is_running = True
    except APIError as exc:
        tracker.mark_error(str(exc))

tracker: ProgressTracker | None = st.session_state.get("tracker")
viewing_history: str | None = st.session_state.get("viewing_history")

if tracker and tracker.task_id and (tracker.is_running or not tracker.final_state):
    try:
        client = get_api_client()
        tracker.update_from_api(client.get_analysis(tracker.task_id))
        if tracker.is_complete and not tracker.final_state:
            result = client.get_analysis_result(tracker.task_id)
            tracker.final_state = result["final_state"]
            tracker.signal = result["signal"]
    except APIError as exc:
        tracker.mark_error(str(exc))


def _render_disclaimer() -> None:
    """在主页面内容底部渲染投资风险声明。"""
    st.html(
        """
        <div class="as-risk">
            风险提示：本项目仅供学习研究与技术演示，不构成任何投资建议。<br>
            投资决策请咨询持牌专业机构。作者不对使用本工具产生的任何损失承担责任。
        </div>
        """
    )


if viewing_history:
    try:
        history = load_history(viewing_history)
        render_report(
            history["final_state"],
            history["ticker"],
            history["trade_date"],
            history["signal"],
        )
    except Exception as exc:
        st.error(f"加载失败: {exc}")

elif tracker and tracker.is_running:
    render_progress(tracker)
    _render_disclaimer()
    time.sleep(2)
    st.rerun()

elif tracker and tracker.is_complete:
    render_report(
        tracker.final_state,
        tracker.ticker,
        tracker.trade_date,
        tracker.signal,
        elapsed=tracker.elapsed,
    )

elif tracker and tracker.error:
    st.error(f"分析失败: {tracker.error}")
    if st.button("重试"):
        st.session_state.pop("tracker", None)
        st.rerun()

else:
    pipeline_html = "\n".join(
        f"""
        <div class="as-stage">
            <div class="as-stage-index">{index:02d}</div>
            <div class="as-stage-name">{stage_name}</div>
            <div class="as-stage-meta">等待调度</div>
        </div>
        """
        for index, stage_name in enumerate(
            [
                "技术分析",
                "市场情绪",
                "新闻舆情",
                "基本面",
                "政策分析",
                "游资追踪",
                "解禁监控",
                "质量门控",
                "多空辩论",
                "交易决策",
                "风控评估",
                "最终决策",
            ],
            start=1,
        )
    )
    st.html(
        f"""
        <div class="as-topbar">
            <div>
                <div class="as-kicker">A-SHARE MULTI-AGENT RESEARCH</div>
                <div class="as-title">投研指挥台</div>
                <div class="as-subtitle">输入股票代码或名称后，系统会调度 7 位分析师、质量门控、辩论与风控链路生成研究结论。</div>
            </div>
            <div class="as-session">
                <div class="as-pill">数据源：A股聚合</div>
                <div class="as-pill">输出：中文研报</div>
                <div class="as-pill">状态：待发起</div>
            </div>
        </div>

        <div class="as-grid">
            <div class="as-panel">
                <div class="as-panel-title">
                    <span>分析流水线</span>
                    <span class="as-muted">12 个阶段 · 自动编排</span>
                </div>
                <div class="as-pipeline">{pipeline_html}</div>
                <div style="display:grid; grid-template-columns:repeat(4, minmax(0, 1fr)); gap:0.75rem; margin-top:1rem; padding-top:1rem; border-top:1px solid #1d2835;">
                    <div class="as-action" style="border-top:0; padding-top:0;">
                        <strong>12-18 min</strong>
                        <div class="as-muted">ETA</div>
                    </div>
                    <div class="as-action" style="border-top:0; padding-top:0;">
                        <strong>0 / 12</strong>
                        <div class="as-muted">Agents</div>
                    </div>
                    <div class="as-action" style="border-top:0; padding-top:0;">
                        <strong>80K-120K</strong>
                        <div class="as-muted">Token Budget</div>
                    </div>
                    <div class="as-action" style="border-top:0; padding-top:0;">
                        <strong>Pending</strong>
                        <div class="as-muted">Signal</div>
                    </div>
                </div>
                <div style="text-align:center; margin:1.25rem 0 0.35rem; color:#f4f7fb; font-size:1.25rem; font-weight:800;">Ready for Research</div>
                <div style="text-align:center; color:#8b98a8; font-size:0.88rem; margin-bottom:1rem;">Use the task panel on the left to choose a ticker, date, and model before starting the run.</div>
                <div class="as-empty-actions">
                    <div class="as-action">
                        <strong>1. 选择标的</strong>
                        <div class="as-muted">支持 6 位代码或股票名称解析。</div>
                    </div>
                    <div class="as-action">
                        <strong>2. 配置模型</strong>
                        <div class="as-muted">快速模型处理检索，深度模型处理辩论与决策。</div>
                    </div>
                    <div class="as-action">
                        <strong>3. 审阅报告</strong>
                        <div class="as-muted">最终信号、风险评估和分章节研报可导出。</div>
                    </div>
                </div>
            </div>

            <div class="as-panel as-decision">
                <div class="as-panel-title">
                    <span>决策预览</span>
                    <span class="as-muted">等待任务</span>
                </div>
                <div class="as-signal-box">
                    <div class="as-muted">交易信号</div>
                    <div class="as-signal">--</div>
                    <div class="as-muted">完成风控评估后生成最终建议</div>
                </div>
                <div>
                    <div class="as-row"><span>当前标的</span><span>未选择</span></div>
                    <div class="as-row"><span>分析日期</span><span>侧边栏设置</span></div>
                    <div class="as-row"><span>报告章节</span><span>技术 / 新闻 / 基本面 / 风控</span></div>
                    <div class="as-row"><span>导出格式</span><span>Markdown / PDF</span></div>
                </div>
            </div>
        </div>
        """
    )

_render_disclaimer()
