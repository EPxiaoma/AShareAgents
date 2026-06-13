from AShareAgents.workflows.trading_graph import AShareAgentsGraph
from AShareAgents.config import DEFAULT_CONFIG

from dotenv import load_dotenv

# 从 .env 文件加载环境变量
load_dotenv()

# 创建自定义配置
config = DEFAULT_CONFIG.copy()
config["deep_think_llm"] = "gpt-5.4-mini"  # 使用其他模型
config["quick_think_llm"] = "gpt-5.4-mini"  # 使用其他模型
config["max_debate_rounds"] = 1  # 增加辩论轮次

# 配置数据供应商（默认使用 yfinance，无需额外 API Key）
config["data_vendors"] = {
    "core_stock_apis": "yfinance",           # 可选: alpha_vantage, yfinance
    "technical_indicators": "yfinance",      # 可选: alpha_vantage, yfinance
    "fundamental_data": "yfinance",          # 可选: alpha_vantage, yfinance
    "news_data": "yfinance",                 # 可选: alpha_vantage, yfinance
}

# 使用自定义配置初始化
ta = AShareAgentsGraph(debug=True, config=config)

# 前向传播
_, decision = ta.propagate("NVDA", "2024-05-10")
print(decision)

# 记住错误并进行反思
# ta.reflect_and_remember(1000) # 参数为持仓收益
