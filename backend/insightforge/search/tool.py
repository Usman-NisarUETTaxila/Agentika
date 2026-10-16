r"""
tool.py - Qdrant search tool + LangGraph agent with context disambiguation.

Existing project code keeps working unchanged:
    from tool import query_db
    query_db("my question", "my_collection")

New agent entry points:
    from tool import ask_agent
    answer = ask_agent("my question", "my_collection")

Agent flow:
    retrieve -> analyze_contexts --(multiple contexts)--> ask_user -> answer -> END
                                 \--(single context)-----------------> answer -> END

The final answer is produced by your existing llm.generate_answer(question, chunks).
The LLM configured below (LLM_MODEL / LLM_PROVIDER) is only used to decide whether
the retrieved documents contain clashing contexts.

Environment variables (read from the process env or your .env):
    QDRANT_URL / QDRANT_API_KEY / QDRANT_TIMEOUT   -> see qdrant_conn.py
    GOOGLE_API_KEY    Gemini key for the clash check (or GEMINI_API_KEY)

Install extras:
    pip install "langgraph>=0.4" langchain langchain-google-genai pydantic python-dotenv
"""

import os
import uuid
from collections import defaultdict
from functools import lru_cache
from typing import Optional, TypedDict

from langchain.chat_models import init_chat_model
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from pydantic import BaseModel, Field
from qdrant_client import models
from sentence_transformers import SentenceTransformer

from .qdrant_conn import ensure_source_index as _ensure_source_index
from .qdrant_conn import get_client as _qdrant

# Load .env first: Django does not read it by itself, and the clash check runs
# before llm.py is ever imported.
try:
    from dotenv import find_dotenv, load_dotenv

    load_dotenv(find_dotenv())  # searches upward from this file
    load_dotenv(find_dotenv(usecwd=True))  # ...and from the working directory (manage.py)
except ImportError:  # python-dotenv not installed: rely on real environment variables
    pass

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
# Small/fast Gemini model used ONLY to detect clashing contexts.
# Needs GOOGLE_API_KEY in the environment. (gemini-2.5-* is being shut down;
# "gemini-3.1-flash-lite" is a cheaper alternative.)
LLM_MODEL = os.getenv("CONTEXT_LLM_MODEL", "gemini-3.6-flash")
LLM_PROVIDER = "google_genai"

encoder = SentenceTransformer("all-MiniLM-L6-v2")


@lru_cache(maxsize=1)
def _llm():
    # Created lazily so importing query_db never requires an LLM API key.
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Gemini API key not found. Add GOOGLE_API_KEY=... (or GEMINI_API_KEY=...) "
            "to your .env and restart the server."
        )
    # Temperature left at Gemini 3's default (Google advises against lowering it).
    return init_chat_model(LLM_MODEL, model_provider=LLM_PROVIDER, api_key=api_key)


# --------------------------------------------------------------------------- #
# Original tool (signature/behaviour preserved; `sources` is optional)
# --------------------------------------------------------------------------- #
def query_db(
    query: str,
    collectionName: str,
    sources: Optional[list[str]] = None,
    limit: int = 10,
) -> list[dict]:
    """
    Semantic search against the Qdrant collection.

    Returns up to `limit` payload dicts (keys: text, source, page, element_type, level).
    If `sources` is given, results are restricted to those documents.
    Returns an empty list if the collection does not exist yet (no docs uploaded).

    Note: All element types (headings, list items, tables, paragraphs, ...) are
    included so the LLM has the full context it needs to answer accurately.
    """
    client = _qdrant()

    # Guard: collection doesn't exist until the first document is uploaded
    if not client.collection_exists(collectionName):
        return []

    query_filter = None
    if sources:
        _ensure_source_index(client, collectionName)
        query_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="source", match=models.MatchAny(any=sources)
                )
            ]
        )

    results = client.query_points(
        collection_name=collectionName,
        query=encoder.encode(query).tolist(),
        using="semantic",
        query_filter=query_filter,
        limit=limit,
    )

    return [point.payload for point in results.points]


# --------------------------------------------------------------------------- #
# Structured output schema for context detection
# --------------------------------------------------------------------------- #
class Context(BaseModel):
    label: str = Field(description="Short human-friendly name for this context")
    description: str = Field(
        description="One sentence explaining how this context treats the topic"
    )
    sources: list[str] = Field(
        description="Exact `source` values (documents) that belong to this context"
    )


class ContextAnalysis(BaseModel):
    contexts: list[Context] = Field(
        description=(
            "Distinct contexts the retrieved documents discuss for the user's topic. "
            "Documents that agree / cover the same context must be merged into ONE "
            "context. Return a single context if there is no real ambiguity."
        )
    )


# --------------------------------------------------------------------------- #
# Graph state
# --------------------------------------------------------------------------- #
class AgentState(TypedDict, total=False):
    question: str
    collection: str
    chunks: list[dict]
    contexts: list[dict]  # only populated when >1 distinct context found
    selected_sources: list[str]  # sources of the context the user picked
    selected_label: str
    invalid_choice: bool
    answer: str


# --------------------------------------------------------------------------- #
# Nodes
# --------------------------------------------------------------------------- #
def retrieve(state: AgentState) -> dict:
    # Wider net than the final answer needs, so different documents/contexts
    # have a chance to show up.
    try:
        chunks = query_db(state["question"], state["collection"], limit=20)
    except Exception as e:
        raise RuntimeError(f"Vector search failed: {e}") from e
    return {"chunks": chunks, "contexts": [], "invalid_choice": False}


def analyze_contexts(state: AgentState) -> dict:
    by_source: dict[str, list[dict]] = defaultdict(list)
    for c in state["chunks"]:
        by_source[c.get("source", "unknown")].append(c)

    # Only one document -> nothing to disambiguate.
    if len(by_source) < 2:
        return {"contexts": []}

    excerpts = "\n\n".join(
        f"### source: {src}\n"
        + "\n".join(f"- {c.get('text', '')[:400]}" for c in items[:3])
        for src, items in by_source.items()
    )

    analysis: ContextAnalysis = _llm().with_structured_output(ContextAnalysis).invoke(
        f"User question: {state['question']}\n\n"
        f"Retrieved excerpts grouped by source document:\n{excerpts}\n\n"
        "Decide whether these documents discuss the topic in genuinely DIFFERENT "
        "contexts (e.g. different products, versions, domains, meanings of the "
        "same term, or conflicting scopes). Group documents that share the same "
        "context together. Use the exact source names given."
    )

    valid = set(by_source)
    contexts = []
    for ctx in analysis.contexts:
        srcs = [s for s in ctx.sources if s in valid]
        if srcs:
            contexts.append({**ctx.model_dump(), "sources": srcs})

    return {"contexts": contexts if len(contexts) > 1 else []}


def ask_user(state: AgentState) -> dict:
    contexts = state["contexts"]

    options = "\n".join(
        f"{i}. {c['label']} - {c['description']} (docs: {', '.join(c['sources'])})"
        for i, c in enumerate(contexts, start=1)
    )
    prompt = (
        "I found several different contexts for your question. "
        "Which one do you mean?\n\n"
        f"{options}\n\nReply with the number or the name."
    )
    if state.get("invalid_choice"):
        prompt = "Sorry, I couldn't match that to an option.\n\n" + prompt

    # Execution pauses here until resumed with Command(resume=...)
    reply = str(interrupt({"prompt": prompt, "options": contexts})).strip()

    chosen = None
    if reply.isdigit() and 1 <= int(reply) <= len(contexts):
        chosen = contexts[int(reply) - 1]
    else:
        for c in contexts:
            label = c["label"].lower()
            if reply.lower() in label or label in reply.lower():
                chosen = c
                break

    if chosen is None:
        return {"invalid_choice": True}

    return {
        "selected_sources": chosen["sources"],
        "selected_label": chosen["label"],
        "invalid_choice": False,
    }


def answer(state: AgentState) -> dict:
    # Imported lazily: keeps your existing LLM setup in llm.py and avoids any
    # circular import between tool.py and llm.py.
    from .llm import generate_answer

    sources = state.get("selected_sources")

    # If the user picked a context, re-query restricted to it so the answer
    # is grounded only in that context.
    try:
        chunks = (
            query_db(state["question"], state["collection"], sources=sources, limit=10)
            if sources
            else state["chunks"][:10]
        )
    except Exception as e:
        raise RuntimeError(f"Vector search failed: {e}") from e

    if not chunks:
        return {
            "answer": "No documents have been uploaded yet, or no relevant passages were found. "
            "Please upload a document first and then ask your question."
        }

    try:
        return {"answer": generate_answer(state["question"], chunks)}
    except Exception as e:
        raise RuntimeError(f"LLM generation failed: {e}") from e


# --------------------------------------------------------------------------- #
# Routing + graph
# --------------------------------------------------------------------------- #
def _after_analysis(state: AgentState) -> str:
    return "ask_user" if state.get("contexts") else "answer"


def _after_ask(state: AgentState) -> str:
    return "ask_user" if state.get("invalid_choice") else "answer"


def build_agent():
    g = StateGraph(AgentState)
    g.add_node("retrieve", retrieve)
    g.add_node("analyze_contexts", analyze_contexts)
    g.add_node("ask_user", ask_user)
    g.add_node("answer", answer)

    g.add_edge(START, "retrieve")
    g.add_edge("retrieve", "analyze_contexts")
    g.add_conditional_edges("analyze_contexts", _after_analysis, ["ask_user", "answer"])
    g.add_conditional_edges("ask_user", _after_ask, ["ask_user", "answer"])
    g.add_edge("answer", END)

    # A checkpointer is required for interrupt() to pause/resume.
    # Swap MemorySaver for a SQLite/Postgres saver if state must survive restarts.
    return g.compile(checkpointer=MemorySaver())


agent = build_agent()


# --------------------------------------------------------------------------- #
# Public helpers
# --------------------------------------------------------------------------- #
def ask_agent(question: str, collectionName: str, input_fn=input) -> str:
    """
    Blocking helper (CLI / scripts). If the agent needs the user to pick a
    context, it calls `input_fn(prompt)` and resumes with the reply.
    """
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    result = agent.invoke({"question": question, "collection": collectionName}, config)

    while "__interrupt__" in result:
        payload = result["__interrupt__"][0].value
        reply = input_fn(f"\nAgent: {payload['prompt']}\nYou: ")
        result = agent.invoke(Command(resume=reply), config)

    return result["answer"]


def start_agent(question: str, collectionName: str, thread_id: Optional[str] = None):
    """
    Non-blocking variant for web/API use. Returns (thread_id, result).
    If result contains "__interrupt__", show result["__interrupt__"][0].value["prompt"]
    to the user, then call resume_agent(thread_id, user_reply).
    """
    thread_id = thread_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    result = agent.invoke({"question": question, "collection": collectionName}, config)
    return thread_id, result


def resume_agent(thread_id: str, user_reply: str):
    config = {"configurable": {"thread_id": thread_id}}
    return agent.invoke(Command(resume=user_reply), config)