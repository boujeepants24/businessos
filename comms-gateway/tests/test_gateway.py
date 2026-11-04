from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient
from twilio.request_validator import RequestValidator

from commsgateway.app import build_gateway
from commsgateway.config import load_tenants
from commsgateway.services import TextBackLog

TOKEN = "test-auth-token"
BASE = "https://comms.example.test"
NUMBER = "+441134960123"
OWNER = "+447700900500"
CALLER = "+447700900777"

CLIENT = {
    "id": "northfield",
    "business": "Northfield Plumbing",
    "twilio_number": NUMBER,
    "owner_phone": OWNER,
    "ops_engine_url": "https://script.google.com/macros/s/TEST/exec",
    "booking_url": "https://book.northfield.example",
    "timezone": "Europe/London",
    "hours": {"days": [0, 1, 2, 3, 4], "open": 8, "close": 18},
}

WEEKDAY_NOON = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)  # Wednesday, 12:00 in London
SUNDAY = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)


class FakeSms:
    def __init__(self, fail: bool = False) -> None:
        self.sent: list[dict[str, str]] = []
        self.fail = fail

    def send(self, to: str, from_: str, body: str) -> str:
        if self.fail:
            raise RuntimeError("carrier rejected")
        self.sent.append({"to": to, "from": from_, "body": body})
        return "SM123"


class FakeOps:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []
        self.down = False

    def post(self, url: str, payload: dict[str, Any]) -> bool:
        if self.down:
            return False
        self.events.append((url, payload))
        return True


@pytest.fixture
def gw(tmp_path: Path, monkeypatch):
    clients = tmp_path / "clients.json"
    clients.write_text(json.dumps({"clients": [CLIENT]}))
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", TOKEN)
    monkeypatch.setenv("COMMS_PUBLIC_URL", BASE)
    monkeypatch.delenv("COMMS_INSECURE_DEV", raising=False)
    sms, ops = FakeSms(), FakeOps()
    clock = {"now": WEEKDAY_NOON}
    gateway = build_gateway(clients, sms=sms, ops=ops, state_dir=tmp_path, clock=lambda: clock["now"])
    return TestClient(gateway.starlette()), sms, ops, clock, gateway


def signed_post(client: TestClient, path: str, params: dict[str, str], token: str = TOKEN):
    sig = RequestValidator(token).compute_signature(BASE + path, params)
    return client.post(path, data=params, headers={"X-Twilio-Signature": sig})


def call(**extra: str) -> dict[str, str]:
    return {"CallSid": "CA0123456789abcdef", "From": CALLER, "To": NUMBER, **extra}


def test_open_hours_ring_the_owner(gw):
    client, sms, ops, _, _ = gw
    r = signed_post(client, "/twilio/voice", call())
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/xml")
    assert f"<Number>{OWNER}</Number>" in r.text
    assert 'timeout="20"' in r.text and f"{BASE}/twilio/voice/dial-result" in r.text
    assert sms.sent == [] and ops.events == []


def test_unanswered_call_texts_back_creates_lead_and_offers_voicemail(gw):
    client, sms, ops, _, _ = gw
    r = signed_post(client, "/twilio/voice/dial-result", call(DialCallStatus="no-answer"))
    assert "<Record" in r.text and f"{BASE}/twilio/voicemail" in r.text and "sent you a text" in r.text
    assert sms.sent == [{"to": CALLER, "from": NUMBER, "body": sms.sent[0]["body"]}]
    assert "https://book.northfield.example" in sms.sent[0]["body"] and "Reply STOP" in sms.sent[0]["body"]
    url, lead = ops.events[0]
    assert url == CLIENT["ops_engine_url"]
    assert lead["source"] == "missed-call" and lead["phone"] == CALLER and lead["skipAutoReply"] is True
    assert lead["ref"] == "MC-89ABCDEF" and "Text-back sent" in lead["notes"]


@pytest.mark.parametrize("status", ["busy", "failed", "canceled"])
def test_other_missed_outcomes(gw, status):
    client, sms, _, _, _ = gw
    signed_post(client, "/twilio/voice/dial-result", call(DialCallStatus=status))
    assert len(sms.sent) == 1


def test_answered_call_does_nothing(gw):
    client, sms, ops, _, _ = gw
    r = signed_post(client, "/twilio/voice/dial-result", call(DialCallStatus="completed"))
    assert "<Hangup" in r.text and sms.sent == [] and ops.events == []


def test_after_hours_skips_ringing_and_says_closed(gw):
    client, sms, ops, clock, _ = gw
    clock["now"] = SUNDAY
    r = signed_post(client, "/twilio/voice", call())
    assert "<Dial" not in r.text and "closed right now" in r.text
    assert len(sms.sent) == 1 and "After-hours call" in ops.events[0][1]["notes"]


def test_hours_use_the_business_timezone(gw):
    client, sms, _, clock, _ = gw
    clock["now"] = datetime(2026, 11, 4, 18, 30, tzinfo=UTC)  # 18:30 London = closed
    assert "<Dial" not in signed_post(client, "/twilio/voice", call()).text
    clock["now"] = datetime(2026, 7, 1, 7, 30, tzinfo=UTC)  # 08:30 London in summer time (UTC+1) = open
    assert "<Dial" in signed_post(client, "/twilio/voice", call()).text


def test_repeat_caller_gets_one_text_per_30_minutes(gw):
    client, sms, ops, _, _ = gw
    for _ in range(3):
        signed_post(client, "/twilio/voice/dial-result", call(DialCallStatus="no-answer"))
    assert len(sms.sent) == 1
    assert len(ops.events) == 3, "every call still reaches the Ops Engine, which merges them"
    assert "No text sent" in ops.events[1][1]["notes"]


def test_hidden_number_gets_no_text_but_still_logs(gw):
    client, sms, ops, _, _ = gw
    signed_post(
        client,
        "/twilio/voice/dial-result",
        {"CallSid": "CA1", "From": "anonymous", "To": NUMBER, "DialCallStatus": "no-answer"},
    )
    assert sms.sent == [] and len(ops.events) == 1


def test_failed_text_still_creates_the_lead(gw):
    client, sms, ops, _, gateway = gw
    gateway.sms = FakeSms(fail=True)
    signed_post(client, "/twilio/voice/dial-result", call(DialCallStatus="no-answer"))
    assert len(ops.events) == 1 and "No text sent" in ops.events[0][1]["notes"]


def test_voicemail_is_forwarded_but_silence_is_not(gw):
    client, _, ops, _, _ = gw
    signed_post(client, "/twilio/voicemail", call(RecordingUrl="https://api.twilio.com/rec/RE1", RecordingDuration="1"))
    assert ops.events == []
    signed_post(
        client, "/twilio/voicemail", call(RecordingUrl="https://api.twilio.com/rec/RE2", RecordingDuration="23")
    )
    assert ops.events[0][1] == {
        "type": "message",
        "channel": "voicemail",
        "phone": CALLER,
        "text": "Voicemail (23s): https://api.twilio.com/rec/RE2",
    }


def test_inbound_text_is_forwarded_and_opt_out_words_are_not(gw):
    client, _, ops, _, _ = gw
    r = signed_post(client, "/twilio/sms", {"From": CALLER, "To": NUMBER, "Body": "  Can you come Friday?  "})
    assert r.status_code == 200 and "<Response" in r.text
    assert ops.events[0][1] == {"type": "message", "channel": "sms", "phone": CALLER, "text": "Can you come Friday?"}
    for word in ("STOP", "stop", "HELP", "Unsubscribe"):
        signed_post(client, "/twilio/sms", {"From": CALLER, "To": NUMBER, "Body": word})
    assert len(ops.events) == 1


def test_forged_or_unsigned_requests_are_rejected(gw):
    client, sms, ops, _, _ = gw
    params = call(DialCallStatus="no-answer")
    assert client.post("/twilio/voice/dial-result", data=params).status_code == 403
    assert signed_post(client, "/twilio/voice/dial-result", params, token="wrong-token").status_code == 403
    sig = RequestValidator(TOKEN).compute_signature(BASE + "/twilio/voice/dial-result", params)
    tampered = {**params, "From": "+15555550100"}
    assert (
        client.post("/twilio/voice/dial-result", data=tampered, headers={"X-Twilio-Signature": sig}).status_code == 403
    )
    assert sms.sent == [] and ops.events == []


def test_unknown_number_is_politely_refused(gw):
    client, sms, _, _, _ = gw
    r = signed_post(client, "/twilio/voice", {"CallSid": "CA1", "From": CALLER, "To": "+15555550199"})
    assert "not in service" in r.text and sms.sent == []


def test_config_validation(tmp_path: Path):
    def check(**overrides: Any) -> None:
        f = tmp_path / "c.json"
        f.write_text(json.dumps({"clients": [{**CLIENT, **overrides}]}))
        load_tenants(f)

    for bad in (
        {"twilio_number": "01134960123"},
        {"owner_phone": NUMBER},
        {"ops_engine_url": "http://insecure"},
        {"timezone": "Mars/Base"},
    ):
        with pytest.raises((ValueError, KeyError)):  # ZoneInfoNotFoundError is a KeyError
            check(**bad)


def test_refuses_to_start_without_credentials(tmp_path: Path, monkeypatch):
    clients = tmp_path / "c.json"
    clients.write_text(json.dumps({"clients": [CLIENT]}))
    monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("COMMS_INSECURE_DEV", raising=False)
    with pytest.raises(RuntimeError, match="TWILIO_AUTH_TOKEN"):
        build_gateway(clients, sms=FakeSms(), ops=FakeOps(), state_dir=tmp_path)


def test_textback_window_expires():
    log = TextBackLog(Path("/tmp") / f"tb-{datetime.now().timestamp()}.db", window_minutes=30)
    assert log.should_text("t", CALLER, now=1000.0)
    assert not log.should_text("t", CALLER, now=1000.0 + 29 * 60)
    assert log.should_text("t", CALLER, now=1000.0 + 31 * 60)


def test_leads_survive_an_ops_engine_outage(gw):
    client, sms, ops, _, gateway = gw
    ops.down = True
    signed_post(client, "/twilio/voice/dial-result", call(DialCallStatus="no-answer"))
    signed_post(client, "/twilio/sms", {"From": CALLER, "To": NUMBER, "Body": "Are you open Saturday?"})
    assert ops.events == [] and gateway.outbox.pending() == 2
    assert len(sms.sent) == 1, "the caller still gets their text during the outage"
    assert client.get("/health").json()["outbox"] == 2

    assert gateway.outbox.flush(ops) == (0, 2), "still down: nothing lost, nothing delivered"
    ops.down = False
    assert gateway.outbox.flush(ops) == (2, 0)
    assert [e[1].get("source") or e[1]["type"] for e in ops.events] == ["missed-call", "message"], "delivered in order"


def test_outbox_gives_up_after_max_attempts(tmp_path: Path):
    from commsgateway.services import Outbox

    box = Outbox(tmp_path / "o.db", max_attempts=3)
    ops = FakeOps()
    ops.down = True
    box.add("https://x", {"a": 1})
    assert box.flush(ops) == (0, 1)
    assert box.flush(ops) == (0, 0), "dropped (and logged) after 3 attempts"


def test_retry_loop_delivers_parked_events_while_running(gw):
    import time as _time

    _, _, ops, _, gateway = gw
    gateway.retry_seconds = 0.05
    ops.down = True
    gateway.deliver("https://script.google.com/macros/s/TEST/exec", {"type": "message", "phone": CALLER, "text": "hi"})
    assert gateway.outbox.pending() == 1
    ops.down = False
    with TestClient(gateway.starlette()) as running:  # runs startup, which starts the retry loop
        deadline = _time.time() + 3
        while gateway.outbox.pending() and _time.time() < deadline:
            _time.sleep(0.05)
        assert running.get("/health").json()["outbox"] == 0
    assert ops.events and ops.events[0][1]["text"] == "hi"
