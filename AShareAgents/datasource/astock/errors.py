"""A 股数据源适配器共享的异常边界。"""

from __future__ import annotations

import urllib.error
from urllib.parse import urlparse

import pandas as pd
from requests import exceptions as requests_exceptions


# 这些失败通常来自远端服务、异常载荷、本地缓存或用户输入。
# 编程错误如 AttributeError、AssertionError 等刻意不放入此列表，
# 避免被数据源回退逻辑吞掉。
RECOVERABLE_DATA_SOURCE_ERRORS = (
    requests_exceptions.RequestException,
    urllib.error.URLError,
    TimeoutError,
    OSError,
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    IndexError,
    pd.errors.ParserError,
    pd.errors.EmptyDataError,
)


def describe_data_source_error(exc: BaseException) -> str:
    """返回面向用户的简短错误摘要，避免泄露过长请求 URL。"""
    host = ""
    request = getattr(exc, "request", None)
    response = getattr(exc, "response", None)
    url = getattr(request, "url", "") or getattr(response, "url", "")
    if url:
        host = urlparse(str(url)).netloc
    host_suffix = f"（{host}）" if host else ""

    if isinstance(exc, requests_exceptions.ProxyError):
        return f"代理连接失败{host_suffix}"
    if isinstance(exc, (requests_exceptions.Timeout, TimeoutError)):
        return f"请求超时{host_suffix}"
    if isinstance(exc, requests_exceptions.HTTPError):
        status = getattr(response, "status_code", None)
        return f"HTTP {status or '错误'}{host_suffix}"
    if isinstance(exc, (requests_exceptions.ConnectionError, urllib.error.URLError)):
        return f"网络连接失败{host_suffix}"

    message = str(exc).strip()
    if "not enough values to unpack" in message or "too many values to unpack" in message:
        return "响应格式异常"
    if isinstance(exc, (pd.errors.ParserError, pd.errors.EmptyDataError)):
        return "表格数据解析失败"
    if isinstance(exc, (KeyError, IndexError, TypeError)):
        return "响应字段不完整"
    if isinstance(exc, ValueError):
        return message if len(message) <= 80 else "响应内容无效"
    return message[:120] if message else type(exc).__name__
