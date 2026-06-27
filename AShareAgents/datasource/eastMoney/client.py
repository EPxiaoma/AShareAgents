"""带请求节流的共享东方财富 HTTP 客户端。"""

from __future__ import annotations

import os
import random
import re
import threading
import time

import requests

DATACENTER_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

_session = requests.Session()
_session.headers.update({"User-Agent": USER_AGENT})
_minimum_interval = float(os.environ.get("EM_MIN_INTERVAL", "1.0"))
_last_call = 0.0
_lock = threading.Lock()


def get(url, params=None, headers=None, timeout=15, **kwargs):
    """使用共享节流会话请求东方财富 GET 端点。"""
    global _last_call
    with _lock:
        wait = _minimum_interval - (time.monotonic() - _last_call)
        if wait > 0:
            time.sleep(wait + random.uniform(0.1, 0.5))
        _last_call = time.monotonic()
    return _session.get(
        url, params=params, headers=headers, timeout=timeout, **kwargs
    )


def datacenter(
    report_name: str,
    columns: str = "ALL",
    filter_str: str = "",
    page_size: int = 50,
    sort_columns: str = "",
    sort_types: str = "-1",
) -> list[dict]:
    """查询东方财富数据中心报表并返回结果行。"""
    response = get(
        DATACENTER_URL,
        params={
            "reportName": report_name,
            "columns": columns,
            "filter": filter_str,
            "pageNumber": "1",
            "pageSize": str(page_size),
            "sortColumns": sort_columns,
            "sortTypes": sort_types,
            "source": "WEB",
            "client": "WEB",
        },
    )
    response.raise_for_status()
    result = response.json().get("result") or {}
    return result.get("data") or []


def resolve_stock_code(keyword: str) -> str | None:
    """通过东方财富联想建议解析中文股票名称。"""
    response = get(
        "https://searchapi.eastmoney.com/api/suggest/get",
        params={
            "input": keyword,
            "type": "14",
            "token": "D43BF722C8E33BDC906FB84D85E326E8",
            "count": "5",
        },
        timeout=10,
    )
    response.raise_for_status()
    stocks = response.json().get("QuotationCodeTable", {}).get("Data", []) or []
    for item in stocks:
        code = str(item.get("Code", "")).strip()
        market = str(item.get("MktNum", "")).strip()
        if re.match(r"^[036]\d{5}$", code) and market in ("0", "1"):
            return code
    return None
