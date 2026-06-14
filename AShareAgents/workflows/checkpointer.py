"""LangGraph断点续传支持模块：提供可恢复的分析运行能力。

每个股票使用独立的SQLite数据库，避免并发股票之间的资源竞争。
提供断点创建、检查、恢复和清理的完整API。
"""

from __future__ import annotations

import hashlib
import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from langgraph.checkpoint.sqlite import SqliteSaver

from AShareAgents.datasource.utils import safe_ticker_component

logger = logging.getLogger(__name__)


def _db_path(data_dir: str | Path, ticker: str) -> Path:
    """返回指定股票的SQLite断点数据库路径。

    Args:
        data_dir: 数据缓存根目录
        ticker: 股票代码

    Returns:
        断点数据库文件的完整路径
    """
    # 拒绝可能逃逸断点目录的股票代码值
    safe = safe_ticker_component(ticker).upper()
    p = Path(data_dir) / "checkpoints"
    p.mkdir(parents=True, exist_ok=True)
    return p / f"{safe}.db"


def thread_id(ticker: str, date: str) -> str:
    """为股票+日期对生成确定性的线程ID。

    Args:
        ticker: 股票代码
        date: 交易日期字符串

    Returns:
        16位十六进制哈希字符串
    """
    return hashlib.sha256(f"{ticker.upper()}:{date}".encode()).hexdigest()[:16]


@contextmanager
def get_checkpointer(data_dir: str | Path, ticker: str) -> Generator[SqliteSaver, None, None]:
    """上下文管理器，返回绑定到指定股票数据库的SqliteSaver。

    Args:
        data_dir: 数据缓存根目录
        ticker: 股票代码

    Yields:
        已初始化的SqliteSaver实例
    """
    db = _db_path(data_dir, ticker)
    conn = sqlite3.connect(str(db), check_same_thread=False)
    try:
        saver = SqliteSaver(conn)
        saver.setup()
        yield saver
    finally:
        conn.close()


def has_checkpoint(data_dir: str | Path, ticker: str, date: str) -> bool:
    """检查指定股票+日期是否存在可恢复的断点。

    Args:
        data_dir: 数据缓存根目录
        ticker: 股票代码
        date: 交易日期字符串

    Returns:
        存在断点时返回True，否则返回False
    """
    return checkpoint_step(data_dir, ticker, date) is not None


def checkpoint_step(data_dir: str | Path, ticker: str, date: str) -> int | None:
    """返回最新断点的步骤编号，若不存在则返回None。

    Args:
        data_dir: 数据缓存根目录
        ticker: 股票代码
        date: 交易日期字符串

    Returns:
        断点步骤编号（整数），无断点时返回None
    """
    db = _db_path(data_dir, ticker)
    if not db.exists():
        return None
    tid = thread_id(ticker, date)
    with get_checkpointer(data_dir, ticker) as saver:
        config = {"configurable": {"thread_id": tid}}
        cp = saver.get_tuple(config)
        if cp is None:
            return None
        return cp.metadata.get("step")


def clear_all_checkpoints(data_dir: str | Path) -> int:
    """删除所有断点数据库文件。

    Args:
        data_dir: 数据缓存根目录

    Returns:
        被删除的文件数量
    """
    cp_dir = Path(data_dir) / "checkpoints"
    if not cp_dir.exists():
        return 0
    dbs = list(cp_dir.glob("*.db"))
    for db in dbs:
        db.unlink()
    return len(dbs)


def clear_checkpoint(data_dir: str | Path, ticker: str, date: str) -> None:
    """删除指定股票+日期的断点（通过删除该线程对应的数据库行实现）。

    Args:
        data_dir: 数据缓存根目录
        ticker: 股票代码
        date: 交易日期字符串
    """
    db = _db_path(data_dir, ticker)
    if not db.exists():
        return
    tid = thread_id(ticker, date)
    conn = sqlite3.connect(str(db))
    try:
        existing_tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        if "writes" in existing_tables:
            conn.execute("DELETE FROM writes WHERE thread_id = ?", (tid,))
        if "checkpoints" in existing_tables:
            conn.execute("DELETE FROM checkpoints WHERE thread_id = ?", (tid,))
        conn.commit()
    except sqlite3.Error:
        conn.rollback()
        logger.warning(
            "Failed to clear checkpoint %s for %s",
            tid,
            ticker,
            exc_info=True,
        )
    finally:
        conn.close()
