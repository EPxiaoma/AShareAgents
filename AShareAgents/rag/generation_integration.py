"""将检索结果整理为可安全注入 Agent 提示词的上下文。"""

from typing import List

from langchain_core.documents import Document


class GenerationIntegrationModule:
    """负责控制 RAG 上下文长度并保留来源信息。"""

    def __init__(self, max_context_chars: int = 12000):
        self.max_context_chars = max_context_chars

    def build_context(self, documents: List[Document]) -> str:
        """格式化检索结果；超过预算时截断末尾文档。"""
        if not documents:
            return "未检索到符合日期和元数据条件的知识文档。"

        parts = []
        used = 0
        for index, document in enumerate(documents, 1):
            metadata = document.metadata
            header = (
                f"【资料 {index}】{metadata.get('title', '未命名资料')}\n"
                f"类型: {metadata.get('document_type', '未知')} | "
                f"发布日期: {metadata.get('publish_date', '未知')} | "
                f"来源级别: {metadata.get('source_level', '未知')}\n"
                f"来源: {metadata.get('source', '未知')}\n"
            )
            if metadata.get("industry"):
                header += f"行业: {metadata['industry']}\n"
            if metadata.get("ticker") or metadata.get("company_name"):
                header += (
                    f"公司: {metadata.get('company_name', '')} "
                    f"{metadata.get('ticker', '')}\n"
                )
            block = f"{header}{document.page_content.strip()}"
            remaining = self.max_context_chars - used
            if remaining <= 0:
                break
            if len(block) > remaining:
                block = block[:remaining].rstrip() + "\n[上下文已截断]"
            parts.append(block)
            used += len(block)

        return "\n\n---\n\n".join(parts)

    def generate_basic_answer(self, query: str, context_docs: List[Document]) -> str:
        """兼容参考接口：返回供现有 Agent 使用的检索上下文。"""
        del query
        return self.build_context(context_docs)
