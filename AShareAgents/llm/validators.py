"""各供应商的模型名称校验器。"""

from .model_catalog import get_known_models


VALID_MODELS = {
    provider: models
    for provider, models in get_known_models().items()
    if provider not in ("ollama", "openrouter")
}


def validate_model(provider: str, model: str) -> bool:
    """检查模型名称对于指定供应商是否有效。

    对于 ollama、openrouter——接受任何模型名称。
    """
    provider_lower = provider.lower()

    if provider_lower in ("ollama", "openrouter"):
        return True

    if provider_lower not in VALID_MODELS:
        return True

    return model in VALID_MODELS[provider_lower]
