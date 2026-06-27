"""腾讯财经实时行情访问封装。"""

from __future__ import annotations

import urllib.request


def _market_prefix(code: str) -> str:
    if code.startswith(("6", "9")):
        return "sh"
    if code.startswith("8"):
        return "bj"
    return "sz"


def get_quotes(codes: list[str]) -> dict[str, dict]:
    """从 qt.gtimg.cn 获取并解析实时行情。"""
    symbols = [f"{_market_prefix(code)}{code}" for code in codes]
    request = urllib.request.Request("https://qt.gtimg.cn/q=" + ",".join(symbols))
    request.add_header("User-Agent", "Mozilla/5.0")
    raw = urllib.request.urlopen(request, timeout=10).read().decode("gbk")
    result = {}
    for line in raw.strip().split(";"):
        if not line.strip() or "=" not in line or '"' not in line:
            continue
        key = line.split("=")[0].split("_")[-1]
        values = line.split('"')[1].split("~")
        if len(values) < 53:
            continue
        code = key[2:]
        result[code] = {
            "name": values[1],
            "price": float(values[3]) if values[3] else 0,
            "last_close": float(values[4]) if values[4] else 0,
            "open": float(values[5]) if values[5] else 0,
            "change_pct": float(values[32]) if values[32] else 0,
            "high": float(values[33]) if values[33] else 0,
            "low": float(values[34]) if values[34] else 0,
            "turnover_pct": float(values[38]) if values[38] else 0,
            "pe_ttm": float(values[39]) if values[39] else 0,
            "mcap_yi": float(values[44]) if values[44] else 0,
            "float_mcap_yi": float(values[45]) if values[45] else 0,
            "pb": float(values[46]) if values[46] else 0,
            "limit_up": float(values[47]) if values[47] else 0,
            "limit_down": float(values[48]) if values[48] else 0,
            "pe_static": float(values[52]) if values[52] else 0,
        }
    return result
