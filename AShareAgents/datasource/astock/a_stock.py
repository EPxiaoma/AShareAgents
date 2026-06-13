"""AShareAgents A股（中国大陆）数据供应商。

零第三方数据依赖（无 akshare），所有数据源均为直接 HTTP API 或 mootdx TCP 连接。

数据来源：
- mootdx (TCP 7709)：OHLCV K线、财务快照、F10文本
- 腾讯财经 (HTTP GBK)：PE/PB/市值/换手率
- 东方财富 push2 / datacenter-web (直连HTTP)：股票信息、龙虎榜、限售解禁
- 新浪财经 (直连HTTP)：K线备用源、财务报表
- 同花顺 (直连HTTP)：一致预期EPS、热门股票、北向资金流向
- 财联社 (直连HTTP)：全球财经快讯
"""

from __future__ import annotations

from typing import Annotated
from datetime import datetime
from dateutil.relativedelta import relativedelta
import json as _json
import os
import logging
import math
import random
import re as _re
import time
import uuid
import urllib.request

import pandas as pd
import requests as _requests

from ..utils import safe_ticker_component

logger = logging.getLogger(__name__)


# 运行期缓存：同一次分析中避免同一数据源重复请求

_run_cache: dict[str, str] = {}


def _cached(key: str, factory, *args) -> str:
    """运行期缓存：同一 key 只执行一次 factory，后续直接返回缓存结果。"""
    if key not in _run_cache:
        _run_cache[key] = factory(*args)
    return _run_cache[key]


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


def _build_name_code_map() -> tuple[dict[str, str], dict[str, str]]:
    """通过 mootdx 构建 名称→代码 和 代码→名称 映射（覆盖沪深两市）。

    当 mootdx 不可达时回退为空映射——单只股票的名称查询将按需改用东方财富搜索API。
    """
    global _name_to_code, _code_to_name
    if _name_to_code is not None:
        return _name_to_code, _code_to_name

    n2c: dict[str, str] = {}
    c2n: dict[str, str] = {}

    try:
        from mootdx.quotes import Quotes

        client = Quotes.factory(market="std")
        for market in (0, 1):  # 0=SZ, 1=SH
            try:
                stocks = client.stocks(market=market)
                if stocks is None or stocks.empty:
                    continue
                for _, row in stocks.iterrows():
                    code = str(row["code"]).strip()
                    name = str(row["name"]).strip()
                    if not _re.match(r"^[036]\d{5}$", code):
                        continue
                    clean_name = name.replace(" ", "").replace("　", "")
                    n2c[clean_name] = code
                    c2n[code] = clean_name
            except Exception:
                logger.warning(
                    "mootdx stocks(market=%d) 获取失败，已跳过", market
                )
    except Exception:
        logger.warning(
            "mootdx 名称-代码映射不可用，将使用 API 回退方案"
        )

    _name_to_code = n2c
    _code_to_name = c2n
    logger.info("已构建股票名称-代码映射：%d 条记录", len(n2c))
    return _name_to_code, _code_to_name


def _resolve_by_api(keyword: str) -> str | None:
    """通过东方财富联想搜索API将中文股票名称解析为6位代码。

    Returns:
        代码字符串，若未匹配到则返回 None。
    """
    try:
        url = "https://searchapi.eastmoney.com/api/suggest/get"
        params = {
            "input": keyword,
            "type": "14",
            "token": "D43BF722C8E33BDC906FB84D85E326E8",
            "count": "5",
        }
        r = _requests.get(url, params=params, timeout=10)
        data = r.json()
        stocks = (
            data.get("QuotationCodeTable", {}).get("Data", [])
            or []
        )
        for item in stocks:
            code = str(item.get("Code", "")).strip()
            market = str(item.get("MktNum", "")).strip()
            # market: "1"=沪市, "0"=深市, 仅保留6位A股代码
            if _re.match(r"^[036]\d{5}$", code) and market in ("0", "1"):
                return code
        return None
    except Exception:
        logger.warning("东方财富联想搜索 API 对 %r 的请求失败", keyword)
        return None


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
        logger.info("API 解析 %r -> %s", s, api_code)
        return api_code

    raise ValueError(f"找不到股票 '{s}'，请检查名称是否正确")


# mootdx 客户端在进程内复用，避免重复建立连接。

_mootdx_client = None


def _get_mootdx_client():
    """惰性初始化 mootdx Quotes 客户端（TCP 连接，可复用）。"""
    global _mootdx_client
    if _mootdx_client is None:
        from mootdx.quotes import Quotes

        _mootdx_client = Quotes.factory(market="std")
    return _mootdx_client


# 腾讯财经 API

def _tencent_quote(codes: list[str]) -> dict[str, dict]:
    """从腾讯财经 (qt.gtimg.cn) 批量获取实时行情。

    Returns:
        dict[code] -> {name, price, pe_ttm, pb, mcap_yi, ...}
    """
    prefixed = [f"{_get_prefix(c)}{c}" for c in codes]
    url = "https://qt.gtimg.cn/q=" + ",".join(prefixed)
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "Mozilla/5.0")
    resp = urllib.request.urlopen(req, timeout=10)
    raw = resp.read().decode("gbk")

    result = {}
    for line in raw.strip().split(";"):
        if not line.strip() or "=" not in line or '"' not in line:
            continue
        key = line.split("=")[0].split("_")[-1]
        vals = line.split('"')[1].split("~")
        if len(vals) < 53:
            continue
        code = key[2:]  # strip sh/sz/bj prefix
        result[code] = {
            "name": vals[1],
            "price": float(vals[3]) if vals[3] else 0,
            "last_close": float(vals[4]) if vals[4] else 0,
            "open": float(vals[5]) if vals[5] else 0,
            "change_pct": float(vals[32]) if vals[32] else 0,
            "high": float(vals[33]) if vals[33] else 0,
            "low": float(vals[34]) if vals[34] else 0,
            "turnover_pct": float(vals[38]) if vals[38] else 0,
            "pe_ttm": float(vals[39]) if vals[39] else 0,
            "mcap_yi": float(vals[44]) if vals[44] else 0,
            "float_mcap_yi": float(vals[45]) if vals[45] else 0,
            "pb": float(vals[46]) if vals[46] else 0,
            "limit_up": float(vals[47]) if vals[47] else 0,
            "limit_down": float(vals[48]) if vals[48] else 0,
            "pe_static": float(vals[52]) if vals[52] else 0,
        }
    return result


# 东方财富数据中心统一查询接口（龙虎榜/解禁 等公用）

_DATACENTER_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


# 东方财富请求节流与会话复用
# 所有 eastmoney.com HTTP 请求统一串行节流，降低多 Agent 并发触发临时封禁的概率。
# 其他数据源不经过此入口；批量任务可通过 EM_MIN_INTERVAL 调高请求间隔。
_EM_SESSION = _requests.Session()
_EM_SESSION.headers.update({"User-Agent": _UA})
# 两次请求的最小间隔可由环境变量覆盖。
_EM_MIN_INTERVAL = float(os.environ.get("EM_MIN_INTERVAL", "1.0"))
_em_last_call = [0.0]


def _em_get(url, params=None, headers=None, timeout=15, **kwargs):
    """请求东方财富接口，并执行串行节流和随机抖动。

    传入的 headers 会覆盖会话默认值，以保留端点要求的 Referer 或 Origin。
    """
    wait = _EM_MIN_INTERVAL - (time.time() - _em_last_call[0])
    if wait > 0:
        time.sleep(wait + random.uniform(0.1, 0.5))
    try:
        return _EM_SESSION.get(
            url, params=params, headers=headers, timeout=timeout, **kwargs
        )
    finally:
        _em_last_call[0] = time.time()


def _eastmoney_datacenter(
    report_name: str,
    columns: str = "ALL",
    filter_str: str = "",
    page_size: int = 50,
    sort_columns: str = "",
    sort_types: str = "-1",
) -> list[dict]:
    """东财数据中心统一查询——龙虎榜/解禁 共用。"""
    params = {
        "reportName": report_name,
        "columns": columns,
        "filter": filter_str,
        "pageNumber": "1",
        "pageSize": str(page_size),
        "sortColumns": sort_columns,
        "sortTypes": sort_types,
        "source": "WEB",
        "client": "WEB",
    }
    r = _em_get(_DATACENTER_URL, params=params, timeout=15)
    d = r.json()
    if d.get("result") and d["result"].get("data"):
        return d["result"]["data"]
    return []


# 同花顺 EPS 一致预期辅助函数（直连 HTTP，无 akshare）


def _ths_eps_forecast(code: str) -> pd.DataFrame:
    """从同花顺获取一致预期 EPS（直连 HTTP）。

    Returns:
        大致包含以下列的 DataFrame：年度、预测机构数、最小值、均值、最大值。
    """
    url = f"https://basic.10jqka.com.cn/new/{code}/worth.html"
    headers = {
        "User-Agent": _UA,
        "Referer": "https://basic.10jqka.com.cn/",
    }
    r = _requests.get(url, headers=headers, timeout=15)
    r.encoding = "gbk"
    # 抑制 HTML 解析器噪声（lxml/html5lib 可能将原始 HTML 输出到 stderr）
    import io as _io, contextlib as _contextlib, warnings as _warnings
    with _contextlib.redirect_stderr(_io.StringIO()):
        with _warnings.catch_warnings():
            _warnings.simplefilter("ignore")
            dfs = pd.read_html(_io.StringIO(r.text))
    # 查找包含 EPS 数据的表格
    for df in dfs:
        cols = [str(c) for c in df.columns]
        if any("每股收益" in c or "均值" in c for c in cols):
            return df
    # 回退：如果存在则返回第一个表格
    return dfs[0] if dfs else pd.DataFrame()


# 新浪 K线备用源（直连 HTTP，无 akshare）


def _sina_kline_fallback(code: str, start_date: str = None, end_date: str = None) -> pd.DataFrame:
    """从新浪 HTTP API 获取日K线，作为 mootdx 的备用数据源。

    Returns:
        包含以下列的 DataFrame：Date、Open、High、Low、Close、Volume。
    """
    prefix = "sh" if code.startswith("6") else "sz"
    url = (
        "http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
        "CN_MarketData.getKLineData"
    )
    params = {
        "symbol": f"{prefix}{code}",
        "scale": "240",  # 日线
        "ma": "no",
        "datalen": "800",
    }
    r = _requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    data = _json.loads(r.text)

    if not data:
        return pd.DataFrame()

    rows = []
    for item in data:
        rows.append({
            "Date": item["day"],
            "Open": float(item["open"]),
            "High": float(item["high"]),
            "Low": float(item["low"]),
            "Close": float(item["close"]),
            "Volume": int(item["volume"]),
        })

    df = pd.DataFrame(rows)
    df["Date"] = pd.to_datetime(df["Date"])

    if start_date:
        df = df[df["Date"] >= pd.to_datetime(start_date)]
    if end_date:
        df = df[df["Date"] <= pd.to_datetime(end_date)]

    return df


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
        client = _get_mootdx_client()
        df = client.bars(symbol=code, category=4, offset=800)

        if df is None or df.empty:
            raise ValueError(f"mootdx 未返回 {code} 的 OHLCV 数据")

        # mootdx 同时返回名为 'datetime' 的索引和列
        # （外加 year/month/day/hour/minute/volume）。重置索引前先删除重复列。
        df = df.drop(columns=["datetime", "year", "month", "day", "hour", "minute"], errors="ignore")
        df = df.reset_index()  # 将索引 'datetime' 移至列 'datetime'
        rename_map = {
            "datetime": "Date",
            "open": "Open",
            "close": "Close",
            "high": "High",
            "low": "Low",
            "volume": "Volume",
        }
        df = df.rename(columns=rename_map)
        df = df[["Date", "Open", "High", "Low", "Close", "Volume"]]
        df["Date"] = pd.to_datetime(df["Date"])
    except Exception as e:
        logger.warning("mootdx OHLCV 获取 %s 失败: %s，尝试新浪 HTTP 回退方案", code, e)
        # 回退：新浪直连 HTTP API
        try:
            df = _sina_kline_fallback(code)
            if df.empty:
                raise ValueError(f"新浪未返回 {code} 的 OHLCV 数据")
        except Exception:
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
    except Exception:
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

    except Exception as e:
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
        except Exception as e:
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
        except Exception as e:
            logger.warning("mootdx 财务数据获取 %s 失败: %s", code, e)

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
        except Exception as e:
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
                except Exception as e:
                    logger.warning("远期 PE 计算 %s 失败: %s", code, e)
        except Exception as e:
            logger.warning("一致预期 EPS 预测获取 %s 失败: %s", code, e)

        if not lines:
            return f"未找到 A 股 '{code}' 的基本面数据"

        header = f"# {code} (A股) 公司基本面\n"
        header += (
            f"# 数据获取时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        )

        return header + "\n".join(lines)

    except Exception as e:
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
    _report_type_map = {
        "资产负债表": "fzb",
        "利润表": "lrb",
        "现金流量表": "llb",
    }
    source_type = _report_type_map.get(report_type, "lrb")

    prefix = "sh" if code.startswith("6") else "sz"
    paper_code = f"{prefix}{code}"
    url = "https://quotes.sina.cn/cn/api/openapi.php/CompanyFinanceService.getFinanceReport2022"
    params = {
        "paperCode": paper_code,
        "source": source_type,
        "type": "0",
        "page": "1",
        "num": "20",
    }
    r = _requests.get(url, params=params, headers={"User-Agent": _UA}, timeout=15)
    d = r.json()

    result = d.get("result", {}).get("data", {})
    items = result.get(source_type, [])
    if not isinstance(items, list) or not items:
        return pd.DataFrame()

    df = pd.DataFrame(items)

    # 按 curr_date 过滤
    if curr_date and "报告日" in df.columns:
        df["报告日"] = pd.to_datetime(df["报告日"], errors="coerce")
        cutoff = pd.to_datetime(curr_date)
        df = df[df["报告日"] <= cutoff]

    # 按频率过滤（年报 = 仅保留12月份报表）
    if freq.lower() == "annual" and "报告日" in df.columns:
        months = pd.to_datetime(df["报告日"], errors="coerce").dt.month
        df = df[months == 12]

    return df.head(8)


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

    except Exception as e:
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

    except Exception as e:
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

    except Exception as e:
        return f"获取 {code} 利润表数据时出错：{str(e)}"


# ---- 7. get_news ----


def _fetch_news_eastmoney(code: str, page_size: int = 20) -> list[dict]:
    """通过东方财富搜索API直接获取个股新闻。"""
    url = "https://search-api-web.eastmoney.com/search/jsonp"
    inner_param = {
        "uid": "",
        "keyword": code,
        "type": ["cmsArticleWebOld"],
        "client": "web",
        "clientType": "web",
        "clientVersion": "curr",
        "param": {
            "cmsArticleWebOld": {
                "searchScope": "default",
                "sort": "default",
                "pageIndex": 1,
                "pageSize": page_size,
                "preTag": "",
                "postTag": "",
            }
        },
    }
    params = {
        "cb": "callback",
        "param": _json.dumps(inner_param, ensure_ascii=False),
        "_": "1",
    }
    headers = {
        "Referer": "https://so.eastmoney.com/",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
        ),
    }

    resp = _em_get(url, params=params, headers=headers, timeout=15)
    resp.raise_for_status()
    text = resp.text
    text = text[text.index("(") + 1 : text.rindex(")")]
    data = _json.loads(text)

    articles: list[dict] = []
    for item in data.get("result", {}).get("cmsArticleWebOld", []):
        articles.append({
            "title": item.get("title", ""),
            "content": item.get("content", ""),
            "time": item.get("date", ""),
            "source": item.get("mediaName", "东方财富"),
            "url": item.get("url", ""),
        })
    return articles


def _fetch_news_sina(code: str, page_size: int = 20) -> list[dict]:
    """新浪财经个股新闻 API（备用数据源）。"""
    prefix = "sh" if code.startswith(("6", "9")) else "sz"
    url = (
        f"https://vip.stock.finance.sina.com.cn/corp/view/"
        f"vCB_AllNewsStock.php?symbol={prefix}{code}&Page=1"
    )
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
        ),
        "Referer": "https://finance.sina.com.cn/",
    }

    resp = _requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    resp.encoding = "gb2312"
    html = resp.text

    articles: list[dict] = []
    rows = _re.findall(
        r"(\d{4}-\d{2}-\d{2})\s*(?:&nbsp;)*(\d{2}:\d{2})\s*(?:&nbsp;)*"
        r"<a[^>]+href='([^']+)'[^>]*>([^<]+)</a>",
        html,
    )
    for date_str, time_str, link, title in rows[:page_size]:
        articles.append({
            "title": title.strip(),
            "content": "",
            "time": f"{date_str} {time_str}",
            "source": "新浪财经",
            "url": link,
        })
    return articles


def get_news(
    ticker: Annotated[str, "A股代码"],
    start_date: Annotated[str, "起始日期，格式 yyyy-mm-dd"],
    end_date: Annotated[str, "结束日期，格式 yyyy-mm-dd"],
) -> str:
    """通过东方财富直连 API 获取个股新闻（新浪作为备用）。"""
    code = _normalize_ticker(ticker)

    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")

    articles: list[dict] = []
    source_label = ""

    try:
        articles = _fetch_news_eastmoney(code)
        source_label = "东方财富"
    except Exception as e:
        logger.warning("东方财富新闻获取 %s 失败: %s", code, e)

    if not articles:
        try:
            articles = _fetch_news_sina(code)
            source_label = "新浪财经"
        except Exception as e:
            logger.warning("新浪财经新闻获取 %s 失败: %s", code, e)

    if not articles:
        return f"未找到 A 股 '{code}' 的新闻"

    news_str = ""
    count = 0
    for art in articles:
        pub_time = art.get("time", "")
        try:
            pub_dt = datetime.strptime(pub_time[:10], "%Y-%m-%d")
            if pub_dt < start_dt or pub_dt > end_dt:
                continue
        except (ValueError, IndexError):
            pass

        title = art["title"]
        content = art.get("content", "")
        source = art.get("source", source_label)
        link = art.get("url", "")

        news_str += f"### {title} (来源: {source})\n"
        if content:
            snippet = content[:300] + "..." if len(content) > 300 else content
            news_str += f"{snippet}\n"
        if link and link != "nan":
            news_str += f"链接: {link}\n"
        news_str += "\n"
        count += 1

    if count == 0:
        return (
            f"在 {start_date} 至 {end_date} 期间未找到 A 股 '{code}' 的新闻"
        )

    return (
        f"## {code} (A股) 新闻，{start_date} 至 {end_date}:\n\n"
        + news_str
    )


# ---- 8. get_global_news ----


def get_global_news(
    curr_date: Annotated[str, "当前日期，格式 yyyy-mm-dd"],
    look_back_days: Annotated[int, "回顾天数"] = 7,
    limit: Annotated[int, "最多文章数"] = 10,
) -> str:
    """通过直连 HTTP 获取中国/全球财经新闻（财联社 + 东方财富）。"""
    return _cached(f"global_news:{curr_date}:{look_back_days}", _get_global_news_impl, curr_date, look_back_days, limit)


def _get_global_news_impl(curr_date: str, look_back_days: int, limit: int) -> str:
    """get_global_news 的实际实现（不含缓存层）。"""
    start_dt = datetime.strptime(curr_date, "%Y-%m-%d") - relativedelta(
        days=look_back_days
    )
    start_date = start_dt.strftime("%Y-%m-%d")

    all_news: list[dict] = []

    # 数据源1：财联社快讯——直连 HTTP
    try:
        cls_url = "https://www.cls.cn/nodeapi/telegraphList"
        cls_params = {"rn": str(limit), "page": "1"}
        cls_headers = {"User-Agent": _UA, "Referer": "https://www.cls.cn/"}
        r_cls = _requests.get(cls_url, params=cls_params, headers=cls_headers, timeout=10)
        d_cls = r_cls.json()
        for item in d_cls.get("data", {}).get("roll_data", []):
            title = item.get("title", "") or item.get("brief", "")
            content = item.get("content", "") or item.get("brief", "")
            ctime = item.get("ctime", "")
            # ctime 是 Unix 时间戳
            pub_time = ""
            if ctime:
                try:
                    pub_time = datetime.fromtimestamp(int(ctime)).strftime("%Y-%m-%d %H:%M")
                except (ValueError, TypeError, OSError):
                    pub_time = str(ctime)
            all_news.append({
                "title": title,
                "content": content,
                "time": pub_time,
                "source": "CLS Wire",
            })
    except Exception as e:
        logger.warning("财联社新闻获取失败: %s", e)

    # 数据源2：东财7x24资讯——直连 HTTP
    try:
        em_url = "https://np-weblist.eastmoney.com/comm/web/getFastNewsList"
        em_params = {
            "client": "web",
            "biz": "web_724",
            "fastColumn": "102",
            "sortEnd": "",
            "pageSize": str(limit),
            "req_trace": str(uuid.uuid4()),
        }
        em_headers = {"User-Agent": _UA, "Referer": "https://kuaixun.eastmoney.com/"}
        r_em = _em_get(em_url, params=em_params, headers=em_headers, timeout=10)
        d_em = r_em.json()
        for item in d_em.get("data", {}).get("fastNewsList", []):
            title = item.get("title", "")
            summary = item.get("summary", "")[:200]
            pub_time = item.get("showTime", "")
            all_news.append({
                "title": title,
                "content": summary,
                "time": pub_time,
                "source": "Eastmoney Global",
            })
    except Exception as e:
        logger.warning("东方财富全球新闻获取失败: %s", e)

    if not all_news:
        return f"未找到 {curr_date} 的全球财经新闻"

    # 按标题去重
    seen: set[str] = set()
    unique: list[dict] = []
    for n in all_news:
        if n["title"] not in seen:
            seen.add(n["title"])
            unique.append(n)

    news_str = ""
    for n in unique[:limit]:
        news_str += f"### {n['title']} (来源: {n['source']})\n"
        if n.get("content"):
            snippet = (
                n["content"][:300] + "..."
                if len(n["content"]) > 300
                else n["content"]
            )
            news_str += f"{snippet}\n"
        news_str += "\n"

    return (
        f"## 中国及全球财经新闻，{start_date} 至 {curr_date}:\n\n"
        + news_str
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

    except Exception as e:
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
        except Exception as e:
            logger.warning("远期 PE 计算 %s 失败: %s", code, e)

        return "\n".join(lines)

    except Exception as e:
        return f"获取 {code} 盈利预测数据时出错：{str(e)}"


# ---- 11. get_hot_stocks ----


def get_hot_stocks(
    curr_date: Annotated[str, "日期，格式 YYYY-MM-DD，空字符串表示今天"] = "",
) -> str:
    """从同花顺编辑团队获取强势股及其题材归因。

    返回触及涨停的股票，附带人工精选的涨停原因标签
    （如 '算力租赁+AI政务'），解释其为何大涨。
    """
    import requests

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
        r = requests.get(url, headers=headers, timeout=10)
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

    except Exception as e:
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
    import requests

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
        r = requests.get(url_rt, headers=hsgt_headers, timeout=10)
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

    except Exception as e:
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
    import requests

    code = _normalize_ticker(ticker)

    try:
        url = (
            "https://finance.pae.baidu.com/api/getrelatedblock"
            f'?stock=[{{"code":"{code}","market":"ab","type":"stock"}}]'
            "&finClientType=pc"
        )
        r = requests.get(url, headers=_BAIDU_PAE_HEADERS, timeout=10)
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

    except Exception as e:
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

    except Exception as e:
        return f"获取 {code} 资金流向数据时出错：{str(e)}"


# ---------------------------------------------------------------------------
# 15. 龙虎榜
# ---------------------------------------------------------------------------

def get_dragon_tiger_board(
    ticker: str,
    trade_date: str,
    look_back_days: int = 30,
) -> str:
    """获取龙虎榜上榜记录及席位明细。

    Args:
        ticker: 6位A股代码，如 '000858'
        trade_date: YYYY-MM-DD 格式日期
        look_back_days: 向前搜索多少天（默认 30）

    Returns:
        格式化文本，包含龙虎榜上榜记录、买卖席位TOP5及机构动向。
    """
    code = safe_ticker_component(ticker)
    end_dt = datetime.strptime(trade_date, "%Y-%m-%d")
    start_dt = end_dt - pd.Timedelta(days=look_back_days)
    start_date_str = start_dt.strftime("%Y-%m-%d")
    lines = [f"# 龙虎榜数据 | {code} | {trade_date} (近{look_back_days}日)"]

    # 1. 上榜记录——东财数据中心直连 HTTP
    try:
        data = _eastmoney_datacenter(
            "RPT_DAILYBILLBOARD_DETAILSNEW",
            filter_str=(
                f"(TRADE_DATE>='{start_date_str}')"
                f"(TRADE_DATE<='{trade_date}')"
                f"(SECURITY_CODE=\"{code}\")"
            ),
            page_size=50,
            sort_columns="TRADE_DATE",
            sort_types="-1",
        )
        if not data:
            lines.append(f"\n近{look_back_days}日未上龙虎榜。")
        else:
            lines.append(f"\n## 上榜记录 ({len(data)} 次)")
            lines.append("日期 | 原因 | 净买入(万) | 换手率")
            for row in data:
                net_buy = round((row.get("BILLBOARD_NET_AMT") or 0) / 10000, 1)
                turnover = round(float(row.get("TURNOVERRATE") or 0), 2)
                lines.append(
                    f"  {str(row.get('TRADE_DATE', ''))[:10]} "
                    f"| {row.get('EXPLANATION', '')} "
                    f"| {net_buy:.0f} "
                    f"| {turnover:.2f}%"
                )
    except Exception as e:
        lines.append(f"龙虎榜列表查询失败: {e}")

    # 2. 最近上榜的买卖席位——东财数据中心直连 HTTP
    try:
        if data:
            latest_date = str(data[0].get("TRADE_DATE", ""))[:10]
            lines.append(f"\n## 最近上榜席位明细 ({latest_date})")

            # 买入席位
            buy_data = _eastmoney_datacenter(
                "RPT_BILLBOARD_DAILYDETAILSBUY",
                filter_str=f"(TRADE_DATE='{latest_date}')(SECURITY_CODE=\"{code}\")",
                page_size=10,
                sort_columns="BUY",
                sort_types="-1",
            )
            if buy_data:
                lines.append("\n### 买入席位 TOP5")
                lines.append("营业部 | 买入(万) | 卖出(万) | 净额(万)")
                for row in buy_data[:5]:
                    buy_amt = round((row.get("BUY") or 0) / 10000, 1)
                    sell_amt = round((row.get("SELL") or 0) / 10000, 1)
                    net = round((row.get("NET") or 0) / 10000, 1)
                    lines.append(
                        f"  {row.get('OPERATEDEPT_NAME', '')} "
                        f"| {buy_amt:.0f} | {sell_amt:.0f} | {net:.0f}"
                    )

            # 卖出席位
            sell_data = _eastmoney_datacenter(
                "RPT_BILLBOARD_DAILYDETAILSSELL",
                filter_str=f"(TRADE_DATE='{latest_date}')(SECURITY_CODE=\"{code}\")",
                page_size=10,
                sort_columns="SELL",
                sort_types="-1",
            )
            if sell_data:
                lines.append("\n### 卖出席位 TOP5")
                lines.append("营业部 | 买入(万) | 卖出(万) | 净额(万)")
                for row in sell_data[:5]:
                    buy_amt = round((row.get("BUY") or 0) / 10000, 1)
                    sell_amt = round((row.get("SELL") or 0) / 10000, 1)
                    net = round((row.get("NET") or 0) / 10000, 1)
                    lines.append(
                        f"  {row.get('OPERATEDEPT_NAME', '')} "
                        f"| {buy_amt:.0f} | {sell_amt:.0f} | {net:.0f}"
                    )
    except Exception:
        pass

    # 3. 机构动向 — 从买卖席位明细筛选机构专用席位 (OPERATEDEPT_CODE="0")
    try:
        inst_buy = 0.0
        inst_sell = 0.0
        for detail, side in [(buy_data, "buy"), (sell_data, "sell")]:
            for row in (detail or []):
                if str(row.get("OPERATEDEPT_CODE", "")) == "0":
                    if side == "buy":
                        inst_buy += (row.get("BUY") or 0)
                    else:
                        inst_sell += (row.get("SELL") or 0)
        if inst_buy > 0 or inst_sell > 0:
            lines.append("\n## 机构动向")
            lines.append(
                f"  机构买入 {inst_buy/1e4:.0f} 万 "
                f"| 卖出 {inst_sell/1e4:.0f} 万 "
                f"| 净额 {(inst_buy - inst_sell)/1e4:.0f} 万"
            )
    except Exception:
        pass

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 16. 限售解禁日历
# ---------------------------------------------------------------------------

def get_lockup_expiry(
    ticker: str,
    trade_date: str,
    forward_days: int = 90,
) -> str:
    """获取个股限售解禁时间表。

    Args:
        ticker: 6位A股代码
        trade_date: YYYY-MM-DD 格式日期
        forward_days: 向前查看多少天（默认 90）

    Returns:
        格式化文本，包含历史解禁记录和即将到期的解禁日历及影响指标。
    """
    code = safe_ticker_component(ticker)
    lines = [f"# 限售解禁日历 | {code} | {trade_date}"]

    # 1. 历史解禁记录——东财数据中心直连 HTTP
    try:
        history_data = _eastmoney_datacenter(
            "RPT_LIFT_STAGE",
            filter_str=f"(SECURITY_CODE=\"{code}\")",
            page_size=15,
            sort_columns="FREE_DATE",
            sort_types="-1",
        )
        if history_data:
            lines.append(f"\n## 个股解禁记录 (共 {len(history_data)} 批)")
            lines.append("解禁时间 | 类型 | 解禁数量 | 占比")
            for row in history_data:
                lines.append(
                    f"  {str(row.get('FREE_DATE', ''))[:10]} "
                    f"| {row.get('LIMITED_STOCK_TYPE', '')} "
                    f"| {row.get('FREE_SHARES_NUM', '')} "
                    f"| {row.get('FREE_RATIO', '')}"
                )
        else:
            lines.append("\n无历史解禁记录。")
    except Exception as e:
        lines.append(f"个股解禁查询失败: {e}")

    # 2. 未来待解禁——东财数据中心直连 HTTP
    try:
        end_dt = datetime.strptime(trade_date, "%Y-%m-%d") + pd.Timedelta(
            days=forward_days
        )
        end_str = end_dt.strftime("%Y-%m-%d")
        upcoming_data = _eastmoney_datacenter(
            "RPT_LIFT_STAGE",
            filter_str=(
                f"(SECURITY_CODE=\"{code}\")"
                f"(FREE_DATE>='{trade_date}')"
                f"(FREE_DATE<='{end_str}')"
            ),
            page_size=20,
            sort_columns="FREE_DATE",
            sort_types="1",
        )
        if upcoming_data:
            lines.append(f"\n## 未来 {forward_days} 天待解禁")
            for row in upcoming_data:
                lines.append(
                    f"  {str(row.get('FREE_DATE', ''))[:10]} "
                    f"| {row.get('LIMITED_STOCK_TYPE', '')} "
                    f"| 数量 {row.get('FREE_SHARES_NUM', '')} "
                    f"| 占比 {row.get('FREE_RATIO', '')}"
                )
        else:
            lines.append(f"\n未来 {forward_days} 天无待解禁。")
    except Exception as e:
        lines.append(f"解禁日历查询失败: {e}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 17. 行业横向对比
# ---------------------------------------------------------------------------

def get_industry_comparison(
    ticker: str,
    trade_date: str,
    top_n: int = 20,
) -> str:
    """获取行业板块表现对比。

    Args:
        ticker: 6位A股代码（用于识别相关行业）
        trade_date: YYYY-MM-DD 格式日期
        top_n: 显示涨幅最高/最低行业数量（默认 20）

    Returns:
        格式化文本，包含行业板块涨跌排名，高亮目标股票所属行业。
    """
    code = safe_ticker_component(ticker)
    lines = [f"# 行业横向对比 | {code} | {trade_date}"]

    # 东财 push2 行业板块排名（直连 HTTP，替代返回401的同花顺接口）
    try:
        url = "https://push2.eastmoney.com/api/qt/clist/get"
        params = {
            "pn": "1",
            "pz": "100",
            "po": "1",
            "np": "1",
            "fltt": "2",
            "invt": "2",
            "fs": "m:90+t:2",
            "fields": "f2,f3,f4,f12,f13,f14,f104,f105,f128,f136,f140,f141,f207",
        }
        r = _em_get(url, params=params, timeout=15)
        d = r.json()
        items = d.get("data", {}).get("diff", [])

        if items:
            lines.append(
                f"\n## 全行业表现 (东财 {len(items)} 个行业)"
            )
            lines.append(
                "排名 | 行业 | 涨跌幅 | 上涨 | 下跌 | 领涨股"
            )
            for i, item in enumerate(items):
                name = item.get("f14", "")
                change_pct = item.get("f3", 0)
                up_count = item.get("f104", 0)
                down_count = item.get("f105", 0)
                leader = item.get("f140", "")
                lines.append(
                    f"  {i+1}. {name} "
                    f"| {change_pct}% "
                    f"| {up_count} "
                    f"| {down_count} "
                    f"| {leader}"
                )
                if i >= top_n * 2 - 1:
                    lines.append(f"  ... (显示前/后 {top_n} 名)")
                    break
        else:
            lines.append("行业数据获取为空。")
    except Exception as e:
        lines.append(f"行业对比查询失败: {e}")

    return "\n".join(lines)
