"""Build or refresh the persisted runbook vector index (also downloads the
embedding model on first run, which otherwise happens lazily on first search).

    python -m app.rag.index
    docker compose exec backend python -m app.rag.index
"""

from app.rag.store import get_runbook_index


def main() -> None:
    index = get_runbook_index()
    count = index.ensure_indexed()
    print(f"Runbook index ready: {count} chunks in {index.persist_dir}")


if __name__ == "__main__":
    main()
