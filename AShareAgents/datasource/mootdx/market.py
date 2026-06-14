"""Low-level mootdx market-data access."""

from __future__ import annotations

import re

import pandas as pd

_client = None


def get_client():
    """Return a process-wide reusable mootdx client."""
    global _client
    if _client is None:
        from mootdx.quotes import Quotes

        _client = Quotes.factory(market="std")
    return _client


def build_name_code_map() -> tuple[dict[str, str], dict[str, str]]:
    """Load Shanghai and Shenzhen stock name/code mappings."""
    name_to_code: dict[str, str] = {}
    code_to_name: dict[str, str] = {}
    client = get_client()
    for market in (0, 1):
        stocks = client.stocks(market=market)
        if stocks is None or stocks.empty:
            continue
        for _, row in stocks.iterrows():
            code = str(row["code"]).strip()
            name = str(row["name"]).strip().replace(" ", "").replace("　", "")
            if re.match(r"^[036]\d{5}$", code):
                name_to_code[name] = code
                code_to_name[code] = name
    return name_to_code, code_to_name


def get_daily_bars(code: str, count: int = 800) -> pd.DataFrame:
    """Return normalized daily OHLCV bars for a six-digit stock code."""
    df = get_client().bars(symbol=code, category=4, offset=count)
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.drop(
        columns=["datetime", "year", "month", "day", "hour", "minute"],
        errors="ignore",
    ).reset_index()
    df = df.rename(
        columns={
            "datetime": "Date",
            "open": "Open",
            "close": "Close",
            "high": "High",
            "low": "Low",
            "volume": "Volume",
        }
    )
    df = df[["Date", "Open", "High", "Low", "Close", "Volume"]]
    df["Date"] = pd.to_datetime(df["Date"])
    return df
