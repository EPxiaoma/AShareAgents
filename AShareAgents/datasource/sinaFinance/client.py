"""新浪财经 HTTP 端点封装。"""

from __future__ import annotations

import json

import pandas as pd
import requests

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


def get(url, params=None, headers=None, timeout=15, **kwargs):
    """请求新浪财经 GET 端点。"""
    return requests.get(
        url, params=params, headers=headers, timeout=timeout, **kwargs
    )


def _prefix(code: str) -> str:
    if code.startswith(("6", "9")):
        return "sh"
    if code.startswith("8"):
        return "bj"
    return "sz"


def get_daily_kline(
    code: str, start_date: str | None = None, end_date: str | None = None
) -> pd.DataFrame:
    """获取标准化的日线 OHLCV 数据。"""
    response = get(
        "http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
        "CN_MarketData.getKLineData",
        params={
            "symbol": f"{_prefix(code)}{code}",
            "scale": "240",
            "ma": "no",
            "datalen": "800",
        },
        timeout=15,
    )
    response.raise_for_status()
    rows = [
        {
            "Date": item["day"],
            "Open": float(item["open"]),
            "High": float(item["high"]),
            "Low": float(item["low"]),
            "Close": float(item["close"]),
            "Volume": int(item["volume"]),
        }
        for item in (json.loads(response.text) or [])
    ]
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["Date"] = pd.to_datetime(df["Date"])
    if start_date:
        df = df[df["Date"] >= pd.to_datetime(start_date)]
    if end_date:
        df = df[df["Date"] <= pd.to_datetime(end_date)]
    return df


def get_financial_report(
    code: str, report_type: str, freq: str, curr_date: str | None = None
) -> pd.DataFrame:
    """获取标准化的新浪资产负债表、利润表或现金流量表。"""
    source_type = {
        "资产负债表": "fzb",
        "利润表": "lrb",
        "现金流量表": "llb",
    }.get(report_type, "lrb")
    response = get(
        "https://quotes.sina.cn/cn/api/openapi.php/"
        "CompanyFinanceService.getFinanceReport2022",
        params={
            "paperCode": f"{_prefix(code)}{code}",
            "source": source_type,
            "type": "0",
            "page": "1",
            "num": "20",
        },
        headers={"User-Agent": USER_AGENT},
        timeout=15,
    )
    response.raise_for_status()
    items = response.json().get("result", {}).get("data", {}).get(source_type, [])
    if not items:
        return pd.DataFrame()
    df = pd.DataFrame(items)
    date_col = next((c for c in ("报告日", "report_date", "date") if c in df), None)
    if date_col and curr_date:
        dates = pd.to_datetime(df[date_col], errors="coerce")
        df = df[dates <= pd.to_datetime(curr_date)]
    if freq == "annual" and date_col:
        dates = pd.to_datetime(df[date_col], errors="coerce")
        df = df[dates.dt.month.eq(12)]
    return df.head(8)
