"""使用 BGE 嵌入模型构建并查询 Milvus 向量索引。"""

import logging
from typing import Any, List, Optional

from langchain_core.documents import Document

from AShareAgents.storage.Milvus import MilvusKnowledgeStore

logger = logging.getLogger(__name__)


class BGEEmbeddings:
    """为中文检索封装 SentenceTransformer BGE 嵌入模型。"""

    QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关文章："

    def __init__(self, model_name: str, device: str = "cpu"):
        self.model_name = model_name
        self.device = device
        self._model = None

    @property
    def model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise RuntimeError(
                    "BGE 嵌入需要安装 sentence-transformers。"
                ) from exc
            self._model = SentenceTransformer(self.model_name, device=self.device)
        return self._model

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        vectors = self.model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return vectors.tolist()

    def embed_query(self, text: str) -> List[float]:
        vector = self.model.encode(
            f"{self.QUERY_INSTRUCTION}{text}",
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return vector.tolist()


class IndexConstructionModule:
    """负责 BGE 向量化、知识写入和两路召回的数据读取。"""

    def __init__(
        self,
        uri: str,
        collection_name: str,
        model_name: str = "BAAI/bge-small-zh-v1.5",
        dimension: int = 512,
        token: Optional[str] = None,
        database: str = "default",
        device: str = "cpu",
        embeddings: Any = None,
        store: Optional[MilvusKnowledgeStore] = None,
        **_: Any,
    ):
        self.model_name = model_name
        self.dimension = dimension
        self.device = device
        self._embeddings = embeddings
        self.store = store or MilvusKnowledgeStore(
            uri=uri,
            token=token,
            database=database,
            collection_name=collection_name,
            dimension=dimension,
        )

    @property
    def embeddings(self):
        """延迟加载 BGE，避免应用启动时下载模型。"""
        if self._embeddings is None:
            self._embeddings = BGEEmbeddings(self.model_name, self.device)
        return self._embeddings

    def build_vector_index(self, chunks: List[Document]) -> int:
        """向量化 200 字子块并写入 Milvus。"""
        if not chunks:
            raise ValueError("文档块列表不能为空")
        vectors = self.embeddings.embed_documents(
            [chunk.page_content for chunk in chunks]
        )
        self._validate_vectors(vectors)
        return self.store.upsert_documents(chunks, vectors, replace_parents=True)

    def add_documents(self, chunks: List[Document]) -> int:
        """新增或替换一批知识文档。"""
        return self.build_vector_index(chunks)

    def similarity_search(
        self,
        query: str,
        k: int = 20,
        knowledge_type: str = "",
        ticker: str = "",
        company_name: str = "",
        industry: str = "",
        publish_before_ts: Optional[int] = None,
    ) -> List[Document]:
        """使用 BGE 查询向量执行语义召回。"""
        query_vector = self.embeddings.embed_query(query)
        self._validate_vectors([query_vector])
        return self.store.search(
            query_vector=query_vector,
            limit=k,
            knowledge_type=knowledge_type,
            ticker=ticker,
            company_name=company_name,
            industry=industry,
            publish_before_ts=publish_before_ts,
        )

    def keyword_candidates(
        self,
        limit: int,
        knowledge_type: str = "",
        ticker: str = "",
        company_name: str = "",
        industry: str = "",
        publish_before_ts: Optional[int] = None,
    ) -> List[Document]:
        """读取符合领域和日期过滤的子块，供 BM25 排名。"""
        return self.store.query_documents(
            limit=limit,
            knowledge_type=knowledge_type,
            ticker=ticker,
            company_name=company_name,
            industry=industry,
            publish_before_ts=publish_before_ts,
        )

    def _validate_vectors(self, vectors: List[List[float]]) -> None:
        if vectors and len(vectors[0]) != self.dimension:
            raise RuntimeError(
                f"嵌入模型输出维度为 {len(vectors[0])}，"
                f"但 Milvus 集合配置维度为 {self.dimension}。"
            )
