"""
llm.py
======
LLM integration for the InsightForge RAG pipeline using LangChain.

Takes retrieved context chunks (from tool.query_db) and generates grounded,
citation-backed answers via Google Gemini through LangChain.

Usage:
    from llm import generate_answer

    chunks = query_db("What is defense in depth?")
    answer = generate_answer("What is defense in depth?", chunks)
    print(answer)

Environment:
    GEMINI_API_KEY  — required, get one at https://aistudio.google.com/apikey
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

load_dotenv()


# Client setup

_api_key = os.environ.get("GEMINI_API_KEY")
if not _api_key:
    raise EnvironmentError(
        "GEMINI_API_KEY environment variable is not set.\n"
        "Get a free key at https://aistudio.google.com/apikey and run:\n"
        "  set GEMINI_API_KEY=your-key-here   (Windows)\n"
        "  export GEMINI_API_KEY=your-key-here (Linux/macOS)"
    )

llm = ChatGoogleGenerativeAI(
    model="gemini-3.5-flash",
    google_api_key=_api_key,
)


# Prompt template

SYSTEM_PROMPT = """\
You are InsightForge, an expert research assistant.

RULES:
1. Answer the user's question using ONLY the context passages provided below.
2. If the provided context does not contain enough information to answer the
   question, say: "I don't have enough information in the loaded documents to
   answer that."
3. Do NOT fabricate information or use knowledge outside the provided context.
4. Be concise but thorough. Use bullet points or numbered lists when helpful.
5. When multiple passages support the same point, prefer the most specific one.
"""

prompt = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    ("human", "Context:\n{context}\n\nQuestion: {question}"),
])


# Chain

chain = prompt | llm | StrOutputParser()


# Context formatting

def _format_context(chunks: list[dict]) -> str:
    """
    Turn the list of payload dicts returned by query_db into numbered
    passages the LLM can reference.
    """
    if not chunks:
        return "(No relevant passages were retrieved.)"

    parts = []
    for i, chunk in enumerate(chunks, 1):
        source = chunk.get("source", "unknown")
        page = chunk.get("page", "?")
        text = chunk.get("text", "")
        parts.append(
            f"--- Passage {i} [Source: {source}, Page {page}] ---\n{text}"
        )
    return "\n\n".join(parts)


# Public API

def generate_answer(query: str, context_chunks: list[dict]) -> str:
    """
    Generate a grounded answer for *query* given retrieved *context_chunks*.

    Args:
        query: the user's natural-language question.
        context_chunks: list of payload dicts from tool.query_db(), each
            containing at least {text, source, page}.

    Returns:
        The model's answer as a plain string.
    """
    context_block = _format_context(context_chunks)

    answer = chain.invoke({
        "context": context_block,
        "question": query,
    })

    return answer or "(The model returned an empty response.)"
