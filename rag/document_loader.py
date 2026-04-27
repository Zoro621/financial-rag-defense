"""
rag/document_loader.py
Loads raw documents from the RBC knowledge base and splits them into chunks.
Saves processed chunks to data/processed/chunks.pkl.
"""

import os
import pickle
from pathlib import Path
from typing import List

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import Document

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    RAW_DOCS_DIR, CHUNKS_PKL_PATH,
    CHUNK_SIZE, CHUNK_OVERLAP,
)


SUPPORTED_EXTENSIONS = {".txt", ".md", ".csv"}


class DocumentLoader:
    """
    Loads all supported documents from RAW_DOCS_DIR,
    splits them into fixed-size chunks, and persists them.
    """

    def __init__(
        self,
        raw_docs_dir: Path = RAW_DOCS_DIR,
        chunks_path: Path = CHUNKS_PKL_PATH,
        chunk_size: int = CHUNK_SIZE,
        chunk_overlap: int = CHUNK_OVERLAP,
    ):
        self.raw_docs_dir = Path(raw_docs_dir)
        self.chunks_path = Path(chunks_path)
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
        )

    # ------------------------------------------------------------------ #
    def load_raw_documents(self) -> List[Document]:
        """Read all supported files from raw_docs_dir into LangChain Documents."""
        docs: List[Document] = []

        for fpath in sorted(self.raw_docs_dir.rglob("*")):
            if fpath.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            try:
                text = fpath.read_text(encoding="utf-8", errors="replace")
            except Exception as e:
                print(f"[WARN] Could not read {fpath}: {e}")
                continue

            docs.append(
                Document(
                    page_content=text,
                    metadata={"source": str(fpath.relative_to(self.raw_docs_dir))},
                )
            )

        print(f"[DocumentLoader] Loaded {len(docs)} raw documents.")
        return docs

    # ------------------------------------------------------------------ #
    def split_documents(self, docs: List[Document]) -> List[Document]:
        """Split raw documents into chunks; preserve source metadata."""
        chunks = self.splitter.split_documents(docs)
        print(f"[DocumentLoader] Produced {len(chunks)} chunks.")
        return chunks

    # ------------------------------------------------------------------ #
    def save_chunks(self, chunks: List[Document]) -> None:
        self.chunks_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.chunks_path, "wb") as f:
            pickle.dump(chunks, f)
        print(f"[DocumentLoader] Saved chunks → {self.chunks_path}")

    # ------------------------------------------------------------------ #
    @staticmethod
    def load_chunks(chunks_path: Path = CHUNKS_PKL_PATH) -> List[Document]:
        with open(chunks_path, "rb") as f:
            return pickle.load(f)

    # ------------------------------------------------------------------ #
    def run(self) -> List[Document]:
        """Full pipeline: load → split → save → return."""
        docs   = self.load_raw_documents()
        chunks = self.split_documents(docs)
        self.save_chunks(chunks)
        return chunks


# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    loader = DocumentLoader()
    loader.run()
