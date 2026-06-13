"""定义 LLM 客户端的统一抽象接口与共享配置。"""

from abc import ABC, abstractmethod
from typing import Any, Optional
import warnings


def normalize_content(response):
    """将 LLM 响应内容规范化为纯文本字符串。

    多个供应商（OpenAI Responses API、Google Gemini 3）返回的内容是类型化
    块的列表，例如 [{'type': 'reasoning', ...}, {'type': 'text', 'text': '...'}]。
    下游 agent 期望 response.content 为字符串。此函数提取并拼接文本块，
    丢弃推理/元数据块。
    """
    content = response.content
    if isinstance(content, list):
        texts = [
            item.get("text", "") if isinstance(item, dict) and item.get("type") == "text"
            else item if isinstance(item, str) else ""
            for item in content
        ]
        response.content = "\n".join(t for t in texts if t)
    return response


class BaseLLMClient(ABC):
    """LLM 客户端的抽象基类。"""

    def __init__(self, model: str, base_url: Optional[str] = None, **kwargs):
        self.model = model
        self.base_url = base_url
        self.kwargs = kwargs

    def get_provider_name(self) -> str:
        """返回用于警告消息中的供应商名称。"""
        provider = getattr(self, "provider", None)
        if provider:
            return str(provider)
        return self.__class__.__name__.removesuffix("Client").lower()

    def warn_if_unknown_model(self) -> None:
        """当模型不在该供应商的已知列表中时发出警告。"""
        if self.validate_model():
            return

        warnings.warn(
            (
                f"模型 '{self.model}' 不在供应商 '{self.get_provider_name()}' "
                f"的已知模型列表中，将继续运行。"
            ),
            RuntimeWarning,
            stacklevel=2,
        )

    @abstractmethod
    def get_llm(self) -> Any:
        """返回配置好的 LLM 实例。"""
        pass

    @abstractmethod
    def validate_model(self) -> bool:
        """验证此客户端是否支持该模型。"""
        pass
