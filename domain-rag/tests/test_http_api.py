from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from domainrag.config import Settings
from domainrag.embeddings import HashEmbedder
from domainrag.http_api import RateLimiter, build_app, client_settings, load_clients
from domainrag.ingest import ingest
from domainrag.store import Store

from .conftest import CORPUS, FakeClient

ORIGIN = "https://book.northfield.example"


@pytest.fixture
def setup(tmp_path: Path, monkeypatch):
    shutil.copytree(CORPUS, tmp_path / "northfield")
    (tmp_path / "empty").mkdir()
    clients = tmp_path / "clients.json"
    clients.write_text(
        json.dumps(
            {
                "clients": [
                    {
                        "id": "northfield",
                        "domain": "the Northfield C30 boiler",
                        "docs_dir": "northfield",
                        "db_path": "nf.db",
                        "allowed_origins": [ORIGIN + "/"],
                        "per_ip_limit": 3,
                        "daily_limit": 5,
                    },
                    {
                        "id": "other-co",
                        "domain": "something else",
                        "docs_dir": "empty",
                        "db_path": "other.db",
                        "allowed_origins": ["https://other.example"],
                    },
                ]
            }
        )
    )
    base = Settings(docs_dir=tmp_path, db_path=tmp_path / "unused.db", chunk_size=400, chunk_overlap=80)
    for c in load_clients(clients):
        cs = client_settings(c, base)
        store = Store(cs.db_path)
        ingest(cs, store, HashEmbedder())
        store.close()
    monkeypatch.setenv("DOMAINRAG_SERVER_KEY", "s3cret-key")
    fake = FakeClient(payload={"answerable": True, "answer": "F28 is an ignition failure.", "citations": ["e1"]})
    app = build_app(clients, base, embedder=HashEmbedder(), anthropic_client=fake)
    return TestClient(app.starlette()), fake, app


def ask(client, question, origin=ORIGIN, cid="northfield", **headers):
    h = {"origin": origin} if origin else {}
    return client.post(f"/v1/clients/{cid}/ask", json={"question": question}, headers={**h, **headers})


def test_answer_for_an_allowed_origin(setup):
    client, fake, _ = setup
    r = ask(client, "What does F28 mean?")
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == ORIGIN
    data = r.json()
    assert data == {
        "answerable": True,
        "answer": "F28 is an ignition failure.",
        "status": "ok",
        "citations": [
            {
                "source": "heating-guide.md",
                "section": "Northfield Combi Boiler Guide > Error codes > F28 ignition failure",
            }
        ],
    }
    assert "Northfield C30 boiler" in fake.calls[0]["system"]


def test_response_never_exposes_document_text_or_costs(setup):
    client, _, _ = setup
    data = ask(client, "What does F28 mean?").json()
    assert set(data) == {"answerable", "answer", "status", "citations"}
    assert set(data["citations"][0]) == {"source", "section"}


def test_preflight_and_unknown_origins(setup):
    client, _, _ = setup
    ok = client.options(
        "/v1/clients/northfield/ask", headers={"origin": ORIGIN, "access-control-request-method": "POST"}
    )
    assert ok.status_code == 204 and ok.headers["access-control-allow-origin"] == ORIGIN
    bad = client.options("/v1/clients/northfield/ask", headers={"origin": "https://evil.example"})
    assert bad.status_code == 403
    assert ask(client, "F28?", origin="https://evil.example").status_code == 403
    assert ask(client, "F28?", origin="https://other.example").status_code == 403, (
        "another client's site can't use this one"
    )


def test_server_to_server_calls_need_the_key(setup):
    client, _, _ = setup
    assert ask(client, "F28?", origin=None).status_code == 403
    assert ask(client, "F28?", origin=None, **{"x-api-key": "wrong"}).status_code == 403
    assert ask(client, "F28?", origin=None, **{"x-api-key": "s3cret-key"}).status_code == 200


def test_input_validation(setup):
    client, _, _ = setup
    assert ask(client, "   ").status_code == 400
    assert ask(client, "x" * 501).status_code == 413
    r = client.post(
        "/v1/clients/northfield/ask",
        content=b"not json",
        headers={"origin": ORIGIN, "content-type": "application/json"},
    )
    assert r.status_code == 400
    assert ask(client, "F28?", cid="nobody").status_code == 404


def test_tenants_are_isolated(setup):
    client, fake, _ = setup
    r = ask(client, "What does F28 mean?", origin="https://other.example", cid="other-co")
    assert r.status_code == 200
    assert r.json()["answerable"] is False and r.json()["status"] == "no_context", "other-co has no boiler documents"
    assert fake.calls == [], "no model call when the client's own index has nothing relevant"


def test_rate_limit_per_visitor(setup):
    client, _, _ = setup
    codes = [ask(client, "What does F28 mean?").status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]


def test_daily_cap_per_client():
    from domainrag.http_api import ClientConfig

    c = ClientConfig("x", "d", Path("."), Path("."), [], daily_limit=2, per_ip_limit=100)
    rl = RateLimiter()
    t = 1_800_000_000.0
    assert rl.allow(c, "1.1.1.1", t) is None
    assert rl.allow(c, "2.2.2.2", t) is None
    assert rl.allow(c, "3.3.3.3", t) is not None, "cap applies across visitors"
    assert rl.allow(c, "3.3.3.3", t + 86_400) is None, "resets the next day"


def test_model_outage_returns_503_without_details(setup):
    import anthropic
    import httpx2

    client, fake, app = setup
    req = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    fake.beta.messages.raises = anthropic.InternalServerError(
        "boom", response=httpx2.Response(500, request=req), body=None
    )
    r = ask(client, "What does F28 mean?")
    assert r.status_code == 503 and "boom" not in r.text


def test_health(setup):
    client, _, _ = setup
    assert client.get("/health").json() == {"ok": True, "clients": ["northfield", "other-co"]}


def test_bad_client_ids_are_rejected(tmp_path: Path):
    f = tmp_path / "c.json"
    f.write_text(json.dumps({"clients": [{"id": "../etc", "domain": "x", "docs_dir": "a", "db_path": "b"}]}))
    with pytest.raises(ValueError):
        load_clients(f)
