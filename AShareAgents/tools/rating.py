"""共享的五档评级词汇表及确定性的启发式解析器。

同一五档评级（Buy、Overweight、Hold、Underweight、Sell）被以下组件使用：
- 研究经理（投资方案推荐）
- 投资组合经理（最终仓位决策）
- 信号处理器（提取评级供下游消费）
- 记忆日志（每条决策记录旁存储评级标签）

在此集中定义可避免各调用点之间的评分标准漂移。
"""

from __future__ import annotations

import re
from typing import Tuple


# 规范化的五档有序评级（从最看多到最看空）
RATINGS_5_TIER: Tuple[str, ...] = (
    "Buy", "Overweight", "Hold", "Underweight", "Sell",
)

_RATING_ALIASES = {
    "buy": "Buy",
    "买入": "Buy",
    "overweight": "Overweight",
    "增持": "Overweight",
    "超配": "Overweight",
    "hold": "Hold",
    "持有": "Hold",
    "中性": "Hold",
    "underweight": "Underweight",
    "减持": "Underweight",
    "低配": "Underweight",
    "sell": "Sell",
    "卖出": "Sell",
    "清仓": "Sell",
}

_EXPLICIT_LABEL_RE = re.compile(
    r"(?:final\s+(?:investment\s+)?(?:rating|decision)|"
    r"final\s+transaction\s+proposal|rating|"
    r"最终(?:投资)?(?:评级|决策|建议|计划)|评级|头寸方向|交易信号)",
    re.IGNORECASE,
)
_ENGLISH_RATING_RE = re.compile(
    r"\b(underweight|overweight|buy|hold|sell)\b",
    re.IGNORECASE,
)
_CHINESE_RATING_RE = re.compile(r"(减持|增持|超配|低配|买入|持有|中性|卖出|清仓)")


def _rating_in_text(text: str) -> str | None:
    """从一段结论文本中提取规范化的五级评级。"""
    english = _ENGLISH_RATING_RE.search(text)
    chinese = _CHINESE_RATING_RE.search(text)

    if english and (not chinese or english.start() < chinese.start()):
        return _RATING_ALIASES[english.group(1).lower()]
    if chinese:
        return _RATING_ALIASES[chinese.group(1)]
    return None


def parse_rating(text: str, default: str = "Hold") -> str:
    """从文本中启发式提取五档评级。

    两遍扫描策略：
    1. 优先查找带有“最终评级 / Rating / 交易信号”等标签的结论行。
    2. 兼容旧报告，从文末向前查找中英文五档评级词。

    返回首字母大写的评级字符串，如果未找到评级词则返回 ``default``。
    """
    lines = [line.strip() for line in str(text).splitlines() if line.strip()]

    for line in reversed(lines):
        if _EXPLICIT_LABEL_RE.search(line):
            rating = _rating_in_text(line)
            if rating:
                return rating

    for line in reversed(lines):
        rating = _rating_in_text(line)
        if rating:
            return rating

    return default
