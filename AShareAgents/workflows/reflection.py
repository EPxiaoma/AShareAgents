"""根据实际收益复盘历史交易决策。

生成的反思文本由交易记忆日志持久化，并作为后续分析的上下文。
"""

from typing import Any


class Reflector:
    """负责对交易决策进行复盘反思。"""

    def __init__(self, quick_thinking_llm: Any):
        """使用LLM实例初始化反思器。

        Args:
            quick_thinking_llm: 快速思考LLM实例
        """
        self.quick_thinking_llm = quick_thinking_llm
        self.log_reflection_prompt = self._get_log_reflection_prompt()

    def _get_log_reflection_prompt(self) -> str:
        """生成反思提示词（用于第二阶段日志条目的 reflect_on_final_decision）。

        输出2-4句简洁的纯文字，足够紧凑以便重新注入到未来的智能体提示词中，
        不会撑爆上下文窗口。
        """
        return (
            "你是一位交易分析师，正在复盘自己过去的决策，现已知晓实际结果。\n"
            "请用2-4句简洁的纯文字（不要使用列表、标题或 Markdown 格式）。\n\n"
            "按顺序涵盖以下内容：\n"
            "1. 方向性判断是否正确？（引用alpha数据）\n"
            "2. 投资逻辑的哪个部分成立或失败了？\n"
            "3. 一条可在下次类似分析中应用的具体经验教训。\n\n"
            "请具体且简洁。你的输出将被逐字存入决策日志，"
            "供未来的分析师重新阅读，因此每个字都应有其价值。"
        )

    def reflect_on_final_decision(
        self,
        final_decision: str,
        raw_return: float,
        alpha_return: float,
    ) -> str:
        """对最终交易决策进行单次反思调用（附带结果数据）。

        用于第二阶段延迟反思。最终交易决策已综合了所有分析师的洞察，
        因此无需单独的市场上下文。

        Args:
            final_decision: 最终交易决策文本
            raw_return: 原始收益率
            alpha_return: 相对沪深300的超额收益率

        Returns:
            反思文本字符串（2-4句简洁英文）
        """
        messages = [
            ("system", self.log_reflection_prompt),
            (
                "human",
                (
                    f"原始收益率: {raw_return:+.1%}\n"
                    f"相对沪深300的超额收益: {alpha_return:+.1%}\n\n"
                    f"最终决策:\n{final_decision}"
                ),
            ),
        ]
        return self.quick_thinking_llm.invoke(messages).content
