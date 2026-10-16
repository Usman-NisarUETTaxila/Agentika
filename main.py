"""
InsightForge — RAG-powered Research Assistant (Streamlit UI)
==============================================================
Chat interface for the InsightForge RAG pipeline. Retrieves relevant
document chunks from Qdrant and generates grounded answers via
Google Gemini.

Prerequisites:
    1. Qdrant running locally at http://localhost:6333
    2. Documents already ingested into the 'Books' collection
    3. GEMINI_API_KEY environment variable set

Run with:
    streamlit run app.py
"""

import streamlit as st

from tool import query_db
from llm import generate_answer


st.set_page_config(
    page_title="InsightForge",
    layout="centered",
)

# ---------------------------------------------------------------------------
# Styling
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
    .stChatMessage { border-radius: 12px; }
    .source-chunk {
        background-color: rgba(120, 120, 120, 0.08);
        border-left: 3px solid #ff4b4b;
        padding: 0.5rem 0.75rem;
        margin-bottom: 0.5rem;
        border-radius: 4px;
        font-size: 0.85rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.title("InsightForge")
st.caption("RAG-Powered Document Research Assistant — ask questions about your ingested documents.")

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []  # list of {"role": ..., "content": ..., "chunks": [...]}

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Settings")
    show_sources = st.toggle("Show retrieved passages", value=True)
    st.divider()
    if st.button("🗑️ Clear conversation", use_container_width=True):
        st.session_state.messages = []
        st.rerun()
    st.divider()
    st.caption(
        "Prerequisites:\n"
        "- Qdrant running at `localhost:6333`\n"
        "- Documents ingested into the `Books` collection\n"
        "- `GEMINI_API_KEY` environment variable set"
    )

# ---------------------------------------------------------------------------
# Render chat history
# ---------------------------------------------------------------------------
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant" and show_sources and msg.get("chunks"):
            with st.expander(f"Sources ({len(msg['chunks'])})"):
                for i, chunk in enumerate(msg["chunks"], start=1):
                    st.markdown(
                        f'<div class="source-chunk"><b>Passage {i}</b><br>{chunk}</div>',
                        unsafe_allow_html=True,
                    )

# ---------------------------------------------------------------------------
# Chat input
# ---------------------------------------------------------------------------
question = st.chat_input("Ask a question about your documents...")

if question:
    # Display + store user message
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    # Retrieve + generate
    with st.chat_message("assistant"):
        with st.spinner("Searching documents..."):
            try:
                chunks = query_db(question, "Docs")
            except Exception as e:
                st.error(f"Error querying the vector database: {e}")
                st.stop()

        if not chunks:
            answer = "⚠️ No relevant passages found in the database."
            st.warning(answer)
            st.session_state.messages.append(
                {"role": "assistant", "content": answer, "chunks": []}
            )
        else:
            with st.spinner("Generating answer..."):
                try:
                    answer = generate_answer(question, chunks)
                except Exception as e:
                    answer = f"Error generating answer: {e}"
                    st.error(answer)
                    st.session_state.messages.append(
                        {"role": "assistant", "content": answer, "chunks": chunks}
                    )
                    st.stop()

            st.markdown(answer)

            if show_sources:
                with st.expander(f"Sources ({len(chunks)})"):
                    for i, chunk in enumerate(chunks, start=1):
                        st.markdown(
                            f'<div class="source-chunk"><b>Passage {i}</b><br>{chunk}</div>',
                            unsafe_allow_html=True,
                        )

            st.session_state.messages.append(
                {"role": "assistant", "content": answer, "chunks": chunks}
            )