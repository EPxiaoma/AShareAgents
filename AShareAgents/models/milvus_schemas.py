"""定义 RAG 知识库使用的 Milvus 集合结构。"""

from typing import Any


DEFAULT_COLLECTION_NAME = "ashareagents_knowledge_bge"


def build_collection_schema(client: Any, dimension: int):
    """构建公司资料与政策知识共用的集合结构。"""
    from pymilvus import DataType

    schema = client.create_schema(auto_id=False, enable_dynamic_field=False)
    schema.add_field(
        field_name="id",
        datatype=DataType.VARCHAR,
        is_primary=True,
        max_length=64,
    )
    schema.add_field(
        field_name="vector",
        datatype=DataType.FLOAT_VECTOR,
        dim=dimension,
    )
    schema.add_field(field_name="content", datatype=DataType.VARCHAR, max_length=65535)
    schema.add_field(field_name="title", datatype=DataType.VARCHAR, max_length=1024)
    schema.add_field(field_name="knowledge_type", datatype=DataType.VARCHAR, max_length=32)
    schema.add_field(field_name="ticker", datatype=DataType.VARCHAR, max_length=32)
    schema.add_field(field_name="company_name", datatype=DataType.VARCHAR, max_length=256)
    schema.add_field(field_name="industry", datatype=DataType.VARCHAR, max_length=512)
    schema.add_field(field_name="document_type", datatype=DataType.VARCHAR, max_length=64)
    schema.add_field(field_name="source", datatype=DataType.VARCHAR, max_length=2048)
    schema.add_field(field_name="source_level", datatype=DataType.VARCHAR, max_length=32)
    schema.add_field(field_name="publish_date", datatype=DataType.VARCHAR, max_length=10)
    schema.add_field(field_name="publish_ts", datatype=DataType.INT64)
    schema.add_field(field_name="effective_date", datatype=DataType.VARCHAR, max_length=10)
    schema.add_field(field_name="effective_ts", datatype=DataType.INT64)
    schema.add_field(field_name="report_period", datatype=DataType.VARCHAR, max_length=32)
    schema.add_field(field_name="event_type", datatype=DataType.VARCHAR, max_length=64)
    schema.add_field(field_name="document_id", datatype=DataType.VARCHAR, max_length=64)
    schema.add_field(field_name="parent_id", datatype=DataType.VARCHAR, max_length=64)
    schema.add_field(field_name="parent_content", datatype=DataType.VARCHAR, max_length=65535)
    schema.add_field(field_name="parent_chunk_index", datatype=DataType.INT64)
    schema.add_field(field_name="chunk_index", datatype=DataType.INT64)
    schema.add_field(field_name="child_index", datatype=DataType.INT64)
    schema.add_field(field_name="content_hash", datatype=DataType.VARCHAR, max_length=64)
    schema.add_field(field_name="ingested_at", datatype=DataType.VARCHAR, max_length=32)
    return schema


def build_index_params(client: Any):
    """创建适用于归一化文本向量的余弦索引参数。"""
    index_params = client.prepare_index_params()
    index_params.add_index(
        field_name="vector",
        index_name="vector_cosine_index",
        index_type="AUTOINDEX",
        metric_type="COSINE",
    )
    return index_params
