"""向基本面与政策分析 Agent 暴露 RAG 检索工具。"""

import logging
from typing import Annotated

from langchain_core.tools import tool

from AShareAgents.datasource.config import get_config

from .service import get_rag_service

logger = logging.getLogger(__name__)


def _rag_disabled_message() -> str:
    return "RAG 当前未启用，请仅使用其他数据工具完成分析。"


@tool
def search_company_official_documents(
    query: Annotated[str, "要检索的公司事实、公告主题或经营问题"],
    ticker: Annotated[str, "A股代码（如 600519）"],
    curr_date: Annotated[str, "分析日期，格式 YYYY-MM-DD"],
    top_k: Annotated[int, "返回资料块数量，建议 3-8"] = 5,
) -> str:
    """检索分析日期前发布的公司公告、财报和投资者关系资料。"""
    config = get_config()
    if not config.get("rag_enabled", True):
        return _rag_disabled_message()
    if top_k == 5:
        top_k = int(config.get("rag_retrieval_top_k", top_k))
    try:
        return get_rag_service().company_context(
            query=query,
            trade_date=curr_date,
            ticker=ticker,
            top_k=max(1, min(top_k, 10)),
        )
    except Exception as exc:
        logger.warning("公司官方资料 RAG 检索失败: %s", exc)
        return f"公司官方资料 RAG 暂时不可用: {exc}"


@tool
def search_policy_industry_knowledge(
    query: Annotated[str, "要检索的政策主题、传导逻辑或行业知识"],
    curr_date: Annotated[str, "分析日期，格式 YYYY-MM-DD"],
    industry: Annotated[str, "行业名称；不确定时传空字符串"] = "",
    top_k: Annotated[int, "返回资料块数量，建议 3-8"] = 5,
) -> str:
    """检索分析日期前发布的政策文件与行业长期知识。"""
    config = get_config()
    if not config.get("rag_enabled", True):
        return _rag_disabled_message()
    if top_k == 5:
        top_k = int(config.get("rag_retrieval_top_k", top_k))
    try:
        return get_rag_service().policy_context(
            query=query,
            trade_date=curr_date,
            industry=industry,
            top_k=max(1, min(top_k, 10)),
        )
    except Exception as exc:
        logger.warning("政策与行业知识 RAG 检索失败: %s", exc)
        return f"政策与行业知识 RAG 暂时不可用: {exc}"
