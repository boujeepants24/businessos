"""MCP server: exposes the knowledge base as tools any MCP client can use (Claude Desktop,
Claude Code, or your own agent).

Tools
  search_knowledge  ranked passages for a query (no model call, free)
  ask               a grounded, cited answer from Claude
  list_sources      documents in the index
  index_status      counts, embedder, folder
  reindex           re-read the knowledge folder (only if DOMAINRAG_ALLOW_REINDEX=1)
Resource
  knowledge://chunk/{chunk_id}   the full text of one passage

stdout belongs to the MCP protocol on the stdio transport, so all logging goes to stderr.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from mcp.server.mcpserver import MCPServer

from .answer import Answerer, AnswerError
from .chunking import section_label
from .config import Settings
from .embeddings import Embedder
from .ingest import ingest
from .retrieval import Retriever
from .store import Store

log = logging.getLogger(__name__)

MAX_QUERY_CHARS = 2000
_CHUNK_ID = re.compile(r"^[0-9a-f]{16}$")


class ToolInputError(ValueError):
    pass


def _check_query(text: str, name: str = "query") -> str:
    text = (text or "").strip()
    if not text:
        raise ToolInputError(f"{name} must not be empty")
    if len(text) > MAX_QUERY_CHARS:
        raise ToolInputError(f"{name} must be at most {MAX_QUERY_CHARS} characters")
    return text


def build_server(settings: Settings, store: Store, embedder: Embedder, answerer: Answerer) -> MCPServer:
    retriever = Retriever(store, embedder)
    server = MCPServer(
        name="domain-rag",
        instructions=(
            f"Knowledge base about {settings.domain}. Use search_knowledge to find passages, or ask for a "
            "cited answer. Answers come only from the indexed documents; if ask returns answerable=false, "
            "the documents don't cover the question."
        ),
    )

    @server.tool(
        description="Find the passages most relevant to a query. Returns text with source and section. Free: no model call."
    )
    def search_knowledge(query: str, top_k: int = 5) -> list[dict[str, Any]]:
        q = _check_query(query)
        k = max(1, min(int(top_k), 20))
        return [
            {
                "chunk_id": h.chunk.id,
                "source": h.chunk.source,
                "section": section_label(h.chunk.title, h.chunk.heading),
                "text": h.chunk.text,
                "score": round(h.score, 5),
                "matched_by": [m for m, r in (("keyword", h.keyword_rank), ("vector", h.vector_rank)) if r],
            }
            for h in retriever.search(q, k=k)
        ]

    @server.tool(
        description="Answer a question using only the knowledge base, with citations. answerable=false means the documents don't contain the answer."
    )
    def ask(question: str) -> dict[str, Any]:
        q = _check_query(question, "question")
        hits = retriever.search(q, k=settings.top_k)
        try:
            result = answerer.answer(q, hits)
        except AnswerError as exc:
            return {"status": "error", "error": str(exc)}
        return result.to_dict()

    @server.tool(description="List the documents in the knowledge base.")
    def list_sources() -> list[dict[str, Any]]:
        return store.list_documents()

    @server.tool(description="Show index size, embedder and knowledge folder.")
    def index_status() -> dict[str, Any]:
        return {
            **store.counts(),
            "embedder": store.get_meta("embedder"),
            "domain": settings.domain,
            "docs_dir": str(settings.docs_dir),
            "model": answerer.model,
        }

    @server.tool(description="Re-read the knowledge folder and update the index. Only changed files are re-embedded.")
    def reindex() -> dict[str, Any]:
        if os.environ.get("DOMAINRAG_ALLOW_REINDEX") != "1":
            return {
                "status": "disabled",
                "error": "Reindexing over MCP is off. Set DOMAINRAG_ALLOW_REINDEX=1 to enable it.",
            }
        report = ingest(settings, store, embedder)
        return {"status": "ok", "summary": report.summary(), **report.to_dict()}

    @server.resource("knowledge://chunk/{chunk_id}", description="Full text of one passage")
    def chunk_resource(chunk_id: str) -> str:
        if not _CHUNK_ID.match(chunk_id):
            raise ToolInputError("invalid chunk id")
        chunk = store.get_chunk(chunk_id)
        if chunk is None:
            raise ToolInputError("no such chunk")
        return f"{chunk.title} > {chunk.heading}\n({chunk.source})\n\n{chunk.text}"

    return server
