"""
gemini_embed.py
===============
Single place that talks to the Gemini embedding API. Both batch_ingest.py
(documents) and tool.py (queries) import from here, so they are guaranteed to
use the same model and the same vector size.

Environment variables (process env or .env):
    GOOGLE_API_KEY / GEMINI_API_KEY   Gemini key
    GEMINI_EMBED_MODEL                default "gemini-embedding-001"
    GEMINI_EMBED_DIM                  default 768  (gemini-embedding-001 supports
                                      any value 128-3072; 768 / 1536 / 3072 are
                                      the recommended ones)

Install:
    pip install google-genai llama-index-core python-dotenv
"""

from __future__ import annotations

import math
import os
import time
from functools import lru_cache

try:
    from dotenv import find_dotenv, load_dotenv

    load_dotenv(find_dotenv())
    load_dotenv(find_dotenv(usecwd=True))
except ImportError:
    pass

from google import genai
from google.genai import types
from llama_index.core.base.embeddings.base import BaseEmbedding

EMBED_MODEL = os.getenv("GEMINI_EMBED_MODEL", "gemini-embedding-001")
EMBED_DIM = int(os.getenv("GEMINI_EMBED_DIM", "768"))

_BATCH_SIZE = 50  # API accepts up to 100 texts per call; stay well under
_MAX_RETRIES = 6


@lru_cache(maxsize=1)
def _client() -> genai.Client:
    # Lazy + cached: importing this module never needs a key, and each worker
    # process builds its own client on first use.
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Gemini API key not found. Add GOOGLE_API_KEY=... (or GEMINI_API_KEY=...) "
            "to your .env and restart."
        )
    return genai.Client(api_key=api_key)


def _normalize(vec: list[float]) -> list[float]:
    # Gemini only returns pre-normalized vectors at the full 3072 dims;
    # truncated sizes must be normalized by the caller.
    norm = math.sqrt(sum(x * x for x in vec))
    return [x / norm for x in vec] if norm else vec


def _embed(texts: list[str], task_type: str) -> list[list[float]]:
    if not texts:
        return []

    out: list[list[float]] = []
    for i in range(0, len(texts), _BATCH_SIZE):
        batch = texts[i : i + _BATCH_SIZE]
        for attempt in range(_MAX_RETRIES):
            try:
                resp = _client().models.embed_content(
                    model=EMBED_MODEL,
                    contents=batch,
                    config=types.EmbedContentConfig(
                        task_type=task_type,
                        output_dimensionality=EMBED_DIM,
                    ),
                )
                out.extend(_normalize(list(e.values)) for e in resp.embeddings)
                break
            except Exception:
                # Rate limits (429) / transient 5xx: exponential backoff.
                if attempt == _MAX_RETRIES - 1:
                    raise
                time.sleep(2**attempt)
    return out


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embed passages/chunks that will be stored in Qdrant."""
    return _embed(texts, "RETRIEVAL_DOCUMENT")


def embed_query(text: str) -> list[float]:
    """Embed a user question for searching the stored chunks."""
    return _embed([text], "RETRIEVAL_QUERY")[0]


# --------------------------------------------------------------------------- #
# LlamaIndex adapter (used by SemanticSplitterNodeParser)
# --------------------------------------------------------------------------- #
class GeminiLlamaEmbedding(BaseEmbedding):
    """Minimal LlamaIndex embedding wrapper around the helpers above.

    Uses the SEMANTIC_SIMILARITY task type since the splitter compares
    neighbouring sentences with each other (not query vs. document).
    """

    def __init__(self, **kwargs):
        kwargs.setdefault("model_name", EMBED_MODEL)
        kwargs.setdefault("embed_batch_size", 50)
        super().__init__(**kwargs)

    @classmethod
    def class_name(cls) -> str:
        return "GeminiLlamaEmbedding"

    def _get_query_embedding(self, query: str) -> list[float]:
        return _embed([query], "SEMANTIC_SIMILARITY")[0]

    async def _aget_query_embedding(self, query: str) -> list[float]:
        return self._get_query_embedding(query)

    def _get_text_embedding(self, text: str) -> list[float]:
        return _embed([text], "SEMANTIC_SIMILARITY")[0]

    def _get_text_embeddings(self, texts: list[str]) -> list[list[float]]:
        return _embed(texts, "SEMANTIC_SIMILARITY")