"""封装知识文档在 Milvus 中的建库、写入和检索操作。"""

import json
import logging
from typing import Any, Iterable, List, Optional

from langchain_core.documents import Document

from AShareAgents.models.milvus_schema import (
    DEFAULT_COLLECTION_NAME,
    build_collection_schema,
    build_index_params,
)

logger = logging.getLogger(__name__)


class MilvusKnowledgeStore:
    """面向 AShareAgents RAG 的 Milvus 存储适配器。"""

    def __init__(
        self,
        uri: str,
        dimension: int,
        collection_name: str = DEFAULT_COLLECTION_NAME,
        token: Optional[str] = None,
        database: str = "default",
        client: Any = None,
    ):
        self.uri = uri
        self.dimension = dimension
        self.collection_name = collection_name
        self.token = token
        self.database = database
        self._client = client

    @property
    def client(self):
        """延迟创建客户端，避免未启用 RAG 时加载可选依赖。"""
        if self._client is None:
            try:
                from pymilvus import MilvusClient
            except ImportError as exc:
                raise RuntimeError(
                    "Milvus RAG 需要安装 pymilvus，请重新安装项目依赖。"
                ) from exc

            kwargs = {"uri": self.uri, "db_name": self.database}
            if self.token:
                kwargs["token"] = self.token
            self._client = MilvusClient(**kwargs)
        return self._client

    def ensure_collection(self) -> None:
        """确保集合和向量索引存在，并校验向量维度。"""
        if self.client.has_collection(collection_name=self.collection_name):
            description = self.client.describe_collection(
                collection_name=self.collection_name
            )
            self._validate_dimension(description)
            self.client.load_collection(collection_name=self.collection_name)
            return

        schema = build_collection_schema(self.client, self.dimension)
        index_params = build_index_params(self.client)
        self.client.create_collection(
            collection_name=self.collection_name,
            schema=schema,
            index_params=index_params,
            consistency_level="Strong",
        )
        logger.info("已创建 Milvus RAG 集合: %s", self.collection_name)

    def upsert_documents(
        self,
        documents: List[Document],
        vectors: List[List[float]],
        replace_parents: bool = True,
    ) -> int:
        """写入文档块；同一父文档重新导入时先清除旧块。"""
        if len(documents) != len(vectors):
            raise ValueError("文档数量与向量数量必须一致")
        if not documents:
            return 0

        self.ensure_collection()
        if replace_parents:
            document_ids = {
                str(doc.metadata.get("document_id", ""))
                for doc in documents
                if doc.metadata.get("document_id")
            }
            self._delete_documents(document_ids)

        rows = [
            self._document_to_row(document, vector)
            for document, vector in zip(documents, vectors)
        ]
        self.client.upsert(collection_name=self.collection_name, data=rows)
        logger.info("已向 Milvus 写入 %d 个知识块", len(rows))
        return len(rows)

    def search(
        self,
        query_vector: List[float],
        limit: int = 5,
        knowledge_type: str = "",
        ticker: str = "",
        company_name: str = "",
        industry: str = "",
        publish_before_ts: Optional[int] = None,
    ) -> List[Document]:
        """执行向量检索，并在服务端应用知识类型与日期过滤。"""
        self.ensure_collection()
        filter_expression = self._build_filter(
            knowledge_type=knowledge_type,
            ticker=ticker,
            company_name=company_name,
            industry=industry,
            publish_before_ts=publish_before_ts,
        )
        output_fields = [
            "content",
            "title",
            "knowledge_type",
            "ticker",
            "company_name",
            "industry",
            "document_type",
            "source",
            "source_level",
            "publish_date",
            "effective_date",
            "report_period",
            "event_type",
            "document_id",
            "parent_id",
            "parent_content",
            "parent_chunk_index",
            "chunk_index",
            "child_index",
            "content_hash",
        ]
        results = self.client.search(
            collection_name=self.collection_name,
            data=[query_vector],
            anns_field="vector",
            filter=filter_expression,
            limit=limit,
            output_fields=output_fields,
            search_params={"metric_type": "COSINE", "params": {}},
        )
        hits = results[0] if results else []
        return [self._hit_to_document(hit) for hit in hits]

    def query_documents(
        self,
        limit: int = 1000,
        knowledge_type: str = "",
        ticker: str = "",
        company_name: str = "",
        industry: str = "",
        publish_before_ts: Optional[int] = None,
    ) -> List[Document]:
        """读取符合过滤条件的子块，供 BM25 关键词召回。"""
        self.ensure_collection()
        filter_expression = self._build_filter(
            knowledge_type=knowledge_type,
            ticker=ticker,
            company_name=company_name,
            industry=industry,
            publish_before_ts=publish_before_ts,
        )
        rows = self.client.query(
            collection_name=self.collection_name,
            filter=filter_expression,
            limit=limit,
            output_fields=[
                "id",
                "content",
                "title",
                "knowledge_type",
                "ticker",
                "company_name",
                "industry",
                "document_type",
                "source",
                "source_level",
                "publish_date",
                "effective_date",
                "report_period",
                "event_type",
                "document_id",
                "parent_id",
                "parent_content",
                "parent_chunk_index",
                "chunk_index",
                "child_index",
                "content_hash",
            ],
        )
        return [self._row_to_document(row) for row in rows]

    def _delete_documents(self, document_ids: Iterable[str]) -> None:
        values = sorted({document_id for document_id in document_ids if document_id})
        if not values:
            return
        encoded = ", ".join(self._quote(value) for value in values)
        self.client.delete(
            collection_name=self.collection_name,
            filter=f"document_id in [{encoded}]",
        )

    def _validate_dimension(self, description: Any) -> None:
        fields = description.get("fields", []) if isinstance(description, dict) else []
        field_names = {
            field.get("name", field.get("field_name")) for field in fields
        }
        required_fields = {
            "vector",
            "document_id",
            "parent_id",
            "parent_content",
            "parent_chunk_index",
            "child_index",
        }
        missing_fields = sorted(required_fields - field_names)
        if missing_fields:
            raise RuntimeError(
                f"现有集合 {self.collection_name} 不兼容父子检索，"
                f"缺少字段: {', '.join(missing_fields)}。请使用新的集合名。"
            )
        vector_field = next(
            (
                field
                for field in fields
                if field.get("name", field.get("field_name")) == "vector"
            ),
            None,
        )
        if not vector_field:
            raise RuntimeError(
                f"现有集合 {self.collection_name} 缺少 vector 字段"
            )
        params = vector_field.get("params", vector_field.get("type_params", {}))
        existing_dimension = int(params.get("dim", 0))
        if existing_dimension and existing_dimension != self.dimension:
            raise RuntimeError(
                f"Milvus 集合向量维度为 {existing_dimension}，"
                f"当前嵌入配置为 {self.dimension}。请更换集合名或统一维度。"
            )

    def _build_filter(
        self,
        knowledge_type: str,
        ticker: str,
        company_name: str,
        industry: str,
        publish_before_ts: Optional[int],
    ) -> str:
        clauses = []
        if knowledge_type:
            clauses.append(f"knowledge_type == {self._quote(knowledge_type)}")
        if ticker:
            clauses.append(f"ticker == {self._quote(ticker)}")
        elif company_name:
            clauses.append(f"company_name == {self._quote(company_name)}")
        if industry:
            clauses.append(f"industry == {self._quote(industry)}")
        if publish_before_ts is not None:
            clauses.append(f"publish_ts <= {int(publish_before_ts)}")
        return " and ".join(clauses)

    @staticmethod
    def _quote(value: str) -> str:
        return json.dumps(str(value), ensure_ascii=False)

    @staticmethod
    def _document_to_row(document: Document, vector: List[float]) -> dict:
        metadata = document.metadata
        return {
            "id": str(metadata["chunk_id"])[:64],
            "vector": vector,
            "content": document.page_content[:65535],
            "title": str(metadata.get("title", ""))[:1024],
            "knowledge_type": str(metadata.get("knowledge_type", ""))[:32],
            "ticker": str(metadata.get("ticker", ""))[:32],
            "company_name": str(metadata.get("company_name", ""))[:256],
            "industry": str(metadata.get("industry", ""))[:512],
            "document_type": str(metadata.get("document_type", ""))[:64],
            "source": str(metadata.get("source", ""))[:2048],
            "source_level": str(metadata.get("source_level", ""))[:32],
            "publish_date": str(metadata.get("publish_date", ""))[:10],
            "publish_ts": int(metadata.get("publish_ts", 0)),
            "effective_date": str(metadata.get("effective_date", ""))[:10],
            "effective_ts": int(metadata.get("effective_ts", 0)),
            "report_period": str(metadata.get("report_period", ""))[:32],
            "event_type": str(metadata.get("event_type", ""))[:64],
            "document_id": str(metadata.get("document_id", ""))[:64],
            "parent_id": str(metadata.get("parent_id", ""))[:64],
            "parent_content": str(metadata.get("parent_content", ""))[:65535],
            "parent_chunk_index": int(metadata.get("parent_chunk_index", 0)),
            "chunk_index": int(metadata.get("chunk_index", 0)),
            "child_index": int(metadata.get("child_index", 0)),
            "content_hash": str(metadata.get("content_hash", ""))[:64],
            "ingested_at": str(metadata.get("ingested_at", ""))[:32],
        }

    @staticmethod
    def _hit_to_document(hit: Any) -> Document:
        entity = hit.get("entity", {}) if isinstance(hit, dict) else {}
        metadata = {key: value for key, value in entity.items() if key != "content"}
        if isinstance(hit, dict):
            metadata["score"] = hit.get("distance", hit.get("score", 0.0))
            metadata["chunk_id"] = hit.get("id", "")
        return Document(
            page_content=str(entity.get("content", "")),
            metadata=metadata,
        )

    @staticmethod
    def _row_to_document(row: Any) -> Document:
        metadata = {key: value for key, value in row.items() if key != "content"}
        metadata["chunk_id"] = row.get("id", "")
        return Document(
            page_content=str(row.get("content", "")),
            metadata=metadata,
        )
