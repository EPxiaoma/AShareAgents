"""演示如何使用自定义配置运行 AShareAgents 分析流程。"""

from dotenv import load_dotenv

load_dotenv()

from AShareAgents.config import DEFAULT_CONFIG  # noqa: E402
from AShareAgents.workflows.trading_graph import AShareAgentsGraph  # noqa: E402

config = DEFAULT_CONFIG.copy()
config["deep_think_llm"] = "gpt-5.4-mini"
config["quick_think_llm"] = "gpt-5.4-mini"
config["max_debate_rounds"] = 1

# 示例使用 yfinance，无需额外 API Key，适合直接运行。
config["data_vendors"] = {
    "core_stock_apis": "yfinance",
    "technical_indicators": "yfinance",
    "fundamental_data": "yfinance",
    "news_data": "yfinance",
}

ta = AShareAgentsGraph(debug=True, config=config)

_, decision = ta.propagate("NVDA", "2024-05-10")
print(decision)

# 示例：获得实际持仓收益后，可启用反思并写入交易记忆。
# 示例调用：ta.reflect_and_remember(1000)
