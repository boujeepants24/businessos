"""The two things the gateway talks to, behind small interfaces so tests (or another provider) can swap them."""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Protocol

import httpx

log = logging.getLogger(__name__)


class SmsSender(Protocol):
    def send(self, to: str, from_: str, body: str) -> str: ...


class OpsEngine(Protocol):
    def post(self, url: str, payload: dict[str, Any]) -> bool: ...


class TwilioSms:
    def __init__(self, client: Any) -> None:
        self._client = client  # twilio.rest.Client

    def send(self, to: str, from_: str, body: str) -> str:
        msg = self._client.messages.create(to=to, from_=from_, body=body)
        return str(msg.sid)


class HttpOpsEngine:
    """Posts events to a client's Ops Engine (Google Apps Script web app). Apps Script answers with a
    redirect, which is followed. One retry on network errors; failures are logged, never raised, because
    they run after Twilio already has its answer."""

    def __init__(self, timeout: float = 20.0) -> None:
        self._http = httpx.Client(timeout=timeout, follow_redirects=True)

    def post(self, url: str, payload: dict[str, Any]) -> bool:
        for attempt in (1, 2):
            try:
                r = self._http.post(url, json=payload, headers={"Content-Type": "text/plain;charset=utf-8"})
                if r.status_code < 400:
                    return True
                log.warning("Ops Engine returned %s for %s event", r.status_code, payload.get("type", "lead"))
                return False
            except httpx.HTTPError as exc:
                log.warning("Ops Engine attempt %d failed: %s", attempt, exc)
                time.sleep(1)
        return False


class TextBackLog:
    """Remembers who was texted recently, so a caller who rings three times gets one text, not three."""

    def __init__(self, path: Path, window_minutes: int = 30) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS textbacks (tenant TEXT, caller TEXT, sent_at REAL, PRIMARY KEY (tenant, caller))"
        )
        self._lock = threading.Lock()
        self.window = window_minutes * 60

    def should_text(self, tenant: str, caller: str, now: float | None = None) -> bool:
        """True (and records the send) if this caller hasn't been texted within the window."""
        now = time.time() if now is None else now
        with self._lock, self._db:
            row = self._db.execute(
                "SELECT sent_at FROM textbacks WHERE tenant = ? AND caller = ?", (tenant, caller)
            ).fetchone()
            if row and now - row[0] < self.window:
                return False
            self._db.execute("INSERT OR REPLACE INTO textbacks VALUES (?, ?, ?)", (tenant, caller, now))
            return True


class Outbox:
    """Events the Ops Engine didn't accept are kept on disk and retried, so a lead is never lost
    because Google was slow or down for a few minutes."""

    def __init__(self, path: Path, max_attempts: int = 288) -> None:  # 288 x 5 min = 24 hours
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS outbox (id INTEGER PRIMARY KEY, url TEXT, payload TEXT, attempts INTEGER, created REAL)"
        )
        self._lock = threading.Lock()
        self.max_attempts = max_attempts

    def add(self, url: str, payload: dict[str, Any]) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO outbox (url, payload, attempts, created) VALUES (?, ?, 1, ?)",
                (url, json.dumps(payload), time.time()),
            )

    def pending(self) -> int:
        with self._lock:
            return int(self._db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0])

    def flush(self, ops: OpsEngine) -> tuple[int, int]:
        """Retry everything waiting. Returns (delivered, still waiting)."""
        with self._lock:
            rows = self._db.execute("SELECT id, url, payload, attempts FROM outbox ORDER BY id").fetchall()
        delivered = 0
        for row_id, url, payload, attempts in rows:
            if ops.post(url, json.loads(payload)):
                delivered += 1
                with self._lock, self._db:
                    self._db.execute("DELETE FROM outbox WHERE id = ?", (row_id,))
            elif attempts + 1 >= self.max_attempts:
                log.error("Giving up on an Ops Engine event after %d attempts: %s", attempts + 1, payload[:300])
                with self._lock, self._db:
                    self._db.execute("DELETE FROM outbox WHERE id = ?", (row_id,))
            else:
                with self._lock, self._db:
                    self._db.execute("UPDATE outbox SET attempts = attempts + 1 WHERE id = ?", (row_id,))
        return delivered, self.pending()
