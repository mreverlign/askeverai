import pandas as pd
import numpy as np
from sentence_transformers import SentenceTransformer
import faiss
import pickle
from typing import List, Dict, Optional
from rank_bm25 import BM25Okapi
import re
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class StructuredMetadataEmbedder:
    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
                 bm25_weight: float = 0.6, semantic_weight: float = 0.4):
        logger.info(f"Loading model: {model_name}")
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

    def _infer_column_role(self, column_name: str, data_type: str, description: str) -> str:
        column_lower = column_name.lower()
        desc_lower = description.lower() if description else ""

        if any(kw in column_lower for kw in ['id', 'key']):
            return "identifier"
        elif any(kw in desc_lower for kw in ['count', 'sum', 'total', 'amount', 'revenue', 'cost', 'price', 'sales', 'value']):
            return "metric"
        elif data_type.lower() in ['int', 'integer', 'bigint', 'float', 'decimal', 'numeric', 'money', 'real', 'double precision']:
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

        embeddings = self.model.encode(texts, show_progress_bar=True, convert_to_numpy=True)
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

        embeddings = self.model.encode(texts, show_progress_bar=True, convert_to_numpy=True)
        self.oltp_column_index = faiss.IndexFlatIP(self.embedding_dim)
        faiss.normalize_L2(embeddings)
        self.oltp_column_index.add(embeddings.astype("float32"))

        logger.info(f"Embedded {len(texts)} OLTP columns")
        return len(texts)

    def load_and_embed_olap_tables(self, csv_path: str) -> int:
        return self._load_and_embed_tables(csv_path, "OLAP")

    def load_and_embed_oltp_tables(self, csv_path: str) -> int:
        return self._load_and_embed_tables(csv_path, "OLTP")

    def load_and_embed_relationships(self, csv_path: str) -> int:
        logger.info(f"Loading relationships: {csv_path}")
        df = self._read_csv(csv_path)
        if df is None:
            raise ValueError(f"Could not read CSV: {csv_path}")

        texts, records, tokenized_texts = [], [], []

        for idx, row in df.iterrows():
            primary_table = str(row.get('Primary Table', '')).strip()
            primary_key = str(row.get('Primary Key', '')).strip()

            foreign_table_col = row.get('Foreign Table', '')
            if pd.isna(foreign_table_col) or str(foreign_table_col).strip() == '':
                foreign_table = str(row.iloc[3]).strip() if len(row) > 3 else ''
            else:
                foreign_table = str(foreign_table_col).strip()

            foreign_key_col = row.get('Foreign Key', '')
            if pd.isna(foreign_key_col) or str(foreign_key_col).strip() == '':
                foreign_key = str(row.iloc[4]).strip() if len(row) > 4 else ''
            else:
                foreign_key = str(foreign_key_col).strip()

            relationship_type = str(row.get('Relationship Type', '')).strip()

            if not primary_table or not foreign_table or primary_table == 'nan' or foreign_table == 'nan':
                continue

            text = (
                f"Table {primary_table} joins to {foreign_table} "
                f"using primary key {primary_key} "
                f"and foreign key {foreign_key}. "
                f"Relationship type: {relationship_type}."
            )

            join_condition = ""
            if primary_key and foreign_key:
                join_condition = f"{primary_table.lower()}.{primary_key.lower()} = {foreign_table.lower()}.{foreign_key.lower()}"

            texts.append(text)
            tokenized_texts.append(self._tokenize(text))
            records.append({
                "primary_table": primary_table.lower(),
                "foreign_table": foreign_table.lower(),
                "primary_key": primary_key.lower() if primary_key else "",
                "foreign_key": foreign_key.lower() if foreign_key else "",
                "join_condition": join_condition,
                "relationship_type": relationship_type,
                "text_for_embedding": text
            })

        if len(texts) == 0:
            return 0

        self.relationship_bm25 = BM25Okapi(tokenized_texts)
        self.relationship_tokenized = tokenized_texts
        self.relationship_texts = texts
        self.relationship_records = records

        embeddings = self.model.encode(texts, show_progress_bar=True, convert_to_numpy=True)
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
            table_name = str(row.get('TABLE_NAME', row.get('table_name', ''))).strip()
            column_name = str(row.get('COLUMN_NAME', row.get('column_name', ''))).strip()
            data_type = str(row.get('Data_Type', row.get('data_type', ''))).strip()
            char_max = str(row.get('Char_Max', row.get('char_max', ''))).strip()
            description = str(row.get('Description', row.get('description', ''))).strip()

            if not table_name or not column_name or table_name == 'nan' or column_name == 'nan':
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
            records.append({
                "id": f"{layer}_{table_name}_{column_name}",
                "layer": layer,
                "table": table_name.lower(),
                "column": column_name.lower(),
                "data_type": data_type,
                "char_max": char_max,
                "description": description,
                "role": role,
                "text_for_embedding": text
            })

        return texts, records, tokenized_texts

    def _load_and_embed_tables(self, csv_path: str, layer: str) -> int:
        logger.info(f"Loading {layer} tables: {csv_path}")
        df = self._read_csv(csv_path)
        if df is None:
            raise ValueError(f"Could not read CSV: {csv_path}")

        tables_grouped = df.groupby('TABLE_NAME')
        texts, records, tokenized_texts = [], [], []

        for table_name, group in tables_grouped:
            columns_info = []
            for _, row in group.iterrows():
                col_name = str(row.get('COLUMN_NAME', row.get('column_name', ''))).strip()
                desc = str(row.get('Description', row.get('description', ''))).strip()
                if col_name and desc:
                    columns_info.append(f"- {col_name}: {desc}")

            purpose = "analytical queries" if layer == "OLAP" else "transactional operations"
            if "fact" in table_name.lower():
                purpose = purpose
            else:
                purpose = "dimensional attributes" if layer == "OLAP" else "operational attributes"

            text = (
                f"Table {table_name} in {layer} layer. "
                f"Contains columns:\n" + "\n".join(columns_info[:10]) + "\n"
                f"This table is primarily used for {purpose}."
            )

            texts.append(text)
            tokenized_texts.append(self._tokenize(text))
            records.append({
                "id": f"{layer}_TABLE_{table_name}",
                "layer": layer,
                "table": table_name.lower(),
                "column_count": len(group),
                "columns": list(group['COLUMN_NAME' if 'COLUMN_NAME' in group.columns else 'column_name']),
                "text_for_embedding": text
            })

        if len(texts) == 0:
            return 0

        embeddings = self.model.encode(texts, show_progress_bar=True, convert_to_numpy=True)

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

    def _hybrid_search(self, query: str, texts: List[str], tokenized_texts: List[List[str]],
                      records: List[Dict], bm25_index, faiss_index, top_k: int = 10) -> List[Dict]:
        if not texts or not records:
            return []

        query_tokens = self._tokenize(query)
        bm25_scores = bm25_index.get_scores(query_tokens)
        bm25_scores_norm = bm25_scores / bm25_scores.max() if bm25_scores.max() > 0 else bm25_scores

        query_embedding = self.model.encode([query], convert_to_numpy=True)
        faiss.normalize_L2(query_embedding)
        semantic_scores, indices = faiss_index.search(query_embedding.astype("float32"), len(texts))
        semantic_score_map = {idx: score for idx, score in zip(indices[0], semantic_scores[0])}

        hybrid_scores = []
        for i in range(len(records)):
            bm25_score = bm25_scores_norm[i] if i < len(bm25_scores_norm) else 0
            semantic_score = semantic_score_map.get(i, 0)
            hybrid_score = (self.bm25_weight * bm25_score) + (self.semantic_weight * semantic_score)
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

    def search_columns(self, query: str, layer: str = "OLAP", top_k: int = 10) -> List[Dict]:
        if layer == "OLAP":
            if self.olap_column_index is None:
                return []
            return self._hybrid_search(query, self.olap_column_texts, self.olap_column_tokenized,
                                      self.olap_column_records, self.olap_column_bm25,
                                      self.olap_column_index, top_k)
        else:
            if self.oltp_column_index is None:
                return []
            return self._hybrid_search(query, self.oltp_column_texts, self.oltp_column_tokenized,
                                      self.oltp_column_records, self.oltp_column_bm25,
                                      self.oltp_column_index, top_k)

    def search_tables(self, query: str, layer: str = "OLAP", top_k: int = 5) -> List[Dict]:
        if layer == "OLAP":
            if self.olap_table_index is None:
                return []
            return self._hybrid_search(query, self.olap_table_texts, self.olap_table_tokenized,
                                      self.olap_table_records, self.olap_table_bm25,
                                      self.olap_table_index, top_k)
        else:
            if self.oltp_table_index is None:
                return []
            return self._hybrid_search(query, self.oltp_table_texts, self.oltp_table_tokenized,
                                      self.oltp_table_records, self.oltp_table_bm25,
                                      self.oltp_table_index, top_k)

    def search_relationships(self, query: str, top_k: int = 10) -> List[Dict]:
        if self.relationship_index is None:
            return []
        return self._hybrid_search(query, self.relationship_texts, self.relationship_tokenized,
                                   self.relationship_records, self.relationship_bm25,
                                   self.relationship_index, top_k)

    def validate_join(self, table1: str, table2: str) -> Optional[Dict]:
        for rel in self.relationship_records:
            if (rel["primary_table"] == table1.lower() and rel["foreign_table"] == table2.lower()) or \
               (rel["primary_table"] == table2.lower() and rel["foreign_table"] == table1.lower()):
                return rel
        return None

    def search_with_layer_preference(self, query: str, top_k: int = 5) -> Dict:
        olap_results = self.search_columns(query, layer="OLAP", top_k=top_k)
        olap_best_score = olap_results[0].get('hybrid_score', 0) if olap_results else 0

        oltp_results = self.search_columns(query, layer="OLTP", top_k=top_k)
        oltp_best_score = oltp_results[0].get('hybrid_score', 0) if oltp_results else 0

        use_oltp = oltp_best_score > olap_best_score * 1.2 or olap_best_score < 0.3
        recommended_db = "OLTP" if use_oltp else "OLAP"

        return {
            "recommended_db": recommended_db,
            "olap_results": olap_results,
            "oltp_results": oltp_results,
            "olap_score": olap_best_score,
            "oltp_score": oltp_best_score,
            "confidence": max(olap_best_score, oltp_best_score)
        }

    def save_indices(self, save_dir: str):
        save_path = Path(save_dir)
        save_path.mkdir(parents=True, exist_ok=True)

        if self.olap_column_index:
            faiss.write_index(self.olap_column_index, str(save_path / "olap_columns.index"))
        if self.oltp_column_index:
            faiss.write_index(self.oltp_column_index, str(save_path / "oltp_columns.index"))
        if self.olap_table_index:
            faiss.write_index(self.olap_table_index, str(save_path / "olap_tables.index"))
        if self.oltp_table_index:
            faiss.write_index(self.oltp_table_index, str(save_path / "oltp_tables.index"))
        if self.relationship_index:
            faiss.write_index(self.relationship_index, str(save_path / "relationships.index"))

        metadata = {
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

        if (load_path / "olap_columns.index").exists():
            self.olap_column_index = faiss.read_index(str(load_path / "olap_columns.index"))
        if (load_path / "oltp_columns.index").exists():
            self.oltp_column_index = faiss.read_index(str(load_path / "oltp_columns.index"))
        if (load_path / "olap_tables.index").exists():
            self.olap_table_index = faiss.read_index(str(load_path / "olap_tables.index"))
        if (load_path / "oltp_tables.index").exists():
            self.oltp_table_index = faiss.read_index(str(load_path / "oltp_tables.index"))
        if (load_path / "relationships.index").exists():
            self.relationship_index = faiss.read_index(str(load_path / "relationships.index"))

        with open(load_path / "metadata.pkl", "rb") as f:
            metadata = pickle.load(f)

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
