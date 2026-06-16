"""数据源持久化辅助函数。"""

from __future__ import annotations

import logging
from typing import Annotated

import pandas as pd

logger = logging.getLogger(__name__)

SavePathType = Annotated[str, "可选的 DataFrame CSV 保存路径。"]


def save_output(data: pd.DataFrame, tag: str, save_path: SavePathType = None) -> None:
    """当提供 ``save_path`` 时将 ``data`` 保存为 CSV。"""
    if save_path:
        data.to_csv(save_path, encoding="utf-8")
        logger.debug("%s 已保存至 %s", tag, save_path)
