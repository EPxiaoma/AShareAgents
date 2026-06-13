"""AShareAgents 集中式日志配置。

在启动时调用一次 ``setup_logging()`` 以保持控制台输出简洁：
仅显示核心运行时消息（WARNING+ 以及 AShareAgents 的 INFO）；
嘈杂的第三方库被静音到 ERROR 级别。
"""

from __future__ import annotations

import logging
import sys


def setup_logging(*, verbose: bool = False) -> None:
    """配置 Python 日志以获得简洁的控制台体验。

    * 根 logger → WARNING（抑制第三方库的 DEBUG/INFO）。
    * ``AShareAgents`` 命名空间 → INFO（使核心操作消息可见）。
    * 嘈杂的库（httpx、urllib3、langchain 等）→ 仅 ERROR。
    * Streamlit 内部 → WARNING（保持其面向用户的 UI 整洁）。
    * ``mootdx`` → ERROR（原始 TCP 级别的杂讯）。

    传入 ``verbose=True`` 可将 AShareAgents logger 恢复为 DEBUG 级别。
    """
    fmt = logging.Formatter(
        "[%(levelname)-7s] %(name)s ‒ %(message)s",
        datefmt="%H:%M:%S",
    )
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(fmt)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.WARNING)

    # 核心应用 — 保持信息丰富
    ashare_level = logging.DEBUG if verbose else logging.INFO
    for name in ("AShareAgents", "frontend", "cli"):
        logging.getLogger(name).setLevel(ashare_level)

    # 第三方库噪音控制
    _SILENCE = (
        "httpx",
        "httpcore",
        "urllib3",
        "requests",
        "openai",
        "anthropic",
        "langchain",
        "langchain_core",
        "langchain_openai",
        "langchain_anthropic",
        "langgraph",
        "langgraph_api",
        "mootdx",
        "stockstats",
        "yfinance",
        "watchfiles",
        "PIL",
        "matplotlib",
        "asyncio",
        "charset_normalizer",
        "numexpr",
        "fpdf",
        "fontTools",
    )
    for name in _SILENCE:
        logging.getLogger(name).setLevel(logging.ERROR)

    # Streamlit 自身在 INFO 级别过于啰嗦；保持 WARNING 级别
    logging.getLogger("streamlit").setLevel(logging.WARNING)
