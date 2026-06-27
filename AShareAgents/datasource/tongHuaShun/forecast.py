"""同花顺一致预期访问封装。"""

from __future__ import annotations

import contextlib
import io
import warnings

import pandas as pd
import requests


def get(url, params=None, headers=None, timeout=15, **kwargs):
    """请求同花顺 GET 端点。"""
    return requests.get(
        url, params=params, headers=headers, timeout=timeout, **kwargs
    )


def get_eps_forecast(code: str) -> pd.DataFrame:
    """获取指定股票的一致预期 EPS 预测表。"""
    response = get(
        f"https://basic.10jqka.com.cn/new/{code}/worth.html",
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
            "Referer": "https://basic.10jqka.com.cn/",
        },
        timeout=15,
    )
    response.raise_for_status()
    response.encoding = "gbk"
    with contextlib.redirect_stderr(io.StringIO()), warnings.catch_warnings():
        warnings.simplefilter("ignore")
        tables = pd.read_html(io.StringIO(response.text))
    for table in tables:
        columns = [str(column) for column in table.columns]
        if any("每股收益" in column or "均值" in column for column in columns):
            return table
    return tables[0] if tables else pd.DataFrame()
