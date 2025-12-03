"""
Enhanced Setup Script for Hybrid RAG System
Creates BM25 + Semantic embeddings from metadata CSVs
"""

import sys
from pathlib import Path
from rag_metadata_embedder_hybrid import HybridMetadataEmbedder
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Main setup function"""
    print("="*80)
    print("🚀 Enhanced Hybrid RAG System - Setup Script")
    print("   (BM25 + Semantic Search with Improved Relationships)")
    print("="*80)
    print()
    
    # Define paths - UPDATE THESE TO YOUR CSV PATHS
    metadata_csv = "/Users/Arham/Desktop/askeverai_version_1/HighTower_Metadata(Metadata) (1).csv"
    relationships_csv = "/Users/Arham/Desktop/askeverai_version_1/HighTower_Metadata(Relationships).csv"
    datamodel_csv = "/Users/Arham/Desktop/askeverai_version_1/HighTower_Metadata(HighTower_Data_Model) (2).csv"
    indices_dir = "./rag_indices_hybrid"
    
    # Check if CSVs exist
    missing_files = []
    for csv_file in [metadata_csv, relationships_csv, datamodel_csv]:
        if not Path(csv_file).exists():
            missing_files.append(csv_file)
    
    if missing_files:
        print("❌ ERROR: The following CSV files are missing:")
        for file in missing_files:
            print(f"   - {file}")
        print()
        print("Please ensure all CSV files are in the current directory or update paths in setup script.")
        sys.exit(1)
    
    print("✅ All CSV files found")
    print()
    
    # Initialize hybrid embedder
    print("🔧 Initializing Hybrid Embedder...")
    print("   - BM25 for keyword matching")
    print("   - Semantic embeddings for conceptual similarity")
    print("   - Model: paraphrase-multilingual-mpnet-base-v2")
    print()
    
    embedder = HybridMetadataEmbedder(
        bm25_weight=0.5,  # 50% weight for keyword matching
        semantic_weight=0.5  # 50% weight for semantic similarity
    )
    print()
    
    # Load and embed metadata
    print("📊 Processing Metadata CSV...")
    print("   - Creating enhanced text representations")
    print("   - Building BM25 index for keyword matching")
    print("   - Generating semantic embeddings")
    metadata_count = embedder.load_and_embed_metadata(metadata_csv)
    print(f"   ✅ Embedded {metadata_count} metadata records")
    print()
    
    # Load and embed relationships
    print("🔗 Processing Relationships CSV...")
    print("   - Creating FULLY QUALIFIED join conditions")
    print("   - Building BM25 index for exact table/key matching")
    print("   - Generating semantic embeddings")
    relationships_count = embedder.load_and_embed_relationships(relationships_csv)
    print(f"   ✅ Embedded {relationships_count} relationship records")
    print()
    
    # Load and embed data model
    print("🗂️ Processing Data Model CSV...")
    print("   - Extracting table structure information")
    print("   - Building hybrid index")
    datamodel_count = embedder.load_and_embed_datamodel(datamodel_csv)
    print(f"   ✅ Embedded {datamodel_count} data model records")
    print()
    
    # Save indices
    print(f"💾 Saving hybrid indices to {indices_dir}/...")
    embedder.save_indices(indices_dir)
    print("   ✅ Indices saved successfully")
    print()
    
    # Test hybrid search
    print("="*80)
    print("🧪 Testing Hybrid Search (BM25 + Semantic)")
    print("="*80)
    print()
    
    test_queries = [
        "customer sales",
        "join client with transactions",
        "dim_client clientid",
        "product categories",
        "fact_transaction_detail"
    ]
    
    for query in test_queries:
        print(f"🔍 Query: '{query}'")
        print("-" * 80)
        
        results = embedder.search_all(query, top_k=3)
        
        # Show top metadata result
        if results['metadata']:
            top = results['metadata'][0]
            print(f"   📊 Top Metadata Match:")
            print(f"      {top.get('table_name', '')}.{top.get('column_name', '')}")
            print(f"      Hybrid Score: {top.get('hybrid_score', 0):.3f} (BM25: {top.get('bm25_score', 0):.3f}, Semantic: {top.get('semantic_score', 0):.3f})")
            if top.get('description'):
                desc = top['description'][:80] + "..." if len(top['description']) > 80 else top['description']
                print(f"      Description: {desc}")
        
        # Show top relationship result
        if results['relationships']:
            top = results['relationships'][0]
            print(f"   🔗 Top Relationship Match:")
            print(f"      {top.get('primary_table', '')} → {top.get('foreign_table', '')}")
            
            # Show fully qualified join condition
            if top.get('primary_key') and top.get('foreign_key'):
                join_cond = f"{top.get('primary_table', '')}.{top.get('primary_key', '')} = {top.get('foreign_table', '')}.{top.get('foreign_key', '')}"
                print(f"      JOIN: {join_cond}")
            
            print(f"      Hybrid Score: {top.get('hybrid_score', 0):.3f} (BM25: {top.get('bm25_score', 0):.3f}, Semantic: {top.get('semantic_score', 0):.3f})")
        
        print()
    
    print("="*80)
    print("✅ Enhanced Hybrid RAG Setup Complete!")
    print("="*80)
    print()
    print("🎯 Key Improvements:")
    print("   1. ✅ Hybrid search (BM25 + Semantic) for better accuracy")
    print("   2. ✅ Fully qualified join conditions (table.key = table.key)")
    print("   3. ✅ Enhanced text representations for better matching")
    print("   4. ✅ Multiple keyword variations for exact matches")
    print("   5. ✅ Improved relationship extraction")
    print()
    print("📱 Next Steps:")
    print("   1. Run the test script: python test_hybrid_rag.py")
    print("   2. Update your application to use the new embedder")
    print("   3. Run the Streamlit app: streamlit run app_rag_enhanced_v2.py")
    print()


if __name__ == "__main__":
    main()