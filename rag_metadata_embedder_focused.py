import pandas as pd
import numpy as np
from sentence_transformers import SentenceTransformer
import faiss
import pickle
from typing import List, Dict, Tuple, Optional
from rank_bm25 import BM25Okapi
import re
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FocusedColumnEmbedder:
    def __init__(self,
                 model_name: str = "sentence-transformers/all-MiniLM-L6-v2",  # Faster, better for short texts
                 bm25_weight: float = 0.6,  # Increase keyword weight
                 semantic_weight: float = 0.4):

        logger.info(f"Loading embedding model: {model_name}")
        self.model = SentenceTransformer(model_name)
        self.embedding_dim = self.model.get_sentence_embedding_dimension()

        # Weights for hybrid scoring (favor keyword matching)
        self.bm25_weight = bm25_weight
        self.semantic_weight = semantic_weight

        # Storage for embeddings and metadata
        self.metadata_index = None
        self.metadata_texts = []
        self.metadata_records = []
        self.metadata_bm25 = None
        self.metadata_tokenized = []

        self.relationships_index = None
        self.relationships_texts = []
        self.relationships_records = []
        self.relationships_bm25 = None
        self.relationships_tokenized = []

        self.datamodel_index = None
        self.datamodel_texts = []
        self.datamodel_records = []
        self.datamodel_bm25 = None
        self.datamodel_tokenized = []

        logger.info(f"✅ Model loaded with embedding dimension: {self.embedding_dim}")
        logger.info(f"🔄 Hybrid weights - BM25: {bm25_weight}, Semantic: {semantic_weight}")

    def _tokenize(self, text: str) -> List[str]:

        text = text.lower()

        # Preserve table.column patterns
        table_col_patterns = re.findall(r'\b\w+\.\w+\b', text)

        # Extract words with underscores (table_name, column_name)
        tokens = re.findall(r'\b[\w_]+\b', text)

        # Add table.column patterns
        tokens.extend(table_col_patterns)

        # Remove very short tokens (but keep 'id')
        tokens = [t for t in tokens if len(t) > 2 or t == 'id']

        return tokens

    def _create_focused_metadata_text(self, table_name: str, column_name: str,
                                      data_type: str, description: str, example: str = "") -> str:

        if not table_name or not column_name:
            return ""

        # Clean inputs
        table_name = str(table_name).strip().lower()
        column_name = str(column_name).strip().lower()
        data_type = str(data_type).strip().lower() if data_type else ""
        description = str(description).strip() if description else ""
        example = str(example).strip() if example else ""

        parts = []

        # 1. EXACT identifiers (highest priority for BM25)
        parts.append(table_name)
        parts.append(column_name)
        parts.append(f"{table_name}.{column_name}")

        # 2. Semantic context (for embeddings)
        parts.append(f"table {table_name}")
        parts.append(f"column {column_name}")

        # 3. Data type (if meaningful)
        if data_type and data_type not in ['nan', 'none', '']:
            parts.append(f"{data_type}")

        # 4. Description (concise, key terms only)
        if description and description not in ['nan', 'none', '']:
            # Extract key terms from description (nouns, important words)
            desc_words = description.lower().split()
            key_words = [w for w in desc_words if len(w) > 4][:5]  # Top 5 meaningful words
            parts.extend(key_words)

        # 5. Example values (for better matching)
        if example and example not in ['nan', 'none', '']:
            parts.append(f"examples: {example.lower()}")

        return " ".join(parts)

    def _create_focused_relationship_text(self, primary_table: str, primary_key: str,
                                          foreign_table: str, foreign_key: str,
                                          relationship_type: str) -> str:

        if not primary_table:
            return ""

        # Clean inputs
        primary_table = str(primary_table).strip().lower()
        primary_key = str(primary_key).strip().lower() if primary_key else ""
        foreign_table = str(foreign_table).strip().lower() if foreign_table else ""
        foreign_key = str(foreign_key).strip().lower() if foreign_key else ""

        parts = []

        # 1. EXACT table names (highest priority)
        parts.append(primary_table)
        if foreign_table:
            parts.append(foreign_table)

        # 2. Join pattern with semantic meaning
        if foreign_table:
            parts.append(f"{primary_table} {foreign_table}")
            parts.append(f"join {primary_table} {foreign_table}")

            # Add semantic context for common patterns
            if 'project' in primary_table and 'fact' in foreign_table:
                parts.append("project orders")
                parts.append("project transactions")
            elif 'client' in primary_table and 'fact' in foreign_table:
                parts.append("client orders")
                parts.append("client sales")
            elif 'item' in primary_table and 'fact' in foreign_table:
                parts.append("product orders")
                parts.append("product sales")

        # 3. Key columns
        if primary_key:
            parts.append(primary_key)
            parts.append(f"{primary_table}.{primary_key}")

        if foreign_key:
            parts.append(foreign_key)
            if foreign_table:
                parts.append(f"{foreign_table}.{foreign_key}")

        # 4. Fully qualified join condition
        if primary_table and primary_key and foreign_table and foreign_key:
            parts.append(f"{primary_table}.{primary_key} {foreign_table}.{foreign_key}")

        return " ".join(parts)

    def _detect_metadata_columns(self, df: pd.DataFrame) -> Dict[str, str]:

        columns_lower = {col.lower().strip(): col for col in df.columns}

        variations = {
            'table_name': ['table name', 'tablename', 'table', 'table_name', 'tbl_name'],
            'column_name': ['column name', 'columnname', 'column', 'column_name', 'col_name', 'field'],
            'data_type': ['data type', 'datatype', 'type', 'data_type', 'dtype'],
            'description': ['description', 'desc', 'comments', 'comment', 'notes'],
            'example': ['example', 'examples', 'sample', 'sample values', 'sample_values']
        }

        mapping = {}
        for standard, variants in variations.items():
            for variant in variants:
                if variant in columns_lower:
                    mapping[standard] = columns_lower[variant]
                    break

        logger.info(f"Detected metadata columns: {mapping}")
        return mapping

    def _detect_relationship_columns(self, df: pd.DataFrame) -> Dict[str, str]:
        
        columns_lower = {col.lower().strip(): col for col in df.columns}

        variations = {
            'primary_table': ['primary table', 'primarytable', 'from table', 'source table', 'parent table'],
            'primary_key': ['primary key', 'primarykey', 'from key', 'source key', 'pk'],
            'foreign_table': ['foreign table', 'foreigntable', 'to table', 'target table', 'child table'],
            'foreign_key': ['foreign key', 'foreignkey', 'to key', 'target key', 'fk'],
            'relationship_type': ['relationship type', 'relationshiptype', 'relation', 'type', 'cardinality']
        }

        mapping = {}
        for standard, variants in variations.items():
            for variant in variants:
                if variant in columns_lower:
                    mapping[standard] = columns_lower[variant]
                    break

        logger.info(f"Detected relationship columns: {mapping}")
        return mapping

    def _clean_relationship_row(self, row: pd.Series, col_mapping: Dict[str, str]) -> Dict[str, str]:
 
        # Get all values from the row
        values = [str(v).strip() for v in row.values if str(v).strip() and str(v).strip() != 'nan']

        # Expected pattern: PrimaryTable, PrimaryKey, ForeignTable (might be in wrong column), ForeignKey, RelType
        result = {
            'primary_table': '',
            'primary_key': '',
            'foreign_table': '',
            'foreign_key': '',
            'relationship_type': ''
        }

        # Try mapped columns first
        for key, col_name in col_mapping.items():
            val = str(row.get(col_name, '')).strip()
            if val and val != 'nan':
                result[key] = val

        # If foreign_table is empty but we have values, try to infer from pattern
        # Pattern: usually fact_transaction_detail is the foreign table
        if not result['foreign_table']:
            for val in values:
                val_lower = val.lower()
                if 'fact_' in val_lower or 'dim_' in val_lower:
                    if val_lower != result['primary_table'].lower():
                        result['foreign_table'] = val
                        break

        # If we still don't have foreign table, assume it's fact_transaction_detail
        if not result['foreign_table'] and result['primary_table']:
            result['foreign_table'] = 'fact_transaction_detail'

        return result

    def load_and_embed_metadata(self, csv_path: str) -> int:
        """Load and embed metadata with focused strategy"""
        logger.info(f"📊 Loading metadata from: {csv_path}")

        # Read CSV
        df = None
        for encoding in ['utf-8-sig', 'utf-8', 'latin-1', 'iso-8859-1']:
            try:
                df = pd.read_csv(csv_path, encoding=encoding)
                logger.info(f"✅ Read CSV with {encoding} encoding")
                break
            except:
                continue

        if df is None:
            raise ValueError(f"Could not read CSV file: {csv_path}")

        logger.info(f"Loaded {len(df)} rows, columns: {df.columns.tolist()}")
        df = df.fillna('')

        # Auto-detect columns
        col_mapping = self._detect_metadata_columns(df)

        # Process rows
        texts = []
        records = []
        tokenized_texts = []

        current_table = None
        for idx, row in df.iterrows():
            # Handle merged cells - table name might be empty
            table_val = str(row.get(col_mapping.get('table_name', ''), '')).strip()
            if table_val and table_val != 'nan':
                current_table = table_val

            column_val = str(row.get(col_mapping.get('column_name', ''), '')).strip()

            if not column_val or column_val == 'nan':
                continue

            if not current_table:
                continue

            data_type = str(row.get(col_mapping.get('data_type', ''), ''))
            description = str(row.get(col_mapping.get('description', ''), ''))
            example = str(row.get(col_mapping.get('example', ''), ''))

            text = self._create_focused_metadata_text(
                current_table, column_val, data_type, description, example
            )

            if text:
                texts.append(text)
                tokenized_texts.append(self._tokenize(text))

                records.append({
                    'table_name': current_table,
                    'column_name': column_val,
                    'data_type': data_type,
                    'description': description,
                    'example': example,
                    'source': 'metadata',
                    'row_id': idx
                })

        logger.info(f"Created {len(texts)} focused metadata texts")

        if len(texts) == 0:
            logger.warning("No valid metadata texts created")
            return 0

        # Create BM25 index
        logger.info("🔍 Creating BM25 index...")
        self.metadata_bm25 = BM25Okapi(tokenized_texts)
        self.metadata_tokenized = tokenized_texts

        # Generate embeddings
        logger.info("🧠 Generating embeddings...")
        embeddings = self.model.encode(texts, show_progress_bar=True, convert_to_numpy=True)

        # Create FAISS index
        logger.info("📇 Creating FAISS index...")
        self.metadata_index = faiss.IndexFlatIP(self.embedding_dim)
        faiss.normalize_L2(embeddings)
        self.metadata_index.add(embeddings.astype('float32'))

        self.metadata_texts = texts
        self.metadata_records = records

        logger.info(f"✅ Embedded {len(texts)} metadata records")
        return len(texts)

    def load_and_embed_relationships(self, csv_path: str) -> int:
        logger.info(f"🔗 Loading relationships from: {csv_path}")

        # Read CSV
        df = None
        for encoding in ['utf-8-sig', 'utf-8', 'latin-1', 'iso-8859-1']:
            try:
                df = pd.read_csv(csv_path, encoding=encoding)
                logger.info(f"✅ Read CSV with {encoding} encoding")
                break
            except:
                continue

        if df is None:
            raise ValueError(f"Could not read CSV file: {csv_path}")

        logger.info(f"Loaded {len(df)} rows, columns: {df.columns.tolist()}")
        df = df.fillna('')

        # Auto-detect columns
        col_mapping = self._detect_relationship_columns(df)

        # Process rows
        texts = []
        records = []
        tokenized_texts = []

        for idx, row in df.iterrows():
            # Clean the row
            cleaned = self._clean_relationship_row(row, col_mapping)

            if not cleaned['primary_table']:
                continue

            text = self._create_focused_relationship_text(
                cleaned['primary_table'],
                cleaned['primary_key'],
                cleaned['foreign_table'],
                cleaned['foreign_key'],
                cleaned['relationship_type']
            )

            if text:
                texts.append(text)
                tokenized_texts.append(self._tokenize(text))

                records.append({
                    'primary_table': cleaned['primary_table'],
                    'primary_key': cleaned['primary_key'],
                    'foreign_table': cleaned['foreign_table'],
                    'foreign_key': cleaned['foreign_key'],
                    'relationship_type': cleaned['relationship_type'],
                    'source': 'relationships',
                    'row_id': idx
                })

        logger.info(f"Created {len(texts)} focused relationship texts")

        if len(texts) == 0:
            logger.warning("No valid relationship texts created")
            return 0

        # Create BM25 index
        logger.info("🔍 Creating BM25 index...")
        self.relationships_bm25 = BM25Okapi(tokenized_texts)
        self.relationships_tokenized = tokenized_texts

        # Generate embeddings
        logger.info("🧠 Generating embeddings...")
        embeddings = self.model.encode(texts, show_progress_bar=True, convert_to_numpy=True)

        # Create FAISS index
        logger.info("📇 Creating FAISS index...")
        self.relationships_index = faiss.IndexFlatIP(self.embedding_dim)
        faiss.normalize_L2(embeddings)
        self.relationships_index.add(embeddings.astype('float32'))

        self.relationships_texts = texts
        self.relationships_records = records

        logger.info(f"✅ Embedded {len(texts)} relationship records")
        return len(texts)

    def load_and_embed_datamodel(self, csv_path: str) -> int:
        logger.info(f"🗂️ Loading data model from: {csv_path}")

        df = None
        for encoding in ['utf-8-sig', 'utf-8', 'latin-1', 'iso-8859-1']:
            try:
                df = pd.read_csv(csv_path, encoding=encoding)
                break
            except:
                continue

        if df is None:
            raise ValueError(f"Could not read CSV file: {csv_path}")

        df = df.fillna('')

        texts = []
        records = []
        tokenized_texts = []

        for idx, row in df.iterrows():
            text_parts = []

            for col in df.columns:
                col_clean = str(col).strip().lower()
                value = str(row[col]).strip()

                if col_clean and value and value != 'nan' and value != '':
                    text_parts.append(col_clean)
                    text_parts.append(value)

            if text_parts:
                text = " ".join(text_parts)
                texts.append(text)
                tokenized_texts.append(self._tokenize(text))

                record = {'source': 'datamodel', 'row_id': idx}
                for col in df.columns:
                    record[col] = row[col]
                records.append(record)

        if len(texts) == 0:
            return 0

        self.datamodel_bm25 = BM25Okapi(tokenized_texts)
        self.datamodel_tokenized = tokenized_texts

        embeddings = self.model.encode(texts, show_progress_bar=True, convert_to_numpy=True)

        self.datamodel_index = faiss.IndexFlatIP(self.embedding_dim)
        faiss.normalize_L2(embeddings)
        self.datamodel_index.add(embeddings.astype('float32'))

        self.datamodel_texts = texts
        self.datamodel_records = records

        logger.info(f"✅ Embedded {len(texts)} data model records")
        return len(texts)

    def _hybrid_search(self, query: str, texts: List[str], tokenized_texts: List[List[str]],
                       records: List[Dict], bm25_index, faiss_index, top_k: int = 10) -> List[Dict]:
        if not texts or not records:
            return []

        # Tokenize query
        query_tokens = self._tokenize(query)

        # BM25 scores
        bm25_scores = bm25_index.get_scores(query_tokens)

        # Normalize BM25 scores
        if bm25_scores.max() > 0:
            bm25_scores_norm = bm25_scores / bm25_scores.max()
        else:
            bm25_scores_norm = bm25_scores

        # Semantic scores
        query_embedding = self.model.encode([query], convert_to_numpy=True)
        faiss.normalize_L2(query_embedding)

        semantic_scores, indices = faiss_index.search(query_embedding.astype('float32'), len(texts))
        semantic_scores = semantic_scores[0]

        semantic_score_map = {idx: score for idx, score in zip(indices[0], semantic_scores)}

        # Combine scores
        hybrid_scores = []
        for i in range(len(records)):
            bm25_score = bm25_scores_norm[i] if i < len(bm25_scores_norm) else 0
            semantic_score = semantic_score_map.get(i, 0)

            # Weighted hybrid score
            hybrid_score = (self.bm25_weight * bm25_score) + (self.semantic_weight * semantic_score)

            hybrid_scores.append({
                'index': i,
                'bm25_score': float(bm25_score),
                'semantic_score': float(semantic_score),
                'hybrid_score': float(hybrid_score)
            })

        # Sort by hybrid score
        hybrid_scores.sort(key=lambda x: x['hybrid_score'], reverse=True)

        # Get top-k results
        results = []
        for score_info in hybrid_scores[:top_k]:
            idx = score_info['index']
            if idx < len(records):
                result = records[idx].copy()
                result['bm25_score'] = score_info['bm25_score']
                result['semantic_score'] = score_info['semantic_score']
                result['hybrid_score'] = score_info['hybrid_score']
                result['score'] = score_info['hybrid_score']
                result['text'] = texts[idx]
                results.append(result)

        return results

    def search_metadata(self, query: str, top_k: int = 5) -> List[Dict]:
        """Search metadata using hybrid search"""
        if self.metadata_index is None:
            return []

        return self._hybrid_search(
            query,
            self.metadata_texts,
            self.metadata_tokenized,
            self.metadata_records,
            self.metadata_bm25,
            self.metadata_index,
            top_k
        )

    def search_relationships(self, query: str, top_k: int = 5) -> List[Dict]:
        """Search relationships using hybrid search"""
        if self.relationships_index is None:
            return []

        return self._hybrid_search(
            query,
            self.relationships_texts,
            self.relationships_tokenized,
            self.relationships_records,
            self.relationships_bm25,
            self.relationships_index,
            top_k
        )

    def search_datamodel(self, query: str, top_k: int = 5) -> List[Dict]:
        """Search data model using hybrid search"""
        if self.datamodel_index is None:
            return []

        return self._hybrid_search(
            query,
            self.datamodel_texts,
            self.datamodel_tokenized,
            self.datamodel_records,
            self.datamodel_bm25,
            self.datamodel_index,
            top_k
        )

    def save_indices(self, save_dir: str):
        """Save indices to disk"""
        save_path = Path(save_dir)
        save_path.mkdir(parents=True, exist_ok=True)

        # Save FAISS indices
        if self.metadata_index:
            faiss.write_index(self.metadata_index, str(save_path / "metadata.index"))
        if self.relationships_index:
            faiss.write_index(self.relationships_index, str(save_path / "relationships.index"))
        if self.datamodel_index:
            faiss.write_index(self.datamodel_index, str(save_path / "datamodel.index"))

        # Save metadata
        metadata = {
            'metadata_texts': self.metadata_texts,
            'metadata_records': self.metadata_records,
            'metadata_tokenized': self.metadata_tokenized,
            'relationships_texts': self.relationships_texts,
            'relationships_records': self.relationships_records,
            'relationships_tokenized': self.relationships_tokenized,
            'datamodel_texts': self.datamodel_texts,
            'datamodel_records': self.datamodel_records,
            'datamodel_tokenized': self.datamodel_tokenized,
            'embedding_dim': self.embedding_dim,
            'bm25_weight': self.bm25_weight,
            'semantic_weight': self.semantic_weight
        }

        with open(save_path / "metadata_focused.pkl", 'wb') as f:
            pickle.dump(metadata, f)

        logger.info(f"✅ Saved indices to {save_dir}")

    def load_indices(self, load_dir: str):
        """Load indices from disk"""
        load_path = Path(load_dir)

        # Load FAISS indices
        if (load_path / "metadata.index").exists():
            self.metadata_index = faiss.read_index(str(load_path / "metadata.index"))
        if (load_path / "relationships.index").exists():
            self.relationships_index = faiss.read_index(str(load_path / "relationships.index"))
        if (load_path / "datamodel.index").exists():
            self.datamodel_index = faiss.read_index(str(load_path / "datamodel.index"))

        # Load metadata
        with open(load_path / "metadata_focused.pkl", 'rb') as f:
            metadata = pickle.load(f)

        self.metadata_texts = metadata['metadata_texts']
        self.metadata_records = metadata['metadata_records']
        self.metadata_tokenized = metadata['metadata_tokenized']
        self.relationships_texts = metadata['relationships_texts']
        self.relationships_records = metadata['relationships_records']
        self.relationships_tokenized = metadata['relationships_tokenized']
        self.datamodel_texts = metadata['datamodel_texts']
        self.datamodel_records = metadata['datamodel_records']
        self.datamodel_tokenized = metadata['datamodel_tokenized']
        self.embedding_dim = metadata['embedding_dim']
        self.bm25_weight = metadata.get('bm25_weight', 0.6)
        self.semantic_weight = metadata.get('semantic_weight', 0.4)

        # Rebuild BM25 indices
        if self.metadata_tokenized:
            self.metadata_bm25 = BM25Okapi(self.metadata_tokenized)
        if self.relationships_tokenized:
            self.relationships_bm25 = BM25Okapi(self.relationships_tokenized)
        if self.datamodel_tokenized:
            self.datamodel_bm25 = BM25Okapi(self.datamodel_tokenized)

        logger.info(f"✅ Loaded indices from {load_dir}")


# Backward compatibility
MetadataEmbedder = FocusedColumnEmbedder
HybridMetadataEmbedder = FocusedColumnEmbedder
