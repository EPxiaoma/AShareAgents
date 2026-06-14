"""AShareAgents A股（中国大陆）数据编排层。

聚合同级供应商适配器的数据，并提供缓存、回退和统一文本输出。

数据来源：
- mootdx (TCP 7709)：OHLCV K线、财务快照、F10文本
- 腾讯财经 (HTTP GBK)：PE/PB/市值/换手率
- 东方财富 push2 / datacenter-web (直连HTTP)：股票信息、龙虎榜、限售解禁
- 新浪财经 (直连HTTP)：K线备用源、财务报表
- 同花顺 (直连HTTP)：一致预期EPS、热门股票、北向资金流向
- 财联社 (直连HTTP)：全球财经快讯
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Annotated, Any
from datetime import datetime
from dateutil.relativedelta import relativedelta
import os
import logging
import math
import threading
import time

import pandas as pd
from ..utils import safe_ticker_component
from ..baiduFinance import get as _baidu_get
from ..eastMoney import datacenter as _eastmoney_datacenter
from ..eastMoney import get as _em_get
from ..eastMoney import resolve_stock_code as _resolve_eastmoney_stock_code
from ..mootdx import build_name_code_map as _load_mootdx_name_code_map
from ..mootdx import get_client as _get_mootdx_client
from ..mootdx import get_daily_bars as _get_mootdx_daily_bars
from ..sinaFinance import get_daily_kline as _sina_kline_fallback
from ..sinaFinance import get_financial_report as _fetch_sina_financial_report
from ..tencentFinance import get_quotes as _tencent_quote
from ..tongHuaShun import get_eps_forecast as _ths_eps_forecast
from ..tongHuaShun import get as _ths_get
from .errors import RECOVERABLE_DATA_SOURCE_ERRORS, describe_data_source_error
from .events import (
    get_dragon_tiger_board as _get_dragon_tiger_board,
    get_industry_comparison as _get_industry_comparison,
    get_lockup_expiry as _get_lockup_expiry,
)
from .news import (
    fetch_eastmoney_company_news as _news_fetch_eastmoney,
    fetch_sina_company_news as _news_fetch_sina,
    get_company_news as _get_company_news,
    get_global_news as _aggregate_global_news,
)

logger = logging.getLogger(__name__)


# 运行期缓存：同一次分析中避免同一数据源重复请求

_RUN_CACHE_TTL_SECONDS = 300.0
_RUN_CACHE_MAX_ENTRIES = 128
_run_cache: OrderedDict[str, tuple[float, Any]] = OrderedDict()
_run_cache_lock = threading.RLock()
_cache_key_locks: dict[str, threading.Lock] = {}
_warning_keys: set[str] = set()


def _cached(key: str, factory, *args) -> Any:
    """Return a short-lived cached result for an expensive external request."""
    now = time.monotonic()
    with _run_cache_lock:
        cached = _run_cache.get(key)
        if cached is not None:
            created_at, value = cached
            if now - created_at < _RUN_CACHE_TTL_SECONDS:
                _run_cache.move_to_end(key)
                return value
            del _run_cache[key]
        key_lock = _cache_key_locks.setdefault(key, threading.Lock())

    # Serialize only identical keys. Unrelated data sources remain parallel.
    with key_lock:
        now = time.monotonic()
        with _run_cache_lock:
            cached = _run_cache.get(key)
            if cached is not None:
                created_at, value = cached
                if now - created_at < _RUN_CACHE_TTL_SECONDS:
                    _run_cache.move_to_end(key)
                    return value
                del _run_cache[key]

        value = factory(*args)
        with _run_cache_lock:
            _run_cache[key] = (time.monotonic(), value)
            _run_cache.move_to_end(key)
            while len(_run_cache) > _RUN_CACHE_MAX_ENTRIES:
                _run_cache.popitem(last=False)
        return value


def _clear_runtime_cache() -> None:
    """Clear process-local data, primarily for deterministic tests."""
    with _run_cache_lock:
        _run_cache.clear()
        _cache_key_locks.clear()


def _warning_once(key: str, message: str, *args) -> None:
    """同类外部数据源故障只告警一次，后续保留在 debug 日志。"""
    with _run_cache_lock:
        if key in _warning_keys:
            logger.debug(message, *args)
            return
        _warning_keys.add(key)
    logger.warning(message, *args)


def _info_once(key: str, message: str, *args) -> None:
    """Log a successful fallback once and keep repeats at debug level."""
    with _run_cache_lock:
        if key in _warning_keys:
            logger.debug(message, *args)
            return
        _warning_keys.add(key)
    logger.info(message, *args)


# 股票代码格式与市场识别

def _get_prefix(code: str) -> str:
    """6位A股代码 -> 腾讯API所需的市场前缀。"""
    if code.startswith(("6", "9")):
        return "sh"
    elif code.startswith("8"):
        return "bj"
    return "sz"


def _normalize_ticker(symbol: str) -> str:
    """去除交易所前缀/后缀，返回纯6位代码。

    支持的格式：'688017'、'SH688017'、'688017.SH'、'sh688017'
    """
    s = symbol.strip().upper()
    # 去除 .SH / .SZ / .BJ 后缀
    for suffix in (".SH", ".SZ", ".BJ"):
        if s.endswith(suffix):
            s = s[: -len(suffix)]
            break
    # 去除 SH / SZ / BJ 前缀
    for prefix in ("SH", "SZ", "BJ"):
        if s.startswith(prefix):
            s = s[len(prefix) :]
            break
    return safe_ticker_component(s)


# 股票名称与代码映射缓存

_name_to_code: dict[str, str] | None = None
_code_to_name: dict[str, str] | None = None
_api_resolution_cache: dict[str, str | None] = {}


def _build_name_code_map() -> tuple[dict[str, str], dict[str, str]]:
    """通过 mootdx 构建 名称→代码 和 代码→名称 映射（覆盖沪深两市）。

    当 mootdx 不可达时回退为空映射——单只股票的名称查询将按需改用东方财富搜索API。
    """
    global _name_to_code, _code_to_name
    if _name_to_code is not None:
        return _name_to_code, _code_to_name

    try:
        n2c, c2n = _load_mootdx_name_code_map()
    except RECOVERABLE_DATA_SOURCE_ERRORS as exc:
        n2c, c2n = {}, {}
        logger.debug("mootdx 名称-代码映射构建失败: %s", exc, exc_info=True)

    _name_to_code = n2c
    _code_to_name = c2n
    if n2c:
        logger.info("已构建股票名称-代码映射：%d 条记录", len(n2c))
    else:
        _info_once(
            "mootdx-name-map",
            "股票名称解析：mootdx 列表不可用，已启用东方财富按需查询",
        )
    return _name_to_code, _code_to_name


def _resolve_by_api(keyword: str) -> str | None:
    """通过东方财富联想搜索API将中文股票名称解析为6位代码。

    Returns:
        代码字符串，若未匹配到则返回 None。
    """
    if keyword in _api_resolution_cache:
        return _api_resolution_cache[keyword]

    result: str | None = None
    try:
        result = _resolve_eastmoney_stock_code(keyword)
    except RECOVERABLE_DATA_SOURCE_ERRORS as exc:
        logger.warning("东方财富联想搜索 API 对 %r 的请求失败: %s", keyword, exc)

    if result is not None:
        _api_resolution_cache[keyword] = result
    return result


def resolve_ticker(user_input: str) -> str:
    """将用户输入（代码或中文名称）解析为6位A股代码。

    支持的输入：'600379'、'SH600379'、'600379.SH'、'宝光股份'

    Returns:
        '600379' 格式的6位代码。

    Raises:
        ValueError: 无法解析时抛出。
    """
    s = user_input.strip()
    if not s:
        raise ValueError("输入不能为空")

    has_chinese = any("一" <= ch <= "鿿" for ch in s)

    if not has_chinese:
        return _normalize_ticker(s)

    clean = s.replace(" ", "").replace("　", "")
    n2c, _ = _build_name_code_map()

    if clean in n2c:
        return n2c[clean]

    matches = {name: code for name, code in n2c.items() if clean in name}
    if len(matches) == 1:
        return next(iter(matches.values()))
    if len(matches) > 1:
        examples = ", ".join(f"{n}({c})" for n, c in list(matches.items())[:5])
        raise ValueError(f"'{s}' 匹配到多只股票: {examples}，请输入完整名称或代码")

    # 回退：本地映射为空或不包含此名称时（如 mootdx 不可达、新股上市），
    # 尝试东方财富联想搜索API。
    api_code = _resolve_by_api(clean)
    if api_code:
        n2c[clean] = api_code
        if _code_to_name is not None:
            _code_to_name.setdefault(api_code, clean)
        logger.info("API 解析 %r -> %s", s, api_code)
        return api_code

    raise ValueError(f"找不到股票 '{s}'，请检查名称是否正确")


# OHLCV 数据优先从 mootdx 获取，并以 CSV 缓存。

def _load_ohlcv_astock(symbol: str, curr_date: str) -> pd.DataFrame:
    """通过 mootdx 获取 OHLCV，缓存至 CSV，按 curr_date 过滤。

    类似 stockstats_utils.load_ohlcv，但使用 mootdx 替代 yfinance。

    Returns:
        包含以下列的 DataFrame：Date、Open、High、Low、Close、Volume。
    """
    from ..config import get_config

    code = _normalize_ticker(symbol)
    config = get_config()
    cache_dir = config.get(
        "data_cache_dir", os.path.expanduser("~/.ashareagents/cache")
    )
    os.makedirs(cache_dir, exist_ok=True)

    cache_file = os.path.join(cache_dir, f"{code}-astock-daily.csv")

    if os.path.exists(cache_file):
        mtime = datetime.fromtimestamp(os.path.getmtime(cache_file))
        if mtime.date() == datetime.now().date():
            data = pd.read_csv(cache_file, on_bad_lines="skip", encoding="utf-8")
            data["Date"] = pd.to_datetime(data["Date"])
            cutoff = pd.to_datetime(curr_date)
            return data[data["Date"] <= cutoff]

    # 从 mootdx 获取 800 根日K线（约3年交易日）
    try:
        df = _get_mootdx_daily_bars(code)
        if df.empty:
            raise ValueError(f"mootdx 未返回 {code} 的 OHLCV 数据")
    except RECOVERABLE_DATA_SOURCE_ERRORS as e:
        mootdx_error = e
        # 回退：新浪直连 HTTP API
        try:
            df = _sina_kline_fallback(code)
            if df.empty:
                raise ValueError(f"新浪未返回 {code} 的 OHLCV 数据")
            logger.info("行情数据源切换：%s 的 mootdx 数据不可用，已使用新浪财经", code)
        except RECOVERABLE_DATA_SOURCE_ERRORS as fallback_error:
            logger.warning(
                "OHLCV 获取 %s 失败：mootdx=%s；新浪=%s",
                code,
                mootdx_error,
                fallback_error,
            )
            raise ValueError(f"mootdx 和新浪均未返回 {code} 的 OHLCV 数据")

    # 缓存到磁盘
    df.to_csv(cache_file, index=False, encoding="utf-8")

    # 按 curr_date 过滤，防止前视偏差
    cutoff = pd.to_datetime(curr_date)
    return df[df["Date"] <= cutoff]


# 以下供应商方法必须与 interface.py 的 VENDOR_METHODS 签名保持一致。


# ---- 1. get_stock_data ----


def get_stock_data(
    symbol: Annotated[str, "A股代码（如 688017、SH688017）"],
    start_date: Annotated[str, "起始日期，格式 yyyy-mm-dd"],
    end_date: Annotated[str, "结束日期，格式 yyyy-mm-dd"],
) -> str:
    """获取 A 股 OHLCV 行情数据，复用 _load_ohlcv_astock 的缓存层。"""
    code = _normalize_ticker(symbol)

    try:
        df = _load_ohlcv_astock(code, end_date)
    except RECOVERABLE_DATA_SOURCE_ERRORS:
        return "K线数据获取失败：mootdx和新浪备用源均不可用，请检查网络连接"

    # 按日期范围过滤
    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)
    df = df[(df["Date"] >= start_dt) & (df["Date"] <= end_dt)]

    if df.empty:
        return f"在 {start_date} 至 {end_date} 期间未找到 A 股 '{code}' 的数据"

    for col in ["Open", "High", "Low", "Close"]:
        if col in df.columns:
            df[col] = df[col].round(2)

    df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")
    csv_out = df[["Date", "Open", "High", "Low", "Close", "Volume"]].to_csv(
        index=False
    )

    header = f"# {code} (A股) 行情数据，{start_date} 至 {end_date}\n"
    header += f"# 总记录数: {len(df)}\n"
    header += (
        f"# 数据获取时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    )

    return header + csv_out


# ---- 2. get_indicators ----

# 支持的技术指标及其说明
_INDICATOR_DESCRIPTIONS = {
    "close_50_sma": "50 日均线：中期趋势指标。",
    "close_200_sma": "200 日均线：长期趋势基准。",
    "close_10_ema": "10 日 EMA：灵敏的短期均线。",
    "macd": "MACD：通过 EMA 差值计算的动量指标。",
    "macds": "MACD 信号线：MACD 线的 EMA 平滑。",
    "macdh": "MACD 柱：MACD 与信号线之间的差值。",
    "rsi": "RSI：超买/超卖动量指标（阈值 70/30）。",
    "boll": "布林带中轨：20 日均线基准线。",
    "boll_ub": "布林带上轨：中轨上方 2 个标准差。",
    "boll_lb": "布林带下轨：中轨下方 2 个标准差。",
    "atr": "ATR：平均真实波幅，衡量波动率。",
    "vwma": "VWMA：成交量加权移动平均。",
    "mfi": "MFI：资金流量指数（成交量 + 价格动量）。",
}


def get_indicators(
    symbol: Annotated[str, "A股代码"],
    indicator: Annotated[
        str, "技术指标（如 rsi、macd、close_50_sma）"
    ],
    curr_date: Annotated[str, "当前交易日，格式 YYYY-mm-dd"],
    look_back_days: Annotated[int, "回顾多少天"],
) -> str:
    """基于 mootdx OHLCV 数据，使用 stockstats 计算技术指标。"""
    from stockstats import wrap

    code = _normalize_ticker(symbol)

    if indicator not in _INDICATOR_DESCRIPTIONS:
        raise ValueError(
            f"不支持的指标 {indicator}。"
            f"请从以下选项中选择：{list(_INDICATOR_DESCRIPTIONS.keys())}"
        )

    try:
        data = _load_ohlcv_astock(code, curr_date)
        df = wrap(data)
        df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")

        # 触发 stockstats 计算
        df[indicator]

        # 构建 日期 -> 指标值 的查找表
        ind_dict = {}
        for _, row in df.iterrows():
            d = row["Date"]
            v = row[indicator]
            ind_dict[d] = "N/A" if pd.isna(v) else str(round(float(v), 4))

        # 生成回顾窗口内的输出
        curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
        before = curr_dt - relativedelta(days=look_back_days)

        lines = []
        dt = curr_dt
        while dt >= before:
            ds = dt.strftime("%Y-%m-%d")
            val = ind_dict.get(ds, "N/A：非交易日（周末或节假日）")
            lines.append(f"{ds}: {val}")
            dt -= relativedelta(days=1)

        result = (
            f"## {code} 的 {indicator} 指标值 "
            f"（{before.strftime('%Y-%m-%d')} 至 {curr_date}）:\n\n"
            + "\n".join(lines)
            + "\n\n"
            + _INDICATOR_DESCRIPTIONS.get(indicator, "")
        )
        return result

    except RECOVERABLE_DATA_SOURCE_ERRORS as e:
        return f"计算 {code} 的 {indicator} 指标时出错：{str(e)}"


# ---- 3. get_fundamentals ----


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


# ---- 4. get_balance_sheet ----


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


# ---- 5. get_cashflow ----


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


# ---- 6. get_income_statement ----


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


# ---- 7. get_news ----


def _fetch_news_eastmoney(code: str, page_size: int = 20) -> list[dict]:
    """Compatibility wrapper for the extracted Eastmoney news adapter."""
    return _news_fetch_eastmoney(code, page_size)




def _fetch_news_sina(code: str, page_size: int = 20) -> list[dict]:
    """Compatibility wrapper for the extracted Sina news adapter."""
    return _news_fetch_sina(code, page_size)




def get_news(
    ticker: Annotated[str, "A股代码"],
    start_date: Annotated[str, "起始日期，格式 yyyy-mm-dd"],
    end_date: Annotated[str, "结束日期，格式 yyyy-mm-dd"],
) -> str:
    """获取个股新闻，东方财富失败时回退到新浪财经。"""
    return _get_company_news(_normalize_ticker(ticker), start_date, end_date)




# ---- 8. get_global_news ----


def get_global_news(
    curr_date: Annotated[str, "当前日期，格式 yyyy-mm-dd"],
    look_back_days: Annotated[int, "回顾天数"] = 7,
    limit: Annotated[int, "最多文章数"] = 10,
) -> str:
    """获取中国及全球财经新闻。"""
    return _cached(
        f"global_news:{curr_date}:{look_back_days}:{limit}",
        _get_global_news_impl,
        curr_date,
        look_back_days,
        limit,
    )


def _get_global_news_impl(curr_date: str, look_back_days: int, limit: int) -> str:
    """Execute the extracted global-news aggregation without caching."""
    return _aggregate_global_news(
        curr_date,
        look_back_days,
        limit,
        warning_once=_warning_once,
    )




# ---- 9. get_insider_transactions ----


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


# ---- 10. get_profit_forecast ----


def get_profit_forecast(
    ticker: Annotated[str, "A股代码"],
    curr_date: Annotated[str, "当前日期（未使用，仅为接口兼容保留）"] = None,
) -> str:
    """获取一致预期EPS预测及远期估值（同花顺直连 HTTP）。"""
    code = _normalize_ticker(ticker)

    try:
        df = _ths_eps_forecast(code)

        if df is None or df.empty:
            return f"未找到 A 股 '{code}' 的分析师覆盖数据"

        lines = [
            f"# {code} (A股) 一致预期 EPS 预测",
            f"# 来源: 同花顺分析师一致预期 (直连 HTTP)",
            f"# 获取时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
        ]

        eps_by_year = {}
        for _, row in df.iterrows():
            year = str(row.iloc[0]) if len(row) > 0 else ""
            count_val = row.iloc[1] if len(row) > 1 else 0
            mean_eps_val = row.iloc[3] if len(row) > 3 else 0
            min_eps_val = row.iloc[2] if len(row) > 2 else "N/A"
            max_eps_val = row.iloc[4] if len(row) > 4 else "N/A"
            try:
                count = int(count_val)
            except (ValueError, TypeError):
                count = 0
            try:
                mean_eps = float(mean_eps_val)
            except (ValueError, TypeError):
                mean_eps = 0
            lines.append(
                f"FY{year}: EPS={mean_eps} (区间 {min_eps_val}~{max_eps_val}), "
                f"机构数={count}"
            )
            if count < 3:
                lines.append("  警告：覆盖机构数量不足（<3 家）")
            eps_by_year[year] = mean_eps

        # 远期估值
        try:
            tq = _tencent_quote([code])
            if code in tq:
                price = tq[code]["price"]
                pe_ttm = tq[code]["pe_ttm"]
                lines.append(f"\n当前: 价格={price}, PE(TTM)={pe_ttm}")

                years_sorted = sorted(eps_by_year.keys())
                if years_sorted and eps_by_year.get(years_sorted[0], 0) > 0:
                    eps_cur = eps_by_year[years_sorted[0]]
                    fwd_pe = price / eps_cur
                    lines.append(
                        f"远期市盈率 (FY{years_sorted[0]}): {fwd_pe:.1f}x"
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
                                f"PEG: {peg:.2f} (复合增长率={cagr * 100:.0f}%)"
                            )
                            if fwd_pe > 30:
                                digest = math.log(fwd_pe / 30) / math.log(
                                    1 + cagr
                                )
                                lines.append(
                                    f"PE 消化至 30 倍所需年数: {digest:.1f} 年"
                                )
                        else:
                            lines.append(
                                f"EPS 下滑 ({cagr * 100:.0f}%), "
                                f"PEG 不适用"
                            )
        except RECOVERABLE_DATA_SOURCE_ERRORS as e:
            logger.warning("远期 PE 计算 %s 失败: %s", code, e)

        return "\n".join(lines)

    except RECOVERABLE_DATA_SOURCE_ERRORS as e:
        return f"获取 {code} 盈利预测数据时出错：{str(e)}"


# ---- 11. get_hot_stocks ----


def get_hot_stocks(
    curr_date: Annotated[str, "日期，格式 YYYY-MM-DD，空字符串表示今天"] = "",
) -> str:
    """从同花顺编辑团队获取强势股及其题材归因。

    返回触及涨停的股票，附带人工精选的涨停原因标签
    （如 '算力租赁+AI政务'），解释其为何大涨。
    """
    if not curr_date or curr_date.strip() == "":
        curr_date = datetime.now().strftime("%Y-%m-%d")

    try:
        url = (
            f"http://zx.10jqka.com.cn/event/api/getharden/"
            f"date/{curr_date}/orderby/date/orderway/desc/charset/GBK/"
        )
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "Chrome/117.0.0.0 Safari/537.36"
            )
        }
        r = _ths_get(url, headers=headers, timeout=10)
        data = r.json()

        if data.get("errocode", 0) != 0:
            return f"同花顺 API 错误: {data.get('errormsg', '未知错误')}"

        rows = data.get("data") or []
        if not rows:
            return (
                f"{curr_date} 无热门股票数据"
                f"（可能为非交易日或数据尚未更新）"
            )

        lines = [
            f"# 热门股票及题材归因 ({curr_date})",
            f"# 来源: 同花顺编辑团队 (人工精选涨停原因标签)",
            f"# 合计: {len(rows)} 只股票",
            "",
        ]

        from collections import Counter

        all_tags: list[str] = []

        for row in rows:
            code = row.get("code", "")
            name = row.get("name", "")
            reason = row.get("reason", "")
            zhangfu = row.get("zhangfu", "")
            huanshou = row.get("huanshou", "")
            chengjiaoe = row.get("chengjiaoe", "")
            dde = row.get("ddejingliang", "")

            lines.append(
                f"{code} {name}: +{zhangfu}% "
                f"换手{huanshou}% 成交额{chengjiaoe} "
                f"大单净量{dde} | {reason}"
            )

            if reason:
                tags = [t.strip() for t in str(reason).split("+") if t.strip()]
                all_tags.extend(tags)

        if all_tags:
            cnt = Counter(all_tags)
            lines.append(f"\n## 题材出现频率 (前15)")
            for tag, n in cnt.most_common(15):
                lines.append(f"  {tag}: {n} 只股票")

        return "\n".join(lines)

    except RECOVERABLE_DATA_SOURCE_ERRORS as e:
        return f"获取 {curr_date} 热门股票数据时出错：{str(e)}"


# ---- 12. get_northbound_flow ----


def _northbound_cache_path() -> str:
    """本地 CSV 缓存路径，存储北向资金每日收盘快照。"""
    from ..config import get_config

    config = get_config()
    cache_dir = config.get(
        "data_cache_dir", os.path.expanduser("~/.ashareagents/cache")
    )
    os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, "northbound_daily.csv")


def _save_northbound_snapshot(date_str: str, hgt: float, sgt: float) -> None:
    """将当日北向资金收盘数据追加到本地 CSV 缓存（按日期去重）。"""
    import csv

    path = _northbound_cache_path()
    existing: dict[str, tuple[str, str]] = {}
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader, None)
            for row in reader:
                if len(row) >= 3:
                    existing[row[0]] = (row[1], row[2])
    existing[date_str] = (f"{hgt:.2f}", f"{sgt:.2f}")
    sorted_dates = sorted(existing.keys())
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "hgt", "sgt"])
        for d in sorted_dates:
            writer.writerow([d, existing[d][0], existing[d][1]])


def _load_northbound_history(n: int = 20) -> list[tuple[str, float, float]]:
    """从本地缓存加载最近 N 天的北向资金收盘数据。"""
    import csv

    path = _northbound_cache_path()
    if not os.path.exists(path):
        return []
    rows: list[tuple[str, float, float]] = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            if len(row) >= 3:
                try:
                    rows.append((row[0], float(row[1]), float(row[2])))
                except ValueError:
                    continue
    return rows[-n:]


def get_northbound_flow(
    curr_date: Annotated[str, "日期，格式 YYYY-MM-DD"],
    include_history: Annotated[
        bool, "是否包含历史日度数据（最近20个交易日）"
    ] = False,
) -> str:
    """从同花顺 hsgtApi 获取北向资金流向（沪深股通）。

    实时数据：分钟级 HGT（沪股通）+ SGT（深股通）累计净买入。
    历史数据：自缓存的每日收盘快照（上游API自2024年8月起停止更新北向历史数据）。
    """
    hsgt_headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "Chrome/117.0.0.0 Safari/537.36"
        ),
        "Host": "data.hexin.cn",
        "Referer": "https://data.hexin.cn/",
    }

    lines = [
        f"# 北向资金流向 ({curr_date})",
        "# 来源: 同花顺 hsgtApi (沪深股通) + 本地缓存",
        "",
    ]

    hgt_close = 0.0
    sgt_close = 0.0
    got_realtime = False

    try:
        url_rt = "https://data.hexin.cn/market/hsgtApi/method/dayChart/"
        r = _ths_get(url_rt, headers=hsgt_headers, timeout=10)
        d = r.json()

        times = d.get("time", [])
        hgt = d.get("hgt", [])
        sgt = d.get("sgt", [])

        if times:
            lines.append("## 实时数据 (累计净买入, 亿元)")
            n = len(times)
            start_idx = max(0, n - 10)
            for i in range(start_idx, n):
                t = times[i]
                h = hgt[i] if i < len(hgt) else "N/A"
                s = sgt[i] if i < len(sgt) else "N/A"
                lines.append(f"  {t}: HGT={h} SGT={s}")

            hgt_close = float(hgt[-1]) if hgt else 0
            sgt_close = float(sgt[-1]) if sgt else 0
            total = hgt_close + sgt_close
            lines.append(
                f"\n收盘: HGT(沪股通)={hgt_close:.2f}亿 "
                f"SGT(深股通)={sgt_close:.2f}亿 "
                f"合计={total:.2f}亿"
            )
            if total > 0:
                lines.append("信号: 北向资金净流入 (看涨)")
            elif total < 0:
                lines.append("信号: 北向资金净流出 (看跌)")
            got_realtime = True
        else:
            lines.append("无实时数据 (非交易时段或节假日)")

        if got_realtime:
            today_str = datetime.now().strftime("%Y-%m-%d")
            _save_northbound_snapshot(today_str, hgt_close, sgt_close)

        if include_history:
            history = _load_northbound_history(20)
            if history:
                lines.append("\n## 历史每日收盘数据 (本地缓存, 亿元)")
                lines.append("日期       | HGT(沪股通) | SGT(深股通) | 合计")
                for date, h, s in history:
                    lines.append(f"  {date}: HGT={h:.2f} SGT={s:.2f} 合计={h + s:.2f}")
                avg_total = sum(h + s for _, h, s in history) / len(history)
                lines.append(
                    f"\n{len(history)} 日均净流入: {avg_total:.2f}亿"
                )
                if got_realtime:
                    today_total = hgt_close + sgt_close
                    diff = today_total - avg_total
                    lines.append(
                        f"今日 vs 均值: {'+' if diff >= 0 else ''}{diff:.2f}亿 "
                        f"({'高于' if diff >= 0 else '低于'} 均值)"
                    )
            else:
                lines.append(
                    "\n## 历史数据: 暂无缓存数据。"
                    "历史数据将在每次调用时自动累积。"
                )

        return "\n".join(lines)

    except RECOVERABLE_DATA_SOURCE_ERRORS as e:
        return f"获取北向资金流向数据时出错：{str(e)}"


# ---------------------------------------------------------------------------
# 百度股市通 (Baidu PAE) 辅助函数
# ---------------------------------------------------------------------------

_BAIDU_PAE_HEADERS = {
    "Host": "finance.pae.baidu.com",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) "
        "Gecko/20100101 Firefox/110.0"
    ),
    "Accept": "application/vnd.finance-web.v1+json",
    "Origin": "https://gushitong.baidu.com",
    "Referer": "https://gushitong.baidu.com/",
}


# ---- 13. get_concept_blocks ----


def get_concept_blocks(
    ticker: Annotated[str, "A股代码（如 688017）"],
) -> str:
    """获取股票所属的概念/行业/地区板块（百度股市通）。

    返回申万行业分类、概念主题和地区板块。
    每个板块包含当日涨跌幅。
    """
    code = _normalize_ticker(ticker)

    try:
        url = (
            "https://finance.pae.baidu.com/api/getrelatedblock"
            f'?stock=[{{"code":"{code}","market":"ab","type":"stock"}}]'
            "&finClientType=pc"
        )
        r = _baidu_get(url, headers=_BAIDU_PAE_HEADERS, timeout=10)
        d = r.json()

        if str(d.get("ResultCode", -1)) != "0":
            return (
                f"百度 PAE 错误: ResultCode={d.get('ResultCode')} "
                f"{d.get('ResultMsg', '')}"
            )

        result = d.get("Result", {})
        categories = result.get(code, [])
        if not categories:
            return f"未找到 {code} 的概念板块数据"

        lines = [
            f"# {code} (A股) 概念及行业板块",
            f"# 来源: 百度股市通 (Baidu PAE)",
            f"# 获取时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
        ]

        concept_names: list[str] = []

        for cat in categories:
            cat_name = cat.get("name", "")
            items = cat.get("list", [])
            if not items:
                continue
            lines.append(f"## {cat_name}")
            for item in items:
                name = item.get("name", "")
                ratio = item.get("ratio", "")
                desc = item.get("describe", "")
                suffix = f" ({desc})" if desc else ""
                lines.append(f"  {name}{suffix}: {ratio}")
                if cat_name == "概念":
                    concept_names.append(name)

        if concept_names:
            lines.append(f"\n概念标签: {' / '.join(concept_names)}")

        return "\n".join(lines)

    except RECOVERABLE_DATA_SOURCE_ERRORS as e:
        return f"获取 {code} 概念板块数据时出错：{str(e)}"


# ---- 14. get_fund_flow ----


def get_fund_flow(
    ticker: Annotated[str, "A股代码"],
    curr_date: Annotated[str, "日期，格式 YYYY-MM-DD"],
    include_history: Annotated[
        bool, "是否包含历史日度资金流向（最近20天）"
    ] = True,
) -> str:
    """从东财 push2 获取个股资金流向。

    实时数据：分钟级主力/大单/中单/小单/超大单净流入。
    历史数据：20个交易日的日度净流入（push2his）。

    V0.2.7：用东财 push2 资金流向 API 替代了百度 PAE
    （fundflow/fundsortlist，自2026年5月起下线）。
    """
    code = _normalize_ticker(ticker)
    secid = f"1.{code}" if code.startswith("6") else f"0.{code}"
    lines = [
        f"# {code} (A股) 资金流向",
        f"# 来源: 东财 push2 (Eastmoney)",
        f"# 获取时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
    ]

    try:
        # 实时分钟级资金流向
        url_rt = "https://push2.eastmoney.com/api/qt/stock/fflow/kline/get"
        params_rt = {
            "secid": secid, "klt": 1,
            "fields1": "f1,f2,f3,f7",
            "fields2": "f51,f52,f53,f54,f55,f56,f57",
        }
        r = _em_get(url_rt, params=params_rt, timeout=10)
        d = r.json()
        klines = d.get("data", {}).get("klines", [])

        if klines:
            lines.append(
                "## 实时分时资金流向 "
                "(主力/小单/中单/大单/超大单 净流入, 元)"
            )
            for line in klines[-10:]:
                parts = line.split(",")
                if len(parts) >= 6:
                    lines.append(
                        f"  {parts[0]}: "
                        f"主力={float(parts[1])/1e4:.0f}万 "
                        f"大单={float(parts[4])/1e4:.0f}万 "
                        f"超大单={float(parts[5])/1e4:.0f}万"
                    )

            last_parts = klines[-1].split(",")
            if len(last_parts) >= 2:
                main_net = float(last_parts[1])
                lines.append(
                    f"\n收盘: 主力净流入={main_net/1e4:.0f}万元"
                )
                if main_net > 0:
                    lines.append(
                        "信号: 主力资金净流入 (看涨)"
                    )
                elif main_net < 0:
                    lines.append(
                        "信号: 主力资金净流出 (看跌)"
                    )
        else:
            lines.append(
                "无实时资金流向数据（非交易时段或节假日）"
            )

        # 历史日度资金流向（push2his）
        if include_history:
            url_hist = (
                "https://push2his.eastmoney.com"
                "/api/qt/stock/fflow/daykline/get"
            )
            params_hist = {
                "secid": secid, "lmt": 20, "klt": 101,
                "fields1": "f1,f2,f3,f7",
                "fields2": "f51,f52,f53,f54,f55,f56,f57",
            }
            rh = _em_get(url_hist, params=params_hist, timeout=10)
            dh = rh.json()
            hist_klines = dh.get("data", {}).get("klines", [])

            if hist_klines:
                lines.append(
                    f"\n## 历史日度资金流向 "
                    f"(最近 {len(hist_klines)} 个交易日)"
                )
                lines.append(
                    "日期 | 主力净流入(万) | 大单(万) "
                    "| 中单(万) | 小单(万) | 超大单(万)"
                )
                for line in hist_klines:
                    parts = line.split(",")
                    if len(parts) >= 6:
                        lines.append(
                            f"  {parts[0]} "
                            f"| 主力={float(parts[1])/1e4:.0f} "
                            f"| 大单={float(parts[4])/1e4:.0f} "
                            f"| 中单={float(parts[3])/1e4:.0f} "
                            f"| 小单={float(parts[2])/1e4:.0f} "
                            f"| 超大={float(parts[5])/1e4:.0f}"
                        )

        return "\n".join(lines)

    except RECOVERABLE_DATA_SOURCE_ERRORS as e:
        return f"获取 {code} 资金流向数据时出错：{str(e)}"


# ---------------------------------------------------------------------------
# 15. 龙虎榜
# ---------------------------------------------------------------------------

def get_dragon_tiger_board(
    ticker: str,
    trade_date: str,
    look_back_days: int = 30,
) -> str:
    """获取龙虎榜记录、席位明细和机构动向。"""
    return _cached(
        f"dragon-tiger:{ticker}:{trade_date}:{look_back_days}",
        _get_dragon_tiger_board,
        ticker,
        trade_date,
        look_back_days,
    )


# ---------------------------------------------------------------------------
# 16. 限售解禁日历
# ---------------------------------------------------------------------------


def get_lockup_expiry(
    ticker: str,
    trade_date: str,
    forward_days: int = 90,
) -> str:
    """获取历史及未来限售解禁安排。"""
    return _cached(
        f"lockup:{ticker}:{trade_date}:{forward_days}",
        _get_lockup_expiry,
        ticker,
        trade_date,
        forward_days,
    )


# ---------------------------------------------------------------------------
# 17. 行业横向对比
# ---------------------------------------------------------------------------


def get_industry_comparison(
    ticker: str,
    trade_date: str,
    top_n: int = 20,
) -> str:
    """获取东方财富行业表现排名。"""
    return _cached(
        f"industry:{ticker}:{trade_date}:{top_n}",
        _get_industry_comparison,
        ticker,
        trade_date,
        top_n,
    )
