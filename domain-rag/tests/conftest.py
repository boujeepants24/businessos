from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from domainrag.config import Settings
from domainrag.embeddings import HashEmbedder
from domainrag.ingest import ingest
from domainrag.retrieval import Retriever
from domainrag.store import Store

CORPUS = Path(__file__).parent / "fixtures" / "corpus"


@dataclass
class Index:
    settings: Settings
    store: Store
    embedder: HashEmbedder
    retriever: Retriever


@pytest.fixture
def index(tmp_path: Path) -> Index:
    docs = tmp_path / "knowledge"
    shutil.copytree(CORPUS, docs)
    settings = Settings(
        docs_dir=docs,
        db_path=tmp_path / "index.db",
        domain="the Northfield C30 boiler",
        chunk_size=400,
        chunk_overlap=80,
    )
    store = Store(settings.db_path)
    embedder = HashEmbedder()
    ingest(settings, store, embedder)
    yield Index(settings, store, embedder, Retriever(store, embedder))
    store.close()


class FakeMessages:
    """Stands in for client.beta.messages: records each request, returns a canned response."""

    def __init__(
        self, payload: dict[str, Any] | None = None, stop_reason: str = "end_turn", raises: Exception | None = None
    ) -> None:
        self.payload = payload or {"answerable": True, "answer": "ok", "citations": ["e1"]}
        self.stop_reason = stop_reason
        self.raises = raises
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.raises:
            raise self.raises
        return SimpleNamespace(
            stop_reason=self.stop_reason,
            content=[SimpleNamespace(type="text", text=json.dumps(self.payload))],
            usage=SimpleNamespace(input_tokens=1200, output_tokens=80),
            model=kwargs["model"],
            _request_id="req_test",
        )


class FakeClient:
    def __init__(self, **kwargs: Any) -> None:
        self.beta = SimpleNamespace(messages=FakeMessages(**kwargs))

    @property
    def calls(self) -> list[dict[str, Any]]:
        return self.beta.messages.calls
