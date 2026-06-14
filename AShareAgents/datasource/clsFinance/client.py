"""CLS Finance HTTP access."""

import requests


def get(url, params=None, headers=None, timeout=15, **kwargs):
    """GET a CLS Finance endpoint."""
    return requests.get(
        url, params=params, headers=headers, timeout=timeout, **kwargs
    )
