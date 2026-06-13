import os

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_CACHE_DIR = os.path.join(_PROJECT_ROOT, "cache")

DEFAULT_CONFIG = {
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    "results_dir": os.getenv("ASHAREAGENTS_RESULTS_DIR", os.path.join(_CACHE_DIR, "results")),
    "data_cache_dir": os.getenv("ASHAREAGENTS_CACHE_DIR", os.path.join(_CACHE_DIR, "ohlcv")),
    "memory_log_path": os.getenv("ASHAREAGENTS_MEMORY_LOG_PATH", os.path.join(_CACHE_DIR, "memory", "trading_memory.md")),
    # 已解决记忆日志条目的可选数量上限。设置后，
    # 一旦超过此限制，最早的已解决条目将被裁剪。
    # 待处理条目永远不会被裁剪。None 表示完全禁用轮转。
    "memory_log_max_entries": None,
    # LLM 设置
    "llm_provider": "openai",
    "deep_think_llm": "gpt-5.4",
    "quick_think_llm": "gpt-5.4-mini",
    # 设为 None 时，各供应商的客户端回退到各自的默认端点
    #（OpenAI 为 api.openai.com，Gemini 为 generativelanguage.googleapis.com，等）。
    # CLI 在用户选择供应商时会分别覆盖此字段。在此保留供应商特定的 URL
    # 会导致泄露（例如 OpenAI 的 /v1 曾被转发到 Gemini，产生畸形的请求 URL）。
    "backend_url": None,
    # 供应商特定的思考配置
    "google_thinking_level": None,      # "high"、"minimal" 等
    "openai_reasoning_effort": None,    # "medium"、"high"、"low"
    "anthropic_effort": None,           # "high"、"medium"、"low"
    # 检查点/恢复：启用后，LangGraph 在每个节点后保存状态，
    # 从而使崩溃的运行能够从最后成功的步骤恢复。
    "checkpoint_enabled": False,
    # 分析师报告和最终决策的输出语言
    # 内部 Agent 辩论保持英文以确保推理质量
    "output_language": "Chinese",
    # 辩论和讨论设置
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1,
    "max_recur_limit": 100,
    # 数据供应商配置
    # 类别级别配置（该类别的所有工具的默认值）
    "data_vendors": {
        "core_stock_apis": "a_stock",        # 可选: a_stock, alpha_vantage, yfinance
        "technical_indicators": "a_stock",   # 可选: a_stock, alpha_vantage, yfinance
        "fundamental_data": "a_stock",       # 可选: a_stock, alpha_vantage, yfinance
        "news_data": "a_stock",              # 可选: a_stock, alpha_vantage, yfinance
        "signal_data": "a_stock",            # 仅 A 股: 题材归属, 资金流向, 一致性预期
    },
    # 工具级别配置（优先级高于类别级别）
    "tool_vendors": {
        # 示例: "get_stock_data": "alpha_vantage",  # 覆盖类别默认值
    },
}
