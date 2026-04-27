"""
data_setup/build_index.py
Step 2 of execution order: build FAISS index from processed chunks.

Run after setup_datasets.py and after running DocumentLoader.

Usage:
    python data_setup/build_index.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import CHUNKS_PKL_PATH
from rag.document_loader import DocumentLoader
from rag.vector_store import VectorStore


if __name__ == "__main__":
    print("=== Building FAISS Index ===")

    # Load or create chunks
    if CHUNKS_PKL_PATH.exists():
        print(f"Loading existing chunks from {CHUNKS_PKL_PATH} …")
        chunks = DocumentLoader.load_chunks()
    else:
        print("Chunks not found — running DocumentLoader …")
        loader = DocumentLoader()
        chunks = loader.run()

    # Build vector store
    vs = VectorStore()
    vs.build(chunks)

    print("\n✅ Index build complete.")
    print(f"   Chunks:   {len(chunks)}")
    print(f"   Index:    {vs.index_dir}")
    print(f"   KB stats: {vs.kb_stats_path}")
