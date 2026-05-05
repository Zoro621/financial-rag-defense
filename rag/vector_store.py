"""
rag/vector_store.py
Builds and manages the FAISS vector index over knowledge-base chunks.
Saves embedding centroids (needed by Unit 2 Retrieval Integrity Checker).
"""

import os
import platform
if platform.system() == "Windows":
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import pickle
from pathlib import Path
from typing import List, Tuple

import numpy as np
from langchain.schema import Document
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    FAISS_INDEX_DIR, KB_STATS_PATH, CHUNKS_PKL_PATH,
    EMBEDDING_MODEL, TOP_K_RETRIEVAL,
)


class VectorStore:
    """
    Wraps a FAISS IndexFlatIP (inner-product / cosine on normalised vectors).

    Usage
    -----
    vs = VectorStore()
    vs.build(chunks)         # first run — creates index + computes kb_stats
    docs = vs.retrieve(query)
    """

    def __init__(
        self,
        index_dir: Path = FAISS_INDEX_DIR,
        kb_stats_path: Path = KB_STATS_PATH,
        embedding_model: str = EMBEDDING_MODEL,
        top_k: int = TOP_K_RETRIEVAL,
    ):
        self.index_dir     = Path(index_dir)
        self.kb_stats_path = Path(kb_stats_path)
        self.top_k         = top_k

        # HuggingFace embeddings (CPU-friendly, 384-dim, normalised internally)
        self.embeddings = HuggingFaceEmbeddings(
            model_name=embedding_model,
            encode_kwargs={"normalize_embeddings": True},
        )

        self._faiss: FAISS | None = None

    # ------------------------------------------------------------------ #
    def build(self, chunks: List[Document]) -> None:
        """
        Build FAISS index from a list of LangChain Document chunks.
        Also computes and saves centroid + per-dim std for Unit 2.
        """
        print(f"[VectorStore] Embedding {len(chunks)} chunks ...")
        texts    = [c.page_content for c in chunks]
        vectors  = np.array(
            self.embeddings.embed_documents(texts), dtype=np.float32
        )  # shape: (N, 384)

        # ---- Compute KB statistics for Retrieval Integrity Checker ---- #
        centroid   = vectors.mean(axis=0)          # (384,)
        per_dim_std = vectors.std(axis=0)          # (384,)
        global_std  = float(per_dim_std.mean())    # scalar

        kb_stats = {
            "centroid":   centroid,
            "std":        per_dim_std,
            "global_std": global_std,
        }
        self.kb_stats_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.kb_stats_path, "wb") as f:
            pickle.dump(kb_stats, f)
        print(f"[VectorStore] Saved kb_stats -> {self.kb_stats_path}")

        # ---- Build FAISS index ---------------------------------------- #
        self._faiss = FAISS.from_documents(chunks, self.embeddings)
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self._faiss.save_local(str(self.index_dir))
        print(f"[VectorStore] Saved FAISS index -> {self.index_dir}")

    # ------------------------------------------------------------------ #
    def load(self) -> None:
        """Load an existing FAISS index from disk."""
        self._faiss = FAISS.load_local(
            str(self.index_dir),
            self.embeddings,
            allow_dangerous_deserialization=True,
        )
        print(f"[VectorStore] Loaded FAISS index from {self.index_dir}")

    # ------------------------------------------------------------------ #
    def retrieve(
        self, query: str, top_k: int | None = None
    ) -> Tuple[List[Document], np.ndarray]:
        """
        Retrieve top-k chunks most similar to query.

        Returns
        -------
        (docs, embeddings_array)
            docs:             list of LangChain Document objects
            embeddings_array: (k, 384) numpy array of chunk embeddings
                              (passed to Unit 2 integrity checker)
        """
        if self._faiss is None:
            self.load()

        k = top_k or self.top_k
        docs = self._faiss.similarity_search(query, k=k)

        # Re-embed the returned chunks to get numpy vectors for Unit 2
        chunk_texts      = [d.page_content for d in docs]
        chunk_embeddings = np.array(
            self.embeddings.embed_documents(chunk_texts), dtype=np.float32
        )

        return docs, chunk_embeddings


# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    from rag.document_loader import DocumentLoader

    chunks = DocumentLoader.load_chunks(CHUNKS_PKL_PATH)
    vs = VectorStore()
    vs.build(chunks)
    print("Index built successfully.")
