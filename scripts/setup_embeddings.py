#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import logging
from pathlib import Path
from src.embedders.structured_embedder import StructuredMetadataEmbedder

logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def main():
    print("="*80)
    print("Structured RAG System Setup")
    print("="*80)

    olap_schema = "/Users/Arham/Desktop/askeverai_version_1/data/schemas/HighTowerDataModelSchemaOLAP.csv"
    oltp_schema = "/Users/Arham/Desktop/askeverai_version_1/data/schemas/HighTower_DataModel_Schema(OLTP).csv"
    relationships = "/Users/Arham/Desktop/askeverai_version_1/data/schemas/HighTowerDataModelSchema.csv"
    indices_dir = "/Users/Arham/Desktop/askeverai_version_1/data/indices/rag_indices"

    missing_files = []
    for file in [olap_schema, oltp_schema, relationships]:
        if not Path(file).exists():
            missing_files.append(file)

    if missing_files:
        print("Missing files:")
        for file in missing_files:
            print(f"  - {file}")
        sys.exit(1)

    print("All schema files found\n")

    if Path(indices_dir).exists():
        print("Removing old indices")
        import shutil
        shutil.rmtree(indices_dir)

    embedder = StructuredMetadataEmbedder(bm25_weight=0.6, semantic_weight=0.4)

    print("Processing OLAP columns...")
    olap_col_count = embedder.load_and_embed_olap_columns(olap_schema)

    print("Processing OLTP columns...")
    oltp_col_count = embedder.load_and_embed_oltp_columns(oltp_schema)

    print("Processing OLAP tables...")
    olap_tbl_count = embedder.load_and_embed_olap_tables(olap_schema)

    print("Processing OLTP tables...")
    oltp_tbl_count = embedder.load_and_embed_oltp_tables(oltp_schema)

    print("Processing relationships...")
    rel_count = embedder.load_and_embed_relationships(relationships)

    print(f"Saving to {indices_dir}...")
    embedder.save_indices(indices_dir)
    print("Saved\n")

    print("="*80)
    print("Testing")
    print("="*80)

    test_queries = ["client sales revenue", "product category"]

    for query in test_queries:
        print(f"\nQuery: '{query}'")
        layer_result = embedder.search_with_layer_preference(query, top_k=2)
        print(f"  Recommended DB: {layer_result['recommended_db']}")

        recommended_layer = layer_result['recommended_db']
        columns = embedder.search_columns(query, layer=recommended_layer, top_k=1)
        if columns:
            top = columns[0]
            print(f"  Column: {top.get('table')}.{top.get('column')} ({top.get('role')})")

    print("\n" + "="*80)
    print("Setup Complete")
    print("="*80)
    print(f"\nEmbeddings:")
    print(f"  OLAP Columns: {olap_col_count}")
    print(f"  OLTP Columns: {oltp_col_count}")
    print(f"  OLAP Tables: {olap_tbl_count}")
    print(f"  OLTP Tables: {oltp_tbl_count}")
    print(f"  Relationships: {rel_count}\n")


if __name__ == "__main__":
    main()
