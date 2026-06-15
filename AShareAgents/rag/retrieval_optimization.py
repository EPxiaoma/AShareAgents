"""BM25 与 BGE 双路召回、RRF 融合和 CrossEncoder 重排序。"""

import logging
import re
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from langchain_core.documents import Document

from .data_preparation import COMPANY_OFFICIAL, POLICY_INDUSTRY
from .index_construction import IndexConstructionModule

logger = logging.getLogger(__name__)


class CrossEncoderReranker:
    """延迟加载 CrossEncoder，并对融合候选进行相关性重排。"""

    def __init__(self, model_name: str, device: str = "cpu"):
        self.model_name = model_name
        self.device = device
        self._model = None

    @property
    def model(self):
        if self._model is None:
            try:
                from sentence_transformers import CrossEncoder
            except ImportError as exc:
                raise RuntimeError(
                    "CrossEncoder 重排序需要安装 sentence-transformers。"
                ) from exc
            self._model = CrossEncoder(self.model_name, device=self.device)
        return self._model

    def score(self, query: str, documents: List[Document]) -> List[float]:
        pairs = [(query, document.page_content) for document in documents]
        scores = self.model.predict(pairs, show_progress_bar=False)
        return [float(score) for score in scores]


class RetrievalOptimizationModule:
    """封装混合召回、融合排序、精排和父块回溯。"""

    def __init__(
        self,
        index: IndexConstructionModule,
        reranker_model: str = "BAAI/bge-reranker-base",
        device: str = "cpu",
        vector_top_k: int = 20,
        bm25_top_k: int = 20,
        bm25_candidate_pool: int = 1000,
        rerank_top_n: int = 30,
        rrf_k: int = 60,
        reranker: Any = None,
    ):
        self.index = index
        self.vector_top_k = vector_top_k
        self.bm25_top_k = bm25_top_k
        self.bm25_candidate_pool = bm25_candidate_pool
        self.rerank_top_n = rerank_top_n
        self.rrf_k = rrf_k
        self.reranker = reranker or CrossEncoderReranker(
            reranker_model, device=device
        )

    def search_company_documents(
        self,
        query: str,
        trade_date: str,
        ticker: str = "",
        company_name: str = "",
        top_k: int = 5,
    ) -> List[Document]:
        """混合检索分析日期前发布的公司官方资料。"""
        return self._hybrid_search(
            query=query,
            top_k=top_k,
            knowledge_type=COMPANY_OFFICIAL,
            ticker=ticker,
            company_name=company_name,
            publish_before_ts=self._cutoff_timestamp(trade_date),
        )

    def search_policy_knowledge(
        self,
        query: str,
        trade_date: str,
        industry: str = "",
        top_k: int = 5,
    ) -> List[Document]:
        """混合检索分析日期前发布的政策与行业知识。"""
        return self._hybrid_search(
            query=query,
            top_k=top_k,
            knowledge_type=POLICY_INDUSTRY,
            industry=industry,
            publish_before_ts=self._cutoff_timestamp(trade_date),
        )

    def metadata_filtered_search(
        self,
        query: str,
        filters: Dict[str, Any],
        top_k: int = 5,
        trade_date: Optional[str] = None,
    ) -> List[Document]:
        """兼容通用元数据过滤入口。"""
        return self._hybrid_search(
            query=query,
            top_k=top_k,
            knowledge_type=str(filters.get("knowledge_type", "")),
            ticker=str(filters.get("ticker", "")),
            company_name=str(filters.get("company_name", "")),
            industry=str(filters.get("industry", "")),
            publish_before_ts=(
                self._cutoff_timestamp(trade_date) if trade_date else None
            ),
        )

    def _hybrid_search(
        self,
        query: str,
        top_k: int,
        knowledge_type: str = "",
        ticker: str = "",
        company_name: str = "",
        industry: str = "",
        publish_before_ts: Optional[int] = None,
    ) -> List[Document]:
        filters = {
            "knowledge_type": knowledge_type,
            "ticker": ticker,
            "company_name": company_name,
            "industry": industry,
            "publish_before_ts": publish_before_ts,
        }
        vector_docs = self.index.similarity_search(
            query=query,
            k=self.vector_top_k,
            **filters,
        )
        bm25_candidates = self.index.keyword_candidates(
            limit=self.bm25_candidate_pool,
            **filters,
        )
        bm25_docs = self._bm25_search(query, bm25_candidates, self.bm25_top_k)
        fused = self._rrf_fuse(vector_docs, bm25_docs)
        reranked = self._cross_encoder_rerank(query, fused[: self.rerank_top_n])
        return self._promote_parent_chunks(reranked, top_k)

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """提取英文词、数字及中文单字/二元词，避免依赖外部分词词典。"""
        normalized = text.lower()
        tokens = re.findall(r"[a-z0-9][a-z0-9_.%+-]*", normalized)
        for sequence in re.findall(r"[\u4e00-\u9fff]+", normalized):
            tokens.extend(sequence)
            tokens.extend(
                sequence[index : index + 2]
                for index in range(max(0, len(sequence) - 1))
            )
        return tokens

    def _bm25_search(
        self, query: str, candidates: List[Document], top_k: int
    ) -> List[Document]:
        if not candidates:
            return []
        try:
            from rank_bm25 import BM25Okapi
        except ImportError as exc:
            raise RuntimeError("BM25 检索需要安装 rank-bm25。") from exc

        corpus = [self._tokenize(document.page_content) for document in candidates]
        bm25 = BM25Okapi(corpus)
        scores = bm25.get_scores(self._tokenize(query))
        ranked = sorted(
            zip(candidates, scores),
            key=lambda item: float(item[1]),
            reverse=True,
        )
        results = []
        for document, score in ranked[:top_k]:
            if float(score) <= 0:
                continue
            document.metadata["bm25_score"] = float(score)
            results.append(document)
        return results

    def _rrf_fuse(
        self, vector_docs: List[Document], bm25_docs: List[Document]
    ) -> List[Document]:
        scores: Dict[str, float] = {}
        documents: Dict[str, Document] = {}
        for source, docs in (("vector", vector_docs), ("bm25", bm25_docs)):
            for rank, document in enumerate(docs, 1):
                chunk_id = self._document_key(document)
                documents[chunk_id] = document
                scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (
                    self.rrf_k + rank
                )
                document.metadata[f"{source}_rank"] = rank

        ordered = sorted(scores, key=scores.get, reverse=True)
        for chunk_id in ordered:
            documents[chunk_id].metadata["rrf_score"] = scores[chunk_id]
        return [documents[chunk_id] for chunk_id in ordered]

    def _cross_encoder_rerank(
        self, query: str, documents: List[Document]
    ) -> List[Document]:
        if not documents:
            return []
        scores = self.reranker.score(query, documents)
        for document, score in zip(documents, scores):
            document.metadata["rerank_score"] = score
        return sorted(
            documents,
            key=lambda document: document.metadata["rerank_score"],
            reverse=True,
        )

    @staticmethod
    def _promote_parent_chunks(
        documents: List[Document], top_k: int
    ) -> List[Document]:
        results = []
        seen_parent_ids = set()
        for document in documents:
            parent_id = document.metadata.get("parent_id") or document.page_content
            if parent_id in seen_parent_ids:
                continue
            seen_parent_ids.add(parent_id)
            metadata = dict(document.metadata)
            metadata["matched_child"] = document.page_content
            parent_content = metadata.pop("parent_content", "") or document.page_content
            results.append(Document(page_content=parent_content, metadata=metadata))
            if len(results) >= top_k:
                break
        return results

    @staticmethod
    def _document_key(document: Document) -> str:
        return str(
            document.metadata.get("chunk_id")
            or document.metadata.get("content_hash")
            or document.page_content
        )

    @staticmethod
    def _cutoff_timestamp(value: str) -> int:
        try:
            parsed = date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"trade_date 必须使用 YYYY-MM-DD 格式: {value}") from exc
        return int(
            datetime(
                parsed.year,
                parsed.month,
                parsed.day,
                23,
                59,
                59,
                tzinfo=timezone.utc,
            ).timestamp()
        )
