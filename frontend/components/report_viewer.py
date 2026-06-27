"""渲染完成的分析报告，包含可展开章节和 PDF 下载功能。"""

from __future__ import annotations

import html
import re
from typing import Any

import streamlit as st

from frontend.pdf_export import generate_markdown, generate_pdf


def _strip_think(text: str) -> str:
    return re.sub(r"<think>.*?</think>\s*", "", text, flags=re.DOTALL).strip()


def _signal_style(signal: str) -> tuple[str, str]:
    s = signal.strip().lower()
    if s == "buy":
        return "#22c55e", "买入"
    if s == "overweight":
        return "#84cc16", "增持"
    if s == "hold":
        return "#eab308", "持有"
    if s == "underweight":
        return "#f97316", "减持"
    if s == "sell":
        return "#ef4444", "卖出"
    return "#8b98a8", "未知"


_ANALYST_SECTIONS = [
    ("market_report", "📊 技术分析"),
    ("sentiment_report", "💬 市场情绪"),
    ("news_report", "📰 新闻舆情"),
    ("fundamentals_report", "📋 基本面"),
    ("policy_report", "🏛️ 政策分析"),
    ("hot_money_report", "🔥 游资追踪"),
    ("lockup_report", "🔒 解禁/减持"),
]


def _count_available_sections(final_state: dict[str, Any]) -> int:
    keys = [key for key, _ in _ANALYST_SECTIONS]
    extra = ["investment_plan", "trader_investment_decision", "risk_debate_state", "investment_debate_state"]
    return sum(1 for key in keys + extra if final_state.get(key))


def render_report(
    final_state: dict[str, Any],
    ticker: str,
    trade_date: str,
    signal: str,
    elapsed: float | None = None,
) -> None:
    """渲染完整的分析报告。"""

    color, cn_signal = _signal_style(signal)
    safe_signal = html.escape(signal.upper())
    safe_ticker = html.escape(str(ticker))
    safe_trade_date = html.escape(str(trade_date))
    section_count = _count_available_sections(final_state)

    elapsed_label = "历史报告"
    if elapsed is not None:
        m, s = divmod(int(elapsed), 60)
        elapsed_label = f"耗时 {m}:{s:02d}"

    st.html(
        f"""
        <div class="as-topbar">
            <div>
                <div class="as-kicker">FINAL RESEARCH MEMO</div>
                <div class="as-title">{safe_ticker} 投研结论</div>
                <div class="as-subtitle">分析日期：{safe_trade_date} · {elapsed_label}</div>
            </div>
            <div class="as-session">
                <div class="as-pill">章节 {section_count}</div>
                <div class="as-pill">AI 自动生成</div>
                <div class="as-pill">可导出</div>
            </div>
        </div>
        """
    )

    st.html(
        f"""
        <div class="as-grid">
            <div class="as-panel">
                <div class="as-panel-title">
                    <span>交易信号</span>
                    <span class="as-muted">Portfolio Manager Decision</span>
                </div>
                <div style="display:flex; align-items:flex-end; justify-content:space-between; gap:1rem;">
                    <div>
                        <div style="font-size:3rem; line-height:1; font-weight:800; color:{color};">{safe_signal}</div>
                        <div style="color:#dbe3ed; margin-top:0.35rem; font-weight:700;">{html.escape(cn_signal)}</div>
                    </div>
                    <div style="text-align:right; color:#8b98a8; font-size:0.86rem; line-height:1.7;">
                        标的：{safe_ticker}<br>
                        日期：{safe_trade_date}<br>
                        {elapsed_label}
                    </div>
                </div>
            </div>
            <div class="as-panel">
                <div class="as-panel-title">
                    <span>报告操作</span>
                    <span class="as-muted">Export</span>
                </div>
                <div class="as-muted" style="line-height:1.7;">下载研究备忘录用于归档、复盘或二次审阅。PDF 生成失败时不会影响报告阅读。</div>
            </div>
        </div>
        """
    )

    col_md, col_pdf, _ = st.columns([1, 1, 2])
    with col_md:
        md_text = generate_markdown(final_state, ticker, trade_date, signal)
        st.download_button(
            "下载 Markdown",
            data=md_text.encode("utf-8"),
            file_name=f"AShareAgents-Astock_{ticker}_{trade_date}.md",
            mime="text/markdown",
            use_container_width=True,
        )
    with col_pdf:
        try:
            pdf_bytes = generate_pdf(final_state, ticker, trade_date, signal)
            st.download_button(
                "下载 PDF",
                data=pdf_bytes,
                file_name=f"AShareAgents-Astock_{ticker}_{trade_date}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        except Exception as exc:  # noqa: BLE001 - PDF 导出异常不得中断结果展示。
            st.button(
                "PDF 不可用",
                disabled=True,
                use_container_width=True,
                help=f"PDF 生成失败，请改用 Markdown 导出。原因：{exc}",
            )

    inv_plan = final_state.get("investment_plan", "")
    if inv_plan:
        st.markdown("### 最终投资建议")
        st.markdown(_strip_think(str(inv_plan)))

    st.markdown("### 分析师报告")
    for key, title in _ANALYST_SECTIONS:
        content = final_state.get(key, "")
        if not content:
            continue
        with st.expander(title, expanded=False):
            st.markdown(_strip_think(str(content)))

    debate = final_state.get("investment_debate_state")
    if debate and isinstance(debate, dict):
        st.markdown("### 多空辩论")
        tab_bull, tab_bear, tab_judge = st.tabs(["多方", "空方", "研究经理"])
        with tab_bull:
            st.markdown(_strip_think(debate.get("bull_history", "") or "无数据"))
        with tab_bear:
            st.markdown(_strip_think(debate.get("bear_history", "") or "无数据"))
        with tab_judge:
            st.markdown(_strip_think(debate.get("judge_decision", "") or "无数据"))

    trader_decision = final_state.get("trader_investment_decision", "")
    if trader_decision:
        with st.expander("交易员决策", expanded=False):
            st.markdown(_strip_think(str(trader_decision)))

    risk = final_state.get("risk_debate_state")
    if risk and isinstance(risk, dict):
        st.markdown("### 风控评估")
        tab_agg, tab_con, tab_neu, tab_rj = st.tabs(["激进", "保守", "中性", "风控决策"])
        with tab_agg:
            st.markdown(_strip_think(risk.get("aggressive_history", "") or "无数据"))
        with tab_con:
            st.markdown(_strip_think(risk.get("conservative_history", "") or "无数据"))
        with tab_neu:
            st.markdown(_strip_think(risk.get("neutral_history", "") or "无数据"))
        with tab_rj:
            st.markdown(_strip_think(risk.get("judge_decision", "") or "无数据"))

    dqs = final_state.get("data_quality_summary", "")
    if dqs:
        with st.expander("数据质量", expanded=False):
            st.markdown(str(dqs))

    st.caption("风险提示：本报告由 AI 自动生成，仅供学习研究，不构成投资建议。")
