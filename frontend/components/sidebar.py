"""侧边栏：股票代码输入、LLM 配置和历史记录列表。"""

from __future__ import annotations

from datetime import date

import streamlit as st

from AShareAgents.llm.model_catalog import MODEL_OPTIONS
from frontend.history import get_history

# 供应商显示名称，按推荐顺序排列
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
    """解析用户输入，返回 (股票代码, 错误信息)。

    接受6位数字代码或中文股票名称（如 '宝光股份'）。
    成功时返回 (code, None)，失败时返回 ("", error_msg)。
    """
    from AShareAgents.datasource.astock.a_stock import resolve_ticker

    try:
        code = resolve_ticker(raw)
        return code, None
    except Exception:
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

    # st.text_input(
    #     "API Base URL（第三方/代理，可选）",
    #     key="llm_base_url",
    #     placeholder="例: https://your-proxy.com/v1",
    #     help=(
    #         "通过第三方中转/代理访问 Claude、OpenAI 等模型时填写网关地址；"
    #         "留空则用所选供应商的官方地址。API Key 仍从 .env 读取，"
    #         "且每个供应商用各自的环境变量——"
    #         "OpenAI=OPENAI_API_KEY、DeepSeek=DEEPSEEK_API_KEY、"
    #         "通义=DASHSCOPE_API_KEY、智谱=ZHIPU_API_KEY、MiniMax=MINIMAX_API_KEY、"
    #         "Claude=ANTHROPIC_API_KEY、OpenRouter=OPENROUTER_API_KEY、xAI=XAI_API_KEY。"
    #         "也可在 .env 里设 BACKEND_URL 代替此处。"
    #     ),
    # )


def render_sidebar() -> None:
    """渲染侧边栏，包含输入控件和历史记录。"""

    st.markdown(
        """
        <div style="text-align:center; margin-bottom:1.5rem;">
            <span style="font-size:2rem; font-weight:800; color:#ff5a1f;">AShare</span><span style="font-size:2rem; font-weight:800; color:#f5f1eb;">Agents</span>
            <div style="font-size:0.85rem; color:#888; margin-top:0.2rem;">
                A股多Agent投研系统
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("---")
    st.markdown("#### 新建分析")

    ticker = st.text_input(
        "股票代码",
        placeholder="例: 300750 或 宁德时代",
        key="input_ticker",
        help="输入6位A股代码或中文股票全称",
    )

    trade_date = st.date_input(
        "分析日期",
        value=date.today(),
        key="input_date",
    )

    with st.expander("⚙️ 模型配置", expanded=False):
        _render_llm_config()

    tracker = st.session_state.get("tracker")
    is_busy = tracker is not None and tracker.is_running

    if st.button(
        "开始分析" if not is_busy else "分析进行中...",
        use_container_width=True,
        disabled=is_busy or not ticker,
        type="primary",
    ):
        resolved_code, err = _resolve_user_input(ticker)
        if err:
            st.error(f"❌ {err}")
        else:
            if resolved_code != ticker.strip():
                st.success(f"✅ {ticker.strip()} → {resolved_code}")
            st.session_state["start_analysis"] = {
                "ticker": resolved_code,
                "trade_date": trade_date.strftime("%Y-%m-%d"),
            }
            st.session_state["viewing_history"] = None

    st.markdown("---")
    st.markdown("#### 历史记录")

    history = get_history()
    if not history:
        st.markdown(
            '<p style="margin:0; color:#888; font-size:0.875rem;">暂无历史记录</p>',
            unsafe_allow_html=True,
        )
    else:
        for entry in history[:20]:
            t, d = entry["ticker"], entry["date"]
            label = f"{t}  ·  {d}"
            if st.button(label, key=f"hist_{t}_{d}", use_container_width=True):
                st.session_state["viewing_history"] = entry["path"]
                st.session_state["start_analysis"] = None

