"""编排并运行 A 股智能分析工作流。

主流程整合分析师、辩论、风险评估、结果持久化、断点恢复和延迟反思。
"""

import logging
import os
from pathlib import Path
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Tuple, List, Optional

import yfinance as yf

logger = logging.getLogger(__name__)

from langgraph.prebuilt import ToolNode

from AShareAgents.llm import create_llm_client

from AShareAgents.agents import *
from AShareAgents.config import DEFAULT_CONFIG
from AShareAgents.memory.memory import TradingMemoryLog
from AShareAgents.datasource.utils import safe_ticker_component
from AShareAgents.tools.agent_states import (
    AgentState,
    InvestDebateState,
    RiskDebateState,
)
from AShareAgents.datasource.config import set_config

# 从 agent_utils 导入抽象工具方法
from AShareAgents.tools.agent_utils import (
    get_stock_data,
    get_indicators,
    get_fundamentals,
    get_balance_sheet,
    get_cashflow,
    get_income_statement,
    get_news,
    get_insider_transactions,
    get_global_news,
    get_profit_forecast,
    get_hot_stocks,
    get_northbound_flow,
    get_concept_blocks,
    get_fund_flow,
    get_dragon_tiger_board,
    get_lockup_expiry,
    get_industry_comparison,
    search_company_official_documents,
    search_policy_industry_knowledge,
)

from .checkpointer import checkpoint_step, clear_checkpoint, get_checkpointer, thread_id
from .conditional_logic import ConditionalLogic
from .setup import GraphSetup
from .propagation import Propagator
from .reflection import Reflector
from .signal_processing import SignalProcessor


class AShareAgentsGraph:
    """A股智能分析图编排器，负责协调所有分析组件的工作流执行。"""

    def __init__(
        self,
        selected_analysts=["market", "social", "news", "fundamentals", "policy", "hot_money", "lockup"],
        debug=False,
        config: Dict[str, Any] = None,
        callbacks: Optional[List] = None,
    ):
        """初始化A股智能分析图及其组件。

        Args:
            selected_analysts: 需要启用的分析师类型列表
            debug: 是否启用调试模式
            config: 配置字典，为None时使用默认配置
            callbacks: 可选的回调处理器列表（用于跟踪LLM/工具调用统计）
        """
        self.debug = debug
        self.config = config or DEFAULT_CONFIG
        self.callbacks = callbacks or []

        # 更新接口配置
        set_config(self.config)

        # 创建必要的目录
        os.makedirs(self.config["data_cache_dir"], exist_ok=True)
        os.makedirs(self.config["results_dir"], exist_ok=True)

        # 初始化LLM客户端，根据提供商配置思考参数
        llm_kwargs = self._get_provider_kwargs()

        # 将回调传入kwargs（传递给LLM构造函数）
        if self.callbacks:
            llm_kwargs["callbacks"] = self.callbacks

        deep_client = create_llm_client(
            provider=self.config["llm_provider"],
            model=self.config["deep_think_llm"],
            base_url=self.config.get("backend_url"),
            **llm_kwargs,
        )
        quick_client = create_llm_client(
            provider=self.config["llm_provider"],
            model=self.config["quick_think_llm"],
            base_url=self.config.get("backend_url"),
            **llm_kwargs,
        )

        self.deep_thinking_llm = deep_client.get_llm()
        self.quick_thinking_llm = quick_client.get_llm()

        self.memory_log = TradingMemoryLog(self.config)

        # 创建工具节点
        self.tool_nodes = self._create_tool_nodes()

        # 初始化各组件
        self.conditional_logic = ConditionalLogic(
            max_debate_rounds=self.config["max_debate_rounds"],
            max_risk_discuss_rounds=self.config["max_risk_discuss_rounds"],
        )
        self.graph_setup = GraphSetup(
            self.quick_thinking_llm,
            self.deep_thinking_llm,
            self.tool_nodes,
            self.conditional_logic,
        )

        self.propagator = Propagator()
        self.reflector = Reflector(self.quick_thinking_llm)
        self.signal_processor = SignalProcessor(self.quick_thinking_llm)

        # 状态追踪
        self.curr_state = None
        self.ticker = None
        self.log_states_dict = {}  # 日期到完整状态字典的映射

        # 构建工作流：保留workflow以便使用断点保存器重新编译
        self.workflow = self.graph_setup.setup_graph(selected_analysts)
        self.graph = self.workflow.compile()
        self._checkpointer_ctx = None

    def _get_provider_kwargs(self) -> Dict[str, Any]:
        """获取LLM客户端创建的供应商特定参数。

        Returns:
            包含供应商特定配置的字典
        """
        kwargs = {}
        provider = self.config.get("llm_provider", "").lower()

        if provider == "google":
            thinking_level = self.config.get("google_thinking_level")
            if thinking_level:
                kwargs["thinking_level"] = thinking_level

        elif provider == "openai":
            reasoning_effort = self.config.get("openai_reasoning_effort")
            if reasoning_effort:
                kwargs["reasoning_effort"] = reasoning_effort

        elif provider == "anthropic":
            effort = self.config.get("anthropic_effort")
            if effort:
                kwargs["effort"] = effort

        return kwargs

    def _create_tool_nodes(self) -> Dict[str, ToolNode]:
        """为不同数据源创建工具节点（基于抽象工具方法）。

        Returns:
            分析师类型到ToolNode的映射字典
        """
        return {
            "market": ToolNode(
                [
                    # 核心股票数据工具
                    get_stock_data,
                    # 技术指标
                    get_indicators,
                ]
            ),
            "social": ToolNode(
                [
                    # 社交媒体分析相关的新闻工具
                    get_news,
                ]
            ),
            "news": ToolNode(
                [
                    # 新闻和内幕信息
                    get_news,
                    get_global_news,
                    get_insider_transactions,
                ]
            ),
            "fundamentals": ToolNode(
                [
                    get_fundamentals,
                    get_balance_sheet,
                    get_cashflow,
                    get_income_statement,
                    get_profit_forecast,
                    get_industry_comparison,
                    search_company_official_documents,
                ]
            ),
            "policy": ToolNode(
                [
                    get_news,
                    get_global_news,
                    search_policy_industry_knowledge,
                ]
            ),
            "hot_money": ToolNode(
                [
                    get_stock_data,
                    get_news,
                    get_insider_transactions,
                    get_hot_stocks,
                    get_northbound_flow,
                    get_concept_blocks,
                    get_fund_flow,
                    get_dragon_tiger_board,
                    get_industry_comparison,
                ]
            ),
            "lockup": ToolNode(
                [
                    get_insider_transactions,
                    get_news,
                    get_fundamentals,
                    get_lockup_expiry,
                ]
            ),
        }

    def _fetch_returns(
        self, ticker: str, trade_date: str, holding_days: int = 5
    ) -> Tuple[Optional[float], Optional[float], Optional[int]]:
        """获取从交易日起持有一定天数后的原始收益和alpha收益。

        Returns:
            (原始收益, alpha收益, 实际持有天数) 的元组；
            若价格数据不可用（时间过近、已退市或网络错误），返回 (None, None, None)。
        """
        try:
            start = datetime.strptime(trade_date, "%Y-%m-%d")
            end = start + timedelta(days=holding_days + 7)  # 为周末/节假留出缓冲
            end_str = end.strftime("%Y-%m-%d")

            stock = yf.Ticker(ticker).history(start=trade_date, end=end_str)
            benchmark = yf.Ticker("000300.SS").history(start=trade_date, end=end_str)

            if len(stock) < 2 or len(benchmark) < 2:
                return None, None, None

            actual_days = min(holding_days, len(stock) - 1, len(benchmark) - 1)
            raw = float(
                (stock["Close"].iloc[actual_days] - stock["Close"].iloc[0])
                / stock["Close"].iloc[0]
            )
            bench_ret = float(
                (benchmark["Close"].iloc[actual_days] - benchmark["Close"].iloc[0])
                / benchmark["Close"].iloc[0]
            )
            alpha = raw - bench_ret
            return raw, alpha, actual_days
        except Exception as e:
            logger.warning(
                "无法获取 %s 在 %s 的结果（下次运行将重试）: %s",
                ticker, trade_date, e,
            )
            return None, None, None

    def _resolve_pending_entries(self, ticker: str) -> None:
        """在新一轮运行开始时，解析该股票待处理的日志条目。

        对每一条同股票的待处理日志获取收益数据、生成反思，
        然后通过单次原子批量写入更新所有条目，避免重复I/O。
        跳过价格数据尚不可用的条目（时间过近或已退市）。

        注意：每次运行仅解析同一股票的待处理条目，其他股票的条目
        将累积到相应股票再次运行时处理。
        """
        pending = [e for e in self.memory_log.get_pending_entries() if e["ticker"] == ticker]
        if not pending:
            return

        updates = []
        for entry in pending:
            raw, alpha, days = self._fetch_returns(ticker, entry["date"])
            if raw is None:
                continue  # 价格数据尚不可用，下次运行再试
            reflection = self.reflector.reflect_on_final_decision(
                final_decision=entry.get("decision", ""),
                raw_return=raw,
                alpha_return=alpha,
            )
            updates.append({
                "ticker": ticker,
                "trade_date": entry["date"],
                "raw_return": raw,
                "alpha_return": alpha,
                "holding_days": days,
                "reflection": reflection,
            })

        if updates:
            self.memory_log.batch_update_with_outcomes(updates)

    def propagate(self, company_name, trade_date):
        """运行A股智能分析图，对指定股票和日期执行全流程分析。

        当配置中启用 ``checkpoint_enabled`` 时，会使用每个股票的
        SqliteSaver 重新编译图，确保崩溃后可从上次成功节点恢复运行。
        """
        self.ticker = company_name

        # 在流水线运行前，解析该股票所有待处理的内存日志条目
        self._resolve_pending_entries(company_name)

        # 若用户启用了断点续传，则重新编译图
        if self.config.get("checkpoint_enabled"):
            self._checkpointer_ctx = get_checkpointer(
                self.config["data_cache_dir"], company_name
            )
            saver = self._checkpointer_ctx.__enter__()
            self.graph = self.workflow.compile(checkpointer=saver)

            step = checkpoint_step(
                self.config["data_cache_dir"], company_name, str(trade_date)
            )
            if step is not None:
                logger.info(
                    "从第 %d 步恢复 %s 在 %s 的分析", step, company_name, trade_date
                )
            else:
                logger.info("全新启动 %s 在 %s 的分析", company_name, trade_date)

        try:
            return self._run_graph(company_name, trade_date)
        finally:
            if self._checkpointer_ctx is not None:
                self._checkpointer_ctx.__exit__(None, None, None)
                self._checkpointer_ctx = None
                self.graph = self.workflow.compile()

    def _run_graph(self, company_name, trade_date):
        """执行图并输出结果状态到磁盘和内存日志。"""
        # 初始化状态，注入PM所需的历史记忆上下文
        past_context = self.memory_log.get_past_context(company_name)
        init_agent_state = self.propagator.create_initial_state(
            company_name, trade_date, past_context=past_context
        )
        args = self.propagator.get_graph_args()

        # 注入thread_id：同一股票+日期可恢复，不同日期则全新开始
        if self.config.get("checkpoint_enabled"):
            tid = thread_id(company_name, str(trade_date))
            args.setdefault("config", {}).setdefault("configurable", {})["thread_id"] = tid

        if self.debug:
            trace = []
            for chunk in self.graph.stream(init_agent_state, **args):
                if len(chunk["messages"]) == 0:
                    pass
                else:
                    trace.append(chunk)
            final_state = trace[-1]
        else:
            final_state = self.graph.invoke(init_agent_state, **args)

        # 保存当前状态供后续反思使用
        self.curr_state = final_state

        # 将状态记录到磁盘
        self._log_state(trade_date, final_state)

        # 存储决策，供该股票下次运行时进行延迟反思
        self.memory_log.store_decision(
            ticker=company_name,
            trade_date=trade_date,
            final_trade_decision=final_state["final_trade_decision"],
        )

        # 成功完成后清除断点，避免残留状态
        if self.config.get("checkpoint_enabled"):
            clear_checkpoint(
                self.config["data_cache_dir"], company_name, str(trade_date)
            )

        return final_state, self.process_signal(final_state["final_trade_decision"])

    def _log_state(self, trade_date, final_state):
        """将最终状态记录到JSON文件。"""
        self.log_states_dict[str(trade_date)] = {
            "company_of_interest": final_state["company_of_interest"],
            "trade_date": final_state["trade_date"],
            "market_report": final_state["market_report"],
            "sentiment_report": final_state["sentiment_report"],
            "news_report": final_state["news_report"],
            "fundamentals_report": final_state["fundamentals_report"],
            "policy_report": final_state.get("policy_report", ""),
            "hot_money_report": final_state.get("hot_money_report", ""),
            "lockup_report": final_state.get("lockup_report", ""),
            "investment_debate_state": {
                "bull_history": final_state["investment_debate_state"]["bull_history"],
                "bear_history": final_state["investment_debate_state"]["bear_history"],
                "history": final_state["investment_debate_state"]["history"],
                "current_response": final_state["investment_debate_state"][
                    "current_response"
                ],
                "judge_decision": final_state["investment_debate_state"][
                    "judge_decision"
                ],
            },
            "trader_investment_decision": final_state["trader_investment_plan"],
            "risk_debate_state": {
                "aggressive_history": final_state["risk_debate_state"]["aggressive_history"],
                "conservative_history": final_state["risk_debate_state"]["conservative_history"],
                "neutral_history": final_state["risk_debate_state"]["neutral_history"],
                "history": final_state["risk_debate_state"]["history"],
                "judge_decision": final_state["risk_debate_state"]["judge_decision"],
            },
            "investment_plan": final_state["investment_plan"],
            "final_trade_decision": final_state["final_trade_decision"],
        }

        # 保存到文件，拒绝可能逃逸结果目录的股票代码
        safe_ticker = safe_ticker_component(self.ticker)
        directory = Path(self.config["results_dir"]) / safe_ticker / "AShareAgentsStrategy_logs"
        directory.mkdir(parents=True, exist_ok=True)

        log_path = directory / f"full_states_log_{trade_date}.json"
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(self.log_states_dict[str(trade_date)], f, indent=4)

    def process_signal(self, full_signal):
        """从完整信号中提取核心交易决策评级。

        Args:
            full_signal: 投资组合经理输出的完整决策文本

        Returns:
            五级评级结果（Buy/Overweight/Hold/Underweight/Sell）
        """
        return self.signal_processor.process_signal(full_signal)
