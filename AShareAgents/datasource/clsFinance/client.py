"""?HTTP 访问封装。"""

import requests


def get(url, params=None, headers=None, timeout=15, **kwargs):
    """请求 GET 端点。"""
    return requests.get(
        url, params=params, headers=headers, timeout=timeout, **kwargs
    )
