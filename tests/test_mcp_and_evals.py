from __future__ import annotations

import json
from pathlib import Path

import pytest
from mcp import Client
from mcp.shared.exceptions import MCPError

from domainrag.answer import Answerer
from domainrag.evals import load_dataset, run_eval
from domainrag.mcp_server import build_server

from .conftest import FakeClient


def _payload(result) -> object:
    """Tool results arrive as MCP content; the structured value is what clients use."""
    if getattr(result, "structured_content", None) is not None:
        sc = result.structured_content
        return sc.get("result", sc) if isinstance(sc, dict) else sc
    return json.loads(result.content[0].text)


@pytest.fixture
def server(index):
    answerer = Answerer(
        index.settings.domain,
        client=FakeClient(payload={"answerable": True, "answer": "Book an engineer.", "citations": ["e1"]}),
    )
    return build_server(index.settings, index.store, index.embedder, answerer)


async def test_lists_the_expected_tools(server):
    async with Client(server) as client:
        names = {t.name for t in (await client.list_tools()).tools}
    assert names == {"search_knowledge", "ask", "list_sources", "index_status", "reindex"}


async def test_search_tool_returns_ranked_passages(server):
    async with Client(server) as client:
        result = await client.call_tool("search_knowledge", {"query": "F22 low pressure", "top_k": 2})
    rows = _payload(result)
    assert 1 <= len(rows) <= 2, "top_k is a maximum; weak matches are filtered, not padded in"
    assert rows[0]["source"] == "heating-guide.md" and "F22" in rows[0]["text"]
    assert "keyword" in rows[0]["matched_by"]


async def test_ask_tool_returns_a_cited_answer(server):
    async with Client(server) as client:
        result = await client.call_tool("ask", {"question": "What should I do about F28?"})
    data = _payload(result)
    assert data["answerable"] is True and data["citations"][0]["source"] == "heating-guide.md"


async def test_empty_and_oversized_inputs_are_rejected(server):
    async with Client(server) as client:
        empty = await client.call_tool("search_knowledge", {"query": "  "})
        huge = await client.call_tool("ask", {"question": "x" * 2001})
    assert empty.is_error and huge.is_error


async def test_status_sources_and_reindex_guard(server, monkeypatch):
    async with Client(server) as client:
        status = _payload(await client.call_tool("index_status", {}))
        sources = _payload(await client.call_tool("list_sources", {}))
        blocked = _payload(await client.call_tool("reindex", {}))
        monkeypatch.setenv("DOMAINRAG_ALLOW_REINDEX", "1")
        allowed = _payload(await client.call_tool("reindex", {}))
    assert status["documents"] == 4 and status["embedder"] == "hash-1024"
    assert len(sources) == 4
    assert blocked["status"] == "disabled"
    assert allowed["status"] == "ok" and len(allowed["unchanged"]) == 4


async def test_chunk_resource_and_bad_ids(server, index):
    chunk_id = index.retriever.search("F28", k=1)[0].chunk.id
    async with Client(server) as client:
        text = await client.read_resource(f"knowledge://chunk/{chunk_id}")
        with pytest.raises(MCPError):
            await client.read_resource("knowledge://chunk/not-a-real-id")
    assert "F28" in text.contents[0].text


def test_eval_metrics_on_a_labelled_dataset(index, tmp_path: Path):
    ds = tmp_path / "ds.jsonl"
    ds.write_text(
        "\n".join(
            [
                "// comment lines are allowed",
                json.dumps({"id": "q1", "question": "What does F28 mean", "expected_sources": ["heating-guide.md"]}),
                json.dumps(
                    {
                        "id": "q2",
                        "question": "how long is the warranty",
                        "expected_sources": ["warranty.txt"],
                        "must_include": ["7 year"],
                    }
                ),
                json.dumps({"id": "q3", "question": "what is the capital of France", "answerable": False}),
            ]
        )
    )
    cases = load_dataset(ds)
    report = run_eval(cases, index.retriever, k=3)
    assert report["summary"]["hit@3"] == 1.0 and report["summary"]["mrr"] == 1.0
    answerer = Answerer(
        index.settings.domain,
        client=FakeClient(payload={"answerable": True, "answer": "A 7 year warranty.", "citations": ["e1"]}),
    )
    graded = run_eval(cases, index.retriever, k=3, answerer=answerer)["summary"]
    assert graded["answerable_accuracy"] == 1.0, "q3 has no hits, so no model call and answerable=false"
    assert graded["invalid_citations"] == 0
    assert graded["must_include_pass"] == 1.0


def test_dataset_errors_are_reported_with_line_numbers(tmp_path: Path):
    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"id": "a", "question": "x"}\n{"id": "a", "question": "y"}\n')
    with pytest.raises(ValueError, match="duplicate"):
        load_dataset(bad)
    bad.write_text('{"id": "a", "question": "x", "nope": 1}\n')
    with pytest.raises(ValueError, match="bad.jsonl:1"):
        load_dataset(bad)
