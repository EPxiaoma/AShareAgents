"""Eastmoney data-source adapter."""

from .client import datacenter, get, resolve_stock_code

__all__ = ["datacenter", "get", "resolve_stock_code"]
