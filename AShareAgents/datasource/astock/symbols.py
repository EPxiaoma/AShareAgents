"""A-share ticker normalization and name/code resolution."""

from __future__ import annotations

import logging

from ..eastMoney import resolve_stock_code as _resolve_eastmoney_stock_code
from ..mootdx import build_name_code_map as _load_mootdx_name_code_map
from ..ticker_safety import safe_ticker_component
from .cache import _info_once
from .errors import RECOVERABLE_DATA_SOURCE_ERRORS

logger = logging.getLogger(__name__)

# 股票代码格式与市场识别

def _get_prefix(code: str) -> str:
    """6位A股代码 -> 腾讯API所需的市场前缀。"""
    if code.startswith(("6", "9")):
        return "sh"
    elif code.startswith("8"):
        return "bj"
    return "sz"


def _normalize_ticker(symbol: str) -> str:
    """去除交易所前缀/后缀，返回纯6位代码。

    支持的格式：'688017'、'SH688017'、'688017.SH'、'sh688017'
    """
    s = symbol.strip().upper()
    # 去除 .SH / .SZ / .BJ 后缀
    for suffix in (".SH", ".SZ", ".BJ"):
        if s.endswith(suffix):
            s = s[: -len(suffix)]
            break
    # 去除 SH / SZ / BJ 前缀
    for prefix in ("SH", "SZ", "BJ"):
        if s.startswith(prefix):
            s = s[len(prefix) :]
            break
    return safe_ticker_component(s)


# 股票名称与代码映射缓存

_name_to_code: dict[str, str] | None = None
_code_to_name: dict[str, str] | None = None
_api_resolution_cache: dict[str, str | None] = {}


def _build_name_code_map() -> tuple[dict[str, str], dict[str, str]]:
    """通过 mootdx 构建 名称→代码 和 代码→名称 映射（覆盖沪深两市）。

    当 mootdx 不可达时回退为空映射——单只股票的名称查询将按需改用东方财富搜索API。
    """
    global _name_to_code, _code_to_name
    if _name_to_code is not None:
        return _name_to_code, _code_to_name

    try:
        n2c, c2n = _load_mootdx_name_code_map()
    except RECOVERABLE_DATA_SOURCE_ERRORS as exc:
        n2c, c2n = {}, {}
        logger.debug("mootdx 名称-代码映射构建失败: %s", exc, exc_info=True)

    _name_to_code = n2c
    _code_to_name = c2n
    if n2c:
        logger.info("已构建股票名称-代码映射：%d 条记录", len(n2c))
    else:
        _info_once(
            "mootdx-name-map",
            "股票名称解析：mootdx 列表不可用，已启用东方财富按需查询",
        )
    return _name_to_code, _code_to_name


def _resolve_by_api(keyword: str) -> str | None:
    """通过东方财富联想搜索API将中文股票名称解析为6位代码。

    Returns:
        代码字符串，若未匹配到则返回 None。
    """
    if keyword in _api_resolution_cache:
        return _api_resolution_cache[keyword]

    result: str | None = None
    try:
        result = _resolve_eastmoney_stock_code(keyword)
    except RECOVERABLE_DATA_SOURCE_ERRORS as exc:
        logger.warning("东方财富联想搜索 API 对 %r 的请求失败: %s", keyword, exc)

    if result is not None:
        _api_resolution_cache[keyword] = result
    return result


def resolve_ticker(user_input: str) -> str:
    """将用户输入（代码或中文名称）解析为6位A股代码。

    支持的输入：'600379'、'SH600379'、'600379.SH'、'宝光股份'

    Returns:
        '600379' 格式的6位代码。

    Raises:
        ValueError: 无法解析时抛出。
    """
    s = user_input.strip()
    if not s:
        raise ValueError("输入不能为空")

    has_chinese = any("一" <= ch <= "鿿" for ch in s)

    if not has_chinese:
        return _normalize_ticker(s)

    clean = s.replace(" ", "").replace("　", "")
    n2c, _ = _build_name_code_map()

    if clean in n2c:
        return n2c[clean]

    matches = {name: code for name, code in n2c.items() if clean in name}
    if len(matches) == 1:
        return next(iter(matches.values()))
    if len(matches) > 1:
        examples = ", ".join(f"{n}({c})" for n, c in list(matches.items())[:5])
        raise ValueError(f"'{s}' 匹配到多只股票: {examples}，请输入完整名称或代码")

    # 回退：本地映射为空或不包含此名称时（如 mootdx 不可达、新股上市），
    # 尝试东方财富联想搜索API。
    api_code = _resolve_by_api(clean)
    if api_code:
        n2c[clean] = api_code
        if _code_to_name is not None:
            _code_to_name.setdefault(api_code, clean)
        logger.info("API 解析 %r -> %s", s, api_code)
        return api_code

    raise ValueError(f"找不到股票 '{s}'，请检查名称是否正确")

