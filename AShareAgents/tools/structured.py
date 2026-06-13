"""调用 Agent 并带有结构化输出及优雅回退的共享辅助函数。

投资组合经理、交易员和研究经理都遵循相同的规范模式：

1. 在 Agent 创建时，用 ``with_structured_output(Schema)`` 包装 LLM，
   使模型返回带类型的 Pydantic 实例。如果供应商不支持结构化输出
   （罕见；主要是较旧的 Ollama 模型），则跳过包装，
   Agent 改用自由文本生成。
2. 在调用时，运行结构化调用并将结果渲染回 markdown。
   如果结构化调用本身因任何原因失败（弱模型产生的畸形 JSON、
   供应商瞬时问题），则回退到普通的 ``llm.invoke``，
   确保流程永不阻塞。

将此模式集中在此处可保持 Agent 工厂的精简性，并确保在触发回退时
所有三个 Agent 记录相同的警告。
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional, TypeVar

from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def bind_structured(llm: Any, schema: type[T], agent_name: str) -> Optional[Any]:
    """返回 ``llm.with_structured_output(schema)``，若不支持则返回 ``None``。

    绑定失败时记录警告，以便用户了解该 Agent 每次调用都将使用自由文本
    生成，而不是一次性回退。
    """
    try:
        return llm.with_structured_output(schema)
    except (NotImplementedError, AttributeError) as exc:
        logger.warning(
            "%s: 供应商不支持 with_structured_output (%s)；"
            "回退到自由文本生成模式",
            agent_name, exc,
        )
        return None


def invoke_structured_or_freetext(
    structured_llm: Optional[Any],
    plain_llm: Any,
    prompt: Any,
    render: Callable[[T], str],
    agent_name: str,
) -> str:
    """运行结构化调用并渲染为 markdown；任何失败时回退到自由文本。

    ``prompt`` 是底层 LLM 接受的任何类型（聊天调用的字符串，
    或聊天模型接受的消息字典列表）。相同的值会转发到自由文本路径，
    以确保回退时看到的输入与结构化调用一致。
    """
    if structured_llm is not None:
        try:
            result = structured_llm.invoke(prompt)
            return render(result)
        except Exception as exc:
            logger.warning(
                "%s: 结构化输出调用失败 (%s)；以自由文本模式重试一次",
                agent_name, exc,
            )

    response = plain_llm.invoke(prompt)
    return response.content
