"""Twilio webhooks: the phone and SMS front door for every BusinessOS client.

Call flow for a client's Twilio number:

    customer calls ──► /twilio/voice
                         open hours  → ring the owner for `ring_seconds`
                         closed      → skip straight to "missed"
                       ──► /twilio/voice/dial-result
                         answered    → done
                         missed      → text the caller the booking link (once per 30 min),
                                       create a lead in the Ops Engine, offer voicemail
                       ──► /twilio/voicemail   → recording link added to the lead
    customer texts ───► /twilio/sms          → message added to their lead (or a new lead)

Every request must carry a valid X-Twilio-Signature, so nobody else can trigger texts or fake leads.
Ops Engine posts happen after the response (Twilio needs an answer within seconds; Apps Script can take
several).
"""

from __future__ import annotations

import argparse
import contextlib
import logging
import os
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import anyio
from starlette.applications import Starlette
from starlette.background import BackgroundTask
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route
from twilio.request_validator import RequestValidator
from twilio.twiml.voice_response import VoiceResponse

from .config import Tenant, load_tenants
from .services import HttpOpsEngine, OpsEngine, Outbox, SmsSender, TextBackLog, TwilioSms

log = logging.getLogger("commsgateway")

MISSED_STATUSES = {"no-answer", "busy", "failed", "canceled"}


def _mask(number: str) -> str:
    """Log-safe phone number: keep the country code and last 3 digits."""
    return number[:3] + "•••" + number[-3:] if len(number) > 6 else "•••"


def twiml(resp: VoiceResponse, background: BackgroundTask | None = None) -> Response:
    return Response(str(resp), media_type="application/xml", background=background)


@dataclass
class Gateway:
    tenants: dict[str, Tenant]
    public_base_url: str  # exactly as configured in Twilio, e.g. https://comms.youragency.example
    validator: RequestValidator | None  # None only in local development
    sms: SmsSender
    ops: OpsEngine
    textbacks: TextBackLog
    outbox: Outbox
    clock: Any = None  # injectable for tests: () -> datetime
    retry_seconds: int = 300

    def now(self) -> datetime:
        return self.clock() if self.clock else datetime.now(UTC)

    # ------------------------------------------------------------------ plumbing

    async def _form(self, request: Request) -> dict[str, str] | None:
        """The POSTed form, or None if the Twilio signature doesn't match."""
        form = {k: str(v) for k, v in (await request.form()).items()}
        if self.validator is None:
            return form
        url = (
            self.public_base_url.rstrip("/") + request.url.path + (f"?{request.url.query}" if request.url.query else "")
        )
        if not self.validator.validate(url, form, request.headers.get("x-twilio-signature", "")):
            log.warning("Rejected request with an invalid Twilio signature on %s", request.url.path)
            return None
        return form

    def deliver(self, url: str, payload: dict[str, Any]) -> None:
        """Send an event to the Ops Engine now, or park it in the outbox for retry."""
        if not self.ops.post(url, payload):
            self.outbox.add(url, payload)
            log.warning("Ops Engine unreachable; event saved for retry (%d waiting)", self.outbox.pending())

    def _url(self, path: str) -> str:
        return self.public_base_url.rstrip("/") + path

    # ------------------------------------------------------------------ voice

    async def voice(self, request: Request) -> Response:
        form = await self._form(request)
        if form is None:
            return Response(status_code=403)
        tenant = self.tenants.get(form.get("To", ""))
        resp = VoiceResponse()
        if tenant is None:
            resp.say("Sorry, this number is not in service.")
            resp.hangup()
            return twiml(resp)

        if tenant.is_open(self.now()) or tenant.forward_after_hours:
            dial = resp.dial(
                timeout=tenant.ring_seconds,
                action=self._url("/twilio/voice/dial-result"),
                method="POST",
                caller_id=tenant.twilio_number,
            )
            dial.number(tenant.owner_phone)
            return twiml(resp)

        # Closed: don't ring anyone; treat it as missed straight away.
        return self._missed(tenant, form, resp, after_hours=True)

    async def dial_result(self, request: Request) -> Response:
        form = await self._form(request)
        if form is None:
            return Response(status_code=403)
        tenant = self.tenants.get(form.get("To", ""))
        resp = VoiceResponse()
        if tenant is None or form.get("DialCallStatus") not in MISSED_STATUSES:
            resp.hangup()
            return twiml(resp)
        return self._missed(tenant, form, resp, after_hours=False)

    def _missed(self, tenant: Tenant, form: dict[str, str], resp: VoiceResponse, after_hours: bool) -> Response:
        caller = form.get("From", "")
        call_sid = form.get("CallSid", "")
        greeting = tenant.after_hours_greeting if after_hours else tenant.greeting
        resp.say(greeting.format(business=tenant.business))
        if tenant.voicemail:
            resp.record(max_length=120, play_beep=True, timeout=5, action=self._url("/twilio/voicemail"), method="POST")
        resp.hangup()

        def follow_up() -> None:
            texted = False
            if caller.startswith("+") and self.textbacks.should_text(tenant.id, caller):
                try:
                    self.sms.send(to=caller, from_=tenant.twilio_number, body=tenant.text_back_message())
                    texted = True
                except Exception as exc:  # a failed text must not lose the lead
                    log.warning("Text-back to %s failed: %s", _mask(caller), exc)
            self.deliver(
                tenant.ops_engine_url,
                {
                    "source": "missed-call",
                    "ref": "MC-" + call_sid[-8:].upper() if call_sid else None,
                    "name": "Missed caller",
                    "phone": caller,
                    "service": "Call back",
                    "notes": ("After-hours call. " if after_hours else "Missed call. ")
                    + ("Text-back sent." if texted else "No text sent (recent text or hidden number)."),
                    "skipAutoReply": True,
                    "page": "phone",
                },
            )
            log.info(
                "tenant=%s missed call from %s after_hours=%s texted=%s", tenant.id, _mask(caller), after_hours, texted
            )

        return twiml(resp, BackgroundTask(follow_up))

    async def voicemail(self, request: Request) -> Response:
        form = await self._form(request)
        if form is None:
            return Response(status_code=403)
        tenant = self.tenants.get(form.get("To", ""))
        resp = VoiceResponse()
        resp.say("Thanks, we'll be in touch soon. Goodbye.")
        resp.hangup()
        seconds = int(form.get("RecordingDuration", "0") or 0)
        if tenant is None or seconds < 2:  # silence or an instant hang-up isn't a message
            return twiml(resp)
        event = {
            "type": "message",
            "channel": "voicemail",
            "phone": form.get("From", ""),
            "text": f"Voicemail ({seconds}s): {form.get('RecordingUrl', '')}",
        }
        return twiml(resp, BackgroundTask(self.deliver, tenant.ops_engine_url, event))

    # ------------------------------------------------------------------ sms

    async def sms_in(self, request: Request) -> Response:
        form = await self._form(request)
        if form is None:
            return Response(status_code=403)
        tenant = self.tenants.get(form.get("To", ""))
        empty = Response('<?xml version="1.0" encoding="UTF-8"?><Response/>', media_type="application/xml")
        body = (form.get("Body") or "").strip()
        # STOP/HELP keywords are handled by Twilio's opt-out management; don't forward them as enquiries.
        if (
            tenant is None
            or not body
            or body.upper() in {"STOP", "STOPALL", "UNSUBSCRIBE", "CANCEL", "END", "QUIT", "START", "HELP"}
        ):
            return empty
        event = {"type": "message", "channel": "sms", "phone": form.get("From", ""), "text": body[:1500]}
        log.info("tenant=%s inbound sms from %s chars=%d", tenant.id, _mask(event["phone"]), len(body))
        return Response(
            empty.body,
            media_type="application/xml",
            background=BackgroundTask(self.deliver, tenant.ops_engine_url, event),
        )

    async def health(self, request: Request) -> Response:
        return JSONResponse(
            {"ok": True, "numbers": len(self.tenants), "outbox": self.outbox.pending(), "time": int(time.time())}
        )

    @contextlib.asynccontextmanager
    async def lifespan(self, app: Starlette) -> AsyncIterator[None]:
        """While the server runs, retry parked Ops Engine events every `retry_seconds`."""

        async def retry_forever() -> None:
            while True:
                await anyio.sleep(self.retry_seconds)
                delivered, waiting = await anyio.to_thread.run_sync(self.outbox.flush, self.ops)
                if delivered or waiting:
                    log.info("Outbox retry: %d delivered, %d still waiting", delivered, waiting)

        async with anyio.create_task_group() as tg:
            tg.start_soon(retry_forever)
            yield
            tg.cancel_scope.cancel()

    def starlette(self) -> Starlette:
        return Starlette(
            lifespan=self.lifespan,
            routes=[
                Route("/health", self.health, methods=["GET"]),
                Route("/twilio/voice", self.voice, methods=["POST"]),
                Route("/twilio/voice/dial-result", self.dial_result, methods=["POST"]),
                Route("/twilio/voicemail", self.voicemail, methods=["POST"]),
                Route("/twilio/sms", self.sms_in, methods=["POST"]),
            ],
        )


def build_gateway(
    clients_file: Path,
    *,
    sms: SmsSender | None = None,
    ops: OpsEngine | None = None,
    state_dir: Path | None = None,
    clock: Any = None,
) -> Gateway:
    token = os.environ.get("TWILIO_AUTH_TOKEN", "")
    insecure = os.environ.get("COMMS_INSECURE_DEV") == "1"
    if not token and not insecure:
        raise RuntimeError(
            "Set TWILIO_AUTH_TOKEN (and TWILIO_ACCOUNT_SID). COMMS_INSECURE_DEV=1 skips signature checks for local testing only."
        )
    base = os.environ.get("COMMS_PUBLIC_URL", "")
    if not base.startswith("https://") and not insecure:
        raise RuntimeError(
            "Set COMMS_PUBLIC_URL to the public https address Twilio calls, e.g. https://comms.youragency.example"
        )
    state = state_dir or Path(os.environ.get("COMMS_STATE_DIR", ".commsgateway"))
    if sms is None:
        from twilio.rest import Client

        sms = TwilioSms(Client(os.environ.get("TWILIO_ACCOUNT_SID"), token))
    return Gateway(
        tenants=load_tenants(clients_file),
        public_base_url=base or "http://localhost:8000",
        validator=None if insecure else RequestValidator(token),
        sms=sms,
        ops=ops or HttpOpsEngine(),
        textbacks=TextBackLog(state / "state.db"),
        outbox=Outbox(state / "outbox.db"),
        clock=clock,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="commsgateway")
    parser.add_argument("--clients", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("twilio.http_client").setLevel(logging.WARNING)  # it logs every request's headers at INFO
    import uvicorn

    uvicorn.run(build_gateway(args.clients).starlette(), host=args.host, port=args.port, proxy_headers=True)
    return 0
