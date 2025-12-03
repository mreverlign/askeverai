"""
Script to rebuild RAG indices with focused column-based embedding strategy
"""

import logging
from rag_metadata_embedder_focused import FocusedColumnEmbedder

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    logger.info("="*80)
    logger.info("REBUILDING RAG INDICES WITH FOCUSED STRATEGY")
    logger.info("="*80)

    # Initialize embedder with optimized weights
    # Higher BM25 weight for better keyword matching
    embedder = FocusedColumnEmbedder(
        model_name="sentence-transformers/all-MiniLM-L6-v2",  # Faster, optimized for short text
        bm25_weight=0.7,  # Favor keyword matching
        semantic_weight=0.4  # Supplement with semantic
    )

    # Load CSV files
    logger.info("\n📊 Step 1: Loading Metadata...")
    try:
        embedder.load_and_embed_metadata("HighTower_Metadata(Metadata) (1).csv")
        logger.info("✅ Metadata loaded and embedded")
    except Exception as e:
        logger.error(f"❌ Error loading metadata: {e}")
        return

    logger.info("\n🔗 Step 2: Loading Relationships...")
    try:
        embedder.load_and_embed_relationships("HighTower_Metadata(Relationships).csv")
        logger.info("✅ Relationships loaded and embedded")
    except Exception as e:
        logger.error(f"❌ Error loading relationships: {e}")
        return

    logger.info("\n🗂️ Step 3: Loading Data Model...")
    try:
        embedder.load_and_embed_datamodel("HighTower_Metadata(HighTower_Data_Model) (2).csv")
        logger.info("✅ Data model loaded and embedded")
    except Exception as e:
        logger.error(f"❌ Error loading data model: {e}")
        return

    # Save indices
    logger.info("\n💾 Step 4: Saving indices...")
    save_dir = "./rag_indices_focused"
    embedder.save_indices(save_dir)
    logger.info(f"✅ Indices saved to {save_dir}")

    # Test search
    logger.info("\n🔍 Step 5: Testing search functionality...")
    test_queries = [
        "project orders",
        "dim_project fact_transaction_detail",
        "client sales",
        "join project transaction"
    ]

    for query in test_queries:
        logger.info(f"\n  Query: '{query}'")

        # Search metadata
        metadata_results = embedder.search_metadata(query, top_k=3)
        if metadata_results:
            logger.info(f"  📋 Top metadata match: {metadata_results[0]['table_name']}.{metadata_results[0]['column_name']} (score: {metadata_results[0]['hybrid_score']:.3f})")

        # Search relationships
        rel_results = embedder.search_relationships(query, top_k=3)
        if rel_results:
            logger.info(f"  🔗 Top relationship: {rel_results[0]['primary_table']} -> {rel_results[0]['foreign_table']} (score: {rel_results[0]['hybrid_score']:.3f})")

    logger.info("\n" + "="*80)
    logger.info("✅ REBUILD COMPLETE!")
    logger.info("="*80)
    logger.info(f"\nTo use the new indices:")
    logger.info(f"1. Update app_rag_enhanced.py to use 'rag_indices_focused' directory")
    logger.info(f"2. Or run: mv rag_indices_focused rag_indices_hybrid")
    logger.info(f"3. Restart your Streamlit app")


if __name__ == "__main__":
    main()
