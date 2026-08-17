import pandas as pd
import numpy as np
import faiss
import pickle
import hashlib
import json
from typing import List, Dict, Optional
from rank_bm25 import BM25Okapi
import re
from pathlib import Path
import logging

from src.domain.hightower import canonical_relationships

INDEX_FORMAT_VERSION = 2


def build_index_fingerprint(model_name: str) -> str:
    """Fingerprint every canonical input used to build the RAG indices."""
    project_root = Path(__file__).resolve().parents[2]
    schema_paths = (
        project_root / "data" / "schemas" / "HighTowerDataModelSchemaOLAP.csv",
        project_root / "data" / "schemas" / "HighTower_DataModel_Schema(OLTP).csv",
    )

    digest = hashlib.sha256()
    digest.update(f"index-format:{INDEX_FORMAT_VERSION}\n".encode())
    digest.update(f"embedding-model:{model_name}\n".encode())
    for schema_path in schema_paths:
        if not schema_path.is_file():
            raise FileNotFoundError(
                f"Cannot fingerprint RAG schema; missing {schema_path}"
            )
        digest.update(schema_path.name.encode())
        digest.update(schema_path.read_bytes())

    normalized_overrides = {
        "|".join(key): value for key, value in sorted(SCHEMA_OVERRIDES.items())
    }
    digest.update(json.dumps(normalized_overrides, sort_keys=True).encode("utf-8"))
    relationships = {
        layer: canonical_relationships(layer) for layer in ("OLAP", "OLTP")
    }
    digest.update(json.dumps(relationships, sort_keys=True).encode("utf-8"))
    return digest.hexdigest()


SCHEMA_OVERRIDES = {
    ("OLAP", "fact_transaction_detail", "itemquantity"): {
        "data_type": "numeric",
        "description": "Source transaction-line quantity; fractional and negative values occur.",
    },
    ("OLAP", "fact_transaction_detail", "itemrate"): {
        "data_type": "numeric",
        "description": "Source transaction-line rate; fractional and negative values occur.",
    },
    ("OLAP", "fact_transaction_detail", "oppclosedate"): {
        "data_type": "date",
        "description": "Opportunity close date; values after year 2100 are source anomalies.",
    },
    ("OLAP", "fact_transaction_detail", "opportunitynumber"): {
        "data_type": "text",
        "description": "Opportunity identifier, including OPP-prefixed values.",
    },
    ("OLAP", "fact_transaction_detail", "customerkeyaccount"): {
        "data_type": "boolean",
        "description": "Whether the customer is marked as a key account.",
    },
    ("OLAP", "fact_transaction_detail", "insts"): {
        "data_type": "timestamp without time zone",
        "description": "Source insertion timestamp.",
    },
    ("OLAP", "dim_date", "weekid"): {
        "description": "Identifier for the calendar week.",
    },
    ("OLAP", "dim_date", "monthid"): {
        "description": "Identifier for the calendar month.",
    },
    ("OLTP", "dim_date", "weekid"): {
        "description": "Identifier for the calendar week.",
    },
    ("OLTP", "dim_date", "monthid"): {
        "description": "Identifier for the calendar month.",
    },
}

for _schema_layer in ("OLAP", "OLTP"):
    SCHEMA_OVERRIDES.update(
        {
            (_schema_layer, "dim_item", "insts"): {
                "description": "Source insertion timestamp."
            },
            (_schema_layer, "dim_item", "option_1"): {
                "description": "First configuration option label."
            },
            (_schema_layer, "dim_item", "option_1_v"): {
                "description": "First configuration option value."
            },
            (_schema_layer, "dim_item", "option_total"): {
                "description": "First configuration option total text."
            },
            (_schema_layer, "dim_item", "option_2"): {
                "description": "Second configuration option label."
            },
            (_schema_layer, "dim_item", "option_2_v"): {
                "description": "Second configuration option value."
            },
            (_schema_layer, "dim_item", "option_total2"): {
                "description": "Second configuration option total text."
            },
            (_schema_layer, "dim_item", "option_3"): {
                "description": "Third configuration option label."
            },
            (_schema_layer, "dim_item", "option_3_v"): {
                "description": "Third configuration option value."
            },
            (_schema_layer, "dim_item", "option_total_3"): {
                "description": "Third configuration option total text."
            },
        }
    )

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class StructuredMetadataEmbedder:
    def __init__(
        self,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        bm25_weight: float = 0.6,
        semantic_weight: float = 0.4,
    ):
        # Loading sentence-transformers imports the full Transformers/tokenizers
        # stack. Keep that optional runtime dependency out of module import so
        # metadata helpers and pre-embedder initialization failures remain
        # testable without constructing the model.
        from sentence_transformers import SentenceTransformer

        logger.info(f"Loading model: {model_name}")
        self.model_name = model_name
        self.model = SentenceTransformer(model_name)
        self.embedding_dim = self.model.get_sentence_embedding_dimension()
        self.bm25_weight = bm25_weight
        self.semantic_weight = semantic_weight

        self.olap_column_index = None
        self.olap_column_texts = []
        self.olap_column_records = []
        self.olap_column_bm25 = None
        self.olap_column_tokenized = []

        self.oltp_column_index = None
        self.oltp_column_texts = []
        self.oltp_column_records = []
        self.oltp_column_bm25 = None
        self.oltp_column_tokenized = []

        self.olap_table_index = None
        self.olap_table_texts = []
        self.olap_table_records = []
        self.olap_table_bm25 = None
        self.olap_table_tokenized = []

        self.oltp_table_index = None
        self.oltp_table_texts = []
        self.oltp_table_records = []
        self.oltp_table_bm25 = None
        self.oltp_table_tokenized = []

        self.relationship_index = None
        self.relationship_texts = []
        self.relationship_records = []
        self.relationship_bm25 = None
        self.relationship_tokenized = []

        logger.info(f"Model loaded (dim: {self.embedding_dim})")

    def _tokenize(self, text: str) -> List[str]:
        text = text.lower()
        table_col_patterns = re.findall(r"\b\w+\.\w+\b", text)
        tokens = re.findall(r"\b[\w_]+\b", text)
        tokens.extend(table_col_patterns)
        tokens = [t for t in tokens if len(t) > 2 or t == "id"]
        return tokens

    def _infer_column_role(
        self, column_name: str, data_type: str, description: str
    ) -> str:
        column_lower = column_name.lower()
        desc_lower = description.lower() if description else ""

        if any(kw in column_lower for kw in ["id", "key"]):
            return "identifier"
        elif any(
            kw in desc_lower
            for kw in [
                "count",
                "sum",
                "total",
                "amount",
                "revenue",
                "cost",
                "price",
                "sales",
                "value",
            ]
        ):
            return "metric"
        elif data_type.lower() in [
            "int",
            "integer",
            "bigint",
            "float",
            "decimal",
            "numeric",
            "money",
            "real",
            "double precision",
        ]:
            return "metric"
        else:
            return "dimension"

    def load_and_embed_olap_columns(self, csv_path: str) -> int:
        logger.info(f"Loading OLAP schema: {csv_path}")
        df = self._read_csv(csv_path)
        if df is None:
            raise ValueError(f"Could not read CSV: {csv_path}")

        texts, records, tokenized_texts = self._process_columns(df, "OLAP")
        if len(texts) == 0:
            return 0

        self.olap_column_bm25 = BM25Okapi(tokenized_texts)
        self.olap_column_tokenized = tokenized_texts
        self.olap_column_texts = texts
        self.olap_column_records = records

        embeddings = self.model.encode(
            texts, show_progress_bar=True, convert_to_numpy=True
        )
        self.olap_column_index = faiss.IndexFlatIP(self.embedding_dim)
        faiss.normalize_L2(embeddings)
        self.olap_column_index.add(embeddings.astype("float32"))

        logger.info(f"Embedded {len(texts)} OLAP columns")
        return len(texts)

    def load_and_embed_oltp_columns(self, csv_path: str) -> int:
        logger.info(f"Loading OLTP schema: {csv_path}")
        df = self._read_csv(csv_path)
        if df is None:
            raise ValueError(f"Could not read CSV: {csv_path}")

        texts, records, tokenized_texts = self._process_columns(df, "OLTP")
        if len(texts) == 0:
            return 0

        self.oltp_column_bm25 = BM25Okapi(tokenized_texts)
        self.oltp_column_tokenized = tokenized_texts
        self.oltp_column_texts = texts
        self.oltp_column_records = records

        embeddings = self.model.encode(
            texts, show_progress_bar=True, convert_to_numpy=True
        )
        self.oltp_column_index = faiss.IndexFlatIP(self.embedding_dim)
        faiss.normalize_L2(embeddings)
        self.oltp_column_index.add(embeddings.astype("float32"))

        logger.info(f"Embedded {len(texts)} OLTP columns")
        return len(texts)

    def load_and_embed_olap_tables(self, csv_path: str) -> int:
        return self._load_and_embed_tables(csv_path, "OLAP")

    def load_and_embed_oltp_tables(self, csv_path: str) -> int:
        return self._load_and_embed_tables(csv_path, "OLTP")

    def load_and_embed_relationships(self, csv_path: str = "") -> int:
        # The legacy relationship CSV has shifted/blank fields and several
        # invalid joins. Build this optional search index from the same
        # validated manifest used by SQL generation instead.
        logger.info("Loading validated HighTower relationships")
        texts, records, tokenized_texts = [], [], []
        seen = set()
        for layer in ("OLAP", "OLTP"):
            for relationship in canonical_relationships(layer):
                key = (
                    layer,
                    relationship["left_table"],
                    relationship["left_column"],
                    relationship["right_table"],
                    relationship["right_column"],
                )
                if key in seen:
                    continue
                seen.add(key)

                text = (
                    f"In the {layer} layer, table {relationship['left_table']} "
                    f"joins to {relationship['right_table']} with "
                    f"{relationship['join_condition']}. "
                    f"Coverage: {relationship.get('coverage', 'complete')}. "
                    f"{relationship.get('note', '')}"
                )

                record = dict(relationship)
                record["search_layer"] = layer
                record["text_for_embedding"] = text
                texts.append(text)
                tokenized_texts.append(self._tokenize(text))
                records.append(record)

        if len(texts) == 0:
            return 0

        self.relationship_bm25 = BM25Okapi(tokenized_texts)
        self.relationship_tokenized = tokenized_texts
        self.relationship_texts = texts
        self.relationship_records = records

        embeddings = self.model.encode(
            texts, show_progress_bar=True, convert_to_numpy=True
        )
        self.relationship_index = faiss.IndexFlatIP(self.embedding_dim)
        faiss.normalize_L2(embeddings)
        self.relationship_index.add(embeddings.astype("float32"))

        logger.info(f"Embedded {len(texts)} relationships")
        return len(texts)

    def _read_csv(self, csv_path: str) -> Optional[pd.DataFrame]:
        for encoding in ["utf-8-sig", "utf-8", "latin-1", "iso-8859-1"]:
            try:
                df = pd.read_csv(csv_path, encoding=encoding)
                df = df.fillna("")
                df.columns = df.columns.str.strip()
                return df
            except:
                continue
        return None

    def _process_columns(self, df: pd.DataFrame, layer: str) -> tuple:
        texts, records, tokenized_texts = [], [], []

        for idx, row in df.iterrows():
            table_name = str(row.get("TABLE_NAME", row.get("table_name", ""))).strip()
            column_name = str(
                row.get("COLUMN_NAME", row.get("column_name", ""))
            ).strip()
            data_type = str(row.get("Data_Type", row.get("data_type", ""))).strip()
            char_max = str(row.get("Char_Max", row.get("char_max", ""))).strip()
            description = str(
                row.get("Description", row.get("description", ""))
            ).strip()

            override = SCHEMA_OVERRIDES.get(
                (layer, table_name.lower(), column_name.lower()), {}
            )
            data_type = override.get("data_type", data_type)
            description = override.get("description", description)

            if (
                not table_name
                or not column_name
                or table_name == "nan"
                or column_name == "nan"
            ):
                continue

            role = self._infer_column_role(column_name, data_type, description)

            text = (
                f"Column {column_name} in table {table_name} ({layer} layer). "
                f"Data type: {data_type}. "
                f"Maximum length: {char_max}. "
                f"Description: {description}. "
                f"Role: {role}."
            )

            texts.append(text)
            tokenized_texts.append(self._tokenize(text))
            records.append(
                {
                    "id": f"{layer}_{table_name}_{column_name}",
                    "layer": layer,
                    "table": table_name.lower(),
                    "column": column_name.lower(),
                    "data_type": data_type,
                    "char_max": char_max,
                    "description": description,
                    "role": role,
                    "text_for_embedding": text,
                }
            )

        return texts, records, tokenized_texts

    def _load_and_embed_tables(self, csv_path: str, layer: str) -> int:
        logger.info(f"Loading {layer} tables: {csv_path}")
        df = self._read_csv(csv_path)
        if df is None:
            raise ValueError(f"Could not read CSV: {csv_path}")

        tables_grouped = df.groupby("TABLE_NAME")
        texts, records, tokenized_texts = [], [], []

        for table_name, group in tables_grouped:
            columns_info = []
            for _, row in group.iterrows():
                col_name = str(
                    row.get("COLUMN_NAME", row.get("column_name", ""))
                ).strip()
                desc = str(row.get("Description", row.get("description", ""))).strip()
                if col_name and desc:
                    columns_info.append(f"- {col_name}: {desc}")

            purpose = (
                "analytical queries" if layer == "OLAP" else "transactional operations"
            )
            if "fact" in table_name.lower():
                purpose = purpose
            else:
                purpose = (
                    "dimensional attributes"
                    if layer == "OLAP"
                    else "operational attributes"
                )

            text = (
                f"Table {table_name} in {layer} layer. "
                f"Contains columns:\n" + "\n".join(columns_info[:10]) + "\n"
                f"This table is primarily used for {purpose}."
            )

            texts.append(text)
            tokenized_texts.append(self._tokenize(text))
            records.append(
                {
                    "id": f"{layer}_TABLE_{table_name}",
                    "layer": layer,
                    "table": table_name.lower(),
                    "column_count": len(group),
                    "columns": list(
                        group[
                            (
                                "COLUMN_NAME"
                                if "COLUMN_NAME" in group.columns
                                else "column_name"
                            )
                        ]
                    ),
                    "text_for_embedding": text,
                }
            )

        if len(texts) == 0:
            return 0

        embeddings = self.model.encode(
            texts, show_progress_bar=True, convert_to_numpy=True
        )

        if layer == "OLAP":
            self.olap_table_bm25 = BM25Okapi(tokenized_texts)
            self.olap_table_tokenized = tokenized_texts
            self.olap_table_texts = texts
            self.olap_table_records = records
            self.olap_table_index = faiss.IndexFlatIP(self.embedding_dim)
            faiss.normalize_L2(embeddings)
            self.olap_table_index.add(embeddings.astype("float32"))
        else:
            self.oltp_table_bm25 = BM25Okapi(tokenized_texts)
            self.oltp_table_tokenized = tokenized_texts
            self.oltp_table_texts = texts
            self.oltp_table_records = records
            self.oltp_table_index = faiss.IndexFlatIP(self.embedding_dim)
            faiss.normalize_L2(embeddings)
            self.oltp_table_index.add(embeddings.astype("float32"))

        logger.info(f"Embedded {len(texts)} {layer} tables")
        return len(texts)

    def _hybrid_search(
        self,
        query: str,
        texts: List[str],
        tokenized_texts: List[List[str]],
        records: List[Dict],
        bm25_index,
        faiss_index,
        top_k: int = 10,
    ) -> List[Dict]:
        if not texts or not records:
            return []

        query_tokens = self._tokenize(query)
        bm25_scores = bm25_index.get_scores(query_tokens)
        bm25_scores_norm = (
            bm25_scores / bm25_scores.max() if bm25_scores.max() > 0 else bm25_scores
        )

        query_embedding = self.model.encode([query], convert_to_numpy=True)
        faiss.normalize_L2(query_embedding)
        semantic_scores, indices = faiss_index.search(
            query_embedding.astype("float32"), len(texts)
        )
        semantic_score_map = {
            idx: score for idx, score in zip(indices[0], semantic_scores[0])
        }

        hybrid_scores = []
        for i in range(len(records)):
            bm25_score = bm25_scores_norm[i] if i < len(bm25_scores_norm) else 0
            semantic_score = semantic_score_map.get(i, 0)
            hybrid_score = (self.bm25_weight * bm25_score) + (
                self.semantic_weight * semantic_score
            )
            hybrid_scores.append({"index": i, "hybrid_score": float(hybrid_score)})

        hybrid_scores.sort(key=lambda x: x["hybrid_score"], reverse=True)

        results = []
        for score_info in hybrid_scores[:top_k]:
            idx = score_info["index"]
            if idx < len(records):
                result = records[idx].copy()
                result["hybrid_score"] = score_info["hybrid_score"]
                results.append(result)

        return results

    def search_columns(
        self, query: str, layer: str = "OLAP", top_k: int = 10
    ) -> List[Dict]:
        if layer == "OLAP":
            if self.olap_column_index is None:
                return []
            return self._hybrid_search(
                query,
                self.olap_column_texts,
                self.olap_column_tokenized,
                self.olap_column_records,
                self.olap_column_bm25,
                self.olap_column_index,
                top_k,
            )
        else:
            if self.oltp_column_index is None:
                return []
            return self._hybrid_search(
                query,
                self.oltp_column_texts,
                self.oltp_column_tokenized,
                self.oltp_column_records,
                self.oltp_column_bm25,
                self.oltp_column_index,
                top_k,
            )

    def search_tables(
        self, query: str, layer: str = "OLAP", top_k: int = 5
    ) -> List[Dict]:
        if layer == "OLAP":
            if self.olap_table_index is None:
                return []
            return self._hybrid_search(
                query,
                self.olap_table_texts,
                self.olap_table_tokenized,
                self.olap_table_records,
                self.olap_table_bm25,
                self.olap_table_index,
                top_k,
            )
        else:
            if self.oltp_table_index is None:
                return []
            return self._hybrid_search(
                query,
                self.oltp_table_texts,
                self.oltp_table_tokenized,
                self.oltp_table_records,
                self.oltp_table_bm25,
                self.oltp_table_index,
                top_k,
            )

    def search_relationships(self, query: str, top_k: int = 10) -> List[Dict]:
        if self.relationship_index is None:
            return []
        return self._hybrid_search(
            query,
            self.relationship_texts,
            self.relationship_tokenized,
            self.relationship_records,
            self.relationship_bm25,
            self.relationship_index,
            top_k,
        )

    def validate_join(self, table1: str, table2: str) -> Optional[Dict]:
        for rel in self.relationship_records:
            if (
                rel["primary_table"] == table1.lower()
                and rel["foreign_table"] == table2.lower()
            ) or (
                rel["primary_table"] == table2.lower()
                and rel["foreign_table"] == table1.lower()
            ):
                return rel
        return None

    def search_with_layer_preference(self, query: str, top_k: int = 5) -> Dict:
        olap_results = self.search_columns(query, layer="OLAP", top_k=top_k)
        olap_best_score = olap_results[0].get("hybrid_score", 0) if olap_results else 0

        oltp_results = self.search_columns(query, layer="OLTP", top_k=top_k)
        oltp_best_score = oltp_results[0].get("hybrid_score", 0) if oltp_results else 0

        use_oltp = oltp_best_score > olap_best_score * 1.2 or olap_best_score < 0.3
        recommended_db = "OLTP" if use_oltp else "OLAP"

        return {
            "recommended_db": recommended_db,
            "olap_results": olap_results,
            "oltp_results": oltp_results,
            "olap_score": olap_best_score,
            "oltp_score": oltp_best_score,
            "confidence": max(olap_best_score, oltp_best_score),
        }

    def save_indices(self, save_dir: str):
        save_path = Path(save_dir)
        save_path.mkdir(parents=True, exist_ok=True)

        if self.olap_column_index:
            faiss.write_index(
                self.olap_column_index, str(save_path / "olap_columns.index")
            )
        if self.oltp_column_index:
            faiss.write_index(
                self.oltp_column_index, str(save_path / "oltp_columns.index")
            )
        if self.olap_table_index:
            faiss.write_index(
                self.olap_table_index, str(save_path / "olap_tables.index")
            )
        if self.oltp_table_index:
            faiss.write_index(
                self.oltp_table_index, str(save_path / "oltp_tables.index")
            )
        if self.relationship_index:
            faiss.write_index(
                self.relationship_index, str(save_path / "relationships.index")
            )

        metadata = {
            "index_format_version": INDEX_FORMAT_VERSION,
            "index_fingerprint": build_index_fingerprint(self.model_name),
            "model_name": self.model_name,
            "olap_column_texts": self.olap_column_texts,
            "olap_column_records": self.olap_column_records,
            "olap_column_tokenized": self.olap_column_tokenized,
            "oltp_column_texts": self.oltp_column_texts,
            "oltp_column_records": self.oltp_column_records,
            "oltp_column_tokenized": self.oltp_column_tokenized,
            "olap_table_texts": self.olap_table_texts,
            "olap_table_records": self.olap_table_records,
            "olap_table_tokenized": self.olap_table_tokenized,
            "oltp_table_texts": self.oltp_table_texts,
            "oltp_table_records": self.oltp_table_records,
            "oltp_table_tokenized": self.oltp_table_tokenized,
            "relationship_texts": self.relationship_texts,
            "relationship_records": self.relationship_records,
            "relationship_tokenized": self.relationship_tokenized,
            "embedding_dim": self.embedding_dim,
            "bm25_weight": self.bm25_weight,
            "semantic_weight": self.semantic_weight,
        }

        with open(save_path / "metadata.pkl", "wb") as f:
            pickle.dump(metadata, f)

        logger.info(f"Saved to {save_dir}")

    def load_indices(self, load_dir: str):
        load_path = Path(load_dir)

        metadata_path = load_path / "metadata.pkl"
        if not metadata_path.is_file():
            raise FileNotFoundError(
                f"RAG metadata is missing at {metadata_path}. "
                "Run `python scripts/setup_embeddings.py`."
            )
        with open(metadata_path, "rb") as f:
            metadata = pickle.load(f)

        expected_fingerprint = build_index_fingerprint(self.model_name)
        if (
            metadata.get("index_format_version") != INDEX_FORMAT_VERSION
            or metadata.get("index_fingerprint") != expected_fingerprint
            or metadata.get("model_name") != self.model_name
            or metadata.get("embedding_dim") != self.embedding_dim
        ):
            raise ValueError(
                "RAG indices are stale or were built with a different schema/model. "
                "Run `python scripts/setup_embeddings.py` before starting the app."
            )

        required_indices = (
            "olap_columns.index",
            "oltp_columns.index",
            "olap_tables.index",
            "oltp_tables.index",
            "relationships.index",
        )
        missing_indices = [
            filename
            for filename in required_indices
            if not (load_path / filename).is_file()
        ]
        if missing_indices:
            raise FileNotFoundError(
                "RAG index set is incomplete (missing "
                + ", ".join(missing_indices)
                + "). Run `python scripts/setup_embeddings.py`."
            )

        if (load_path / "olap_columns.index").exists():
            self.olap_column_index = faiss.read_index(
                str(load_path / "olap_columns.index")
            )
        if (load_path / "oltp_columns.index").exists():
            self.oltp_column_index = faiss.read_index(
                str(load_path / "oltp_columns.index")
            )
        if (load_path / "olap_tables.index").exists():
            self.olap_table_index = faiss.read_index(
                str(load_path / "olap_tables.index")
            )
        if (load_path / "oltp_tables.index").exists():
            self.oltp_table_index = faiss.read_index(
                str(load_path / "oltp_tables.index")
            )
        if (load_path / "relationships.index").exists():
            self.relationship_index = faiss.read_index(
                str(load_path / "relationships.index")
            )

        self.olap_column_texts = metadata["olap_column_texts"]
        self.olap_column_records = metadata["olap_column_records"]
        self.olap_column_tokenized = metadata["olap_column_tokenized"]
        self.oltp_column_texts = metadata["oltp_column_texts"]
        self.oltp_column_records = metadata["oltp_column_records"]
        self.oltp_column_tokenized = metadata["oltp_column_tokenized"]
        self.olap_table_texts = metadata["olap_table_texts"]
        self.olap_table_records = metadata["olap_table_records"]
        self.olap_table_tokenized = metadata["olap_table_tokenized"]
        self.oltp_table_texts = metadata["oltp_table_texts"]
        self.oltp_table_records = metadata["oltp_table_records"]
        self.oltp_table_tokenized = metadata["oltp_table_tokenized"]
        self.relationship_texts = metadata["relationship_texts"]
        self.relationship_records = metadata["relationship_records"]
        self.relationship_tokenized = metadata["relationship_tokenized"]
        self.embedding_dim = metadata["embedding_dim"]
        self.bm25_weight = metadata.get("bm25_weight", 0.6)
        self.semantic_weight = metadata.get("semantic_weight", 0.4)

        if self.olap_column_tokenized:
            self.olap_column_bm25 = BM25Okapi(self.olap_column_tokenized)
        if self.oltp_column_tokenized:
            self.oltp_column_bm25 = BM25Okapi(self.oltp_column_tokenized)
        if self.olap_table_tokenized:
            self.olap_table_bm25 = BM25Okapi(self.olap_table_tokenized)
        if self.oltp_table_tokenized:
            self.oltp_table_bm25 = BM25Okapi(self.oltp_table_tokenized)
        if self.relationship_tokenized:
            self.relationship_bm25 = BM25Okapi(self.relationship_tokenized)

        logger.info(f"Loaded from {load_dir}")
