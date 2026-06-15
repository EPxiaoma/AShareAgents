"""将本地知识文件分块、向量化并写入 Milvus。"""

import argparse
import logging
from dotenv import load_dotenv

load_dotenv()

from AShareAgents.config import DEFAULT_CONFIG

from .data_preparation import DataPreparationModule, SUPPORTED_KNOWLEDGE_TYPES
from .index_construction import IndexConstructionModule


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="导入 AShareAgents RAG 知识文档")
    parser.add_argument("path", help="知识文件或目录路径")
    parser.add_argument(
        "--knowledge-type",
        required=True,
        choices=sorted(SUPPORTED_KNOWLEDGE_TYPES),
        help="知识类型",
    )
    parser.add_argument("--parent-chunk-size", type=int, default=DEFAULT_CONFIG["rag_parent_chunk_size"])
    parser.add_argument("--parent-chunk-overlap", type=int, default=DEFAULT_CONFIG["rag_parent_chunk_overlap"])
    parser.add_argument("--child-chunk-size", type=int, default=DEFAULT_CONFIG["rag_child_chunk_size"])
    parser.add_argument("--child-chunk-overlap", type=int, default=DEFAULT_CONFIG["rag_child_chunk_overlap"])
    return parser


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    args = build_parser().parse_args()

    preparation = DataPreparationModule(
        data_path=args.path,
        knowledge_type=args.knowledge_type,
        parent_chunk_size=args.parent_chunk_size,
        parent_chunk_overlap=args.parent_chunk_overlap,
        child_chunk_size=args.child_chunk_size,
        child_chunk_overlap=args.child_chunk_overlap,
    )
    documents = preparation.load_documents()
    chunks = preparation.chunk_documents(documents)

    index = IndexConstructionModule(
        uri=DEFAULT_CONFIG["milvus_uri"],
        token=DEFAULT_CONFIG.get("milvus_token") or None,
        database=DEFAULT_CONFIG["milvus_database"],
        collection_name=DEFAULT_CONFIG["milvus_collection"],
        model_name=DEFAULT_CONFIG["rag_embedding_model"],
        dimension=DEFAULT_CONFIG["rag_embedding_dimension"],
        device=DEFAULT_CONFIG["rag_model_device"],
    )
    count = index.build_vector_index(chunks)
    print(f"导入完成: {len(documents)} 份文档，{count} 个知识块")


if __name__ == "__main__":
    main()
