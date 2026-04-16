"""Persisted ChromaDB index over the runbook library.

Embeddings are Chroma's default ONNX all-MiniLM-L6-v2 — fully local, no API
key, downloaded and cached on first use — so semantic retrieval works even in
MOCK_LLM mode. Runbooks are split per markdown section (LangChain's
MarkdownHeaderTextSplitter) so a query built from an alert + log lines lands
on the matching Symptoms/Mitigation section, not just the right file.

Indexing is fingerprint-guarded: the collection stores a content hash of the
runbook files and rebuilds only when they change.
"""

from __future__ import annotations

import asyncio
import hashlib
import threading
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import chromadb
from langchain_text_splitters import MarkdownHeaderTextSplitter

from app.config import get_settings

COLLECTION = "runbooks"
_HEADERS = [("#", "title"), ("##", "section")]


@dataclass(frozen=True)
class RunbookChunk:
    source: str
    title: str
    section: str
    content: str
    score: float  # 1 - cosine distance; higher is better


class RunbookIndex:
    def __init__(self, persist_dir: Path, runbooks_dir: Path) -> None:
        self.persist_dir = Path(persist_dir)
        self.runbooks_dir = Path(runbooks_dir)
        self._collection = None
        self._lock = threading.Lock()

    @property
    def collection_id(self):
        return self._collection.id if self._collection is not None else None

    # -- indexing ----------------------------------------------------------

    def ensure_indexed(self) -> int:
        """Idempotent build. Returns the chunk count."""
        with self._lock:
            return self._ensure_locked().count()

    def _ensure_locked(self):
        if self._collection is not None:
            return self._collection

        client = chromadb.PersistentClient(
            path=str(self.persist_dir),
            settings=chromadb.Settings(anonymized_telemetry=False),
        )
        collection = client.get_or_create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})
        self._collection = collection
        return collection
