"""Exception boundaries shared by A-share data-source adapters."""

from __future__ import annotations

import urllib.error
from urllib.parse import urlparse

import pandas as pd
from requests import exceptions as requests_exceptions


# These failures can reasonably be caused by remote services, malformed payloads,
# local caches, or user-supplied values. Programming errors such as AttributeError
# and AssertionError are deliberately excluded so they are not hidden by fallbacks.
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
    """Return a concise, user-facing summary without leaking long request URLs."""
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
