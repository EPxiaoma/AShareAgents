from typing import Optional

from .base_client import BaseLLMClient

# 使用 OpenAI 兼容 chat completions API 的供应商
_OPENAI_COMPATIBLE = (
    "openai", "xai", "deepseek", "qwen", "glm", "ollama", "openrouter", "minimax",
)


def create_llm_client(
    provider: str,
    model: str,
    base_url: Optional[str] = None,
    **kwargs,
) -> BaseLLMClient:
    """为指定供应商创建 LLM 客户端。

    供应商模块采用懒加载方式导入，这样仅在导入此工厂函数时（例如在测试
    收集期间）不会拉入重量级的 LLM SDK，也不会因缺少 API Key 而失败。

    Args:
        provider: LLM 供应商名称
        model: 模型名称/标识符
        base_url: API 端点的可选基础 URL
        **kwargs: 供应商特定的额外参数

    Returns:
        配置好的 BaseLLMClient 实例

    Raises:
        ValueError: 如果供应商不受支持
    """
    provider_lower = provider.lower()

    if provider_lower in _OPENAI_COMPATIBLE:
        from .openai_client import OpenAIClient
        return OpenAIClient(model, base_url, provider=provider_lower, **kwargs)

    if provider_lower == "anthropic":
        from .anthropic_client import AnthropicClient
        return AnthropicClient(model, base_url, **kwargs)

    if provider_lower == "google":
        from .google_client import GoogleClient
        return GoogleClient(model, base_url, **kwargs)

    if provider_lower == "azure":
        from .azure_client import AzureOpenAIClient
        return AzureOpenAIClient(model, base_url, **kwargs)

    raise ValueError(f"不支持的LLM供应商：{provider}")
