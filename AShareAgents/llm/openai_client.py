import os
from typing import Any, Optional

from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI

from .base_client import BaseLLMClient, normalize_content
from .validators import validate_model


class NormalizedChatOpenAI(ChatOpenAI):
    """输出内容已规范化的 ChatOpenAI。

    Responses API 将内容以类型化块列表（推理、文本等）返回。
    ``invoke`` 将其规范化为字符串，以保证下游处理的一致性。
    ``with_structured_output`` 默认使用函数调用模式，避免走
    Responses-API 的解析路径（langchain-openai 的解析路径每次调用
    都会产生 PydanticSerializationUnexpectedValue 警告，但不影响正确性）。

    供应商特定的怪癖（例如 DeepSeek 的思考模式）放在下面的专用子类中，
    以保持此基类的精简。
    """

    def invoke(self, input, config=None, **kwargs):
        return normalize_content(super().invoke(input, config, **kwargs))

    def with_structured_output(self, schema, *, method=None, **kwargs):
        if method is None:
            method = "function_calling"
        return super().with_structured_output(schema, method=method, **kwargs)


def _input_to_messages(input_: Any) -> list:
    """将 langchain LLM 输入规范化为消息对象列表。

    接受消息列表、``ChatPromptValue``（来自 ChatPromptTemplate），
    或其他任何类型（视为无消息）。供需要遍历传出消息历史的供应商使用；
    特别是 DeepSeek 思考模式的传播必须同时支持裸列表调用和
    ChatPromptTemplate 驱动的调用，因此在这里仅处理 ``list``
    会静默跳过一半的调用点。
    """
    if isinstance(input_, list):
        return input_
    if hasattr(input_, "to_messages"):
        return input_.to_messages()
    return []


class DeepSeekChatOpenAI(NormalizedChatOpenAI):
    """DeepSeek 专用覆盖，基于 OpenAI 兼容客户端。

    两个不适用于其他 OpenAI 兼容供应商的怪癖：

    1. **思考模式往返传播。** 当 DeepSeek 的思考模型返回包含 ``reasoning_content``
       的响应时，该字段必须在下一轮作为 assistant 消息的一部分原样回传，
       否则 API 会报 HTTP 400 错误。``_create_chat_result`` 在接收时捕获该字段，
       ``_get_request_payload`` 在发送时重新附加。

    2. **deepseek-reasoner 不支持 tool_choice。** 通过函数调用实现的结构化输出
       不可用，因此我们抛出 NotImplementedError，让 agent 工厂回退到自由文本生成
       （参见 ``AShareAgents/tools/structured.py``）。
    """

    def _get_request_payload(self, input_, *, stop=None, **kwargs):
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        outgoing = payload.get("messages", [])
        for message_dict, message in zip(outgoing, _input_to_messages(input_)):
            if not isinstance(message, AIMessage):
                continue
            reasoning = message.additional_kwargs.get("reasoning_content")
            if reasoning is not None:
                message_dict["reasoning_content"] = reasoning
        return payload

    def _create_chat_result(self, response, generation_info=None):
        chat_result = super()._create_chat_result(response, generation_info)
        response_dict = (
            response
            if isinstance(response, dict)
            else response.model_dump(
                exclude={"choices": {"__all__": {"message": {"parsed"}}}}
            )
        )
        for generation, choice in zip(
            chat_result.generations, response_dict.get("choices", [])
        ):
            reasoning = choice.get("message", {}).get("reasoning_content")
            if reasoning is not None:
                generation.message.additional_kwargs["reasoning_content"] = reasoning
        return chat_result

    def with_structured_output(self, schema, *, method=None, **kwargs):
        if self.model_name == "deepseek-reasoner":
            raise NotImplementedError(
                "deepseek-reasoner 不支持 tool_choice，结构化输出不可用。"
                "Agent 工厂将自动回退到自由文本生成模式。"
            )
        return super().with_structured_output(schema, method=method, **kwargs)

# 从用户配置转发给 ChatOpenAI 的 kwargs
_PASSTHROUGH_KWARGS = (
    "timeout", "max_retries", "reasoning_effort",
    "api_key", "callbacks", "http_client", "http_async_client",
)

# 各供应商的基础 URL 和 API Key 环境变量
_PROVIDER_CONFIG = {
    "xai": ("https://api.x.ai/v1", "XAI_API_KEY"),
    "deepseek": ("https://api.deepseek.com", "DEEPSEEK_API_KEY"),
    "qwen": ("https://dashscope-intl.aliyuncs.com/compatible-mode/v1", "DASHSCOPE_API_KEY"),
    "glm": ("https://api.z.ai/api/paas/v4/", "ZHIPU_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    "ollama": ("http://localhost:11434/v1", None),
    "minimax": ("https://api.minimax.chat/v1", "MINIMAX_API_KEY"),
}


class OpenAIClient(BaseLLMClient):
    """OpenAI、Ollama、OpenRouter 和 xAI 供应商的客户端。

    对于原生 OpenAI 模型，使用 Responses API (/v1/responses)，该 API 支持
    在所有模型系列（GPT-4.1、GPT-5）中使用 reasoning_effort 配合函数工具。
    第三方兼容供应商（xAI、OpenRouter、Ollama）使用标准 Chat Completions。
    """

    def __init__(
        self,
        model: str,
        base_url: Optional[str] = None,
        provider: str = "openai",
        **kwargs,
    ):
        super().__init__(model, base_url, **kwargs)
        self.provider = provider.lower()

    def get_llm(self) -> Any:
        """返回配置好的 ChatOpenAI 实例。"""
        self.warn_if_unknown_model()
        llm_kwargs = {"model": self.model}

        # 供应商特定的基础 URL 和认证。客户端上的显式 base_url（例如
        # 企业代理）优先于供应商默认值，以便用户通过自己的网关路由。
        if self.provider in _PROVIDER_CONFIG:
            default_base, api_key_env = _PROVIDER_CONFIG[self.provider]
            llm_kwargs["base_url"] = self.base_url or default_base
            if api_key_env:
                api_key = os.environ.get(api_key_env)
                if api_key:
                    llm_kwargs["api_key"] = api_key
                elif "api_key" not in self.kwargs:
                    # 否则 ChatOpenAI 下游会报 "OPENAI_API_KEY must be set"
                    # 但 deepseek/qwen/glm/minimax 各自需要自己的环境变量，
                    # 这里明确指出所需的具体变量名 (#42)。
                    raise RuntimeError(
                        f"未找到 {self.provider} 的 API Key。请在 .env 文件或环境变量中设置 "
                        f"`{api_key_env}`（例如 `{api_key_env}=你的key`），设置后重启程序。"
                        f"注意：{self.provider} 用的是 {api_key_env}，不是 OPENAI_API_KEY。"
                    )
            else:
                llm_kwargs["api_key"] = "ollama"
        elif self.base_url:
            llm_kwargs["base_url"] = self.base_url

        # 转发用户提供的 kwargs
        for key in _PASSTHROUGH_KWARGS:
            if key in self.kwargs:
                llm_kwargs[key] = self.kwargs[key]

        # 原生 OpenAI：使用 Responses API 以在所有模型系列中保持一致行为。
        # 第三方供应商使用 Chat Completions。
        if self.provider == "openai":
            llm_kwargs["use_responses_api"] = True

        # DeepSeek 的思考模式怪癖放在自己的子类中，以保持
        # 基础 NormalizedChatOpenAI 不包含供应商特定的分支。
        chat_cls = DeepSeekChatOpenAI if self.provider == "deepseek" else NormalizedChatOpenAI
        return chat_cls(**llm_kwargs)

    def validate_model(self) -> bool:
        """验证该供应商的模型是否有效。"""
        return validate_model(self.provider, self.model)
