"""Public HTTP API for website chat widgets, serving many clients from one process.

Each client (business) has its own documents, index and allowed website origins, configured in a
clients file (see deploy/clients.example.json). The chat widget on a client's site calls:

    POST /v1/clients/{client_id}/ask   {"question": "..."}
    -> {"answerable": bool, "answer": str, "citations": [{"source", "section"}], "status": str}

This endpoint is reachable from the public internet, so it is deliberately narrow:
- Only browsers on that client's allowed origins may call it (CORS); calls without an Origin
  header need the server key (for back-end use and monitoring).
- Questions are capped at 500 characters.
- Rate limits per visitor IP and a daily cap per client keep a bot from running up the Claude bill.
- Responses carry the answer and the section names it came from, never raw document text, token
  counts or costs.
- Question text is not logged (it may contain personal details); only its length and the outcome.
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import anyio
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .answer import Answerer, AnswerError
from .config import Settings
from .embeddings import Embedder, make_embedder
from .retrieval import Retriever
from .store import Store

log = logging.getLogger(__name__)

MAX_QUESTION_CHARS = 500


@dataclass
class ClientConfig:
    id: str
    domain: str
    docs_dir: Path
    db_path: Path
    allowed_origins: list[str]
    daily_limit: int = 300
    per_ip_limit: int = 12  # questions per IP per 10 minutes


@dataclass
class Tenant:
    config: ClientConfig
    store: Store
    retriever: Retriever
    answerer: Answerer
    settings: Settings


def load_clients(path: Path) -> list[ClientConfig]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    base = path.parent
    clients = []
    for c in raw.get("clients", []):
        cid = str(c["id"])
        if not cid.replace("-", "").replace("_", "").isalnum():
            raise ValueError(f"client id {cid!r} may only use letters, digits, - and _")
        clients.append(
            ClientConfig(
                id=cid,
                domain=c["domain"],
                docs_dir=(base / c["docs_dir"]).resolve(),
                db_path=(base / c["db_path"]).resolve(),
                allowed_origins=[o.rstrip("/") for o in c.get("allowed_origins", [])],
                daily_limit=int(c.get("daily_limit", 300)),
                per_ip_limit=int(c.get("per_ip_limit", 12)),
            )
        )
    if len({c.id for c in clients}) != len(clients):
        raise ValueError("duplicate client ids")
    return clients


def client_settings(c: ClientConfig, base: Settings) -> Settings:
    return Settings(
        docs_dir=c.docs_dir,
        db_path=c.db_path,
        domain=c.domain,
        embedder=base.embedder,
        voyage_model=base.voyage_model,
        claude_model=base.claude_model,
        effort=base.effort,
        chunk_size=base.chunk_size,
        chunk_overlap=base.chunk_overlap,
        top_k=base.top_k,
    )


class RateLimiter:
    """In-memory sliding windows. Good for one server process; use Redis if you run several."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._ip: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._day: dict[str, tuple[str, int]] = {}

    def allow(self, client: ClientConfig, ip: str, now: float | None = None) -> str | None:
        """None if allowed, otherwise the reason it was refused."""
        now = time.time() if now is None else now
        today = time.strftime("%Y-%m-%d", time.gmtime(now))
        with self._lock:
            window = self._ip[(client.id, ip)]
            while window and now - window[0] > 600:
                window.popleft()
            if len(window) >= client.per_ip_limit:
                return "Too many questions from this device. Please try again in a few minutes."
            day, count = self._day.get(client.id, (today, 0))
            if day != today:
                count = 0
            if count >= client.daily_limit:
                return "The assistant is busy today. Please call or use the booking form."
            window.append(now)
            self._day[client.id] = (today, count + 1)
        return None


@dataclass
class App:
    tenants: dict[str, Tenant]
    server_key: str | None = None
    limiter: RateLimiter = field(default_factory=RateLimiter)

    def _cors(self, tenant: Tenant, origin: str | None) -> dict[str, str]:
        if origin and origin.rstrip("/") in tenant.config.allowed_origins:
            return {
                "Access-Control-Allow-Origin": origin,
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type",
                "Access-Control-Max-Age": "600",
                "Vary": "Origin",
            }
        return {}

    def _authorised(self, tenant: Tenant, request: Request) -> bool:
        origin = request.headers.get("origin")
        if origin is not None:
            return origin.rstrip("/") in tenant.config.allowed_origins
        key = request.headers.get("x-api-key", "")
        return bool(self.server_key) and hmac.compare_digest(key, self.server_key or "")

    async def health(self, request: Request) -> Response:
        return JSONResponse({"ok": True, "clients": sorted(self.tenants)})

    async def ask(self, request: Request) -> Response:
        tenant = self.tenants.get(request.path_params["client_id"])
        if tenant is None:
            return JSONResponse({"error": "unknown client"}, status_code=404)
        cors = self._cors(tenant, request.headers.get("origin"))
        if request.method == "OPTIONS":
            return Response(status_code=204 if cors else 403, headers=cors)
        if not self._authorised(tenant, request):
            return JSONResponse({"error": "origin not allowed"}, status_code=403)

        try:
            body = await request.json()
            question = str(body.get("question", "")).strip()
        except (json.JSONDecodeError, AttributeError, UnicodeDecodeError):
            return JSONResponse({"error": 'send JSON: {"question": "..."}'}, status_code=400, headers=cors)
        if not question:
            return JSONResponse({"error": "question is empty"}, status_code=400, headers=cors)
        if len(question) > MAX_QUESTION_CHARS:
            return JSONResponse(
                {"error": f"question is over {MAX_QUESTION_CHARS} characters"}, status_code=413, headers=cors
            )

        ip = request.client.host if request.client else "unknown"
        refused = self.limiter.allow(tenant.config, ip)
        if refused:
            return JSONResponse({"error": refused}, status_code=429, headers={**cors, "Retry-After": "600"})

        started = time.perf_counter()

        def work() -> Any:
            hits = tenant.retriever.search(question, k=tenant.settings.top_k)
            return tenant.answerer.answer(question, hits)

        try:
            result = await anyio.to_thread.run_sync(work)
        except AnswerError as exc:
            log.warning("client=%s ask failed: %s", tenant.config.id, exc)
            return JSONResponse({"error": "The assistant is unavailable right now."}, status_code=503, headers=cors)

        log.info(
            "client=%s chars=%d status=%s answerable=%s tokens=%d/%d ms=%d",
            tenant.config.id,
            len(question),
            result.status,
            result.answerable,
            result.input_tokens,
            result.output_tokens,
            int((time.perf_counter() - started) * 1000),
        )
        payload = {
            "answerable": result.answerable,
            "answer": result.answer,
            "status": result.status,
            "citations": [{"source": c.source, "section": c.section} for c in result.citations],
        }
        return JSONResponse(payload, headers=cors)

    def starlette(self) -> Starlette:
        return Starlette(
            routes=[
                Route("/health", self.health, methods=["GET"]),
                Route("/v1/clients/{client_id}/ask", self.ask, methods=["POST", "OPTIONS"]),
            ]
        )


def build_app(
    clients_file: Path,
    base: Settings | None = None,
    embedder: Embedder | None = None,
    anthropic_client: Any | None = None,
) -> App:
    base = base or Settings.from_env()
    tenants: dict[str, Tenant] = {}
    for c in load_clients(clients_file):
        settings = client_settings(c, base)
        store = Store(c.db_path)
        emb = embedder or make_embedder(settings)
        if store.get_meta("embedder"):
            store.bind_embedder(emb.name)
        answerer = Answerer(c.domain, base.claude_model, base.effort, client=anthropic_client)
        tenants[c.id] = Tenant(c, store, Retriever(store, emb), answerer, settings)
    return App(tenants=tenants, server_key=os.environ.get("DOMAINRAG_SERVER_KEY") or None)
