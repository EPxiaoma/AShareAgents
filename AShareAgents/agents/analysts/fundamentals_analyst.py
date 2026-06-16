"""基本面分析师模块，提供基于财务数据（利润表、资产负债表、现金流量表）的 A 股公司基本面分析功能，支持行业横向对比和估值分析。"""

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from AShareAgents.tools.agent_helpers import (
    build_instrument_context,
    get_language_instruction,
)
from AShareAgents.tools.tool_registry import (
    get_balance_sheet,
    get_cashflow,
    get_fundamentals,
    get_income_statement,
    get_industry_comparison,
    get_insider_transactions,
    get_profit_forecast,
    search_company_official_documents,
)
from AShareAgents.datasource.config import get_config


def create_fundamentals_analyst(llm):
    def fundamentals_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = [
            get_fundamentals,
            get_balance_sheet,
            get_cashflow,
            get_income_statement,
            get_profit_forecast,
            get_industry_comparison,
            search_company_official_documents,
        ]

        system_message = (
            "你是一位专注于 A 股市场的基本面分析师。你的任务是全面分析目标公司的基本面信息，为投资决策提供扎实的数据支撑。"
            "\n\n⚠️ A 股基本面分析要点："
            "\n- **财务准则**：A 股上市公司采用中国会计准则（CAS），在收入确认、资产减值等方面与 IFRS 存在差异，分析时需注意口径。"
            "\n- **估值参照系**：A 股整体 PE 中位数偏高（30-50x 为常态），不能照搬美股 15-25x 标准；应对标同行业 A 股公司横向比较。"
            "\n- **核心指标**：重点关注营收增长率、归母净利润、扣非净利润（剔除非经常性损益）、ROE、毛利率、经营性现金流与净利润的匹配度。"
            "\n- **财报披露节奏**：一季报（4月底前）、半年报（8月底前）、三季报（10月底前）、年报（次年4月底前）。分析时注意数据的时效性。"
            "\n- **特殊风险关注**：商誉减值（并购后遗症）、股权质押比例、大股东减持计划、关联交易规模。"
            "\n\n请使用以下工具获取数据："
            "\n- `get_fundamentals`：获取公司综合基本面信息（PE/PB/总市值/季报财务快照/一致预期EPS/前向PE/PEG等）"
            "\n- `get_profit_forecast`：获取机构一致预期EPS详情（覆盖机构数、EPS区间、前向PE、PEG、PE消化时间）"
            "\n- `get_balance_sheet`：资产负债表详细数据"
            "\n- `get_cashflow`：现金流量表详细数据"
            "\n- `get_income_statement`：利润表详细数据"
            "\n- `get_industry_comparison(ticker, curr_date)`：获取全行业横向对比（90个行业涨跌幅/成交额/净流入排名，用于估值对标和行业定位）"
            "\n- `search_company_official_documents(query, ticker, curr_date)`：检索分析日之前发布的公司公告、财报和投资者关系资料"
            "\n\n在形成结论前，应调用 `search_company_official_documents` 补充公司官方资料。"
            "只使用发布日期不晚于当前分析日期的结果，并在引用时注明资料标题、发布日期和来源；"
            "若工具不可用或未命中，不得虚构官方资料。"
            "\n\n撰写详尽的基本面研究报告，给出具体数据支撑的分析结论（仅供研究参考，不构成投资建议）。报告末尾附 Markdown 表格汇总关键财务指标和估值水平。"
            "\n\n📋 必采清单 — 以下数据点必须出现在报告中，无法获取时标注 [数据缺失: xxx]："
            "\n1. PE（TTM）、PB、总市值"
            "\n2. 营收同比增长率"
            "\n3. 归母净利润及同比增长率"
            "\n4. ROE"
            "\n5. 资产负债率"
            "\n6. 经营性现金流与净利润比值"
            "\n7. 机构一致预期 EPS（调用 get_profit_forecast 获取）"
            + get_language_instruction()
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你是一个乐于助人的 AI 助手，与其他助手协作完成任务。"
                    " 使用提供的工具推进问题的解答。"
                    " 如果你无法完全回答，没关系；其他拥有不同工具的助手"
                    " 会在你停下的地方继续。尽你所能推动进展。"
                    " 如果你或其他助手得到了最终交易建议：**买入/持有/卖出** 或可交付成果，"
                    " 请在回复前加上 最终交易建议：**买入/持有/卖出**，以便团队知道可以停止。"
                    " 你可以使用以下工具：{tool_names}。\n{system_message}"
                    "供你参考，当前日期是 {current_date}。{instrument_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        chain = prompt | llm.bind_tools(tools)

        result = chain.invoke(state["messages"])

        report = ""

        if len(result.tool_calls) == 0:
            report = result.content

        return {
            "messages": [result],
            "fundamentals_report": report,
        }

    return fundamentals_analyst_node
