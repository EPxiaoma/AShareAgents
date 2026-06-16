"""供 CLI 选择与校验使用的共享模型目录。"""

from __future__ import annotations

from typing import Dict, List, Tuple

ModelOption = Tuple[str, str]
ProviderModeOptions = Dict[str, Dict[str, List[ModelOption]]]


MODEL_OPTIONS: ProviderModeOptions = {
    "openai": {
        "quick": [
            ("GPT-5.4", "gpt-5.4-mini"),
            ("GPT-5.4", "gpt-5.4-nano"),
            ("GPT-5.4", "gpt-5.4"),
            ("GPT-4.1", "gpt-4.1"),
        ],
        "deep": [
            ("GPT-5.4", "gpt-5.4"),
            ("GPT-5.2", "gpt-5.2"),
            ("GPT-5.4 Mini", "gpt-5.4-mini"),
            ("GPT-5.4 Pro", "gpt-5.4-pro"),
        ],
    },
    "anthropic": {
        "quick": [
            ("Claude Sonnet 4.6", "claude-sonnet-4-6"),
            ("Claude Haiku 4.5", "claude-haiku-4-5"),
            ("Claude Sonnet 4.5", "claude-sonnet-4-5"),
        ],
        "deep": [
            ("Claude Opus 4.6", "claude-opus-4-6"),
            ("Claude Opus 4.5", "claude-opus-4-5"),
            ("Claude Sonnet 4.6", "claude-sonnet-4-6"),
            ("Claude Sonnet 4.5", "claude-sonnet-4-5"),
        ],
    },
    "google": {
        "quick": [
            ("Gemini 3 Flash", "gemini-3-flash-preview"),
            ("Gemini 2.5 Flash", "gemini-2.5-flash"),
            ("Gemini 3.1 Flash Lite", "gemini-3.1-flash-lite-preview"),
            ("Gemini 2.5 Flash Lite", "gemini-2.5-flash-lite"),
        ],
        "deep": [
            ("Gemini 3.1 Pro ", "gemini-3.1-pro-preview"),
            ("Gemini 3 Flash", "gemini-3-flash-preview"),
            ("Gemini 2.5 Pro", "gemini-2.5-pro"),
            ("Gemini 2.5 Flash", "gemini-2.5-flash"),
        ],
    },
    "xai": {
        "quick": [
            ("Grok 4.1 Fast (Non-Reasoning), 2M ctx", "grok-4-1-fast-non-reasoning"),
            ("Grok 4 Fast (Non-Reasoning)", "grok-4-fast-non-reasoning"),
            ("Grok 4.1 Fast (Reasoning)", "grok-4-1-fast-reasoning"),
        ],
        "deep": [
            ("Grok 4", "grok-4-0709"),
            ("Grok 4.1 Fast (Reasoning)", "grok-4-1-fast-reasoning"),
            ("Grok 4 Fast (Reasoning)", "grok-4-fast-reasoning"),
            ("Grok 4.1 Fast (Non-Reasoning)", "grok-4-1-fast-non-reasoning"),
        ],
    },
    "deepseek": {
        "quick": [
            ("DeepSeek V4 Flash", "deepseek-v4-flash"),
            ("DeepSeek V3.2", "deepseek-chat"),
            ("Custom model ID", "custom"),
        ],
        "deep": [
            ("DeepSeek V4 Pro", "deepseek-v4-pro"),
            ("DeepSeek V3.2 (thinking)", "deepseek-reasoner"),
            ("DeepSeek V3.2", "deepseek-chat"),
            ("Custom model ID", "custom"),
        ],
    },
    "qwen": {
        "quick": [
            ("Qwen 3.5 Flash", "qwen3.5-flash"),
            ("Qwen Plus", "qwen-plus"),
            ("Custom model ID", "custom"),
        ],
        "deep": [
            ("Qwen 3.6 Plus", "qwen3.6-plus"),
            ("Qwen 3.5 Plus", "qwen3.5-plus"),
            ("Qwen 3 Max", "qwen3-max"),
            ("Custom model ID", "custom"),
        ],
    },
    "glm": {
        "quick": [
            ("GLM-4.7", "glm-4.7"),
            ("GLM-5", "glm-5"),
            ("Custom model ID", "custom"),
        ],
        "deep": [
            ("GLM-5.1", "glm-5.1"),
            ("GLM-5", "glm-5"),
            ("Custom model ID", "custom"),
        ],
    },
    "minimax": {
        "quick": [
            ("MiniMax-M2.7-highspeed", "MiniMax-M2.7-highspeed"),
            ("MiniMax-M2.5-highspeed", "MiniMax-M2.5-highspeed"),
            ("Custom model ID", "custom"),
        ],
        "deep": [
            ("MiniMax-M2.7", "MiniMax-M2.7"),
            ("MiniMax-M2.5", "MiniMax-M2.5"),
            ("MiniMax-M2.7-highspeed", "MiniMax-M2.7-highspeed"),
            ("Custom model ID", "custom"),
        ],
    },
    # 模型来源说明：OpenRouter 动态获取；Azure 可使用任何已部署的模型名称。
    "ollama": {
        "quick": [
            ("Qwen3:latest (8B, local)", "qwen3:latest"),
            ("GPT-OSS:latest (20B, local)", "gpt-oss:latest"),
            ("GLM-4.7-Flash:latest (30B, local)", "glm-4.7-flash:latest"),
        ],
        "deep": [
            ("GLM-4.7-Flash:latest (30B, local)", "glm-4.7-flash:latest"),
            ("GPT-OSS:latest (20B, local)", "gpt-oss:latest"),
            ("Qwen3:latest (8B, local)", "qwen3:latest"),
        ],
    },
}


def get_model_options(provider: str, mode: str) -> List[ModelOption]:
    """返回指定供应商和选择模式的共享模型选项。"""
    return MODEL_OPTIONS[provider.lower()][mode]


def get_known_models() -> Dict[str, List[str]]:
    """从共享的 CLI 目录中构建已知模型名称列表。"""
    return {
        provider: sorted(
            {
                value
                for options in mode_options.values()
                for _, value in options
            }
        )
        for provider, mode_options in MODEL_OPTIONS.items()
    }
