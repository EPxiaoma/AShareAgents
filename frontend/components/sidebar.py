"""侧边栏：股票代码输入、LLM 配置和历史记录列表。"""

from __future__ import annotations

from datetime import date

import streamlit as st

from AShareAgents.api.client import APIError, get_api_client
from AShareAgents.llm.model_catalog import MODEL_OPTIONS
from frontend.history import get_history

_PROVIDERS: list[tuple[str, str]] = [
    ("DeepSeek", "deepseek"),
    ("GLM", "glm"),
    ("MiniMax（未设置API KEY）", "minimax"),
    ("Qwen（未设置API KEY）", "qwen"),
    ("OpenAI（未设置API KEY）", "openai"),
    ("Anthropic（未设置API KEY）", "anthropic"),
    ("Google Gemini（未设置API KEY）", "google"),
    ("xAI Grok（未设置API KEY）", "xai"),
    ("Ollama（未设置API KEY）", "ollama"),
]

_PROVIDER_DISPLAY = [name for name, _ in _PROVIDERS]
_PROVIDER_KEYS = [key for _, key in _PROVIDERS]


def _resolve_user_input(raw: str) -> tuple[str, str | None]:
    """解析用户输入，返回 (股票代码, 错误信息)。"""
    try:
        code = get_api_client().resolve_ticker(raw)
        return code, None
    except APIError:
        import logging

        logging.getLogger(__name__).warning("Failed to resolve ticker %r", raw)
        return "", "股票名称解析失败，请检查网络连接后重试，或直接输入6位数字代码"


def _render_llm_config() -> None:
    """渲染 LLM 供应商和模型选择控件。"""

    provider_idx = st.selectbox(
        "LLM 供应商",
        range(len(_PROVIDERS)),
        format_func=lambda i: _PROVIDER_DISPLAY[i],
        key="llm_provider_idx",
        help="选择你配置了 API Key 的供应商",
    )
    provider_key = _PROVIDER_KEYS[provider_idx]
    st.session_state["llm_provider"] = provider_key

    if provider_key in MODEL_OPTIONS:
        quick_options = MODEL_OPTIONS[provider_key]["quick"]
        deep_options = MODEL_OPTIONS[provider_key]["deep"]

        quick_labels = [label for label, _ in quick_options]
        quick_values = [value for _, value in quick_options]
        deep_labels = [label for label, _ in deep_options]
        deep_values = [value for _, value in deep_options]

        quick_idx = st.selectbox(
            "快速思考模型",
            range(len(quick_options)),
            format_func=lambda i: quick_labels[i],
            key=f"quick_model_idx_{provider_key}",
            help="用于常规分析任务，速度优先",
        )
        st.session_state["quick_think_llm"] = quick_values[quick_idx]

        deep_idx = st.selectbox(
            "深度思考模型",
            range(len(deep_options)),
            format_func=lambda i: deep_labels[i],
            key=f"deep_model_idx_{provider_key}",
            help="用于辩论/决策等需要深度推理的任务",
        )
        st.session_state["deep_think_llm"] = deep_values[deep_idx]
    else:
        custom_quick = st.text_input("快速思考模型 ID", key="custom_quick_model")
        custom_deep = st.text_input("深度思考模型 ID", key="custom_deep_model")
        st.session_state["quick_think_llm"] = custom_quick
        st.session_state["deep_think_llm"] = custom_deep


def render_sidebar() -> None:
    """渲染侧边栏，包含输入控件和历史记录。"""

    st.markdown(
        """
        <div style="padding:0 0 1rem; border-bottom:1px solid #1d2835; margin-bottom:1rem;">
            <div style="font-size:1.65rem; font-weight:800; line-height:1;">
                <span style="color:#f59e0b;">AShare</span><span style="color:#f4f7fb;">Agents</span>
            </div>
            <div style="color:#8b98a8; font-size:0.78rem; margin-top:0.45rem; letter-spacing:0.02em;">
                A股多智能体投研操作台
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("##### 新建研究任务")

    ticker = st.text_input(
        "股票代码 / 名称",
        placeholder="例：300750 或 宁德时代",
        key="input_ticker",
        help="输入6位A股代码或中文股票全称",
    )

    trade_date = st.date_input(
        "分析日期",
        value=date.today(),
        key="input_date",
    )

    with st.expander("模型与推理配置", expanded=False):
        _render_llm_config()

    tracker = st.session_state.get("tracker")
    is_busy = tracker is not None and tracker.is_running

    st.markdown(
        """
        <div style="margin:0.85rem 0; color:#657386; font-size:0.78rem; line-height:1.6;">
            任务会依次执行技术面、舆情、新闻、基本面、政策、游资与解禁监控，并进入多空辩论和风控评估。
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.button(
        "启动分析" if not is_busy else "分析进行中...",
        use_container_width=True,
        disabled=is_busy or not ticker,
        type="primary",
    ):
        resolved_code, err = _resolve_user_input(ticker)
        if err:
            st.error(f"{err}")
        else:
            if resolved_code != ticker.strip():
                st.success(f"{ticker.strip()} → {resolved_code}")
            st.session_state["start_analysis"] = {
                "ticker": resolved_code,
                "trade_date": trade_date.strftime("%Y-%m-%d"),
            }
            st.session_state["viewing_history"] = None

    if tracker is not None and st.session_state.get("viewing_history"):
        if tracker.is_running:
            return_label = "返回正在运行的分析"
        elif tracker.is_complete:
            return_label = "返回当前分析结果"
        else:
            return_label = "返回当前分析状态"

        if st.button(return_label, use_container_width=True, type="primary"):
            st.session_state["viewing_history"] = None
            st.rerun()

    st.markdown("---")
    st.markdown("##### 历史研究")

    try:
        history = get_history()
    except APIError as exc:
        st.error(str(exc))
        history = []
    if not history:
        st.markdown(
            '<p style="margin:0; color:#657386; font-size:0.84rem;">暂无历史记录</p>',
            unsafe_allow_html=True,
        )
    else:
        for entry in history[:20]:
            t, d, analysis_time = entry["ticker"], entry["date"], entry["time"]
            label = f"{t}  ·  {d}  ·  {analysis_time}"
            if st.button(
                label,
                key=f"hist_{t}_{d}_{analysis_time}",
                use_container_width=True,
            ):
                st.session_state["viewing_history"] = entry["path"]
                st.session_state["start_analysis"] = None
                st.rerun()
