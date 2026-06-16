"""Agent 提示词和消息处理共享辅助函数。"""

from __future__ import annotations

from langchain_core.messages import HumanMessage, RemoveMessage


def get_language_instruction() -> str:
    """根据运行时配置返回输出语言指令。"""
    from AShareAgents.datasource.config import get_config

    lang = get_config().get("output_language", "English")
    if lang.strip().lower() == "english":
        return ""
    return f" Write your entire response in {lang}."


def build_instrument_context(ticker: str) -> str:
    """描述需要在工具调用中保持一致的交易标的。"""
    return (
        f"The instrument to analyze is `{ticker}`. "
        "Use this exact ticker in every tool call, report, and recommendation, "
        "preserving any exchange suffix (e.g. `.TO`, `.L`, `.HK`, `.T`)."
    )


def create_msg_delete():
    """创建清理历史消息并保留占位消息的图节点。"""
    def delete_messages(state):
        messages = state["messages"]
        removal_operations = [RemoveMessage(id=m.id) for m in messages]
        placeholder = HumanMessage(content="Continue")
        return {"messages": removal_operations + [placeholder]}

    return delete_messages
