"""
qdrant_conn.py - single place for Qdrant Cloud connection settings.

Used by tool.py (search), batchingest.py (ingestion) and the documents views
(delete), so credentials live in one spot and come only from the environment:

    QDRANT_URL        e.g. https://xxxx.region.cloud.qdrant.io:6333
    QDRANT_API_KEY    your Qdrant Cloud API key
    QDRANT_TIMEOUT    optional, seconds (default 30)

Deliberately lightweight (no ML / LangGraph imports) so process-pool workers
that import batchingest.py don't pay for anything extra.
"""

import os
from functools import lru_cache

from qdrant_client import QdrantClient, models

# Load .env: Django does not read it by itself.
try:
    from dotenv import find_dotenv, load_dotenv

    load_dotenv(find_dotenv())  # searches upward from this file
    load_dotenv(find_dotenv(usecwd=True))  # ...and from the working directory (manage.py)
except ImportError:  # python-dotenv not installed: rely on real environment variables
    pass


@lru_cache(maxsize=1)
def get_client() -> QdrantClient:
    """One shared client per process, built from QDRANT_URL / QDRANT_API_KEY."""
    url = os.getenv("QDRANT_URL")
    api_key = os.getenv("QDRANT_API_KEY")
    if not url:
        raise RuntimeError(
            "QDRANT_URL is not set. Add QDRANT_URL=... and QDRANT_API_KEY=... "
            "to your .env and restart the server."
        )
    if not api_key and not any(h in url for h in ("localhost", "127.0.0.1")):
        raise RuntimeError(
            "QDRANT_API_KEY is not set. Add QDRANT_API_KEY=... to your .env "
            "and restart the server."
        )
    return QdrantClient(
        url=url,
        api_key=api_key,
        timeout=int(os.getenv("QDRANT_TIMEOUT", "30")),
    )


_source_indexed: set[str] = set()


def ensure_source_index(client: QdrantClient, collection_name: str) -> None:
    """
    Qdrant Cloud enables strict mode by default, which rejects filtered reads
    AND filtered deletes on payload fields that have no index. Both the
    "answer from the chosen context" search and per-document delete filter on
    `source`, so make sure it has a keyword index (creating an existing index
    is a harmless no-op).
    """
    if collection_name in _source_indexed:
        return
    try:
        client.create_payload_index(
            collection_name=collection_name,
            field_name="source",
            field_schema=models.PayloadSchemaType.KEYWORD,
            wait=True,
        )
        _source_indexed.add(collection_name)
    except Exception:
        # e.g. a read-only API key. Carry on: if the index really is missing,
        # the actual operation fails with Qdrant's own (descriptive) error.
        pass