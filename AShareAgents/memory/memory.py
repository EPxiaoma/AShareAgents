"""带结构化存储和可读 Markdown 镜像的交易决策记忆。"""

from __future__ import annotations

import json
import math
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional, Protocol

from AShareAgents.tools.rating import parse_rating


class MemoryVectorIndex(Protocol):
    """交易记忆条目的可选语义索引适配器。"""

    def upsert_entries(self, entries: List[dict]) -> None:
        """存储或刷新已解析记忆条目的语义向量。"""

    def search(self, query: str, top_k: int = 5) -> List[dict]:
        """返回按语义相似度排序的记忆字典。"""


class LocalMemoryVectorIndex:
    """面向本地开发的无额外依赖语义旁路索引。

    项目后续可以将该协议替换为 Milvus/BGE。此本地索引保持相同的记忆边界，
    并使用余弦相似度对简单 token 向量进行排序。
    """

    _TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]")

    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def upsert_entries(self, entries: List[dict]) -> None:
        rows = []
        for entry in entries:
            if entry.get("pending"):
                continue
            text = self._entry_text(entry)
            rows.append(
                (
                    self._entry_id(entry),
                    entry.get("ticker", ""),
                    entry.get("date", ""),
                    text,
                    json.dumps(self._vectorize(text), ensure_ascii=False, sort_keys=True),
                    self._now(),
                )
            )
        if not rows:
            return
        with sqlite3.connect(self.path) as conn:
            conn.executemany(
                """
                INSERT INTO memory_vectors(entry_id, ticker, trade_date, text, vector, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(entry_id) DO UPDATE SET
                    ticker = excluded.ticker,
                    trade_date = excluded.trade_date,
                    text = excluded.text,
                    vector = excluded.vector,
                    updated_at = excluded.updated_at
                """,
                rows,
            )

    def search(self, query: str, top_k: int = 5) -> List[dict]:
        query_vector = self._vectorize(query)
        if not query_vector:
            return []
        with sqlite3.connect(self.path) as conn:
            rows = conn.execute(
                "SELECT entry_id, ticker, trade_date, text, vector FROM memory_vectors"
            ).fetchall()
        scored = []
        for entry_id, ticker, trade_date, text, vector_json in rows:
            score = self._cosine(query_vector, json.loads(vector_json))
            if score > 0:
                scored.append(
                    {
                        "entry_id": entry_id,
                        "ticker": ticker,
                        "date": trade_date,
                        "text": text,
                        "score": score,
                    }
                )
        scored.sort(key=lambda row: row["score"], reverse=True)
        return scored[:top_k]

    def _ensure_schema(self) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_vectors (
                    entry_id TEXT PRIMARY KEY,
                    ticker TEXT NOT NULL,
                    trade_date TEXT NOT NULL,
                    text TEXT NOT NULL,
                    vector TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    @classmethod
    def _vectorize(cls, text: str) -> dict[str, float]:
        counts: dict[str, float] = {}
        for token in cls._TOKEN_RE.findall(text.lower()):
            counts[token] = counts.get(token, 0.0) + 1.0
        return counts

    @staticmethod
    def _cosine(left: dict[str, float], right: dict[str, float]) -> float:
        common = set(left).intersection(right)
        dot = sum(left[k] * right[k] for k in common)
        if dot == 0:
            return 0.0
        left_norm = math.sqrt(sum(v * v for v in left.values()))
        right_norm = math.sqrt(sum(v * v for v in right.values()))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return dot / (left_norm * right_norm)

    @staticmethod
    def _entry_id(entry: dict) -> str:
        return f"{entry.get('date', '')}:{entry.get('ticker', '')}"

    @staticmethod
    def _entry_text(entry: dict) -> str:
        return "\n".join(
            part
            for part in [
                entry.get("ticker", ""),
                entry.get("rating", ""),
                entry.get("decision", ""),
                entry.get("reflection", ""),
            ]
            if part
        )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()



class MilvusMemoryVectorIndex:
    """面向已解析交易记忆条目的 Milvus + BGE 语义索引。"""

    def __init__(
        self,
        uri: str,
        collection_name: str,
        dimension: int,
        model_name: str = "BAAI/bge-small-zh-v1.5",
        token: Optional[str] = None,
        database: str = "default",
        device: str = "cpu",
        embeddings: Any = None,
        client: Any = None,
    ):
        self.uri = uri
        self.collection_name = collection_name
        self.dimension = dimension
        self.model_name = model_name
        self.token = token
        self.database = database
        self.device = device
        self._embeddings = embeddings
        self._client = client

    @property
    def embeddings(self):
        if self._embeddings is None:
            from AShareAgents.rag.index_construction import BGEEmbeddings

            self._embeddings = BGEEmbeddings(self.model_name, self.device)
        return self._embeddings

    @property
    def client(self):
        if self._client is None:
            try:
                from pymilvus import MilvusClient
            except ImportError as exc:
                raise RuntimeError("Milvus memory vector index requires pymilvus.") from exc
            kwargs = {"uri": self.uri, "db_name": self.database}
            if self.token:
                kwargs["token"] = self.token
            self._client = MilvusClient(**kwargs)
        return self._client

    def upsert_entries(self, entries: List[dict]) -> None:
        resolved = [entry for entry in entries if not entry.get("pending")]
        if not resolved:
            return
        texts = [self._entry_text(entry) for entry in resolved]
        vectors = self.embeddings.embed_documents(texts)
        self._validate_vectors(vectors)
        self.ensure_collection()
        rows = [
            self._entry_to_row(entry, text, vector)
            for entry, text, vector in zip(resolved, texts, vectors)
        ]
        self.client.upsert(collection_name=self.collection_name, data=rows)

    def search(self, query: str, top_k: int = 5) -> List[dict]:
        query_vector = self.embeddings.embed_query(query)
        self._validate_vectors([query_vector])
        self.ensure_collection()
        output_fields = [
            "content", "ticker", "trade_date", "rating", "raw", "alpha",
            "holding", "decision", "reflection", "updated_at",
        ]
        results = self.client.search(
            collection_name=self.collection_name,
            data=[query_vector],
            anns_field="vector",
            filter="",
            limit=top_k,
            output_fields=output_fields,
            search_params={"metric_type": "COSINE", "params": {}},
        )
        hits = results[0] if results else []
        return [self._hit_to_result(hit) for hit in hits]

    def ensure_collection(self) -> None:
        if self.client.has_collection(collection_name=self.collection_name):
            description = self.client.describe_collection(collection_name=self.collection_name)
            self._validate_collection_dimension(description)
            self.client.load_collection(collection_name=self.collection_name)
            return

        try:
            from pymilvus import DataType
        except ImportError as exc:
            raise RuntimeError("Milvus memory vector index requires pymilvus.") from exc

        schema = self.client.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field(field_name="id", datatype=DataType.VARCHAR, is_primary=True, max_length=64)
        schema.add_field(field_name="vector", datatype=DataType.FLOAT_VECTOR, dim=self.dimension)
        schema.add_field(field_name="content", datatype=DataType.VARCHAR, max_length=65535)
        schema.add_field(field_name="ticker", datatype=DataType.VARCHAR, max_length=32)
        schema.add_field(field_name="trade_date", datatype=DataType.VARCHAR, max_length=10)
        schema.add_field(field_name="rating", datatype=DataType.VARCHAR, max_length=32)
        schema.add_field(field_name="raw", datatype=DataType.VARCHAR, max_length=32)
        schema.add_field(field_name="alpha", datatype=DataType.VARCHAR, max_length=32)
        schema.add_field(field_name="holding", datatype=DataType.VARCHAR, max_length=32)
        schema.add_field(field_name="decision", datatype=DataType.VARCHAR, max_length=65535)
        schema.add_field(field_name="reflection", datatype=DataType.VARCHAR, max_length=65535)
        schema.add_field(field_name="updated_at", datatype=DataType.VARCHAR, max_length=32)

        index_params = self.client.prepare_index_params()
        index_params.add_index(
            field_name="vector",
            index_name="memory_vector_cosine_index",
            index_type="AUTOINDEX",
            metric_type="COSINE",
        )
        self.client.create_collection(
            collection_name=self.collection_name,
            schema=schema,
            index_params=index_params,
            consistency_level="Strong",
        )
        self.client.load_collection(collection_name=self.collection_name)

    def _entry_to_row(self, entry: dict, text: str, vector: List[float]) -> dict:
        return {
            "id": self._entry_id(entry),
            "vector": vector,
            "content": text[:65535],
            "ticker": str(entry.get("ticker", ""))[:32],
            "trade_date": str(entry.get("date", ""))[:10],
            "rating": str(entry.get("rating", ""))[:32],
            "raw": str(entry.get("raw", ""))[:32],
            "alpha": str(entry.get("alpha", ""))[:32],
            "holding": str(entry.get("holding", ""))[:32],
            "decision": str(entry.get("decision", ""))[:65535],
            "reflection": str(entry.get("reflection", ""))[:65535],
            "updated_at": self._now(),
        }

    def _hit_to_result(self, hit: Any) -> dict:
        entity = hit.get("entity", {}) if isinstance(hit, dict) else {}
        return {
            "entry_id": hit.get("id", entity.get("id", "")) if isinstance(hit, dict) else "",
            "ticker": entity.get("ticker", ""),
            "date": entity.get("trade_date", ""),
            "rating": entity.get("rating", ""),
            "raw": entity.get("raw", ""),
            "alpha": entity.get("alpha", ""),
            "holding": entity.get("holding", ""),
            "decision": entity.get("decision", ""),
            "reflection": entity.get("reflection", ""),
            "text": entity.get("content", ""),
            "score": hit.get("distance", hit.get("score", 0.0)) if isinstance(hit, dict) else 0.0,
        }

    def _validate_vectors(self, vectors: List[List[float]]) -> None:
        if vectors and len(vectors[0]) != self.dimension:
            raise RuntimeError(
                f"BGE embedding dimension {len(vectors[0])} does not match Milvus dimension {self.dimension}."
            )

    def _validate_collection_dimension(self, description: Any) -> None:
        fields = description.get("fields", []) if isinstance(description, dict) else []
        vector_field = next(
            (field for field in fields if field.get("name", field.get("field_name")) == "vector"),
            None,
        )
        if not vector_field:
            raise RuntimeError(f"Milvus collection {self.collection_name} is missing vector field.")
        params = vector_field.get("params", vector_field.get("type_params", {}))
        existing_dimension = int(params.get("dim", 0))
        if existing_dimension and existing_dimension != self.dimension:
            raise RuntimeError(
                f"Milvus collection {self.collection_name} dimension is {existing_dimension}, "
                f"but memory embedding dimension is {self.dimension}."
            )

    @staticmethod
    def _entry_id(entry: dict) -> str:
        return f"{entry.get('date', '')}:{entry.get('ticker', '')}"

    @staticmethod
    def _entry_text(entry: dict) -> str:
        return "\n".join(
            part
            for part in [
                entry.get("ticker", ""), entry.get("rating", ""),
                entry.get("decision", ""), entry.get("reflection", ""),
            ]
            if part
        )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

class TradingMemoryLog:
    """由 SQLite 和可读 Markdown 支撑的交易决策记忆。"""

    _SEPARATOR = "\n\n<!-- ENTRY_END -->\n\n"
    _DECISION_RE = re.compile(r"DECISION:\n(.*?)(?=\nREFLECTION:|\Z)", re.DOTALL)
    _REFLECTION_RE = re.compile(r"REFLECTION:\n(.*?)$", re.DOTALL)
    _NA = "N/A"

    def __init__(self, config: dict = None):
        cfg = config or {}
        self._log_path = None
        path = cfg.get("memory_log_path")
        if path:
            self._log_path = Path(path).expanduser()
            self._log_path.parent.mkdir(parents=True, exist_ok=True)

        db_path = cfg.get("memory_db_path")
        if db_path:
            self._db_path = Path(db_path).expanduser()
        elif self._log_path:
            self._db_path = self._log_path.with_suffix(".sqlite")
        else:
            self._db_path = None
        if self._db_path:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._ensure_schema()
            self._migrate_legacy_markdown_if_empty()

        self._max_entries = cfg.get("memory_log_max_entries")
        self._vector_index = cfg.get("memory_vector_index")
        if self._vector_index is None:
            backend = cfg.get("memory_vector_backend")
            if backend == "local":
                vector_path = cfg.get("memory_vector_path")
                if vector_path:
                    self._vector_index = LocalMemoryVectorIndex(vector_path)
            elif backend == "milvus":
                self._vector_index = MilvusMemoryVectorIndex(
                    uri=cfg["milvus_uri"],
                    token=cfg.get("milvus_token") or None,
                    database=cfg.get("milvus_database", "default"),
                    collection_name=cfg.get(
                        "memory_milvus_collection",
                        "ashareagents_trading_memory_bge",
                    ),
                    model_name=cfg.get(
                        "memory_embedding_model",
                        cfg.get("rag_embedding_model", "BAAI/bge-small-zh-v1.5"),
                    ),
                    dimension=int(
                        cfg.get(
                            "memory_embedding_dimension",
                            cfg.get("rag_embedding_dimension", 512),
                        )
                    ),
                    device=cfg.get("memory_model_device", cfg.get("rag_model_device", "cpu")),
                )

    def store_decision(self, ticker: str, trade_date: str, final_trade_decision: str) -> None:
        """不调用 LLM，直接存储待处理决策。"""
        if not self._log_path and not self._db_path:
            return
        rating = parse_rating(final_trade_decision)
        if self._db_path:
            now = self._now()
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO trading_memory (
                        ticker, trade_date, rating, status, final_decision,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, 'pending', ?, ?, ?)
                    """,
                    (ticker, trade_date, rating, final_trade_decision, now, now),
                )
            self._render_markdown_from_db()
            return

        if self._legacy_pending_exists(ticker, trade_date):
            return
        tag = f"[{trade_date} | {ticker} | {rating} | pending]"
        entry = f"{tag}\n\nDECISION:\n{final_trade_decision}{self._SEPARATOR}"
        with open(self._log_path, "a", encoding="utf-8") as f:
            f.write(entry)

    def load_entries(self) -> List[dict]:
        """返回所有记忆条目，优先使用结构化记录而非 Markdown。"""
        if self._db_path and self._table_has_rows():
            return self._load_db_entries()
        return self._load_markdown_entries()

    def get_pending_entries(self) -> List[dict]:
        return [e for e in self.load_entries() if e.get("pending")]

    def get_past_context(self, ticker: str, n_same: int = 5, n_cross: int = 3) -> str:
        entries = [e for e in self.load_entries() if not e.get("pending")]
        if not entries:
            return ""

        same, cross = [], []
        for e in reversed(entries):
            if len(same) >= n_same and len(cross) >= n_cross:
                break
            if e["ticker"] == ticker and len(same) < n_same:
                same.append(e)
            elif e["ticker"] != ticker and len(cross) < n_cross:
                cross.append(e)

        if not same and not cross:
            return ""

        parts = []
        if same:
            parts.append(f"Historical memory for {ticker} (most recent first):")
            parts.extend(self._format_full(e) for e in same)
        if cross:
            parts.append("Recent cross-ticker lessons:")
            parts.extend(self._format_reflection_only(e) for e in cross)
        return "\n\n".join(parts)

    def semantic_search(self, query: str, top_k: int = 5) -> List[dict]:
        """搜索可选的语义记忆索引。"""
        if not self._vector_index:
            return []
        return self._vector_index.search(query, top_k=top_k)

    def update_with_outcome(
        self,
        ticker: str,
        trade_date: str,
        raw_return: float,
        alpha_return: float,
        holding_days: int,
        reflection: str,
    ) -> None:
        self.batch_update_with_outcomes(
            [
                {
                    "ticker": ticker,
                    "trade_date": trade_date,
                    "raw_return": raw_return,
                    "alpha_return": alpha_return,
                    "holding_days": holding_days,
                    "reflection": reflection,
                }
            ]
        )

    def batch_update_with_outcomes(self, updates: List[dict]) -> None:
        if not updates:
            return
        if self._db_path:
            self._batch_update_db(updates)
            self._render_markdown_from_db()
            self._refresh_vector_index()
            return
        self._batch_update_markdown(updates)

    def _ensure_schema(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trading_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT NOT NULL,
                    trade_date TEXT NOT NULL,
                    rating TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('pending', 'resolved', 'failed')),
                    final_decision TEXT NOT NULL,
                    raw_return REAL,
                    alpha_return REAL,
                    holding_days INTEGER,
                    reflection TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(ticker, trade_date)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_trading_memory_lookup "
                "ON trading_memory(ticker, trade_date, status)"
            )

    def _migrate_legacy_markdown_if_empty(self) -> None:
        if not self._log_path or not self._log_path.exists() or self._table_has_rows():
            return
        entries = self._load_markdown_entries()
        if not entries:
            return
        now = self._now()
        with sqlite3.connect(self._db_path) as conn:
            conn.executemany(
                """
                INSERT OR IGNORE INTO trading_memory (
                    ticker, trade_date, rating, status, final_decision,
                    raw_return, alpha_return, holding_days, reflection,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        e["ticker"],
                        e["date"],
                        e["rating"],
                        "pending" if e["pending"] else "resolved",
                        e["decision"],
                        self._parse_pct(e.get("raw")),
                        self._parse_pct(e.get("alpha")),
                        self._parse_holding(e.get("holding")),
                        e.get("reflection", ""),
                        now,
                        now,
                    )
                    for e in entries
                ],
            )

    def _table_has_rows(self) -> bool:
        if not self._db_path or not self._db_path.exists():
            return False
        with sqlite3.connect(self._db_path) as conn:
            try:
                row = conn.execute("SELECT 1 FROM trading_memory LIMIT 1").fetchone()
            except sqlite3.OperationalError:
                return False
        return row is not None

    def _load_db_entries(self) -> List[dict]:
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                """
                SELECT trade_date, ticker, rating, status, final_decision,
                       raw_return, alpha_return, holding_days, reflection
                FROM trading_memory
                ORDER BY trade_date, id
                """
            ).fetchall()
        return [self._row_to_entry(row) for row in rows]

    def _row_to_entry(self, row: tuple) -> dict:
        trade_date, ticker, rating, status, decision, raw, alpha, holding, reflection = row
        pending = status == "pending"
        return {
            "date": trade_date,
            "ticker": ticker,
            "rating": rating,
            "pending": pending,
            "raw": None if pending or raw is None else f"{raw:+.1%}",
            "alpha": None if pending or alpha is None else f"{alpha:+.1%}",
            "holding": None if pending or holding is None else f"{holding}d",
            "decision": decision,
            "reflection": reflection or "",
        }

    def _load_markdown_entries(self) -> List[dict]:
        if not self._log_path or not self._log_path.exists():
            return []
        text = self._log_path.read_text(encoding="utf-8")
        raw_entries = [e.strip() for e in text.split(self._SEPARATOR) if e.strip()]
        entries = []
        for raw in raw_entries:
            parsed = self._parse_entry(raw)
            if parsed:
                entries.append(parsed)
        return entries

    def _batch_update_db(self, updates: List[dict]) -> None:
        now = self._now()
        with sqlite3.connect(self._db_path) as conn:
            for upd in updates:
                conn.execute(
                    """
                    UPDATE trading_memory
                    SET status = 'resolved',
                        raw_return = ?,
                        alpha_return = ?,
                        holding_days = ?,
                        reflection = ?,
                        updated_at = ?
                    WHERE trade_date = ? AND ticker = ? AND status = 'pending'
                    """,
                    (
                        upd["raw_return"],
                        upd["alpha_return"],
                        upd["holding_days"],
                        upd["reflection"],
                        now,
                        upd["trade_date"],
                        upd["ticker"],
                    ),
                )
            self._apply_db_rotation(conn)

    def _apply_db_rotation(self, conn: sqlite3.Connection) -> None:
        if not self._max_entries or self._max_entries <= 0:
            return
        rows = conn.execute(
            """
            SELECT id FROM trading_memory
            WHERE status != 'pending'
            ORDER BY trade_date, id
            """
        ).fetchall()
        overflow = len(rows) - self._max_entries
        if overflow <= 0:
            return
        drop_ids = [row[0] for row in rows[:overflow]]
        conn.executemany("DELETE FROM trading_memory WHERE id = ?", [(i,) for i in drop_ids])

    def _render_markdown_from_db(self) -> None:
        if not self._log_path or not self._db_path:
            return
        blocks = [self._format_full(e) for e in self._load_db_entries()]
        text = self._SEPARATOR.join(blocks)
        if text:
            text += self._SEPARATOR
        tmp_path = self._log_path.with_suffix(".tmp")
        tmp_path.write_text(text, encoding="utf-8")
        tmp_path.replace(self._log_path)

    def _refresh_vector_index(self) -> None:
        if not self._vector_index:
            return
        resolved = [entry for entry in self.load_entries() if not entry.get("pending")]
        self._vector_index.upsert_entries(resolved)

    def _batch_update_markdown(self, updates: List[dict]) -> None:
        if not self._log_path or not self._log_path.exists():
            return
        entries = self.load_entries()
        update_map = {(u["trade_date"], u["ticker"]): u for u in updates}
        for entry in entries:
            upd = update_map.get((entry["date"], entry["ticker"]))
            if not upd or not entry.get("pending"):
                continue
            entry["pending"] = False
            entry["raw"] = f"{upd['raw_return']:+.1%}"
            entry["alpha"] = f"{upd['alpha_return']:+.1%}"
            entry["holding"] = f"{upd['holding_days']}d"
            entry["reflection"] = upd["reflection"]
        entries = self._apply_rotation_entries(entries)
        text = self._SEPARATOR.join(self._format_full(e) for e in entries)
        if text:
            text += self._SEPARATOR
        tmp_path = self._log_path.with_suffix(".tmp")
        tmp_path.write_text(text, encoding="utf-8")
        tmp_path.replace(self._log_path)

    def _apply_rotation_entries(self, entries: List[dict]) -> List[dict]:
        if not self._max_entries or self._max_entries <= 0:
            return entries
        resolved = [e for e in entries if not e.get("pending")]
        overflow = len(resolved) - self._max_entries
        if overflow <= 0:
            return entries
        kept = []
        for entry in entries:
            if not entry.get("pending") and overflow > 0:
                overflow -= 1
                continue
            kept.append(entry)
        return kept

    def _legacy_pending_exists(self, ticker: str, trade_date: str) -> bool:
        if self._log_path and self._log_path.exists():
            raw = self._log_path.read_text(encoding="utf-8")
            for line in raw.splitlines():
                if line.startswith(f"[{trade_date} | {ticker} |") and line.endswith("| pending]"):
                    return True
        return False

    def _parse_entry(self, raw: str) -> Optional[dict]:
        lines = raw.strip().splitlines()
        if not lines:
            return None
        tag_line = lines[0].strip()
        if not (tag_line.startswith("[") and tag_line.endswith("]")):
            return None
        fields = [f.strip() for f in tag_line[1:-1].split("|")]
        if len(fields) < 4:
            return None
        entry = {
            "date": fields[0],
            "ticker": fields[1],
            "rating": fields[2],
            "pending": fields[3] == "pending",
            "raw": fields[3] if fields[3] != "pending" else None,
            "alpha": fields[4] if len(fields) > 4 else None,
            "holding": fields[5] if len(fields) > 5 else None,
        }
        body = "\n".join(lines[1:]).strip()
        decision_match = self._DECISION_RE.search(body)
        reflection_match = self._REFLECTION_RE.search(body)
        entry["decision"] = decision_match.group(1).strip() if decision_match else ""
        entry["reflection"] = reflection_match.group(1).strip() if reflection_match else ""
        return entry

    def _format_full(self, e: dict) -> str:
        if e.get("pending"):
            tag = f"[{e['date']} | {e['ticker']} | {e['rating']} | pending]"
        else:
            raw = e["raw"] or self._NA
            alpha = e["alpha"] or self._NA
            holding = e["holding"] or self._NA
            tag = f"[{e['date']} | {e['ticker']} | {e['rating']} | {raw} | {alpha} | {holding}]"
        parts = [tag, f"DECISION:\n{e['decision']}"]
        if e.get("reflection"):
            parts.append(f"REFLECTION:\n{e['reflection']}")
        return "\n\n".join(parts)

    def _format_reflection_only(self, e: dict) -> str:
        tag = f"[{e['date']} | {e['ticker']} | {e['rating']} | {e['raw'] or self._NA}]"
        if e.get("reflection"):
            return f"{tag}\n{e['reflection']}"
        text = e.get("decision", "")[:300]
        suffix = "..." if len(e.get("decision", "")) > 300 else ""
        return f"{tag}\n{text}{suffix}"

    def _parse_pct(self, value: str | None) -> float | None:
        if not value or value == self._NA:
            return None
        return float(value.strip().rstrip("%")) / 100.0

    def _parse_holding(self, value: str | None) -> int | None:
        if not value or value == self._NA:
            return None
        return int(value.strip().rstrip("d"))

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
