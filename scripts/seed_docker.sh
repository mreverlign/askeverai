#!/bin/sh
# One-shot seed for Docker: CSV → Postgres, then schema CSVs → RAG indices.
set -e

echo "=== 1/2 Ingesting OLAP/OLTP CSVs into Postgres ==="
python scripts/ingest_dual_servers.py --yes

echo "=== 2/2 Building RAG embeddings/indices ==="
python scripts/setup_embeddings.py

echo "=== Seed complete ==="
