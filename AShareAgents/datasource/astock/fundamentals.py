"""A 股基本面、财务报告和股东数据适配器。"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
import logging
import math

import pandas as pd

from ..eastMoney import get as _em_get
from ..mootdx import get_client as _get_mootdx_client
from ..sinaFinance import get_financial_report as _fetch_sina_financial_report
from ..tencentFinance import get_quotes as _tencent_quote
from ..tongHuaShun import get_eps_forecast as _ths_eps_forecast
from .cache import _cached, _info_once
from .errors import RECOVERABLE_DATA_SOURCE_ERRORS, describe_data_source_error
from .symbols import _get_prefix, _normalize_ticker

logger = logging.getLogger(__name__)

# ---- 3. 获取基本面（get_fundamentals）----


def get_fundamentals(
    ticker: Annotated[str, "A股代码"],
    curr_date: Annotated[str, "当前日期"] = None,
) -> str:
    """从腾讯 + mootdx + 东方财富 + 同花顺获取公司基本面数据。"""
    code = _normalize_ticker(ticker)
    return _cached(f"fundamentals:{code}", _get_fundamentals_impl, code)


def _get_fundamentals_impl(code: str) -> str:
    """get_fundamentals 的实际实现（不含缓存层）。"""
    try:
        lines = []

        # --- 腾讯：实时估值 ---
        try:
            tq = _tencent_quote([code])
            if code in tq:
                q = tq[code]
                lines.extend(
                    [
                        f"名称: {q['name']}",
                        f"最新价: {q['price']}",
                        f"市盈率 (TTM): {q['pe_ttm']}",
                        f"市盈率 (静态): {q['pe_static']}",
                        f"市净率: {q['pb']}",
                        f"总市值 (亿元): {q['mcap_yi']}",
                        f"流通市值 (亿元): {q['float_mcap_yi']}",
                        f"换手率: {q['turnover_pct']}%",
                        f"涨跌幅: {q['change_pct']}%",
                        f"涨停价: {q['limit_up']}",
                        f"跌停价: {q['limit_down']}",
                    ]
                )
        except RECOVERABLE_DATA_SOURCE_ERRORS as e:
            logger.warning("腾讯行情获取 %s 失败: %s", code, e)

        # --- mootdx：财务快照（季度） ---
        try:
            client = _get_mootdx_client()
            fin = client.finance(symbol=code)
            if fin is not None and not (
                isinstance(fin, pd.DataFrame) and fin.empty
            ):
                row = fin.iloc[0] if isinstance(fin, pd.DataFrame) else fin
                field_map = {
                    "eps": "每股收益 (季度)",
                    "bvps": "每股净资产",
                    "roe": "净资产收益率 (%)",
                    "profit": "净利润",
                    "income": "营业收入",
                    "liutongguben": "流通股本",
                    "zongguben": "总股本",
                }
                idx = row.index if hasattr(row, "index") else []
                for field, label in field_map.items():
                    if field in idx:
                        val = row[field]
                        if val is not None and str(val) != "nan":
                            lines.append(f"{label}: {val}")
        except RECOVERABLE_DATA_SOURCE_ERRORS as e:
            _info_once(
                "mootdx-finance",
                "财务数据源切换：mootdx 快照不可用，已继续使用其他数据源",
            )
            logger.debug(
                "mootdx 财务快照 %s 失败: %s",
                code,
                describe_data_source_error(e),
                exc_info=True,
            )

        # --- 东方财富 push2：股票基本信息（直连 HTTP） ---
        try:
            market_code = 1 if code.startswith("6") else 0
            _info_url = "https://push2.eastmoney.com/api/qt/stock/get"
            _info_params = {
                "fltt": "2",
                "invt": "2",
                "fields": "f57,f58,f84,f85,f127,f116,f117,f189,f43",
                "secid": f"{market_code}.{code}",
            }
            r = _em_get(_info_url, params=_info_params, timeout=10)
            d = r.json().get("data", {})
            if d:
                if d.get("f127"):
                    lines.append(f"行业: {d['f127']}")
                if d.get("f84"):
                    lines.append(f"总股本: {d['f84']}")
                if d.get("f85"):
                    lines.append(f"流通股本: {d['f85']}")
                if d.get("f116"):
                    lines.append(f"总市值: {d['f116']}")
                if d.get("f117"):
                    lines.append(f"流通市值: {d['f117']}")
                if d.get("f189"):
                    lines.append(f"上市日期: {d['f189']}")
        except RECOVERABLE_DATA_SOURCE_ERRORS as e:
            logger.warning("东方财富 push2 股票信息获取 %s 失败: %s", code, e)

        # --- 同花顺直连 HTTP：一致预期 EPS 预测 ---
        try:
            forecast_df = _ths_eps_forecast(code)
            if forecast_df is not None and not forecast_df.empty:
                lines.append("\n--- 一致预期 EPS 预测 (同花顺) ---")
                eps_by_year = {}
                for _, row in forecast_df.iterrows():
                    year = str(row.iloc[0]) if len(row) > 0 else ""
                    mean_eps_val = row.iloc[3] if len(row) > 3 else 0
                    count_val = row.iloc[1] if len(row) > 1 else 0
                    min_eps_val = row.iloc[2] if len(row) > 2 else "N/A"
                    max_eps_val = row.iloc[4] if len(row) > 4 else "N/A"
                    try:
                        mean_eps = float(mean_eps_val)
                    except (ValueError, TypeError):
                        mean_eps = 0
                    try:
                        count = int(count_val)
                    except (ValueError, TypeError):
                        count = 0
                    lines.append(
                        f"FY{year}: EPS={mean_eps} "
                        f"(区间 {min_eps_val}~{max_eps_val}，{count} 家机构)"
                    )
                    if count < 3:
                        lines.append("  警告：覆盖机构数量不足（<3 家）")
                    eps_by_year[year] = mean_eps

                # 远期PE / PEG / PE消化年数
                try:
                    tq = _tencent_quote([code])
                    if code in tq:
                        price = tq[code]["price"]
                        years_sorted = sorted(eps_by_year.keys())
                        if years_sorted and eps_by_year.get(years_sorted[0], 0) > 0:
                            eps_cur = eps_by_year[years_sorted[0]]
                            fwd_pe = price / eps_cur
                            lines.append(
                                f"\n远期市盈率 (FY{years_sorted[0]}): "
                                f"{fwd_pe:.1f}x (价格={price}, EPS={eps_cur})"
                            )
                            if (
                                len(years_sorted) >= 2
                                and eps_by_year.get(years_sorted[1], 0) > 0
                            ):
                                eps_next = eps_by_year[years_sorted[1]]
                                cagr = eps_next / eps_cur - 1
                                if cagr > 0:
                                    peg = fwd_pe / (cagr * 100)
                                    lines.append(
                                        f"PEG: {peg:.2f} "
                                        f"(EPS 复合增长率={cagr * 100:.0f}%)"
                                    )
                                    if fwd_pe > 30:
                                        digest = math.log(fwd_pe / 30) / math.log(
                                            1 + cagr
                                        )
                                        lines.append(
                                            f"PE 消化至 30 倍所需年数: {digest:.1f} 年"
                                        )
                                    else:
                                        lines.append("PE 已低于 30 倍目标")
                                else:
                                    lines.append(
                                        f"EPS 下滑 ({cagr * 100:.0f}%), "
                                        f"PEG 不适用"
                                    )
                except RECOVERABLE_DATA_SOURCE_ERRORS as e:
                    logger.warning("远期 PE 计算 %s 失败: %s", code, e)
        except RECOVERABLE_DATA_SOURCE_ERRORS as e:
            logger.warning("一致预期 EPS 预测获取 %s 失败: %s", code, e)

        if not lines:
            return f"未找到 A 股 '{code}' 的基本面数据"

        header = f"# {code} (A股) 公司基本面\n"
        header += (
            f"# 数据获取时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        )

        return header + "\n".join(lines)

    except RECOVERABLE_DATA_SOURCE_ERRORS as e:
        return f"获取 {code} 基本面数据时出错：{str(e)}"


# ---- 4. 获取资产负债表（get_balance_sheet）----


def _sina_stock_code(code: str) -> str:
    """纯6位代码 -> 新浪格式 (sh688017 / sz000001 / bj832000)。"""
    return f"{_get_prefix(code)}{code}"


def _get_financial_report_sina(
    code: str, report_type: str, freq: str, curr_date: str = None,
) -> pd.DataFrame:
    """公用辅助函数：通过新浪直连 HTTP API 获取财务报表。

    Args:
        report_type: '资产负债表' | '利润表' | '现金流量表'
    """
    return _fetch_sina_financial_report(code, report_type, freq, curr_date)


def get_balance_sheet(
    ticker: Annotated[str, "A股代码"],
    freq: Annotated[str, "频率：'annual' 或 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "当前日期，格式 YYYY-MM-DD"] = None,
) -> str:
    """通过新浪直连 HTTP API 获取资产负债表。"""
    code = _normalize_ticker(ticker)

    try:
        df = _get_financial_report_sina(code, "资产负债表", freq, curr_date)

        if df.empty:
            return f"未找到 A 股 '{code}' 的资产负债表数据"

        csv_string = df.to_csv(index=False)

        header = f"# {code} (A股, {freq}) 资产负债表\n"
        header += "# 数据来源: 新浪直连 HTTP\n"
        header += (
            f"# 数据获取时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        )

        return header + csv_string

    except RECOVERABLE_DATA_SOURCE_ERRORS as e:
        return f"获取 {code} 资产负债表数据时出错：{str(e)}"


# ---- 5. 获取现金流量表（get_cashflow）----


def get_cashflow(
    ticker: Annotated[str, "A股代码"],
    freq: Annotated[str, "频率：'annual' 或 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "当前日期，格式 YYYY-MM-DD"] = None,
) -> str:
    """通过新浪直连 HTTP API 获取现金流量表。"""
    code = _normalize_ticker(ticker)

    try:
        df = _get_financial_report_sina(code, "现金流量表", freq, curr_date)

        if df.empty:
            return f"未找到 A 股 '{code}' 的现金流量表数据"

        csv_string = df.to_csv(index=False)

        header = f"# {code} (A股, {freq}) 现金流量表\n"
        header += "# 数据来源: 新浪直连 HTTP\n"
        header += (
            f"# 数据获取时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        )

        return header + csv_string

    except RECOVERABLE_DATA_SOURCE_ERRORS as e:
        return f"获取 {code} 现金流量表数据时出错：{str(e)}"


# ---- 6. 获取利润表（get_income_statement）----


def get_income_statement(
    ticker: Annotated[str, "A股代码"],
    freq: Annotated[str, "频率：'annual' 或 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "当前日期，格式 YYYY-MM-DD"] = None,
) -> str:
    """通过新浪直连 HTTP API 获取利润表。"""
    code = _normalize_ticker(ticker)

    try:
        df = _get_financial_report_sina(code, "利润表", freq, curr_date)

        if df.empty:
            return f"未找到 A 股 '{code}' 的利润表数据"

        csv_string = df.to_csv(index=False)

        header = f"# {code} (A股, {freq}) 利润表\n"
        header += "# 数据来源: 新浪直连 HTTP\n"
        header += (
            f"# 数据获取时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        )

        return header + csv_string

    except RECOVERABLE_DATA_SOURCE_ERRORS as e:
        return f"获取 {code} 利润表数据时出错：{str(e)}"


# ---- 9. 获取股东/内部人活动（get_insider_transactions）----


def get_insider_transactions(
    ticker: Annotated[str, "A股代码"],
) -> str:
    """通过 mootdx F10 获取股东/内部人活动。

    注意：A股内部人交易数据与美股市场不同。
    此处使用 mootdx F10 股东研究作为最接近的等价数据。
    """
    code = _normalize_ticker(ticker)

    try:
        client = _get_mootdx_client()
        text = client.F10(symbol=code, name="股东研究")

        if not text or not text.strip():
            return f"未找到 A 股 '{code}' 的股东/内部人数据"

        header = f"# {code} (A股) 股东研究\n"
        header += "# 注：A 股内部人交易等价数据\n"
        header += "# 数据来源: mootdx F10\n"
        header += (
            f"# 数据获取时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        )

        import re

        sec4_hits = list(re.finditer(r"\r?\n【4\.股东变化】\r?\n", text))
        if sec4_hits:
            sec4_pos = sec4_hits[-1].start()
            before_sec4 = text[:sec4_pos]
            sec4_text = text[sec4_pos:]
            cut_at = 2000
            if len(sec4_text) > cut_at:
                sec4_text = (
                    sec4_text[:cut_at]
                    + "\n\n(... 较早的股东历史已省略，"
                    f"共截断 {len(text) - sec4_pos - cut_at} 字符 ...)"
                )
            text = before_sec4 + sec4_text

        return header + text

    except RECOVERABLE_DATA_SOURCE_ERRORS as e:
        return f"获取 {code} 股东/内部人数据时出错：{str(e)}"

