"""
batch_ingest.py
================
Folder-level ingestion on top of doc_parser.py:

  - Parses multiple documents IN PARALLEL (one process per CPU core) --
    parsing different files is embarrassingly parallel, no reason to do it
    one-by-one.
  - Caches parsed output by file content hash, so re-running ingestion on a
    folder after adding a few new files only (re)parses what actually
    changed, not the whole corpus.
  - Also writes one human-readable JSON file per source document into
    parsed_docs/, named after the original file -- separate from the
    hash-keyed cache, meant for you to actually browse or hand to a chunker.
  - This step runs ONCE per document at ingestion time. It has zero effect
    on query-time latency -- that's governed only by retrieval + LLM
    generation against the already-built vector index.

Usage:
    from batch_ingest import ingest_folder

    results = ingest_folder("my_docs/", doc_type="auto", cache_dir=".parse_cache")
    for path, parsed in results.items():
        print(path, parsed["doc_type"], len(parsed["elements"]))
"""

from __future__ import annotations
import hashlib
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Optional
from qdrant_client import models
from llama_index.core.node_parser import SemanticSplitterNodeParser
from llama_index.core import Document
from .doc_parser import parse_document
from .qdrant_conn import ensure_source_index, get_client
from .gemini_embed import (
    EMBED_DIM,
    GeminiLlamaEmbedding,
    embed_documents,
)

embed_model = GeminiLlamaEmbedding()

semantic_parser = SemanticSplitterNodeParser(
    buffer_size=1,
    breakpoint_percentile_threshold=95,
    embed_model=embed_model,
)

def _get_semantic_chunks(text):
    d = Document(text=text) 
    nodes = semantic_parser.get_nodes_from_documents([d])
    return [n.text for n in nodes]
      

def _vectorize_points(data):
    import uuid
    records = []  # (chunk_text, original_point)

    for point in data:
        for chunk in _get_semantic_chunks(point["text"]):
            if chunk.strip():  # the embedding API rejects empty strings
                records.append((chunk, point))

    if not records:
        return []

    # One batched API call per ~50 chunks instead of one call per chunk.
    vectors = embed_documents([chunk for chunk, _ in records])

    return [
        models.PointStruct(
            id=uuid.uuid4().hex,
            vector={'semantic': vec},
            payload={
                "text": chunk,
                "source": point["source"],
                "page": point["page"],
                "element_type": point["element_type"],
                "level": point["level"]
            }
        )
        for (chunk, point), vec in zip(records, vectors)
    ]

def _upload_to_qdrant(points, collection_name="Docs"):
    client = get_client()  # QDRANT_URL / QDRANT_API_KEY from the environment

    if not client.collection_exists(collection_name):
        client.create_collection(
            collection_name=collection_name,
            vectors_config={
                'fixed': models.VectorParams(size=EMBED_DIM, distance=models.Distance.COSINE),
                'sentence': models.VectorParams(size=EMBED_DIM, distance=models.Distance.COSINE),
                'semantic': models.VectorParams(size=EMBED_DIM, distance=models.Distance.COSINE),
            },
        )
    else:
        # An existing collection built with MiniLM has 384-dim vectors and
        # cannot accept Gemini vectors.
        vc = client.get_collection(collection_name).config.params.vectors
        if isinstance(vc, dict) and "semantic" in vc and vc["semantic"].size != EMBED_DIM:
            raise RuntimeError(
                f"Collection '{collection_name}' has {vc['semantic'].size}-dim vectors but "
                f"the Gemini model is configured for {EMBED_DIM}. Delete the collection "
                f"(client.delete_collection('{collection_name}')) and re-ingest."
            )

    # Qdrant Cloud strict mode needs an index on any field used in a filter
    # (answer-from-chosen-context search and per-document delete use `source`).
    ensure_source_index(client, collection_name)

    upload_points = _vectorize_points(points)

    client.upload_points(
        collection_name=collection_name,
        points=upload_points
    )

    print(f"Uploaded Vectors to Qdrant collection '{collection_name}'")


def _file_hash(path: str, chunk_size: int = 1 << 20) -> str:
    """Content hash (not mtime) -- survives file copies/renames/re-uploads."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


def _cache_path(cache_dir: str, file_hash: str) -> str:
    return os.path.join(cache_dir, f"{file_hash}.json")


def _parse_one(args: tuple) -> tuple[str, dict, bool]:
    """
    Worker function run in a separate process. Returns
    (file_path, parsed_result, was_cached).
    """
    path, doc_type, id_patterns, include_tables, cache_dir = args

    file_hash = _file_hash(path)
    cache_file = _cache_path(cache_dir, file_hash)

    if os.path.exists(cache_file):
        with open(cache_file, "r") as f:
            return path, json.load(f), True

    result = parse_document(path, doc_type=doc_type,
                             id_patterns=id_patterns, include_tables=include_tables)
    result["_source_file"] = path
    result["_file_hash"] = file_hash

    os.makedirs(cache_dir, exist_ok=True)
    with open(cache_file, "w") as f:
        json.dump(result, f)

    return path, result, False


def _save_parsed_json(path: str, parsed: dict, base_folder: str, output_dir: str) -> str:
    """
    Writes the parsed result to output_dir, named after the SOURCE file
    (not its content hash) -- e.g. my_docs/policy.pdf -> parsed_docs/policy.json.
    Mirrors any subfolder structure under base_folder so same-named files in
    different subfolders don't collide.
  
    """

    # Preprocessing
    data = parsed
    source_file = data.get("_source_file", "unknown")
        
    points = []
    point_id_counter = 1
    
    # Iterate through all parsed elements
    for element in data.get("elements", []):
        el_type = element.get("type")
        
        # Skip table of contents entries to keep the vector space clean
        if el_type == "toc_entry":
            continue
            
        text = element.get("text", "").strip()
        if not text:
            continue
            
        # Construct the payload schema using normal numbering
        point = {
            "id": point_id_counter,
            "text": text,
            "source": source_file,
            "page": element.get("page"),
            "element_type": el_type,
            "level": element.get("level")
            }
        
        points.append(point)
        point_id_counter += 1

    rel_path = Path(path).resolve().relative_to(Path(base_folder).resolve())
    out_path = Path(output_dir) / rel_path.with_suffix(".json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(points, f, ensure_ascii=False, indent=2)

    return points


def ingest_folder(
    folder_path: str,
    doc_type: str = "auto",
    id_patterns: Optional[dict[str, str]] = None,
    include_tables: bool = True,
    cache_dir: str = ".parse_cache",
    output_dir: Optional[str] = "parsed_docs",
    max_workers: Optional[int] = None,
    extensions: tuple[str, ...] = (".pdf",),
) -> dict[str, dict]:
    """
    Parse every document in a folder, in parallel, with caching.

    Args:
        folder_path: directory containing documents to ingest.
        doc_type: passed through to parse_document per file. "auto" (default)
                  lets each file be classified independently -- appropriate
                  for a folder with mixed document types.
        id_patterns: passed through when doc_type == "standard".
        include_tables: passed through to parse_document.
        cache_dir: internal cache keyed by content hash -- speeds up re-runs,
                  not meant for browsing. Safe to point this at a persistent
                  location across ingestion runs.
        output_dir: if set (default "parsed_docs"), also writes one
                  human-readable JSON file per source document here, named
                  after the original file (e.g. book.pdf -> parsed_docs/book.json),
                  mirroring any subfolder structure. This is what you'd
                  inspect by hand or hand off to the chunker -- distinct from
                  cache_dir, which is keyed by hash and not meant for that.
                  Pass None to skip writing these.
        max_workers: process pool size. Defaults to os.cpu_count().
        extensions: file extensions to include.

    Returns:
        {file_path: parsed_result_dict, ...}
    """
    paths = [str(p) for p in Path(folder_path).rglob("*")
             if p.suffix.lower() in extensions]

    if not paths:
        return {}

    tasks = [(p, doc_type, id_patterns, include_tables, cache_dir) for p in paths]

    results: dict[str, dict] = {}
    all_points: list[dict] = []
    n_cached = 0
    t0 = time.time()

    with ProcessPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_parse_one, t): t[0] for t in tasks}
        for future in as_completed(futures):
            path, parsed, was_cached = future.result()
            results[path] = parsed
            n_cached += int(was_cached)

    elapsed = time.time() - t0
    print(f"Ingested {len(paths)} files in {elapsed:.2f}s "
          f"({n_cached} served from cache, {len(paths) - n_cached} freshly parsed)")

    if output_dir is not None:
        for path, parsed in results.items():
            # Saving to local storage
            ready_points = _save_parsed_json(path, parsed, folder_path, output_dir)
            all_points.extend(ready_points)

        print("Documents Parsed and Preprocessed for Vectorization")       
        print(f"Wrote {len(results)} parsed JSON files to {output_dir}/")

    # Uploading to Qdrant
    _upload_to_qdrant(all_points, collection_name="Docs")
    print("Documents Uploaded to Qdrant")
    return results


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python batch_ingest.py <folder_path>")
        sys.exit(1)

    out = ingest_folder(sys.argv[1])
    for path, parsed in out.items():
        print(f"{path}: doc_type={parsed['doc_type']}  elements={len(parsed['elements'])}")