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
        fingerprint = self._fingerprint()
        try:
            existing = client.get_collection(COLLECTION)
            if (existing.metadata or {}).get("fingerprint") == fingerprint and existing.count():
                self._collection = existing
                return existing
            client.delete_collection(COLLECTION)
        except Exception:
            # collection doesn't exist yet — the raised type varies across chroma versions
            pass

        collection = client.create_collection(
            COLLECTION, metadata={"hnsw:space": "cosine", "fingerprint": fingerprint}
        )
        splitter = MarkdownHeaderTextSplitter(headers_to_split_on=_HEADERS)
        ids: list[str] = []
        documents: list[str] = []
        metadatas: list[dict] = []
        for path in sorted(self.runbooks_dir.glob("*.md")):
            for i, doc in enumerate(splitter.split_text(path.read_text())):
                title = doc.metadata.get("title", path.stem)
                section = doc.metadata.get("section", "")
                ids.append(f"{path.name}#{i}")
                # headers prepended so section context shapes the embedding
                documents.append(f"{title}\n{section}\n{doc.page_content}")
                metadatas.append({"source": path.name, "title": title, "section": section})

        collection.add(ids=ids, documents=documents, metadatas=metadatas)
        self._collection = collection
        return collection

    def _fingerprint(self) -> str:
        digest = hashlib.sha256()
        for path in sorted(self.runbooks_dir.glob("*.md")):
            digest.update(path.name.encode())
            digest.update(path.read_bytes())
        return digest.hexdigest()

    # -- retrieval ----------------------------------------------------------

    def search_sync(self, query: str, k: int = 4) -> list[RunbookChunk]:
        with self._lock:
            collection = self._ensure_locked()
            n = min(k, collection.count())
            if n == 0:
                return []
            result = collection.query(
                query_texts=[query],
                n_results=n,
                include=["documents", "metadatas", "distances"],
            )

        return [
            RunbookChunk(
                source=meta["source"],
                title=meta.get("title", ""),
                section=meta.get("section", ""),
                content=doc,
                score=round(1 - dist, 4),
            )
            for doc, meta, dist in zip(
                result["documents"][0], result["metadatas"][0], result["distances"][0]
            )
        ]

    async def search(self, query: str, k: int = 4) -> list[RunbookChunk]:
        # chroma + onnx inference are sync and CPU-bound; keep them off the event loop
        return await asyncio.to_thread(self.search_sync, query, k)
