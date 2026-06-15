"""准备公司官方资料与政策行业知识，供 Milvus 建立向量索引。"""

import hashlib
import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from langchain_core.documents import Document
from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)

logger = logging.getLogger(__name__)

COMPANY_OFFICIAL = "company_official"
POLICY_INDUSTRY = "policy_industry"
SUPPORTED_KNOWLEDGE_TYPES = {COMPANY_OFFICIAL, POLICY_INDUSTRY}


class DataPreparationModule:
    """负责知识文档加载、校验和结构感知分块。"""

    def __init__(
        self,
        data_path: Optional[str] = None,
        knowledge_type: str = "",
        parent_chunk_size: int = 800,
        parent_chunk_overlap: int = 100,
        child_chunk_size: int = 200,
        child_chunk_overlap: int = 40,
    ):
        self.data_path = Path(data_path) if data_path else None
        self.knowledge_type = knowledge_type
        self.parent_chunk_size = parent_chunk_size
        self.parent_chunk_overlap = parent_chunk_overlap
        self.child_chunk_size = child_chunk_size
        self.child_chunk_overlap = child_chunk_overlap
        self.documents: List[Document] = []
        self.parent_chunks: List[Document] = []
        self.chunks: List[Document] = []

    def load_documents(self) -> List[Document]:
        """从 Markdown、纯文本、JSON 或 JSONL 文件加载知识文档。"""
        if not self.data_path:
            raise ValueError("未配置知识文件路径")
        if not self.data_path.exists():
            raise FileNotFoundError(f"知识文件路径不存在: {self.data_path}")

        files = (
            [self.data_path]
            if self.data_path.is_file()
            else sorted(
                path
                for path in self.data_path.rglob("*")
                if path.is_file()
                and path.suffix.lower() in {".md", ".txt", ".json", ".jsonl"}
                and not path.name.endswith(".metadata.json")
            )
        )
        documents: List[Document] = []
        for file_path in files:
            try:
                documents.extend(self._load_file(file_path))
            except Exception as exc:
                logger.warning("读取知识文件 %s 失败: %s", file_path, exc)

        self.documents = documents
        logger.info("已加载 %d 份 RAG 知识文档", len(documents))
        return documents

    def prepare_records(self, records: Iterable[Dict[str, Any]]) -> List[Document]:
        """将调用方提供的结构化记录转换为可分块文档。"""
        documents = []
        for index, record in enumerate(records):
            content = str(record.get("content", "")).strip()
            metadata = dict(record.get("metadata", {}))
            metadata.update(
                {
                    key: value
                    for key, value in record.items()
                    if key not in {"content", "metadata"}
                }
            )
            metadata.setdefault("source", f"record:{index}")
            documents.append(self._create_document(content, metadata))
        self.documents = documents
        return documents

    def chunk_documents(
        self, documents: Optional[List[Document]] = None
    ) -> List[Document]:
        """生成 800 字父块和用于检索的 200 字子块。"""
        source_documents = documents if documents is not None else self.documents
        if not source_documents:
            raise ValueError("请先加载或准备知识文档")

        header_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=[
                ("#", "header_1"),
                ("##", "header_2"),
                ("###", "header_3"),
            ],
            strip_headers=False,
        )
        parent_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.parent_chunk_size,
            chunk_overlap=self.parent_chunk_overlap,
            separators=["\n\n", "\n", "。", "；", "，", " "],
        )
        child_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.child_chunk_size,
            chunk_overlap=self.child_chunk_overlap,
            separators=["\n\n", "\n", "。", "；", "，", " "],
        )

        parent_chunks: List[Document] = []
        chunks: List[Document] = []
        for document in source_documents:
            sections = header_splitter.split_text(document.page_content)
            if not sections:
                sections = [Document(page_content=document.page_content)]
            parent_chunk_index = 0
            child_global_index = 0
            for section in sections:
                section_document = Document(
                    page_content=section.page_content,
                    metadata={**document.metadata, **section.metadata},
                )
                for parent_chunk in parent_splitter.split_documents(
                    [section_document]
                ):
                    parent_content = parent_chunk.page_content.strip()
                    parent_hash = hashlib.sha256(
                        parent_content.encode("utf-8")
                    ).hexdigest()
                    document_id = str(document.metadata["document_id"])
                    parent_key = (
                        f"{document_id}:{parent_chunk_index}:{parent_hash}"
                    )
                    parent_id = hashlib.sha256(
                        parent_key.encode("utf-8")
                    ).hexdigest()
                    parent_metadata = dict(parent_chunk.metadata)
                    parent_metadata.update(
                        {
                            "document_id": document_id,
                            "parent_id": parent_id,
                            "parent_chunk_index": parent_chunk_index,
                            "content_hash": parent_hash,
                            "doc_type": "parent_chunk",
                        }
                    )
                    parent_document = Document(
                        page_content=parent_content,
                        metadata=parent_metadata,
                    )
                    parent_chunks.append(parent_document)

                    child_index = 0
                    for child in child_splitter.split_documents([parent_document]):
                        child_content = child.page_content.strip()
                        content_hash = hashlib.sha256(
                            child_content.encode("utf-8")
                        ).hexdigest()
                        chunk_key = f"{parent_id}:{child_index}:{content_hash}"
                        metadata = dict(parent_metadata)
                        metadata.update(
                            {
                                "chunk_id": hashlib.sha256(
                                    chunk_key.encode("utf-8")
                                ).hexdigest(),
                                "chunk_index": child_global_index,
                                "child_index": child_index,
                                "content_hash": content_hash,
                                "parent_content": parent_content,
                                "doc_type": "child",
                            }
                        )
                        chunks.append(
                            Document(page_content=child_content, metadata=metadata)
                        )
                        child_index += 1
                        child_global_index += 1
                    parent_chunk_index += 1

        self.parent_chunks = parent_chunks
        self.chunks = chunks
        logger.info(
            "RAG 父子分块完成，共生成 %d 个父块和 %d 个子块",
            len(parent_chunks),
            len(chunks),
        )
        return chunks

    def get_statistics(self) -> Dict[str, Any]:
        """返回当前批次的文档与知识类型统计。"""
        type_counts: Dict[str, int] = {}
        for document in self.documents:
            knowledge_type = document.metadata.get("knowledge_type", "unknown")
            type_counts[knowledge_type] = type_counts.get(knowledge_type, 0) + 1
        return {
            "total_documents": len(self.documents),
            "total_parent_chunks": len(self.parent_chunks),
            "total_chunks": len(self.chunks),
            "knowledge_types": type_counts,
            "avg_chunk_size": (
                sum(len(chunk.page_content) for chunk in self.chunks)
                / len(self.chunks)
                if self.chunks
                else 0
            ),
        }

    def _load_file(self, file_path: Path) -> List[Document]:
        suffix = file_path.suffix.lower()
        if suffix in {".md", ".txt"}:
            content = file_path.read_text(encoding="utf-8")
            metadata = self._load_sidecar_metadata(file_path)
            metadata.setdefault("title", file_path.stem)
            metadata.setdefault("source", str(file_path))
            metadata.setdefault("knowledge_type", self.knowledge_type)
            return [self._create_document(content, metadata)]

        if suffix == ".jsonl":
            records = [
                json.loads(line)
                for line in file_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        else:
            payload = json.loads(file_path.read_text(encoding="utf-8"))
            records = payload if isinstance(payload, list) else [payload]

        documents = []
        for index, record in enumerate(records):
            if not isinstance(record, dict):
                raise ValueError("JSON 知识记录必须是对象")
            metadata = dict(record.get("metadata", {}))
            metadata.update(
                {
                    key: value
                    for key, value in record.items()
                    if key not in {"content", "metadata"}
                }
            )
            metadata.setdefault("source", f"{file_path}#{index}")
            metadata.setdefault("knowledge_type", self.knowledge_type)
            documents.append(
                self._create_document(str(record.get("content", "")), metadata)
            )
        return documents

    @staticmethod
    def _load_sidecar_metadata(file_path: Path) -> Dict[str, Any]:
        sidecar = file_path.with_name(f"{file_path.name}.metadata.json")
        if not sidecar.exists():
            return {}
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"元数据文件必须是 JSON 对象: {sidecar}")
        return payload

    def _create_document(self, content: str, metadata: Dict[str, Any]) -> Document:
        content = content.strip()
        if not content:
            raise ValueError("知识文档正文不能为空")

        normalized = self._normalize_metadata(metadata)
        source_key = str(normalized["source"])
        normalized["document_id"] = hashlib.sha256(
            source_key.encode("utf-8")
        ).hexdigest()
        normalized["doc_type"] = "parent"
        normalized["ingested_at"] = datetime.now(timezone.utc).isoformat(
            timespec="seconds"
        )
        return Document(page_content=content, metadata=normalized)

    def _normalize_metadata(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        result = {
            "title": str(metadata.get("title", "")).strip(),
            "knowledge_type": str(
                metadata.get("knowledge_type", self.knowledge_type)
            ).strip(),
            "ticker": str(metadata.get("ticker", "")).strip(),
            "company_name": str(metadata.get("company_name", "")).strip(),
            "industry": str(metadata.get("industry", "")).strip(),
            "document_type": str(metadata.get("document_type", "other")).strip(),
            "source": str(metadata.get("source", "")).strip(),
            "source_level": str(metadata.get("source_level", "official")).strip(),
            "publish_date": str(metadata.get("publish_date", "")).strip(),
            "effective_date": str(metadata.get("effective_date", "")).strip(),
            "report_period": str(metadata.get("report_period", "")).strip(),
            "event_type": str(metadata.get("event_type", "")).strip(),
        }
        self._validate_metadata(result)
        result["publish_ts"] = self._date_to_timestamp(result["publish_date"])
        result["effective_ts"] = (
            self._date_to_timestamp(result["effective_date"])
            if result["effective_date"]
            else 0
        )
        return result

    @staticmethod
    def _validate_metadata(metadata: Dict[str, Any]) -> None:
        knowledge_type = metadata["knowledge_type"]
        if knowledge_type not in SUPPORTED_KNOWLEDGE_TYPES:
            raise ValueError(
                "knowledge_type 必须是 company_official 或 policy_industry"
            )
        if not metadata["title"]:
            raise ValueError("知识文档必须提供 title")
        if not metadata["source"]:
            raise ValueError("知识文档必须提供 source")
        if not metadata["publish_date"]:
            raise ValueError("知识文档必须提供 publish_date，防止回测未来数据泄漏")
        DataPreparationModule._parse_date(metadata["publish_date"])
        if metadata["effective_date"]:
            DataPreparationModule._parse_date(metadata["effective_date"])
        if knowledge_type == COMPANY_OFFICIAL and not (
            metadata["ticker"] or metadata["company_name"]
        ):
            raise ValueError("公司官方资料必须提供 ticker 或 company_name")
        if knowledge_type == POLICY_INDUSTRY and not metadata["industry"]:
            raise ValueError("政策与行业知识必须提供 industry")

    @staticmethod
    def _parse_date(value: str) -> date:
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"日期必须使用 YYYY-MM-DD 格式: {value}") from exc

    @staticmethod
    def _date_to_timestamp(value: str) -> int:
        parsed = DataPreparationModule._parse_date(value)
        return int(datetime(parsed.year, parsed.month, parsed.day, tzinfo=timezone.utc).timestamp())
