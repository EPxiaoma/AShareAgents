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

_RATING_SET = {r.lower() for r in RATINGS_5_TIER}

# 匹配 "Rating: X" / "rating - X" / "Rating: **X**" — 兼容 markdown
# 粗体包装以及冒号或连字符分隔符。
_RATING_LABEL_RE = re.compile(r"rating.*?[:\-][\s*]*(\w+)", re.IGNORECASE)


def parse_rating(text: str, default: str = "Hold") -> str:
    """从文本中启发式提取五档评级。

    两遍扫描策略：
    1. 查找显式的 "Rating: X" 标签（兼容 markdown 粗体）。
    2. 回退到文本中任意位置找到的第一个五档评级词。

    返回首字母大写的评级字符串，如果未找到评级词则返回 ``default``。
    """
    for line in text.splitlines():
        m = _RATING_LABEL_RE.search(line)
        if m and m.group(1).lower() in _RATING_SET:
            return m.group(1).capitalize()

    for line in text.splitlines():
        for word in line.lower().split():
            clean = word.strip("*:.,")
            if clean in _RATING_SET:
                return clean.capitalize()

    return default
