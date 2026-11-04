"""Per-business settings. One gateway serves every client; each client is keyed by its Twilio number."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

E164 = re.compile(r"^\+[1-9]\d{7,14}$")

DEFAULT_TEXT_BACK = (
    "Hi, it's {business}. Sorry we missed your call! Reply to this text with what you need and we'll get back to you, "
    "or book a time here: {booking_url}"
)
DEFAULT_GREETING = (
    "Sorry, we can't take your call right now. We've just sent you a text. To leave a message, speak after the tone."
)
DEFAULT_AFTER_HOURS = "Thanks for calling {business}. We're closed right now. We've sent you a text with our booking link. To leave a message, speak after the tone."


@dataclass(frozen=True)
class Hours:
    days: tuple[int, ...] = (0, 1, 2, 3, 4)  # Monday = 0 (Python's weekday())
    open: int = 8
    close: int = 18


@dataclass(frozen=True)
class Tenant:
    id: str
    business: str
    twilio_number: str  # the number customers call (E.164)
    owner_phone: str  # where calls are forwarded during opening hours
    ops_engine_url: str  # the client's Ops Engine web-app URL (leads and messages go here)
    booking_url: str
    timezone: str = "UTC"
    hours: Hours = field(default_factory=Hours)
    ring_seconds: int = 20
    forward_after_hours: bool = False  # True = ring the owner even when closed
    voicemail: bool = True
    text_back: str = DEFAULT_TEXT_BACK
    greeting: str = DEFAULT_GREETING
    after_hours_greeting: str = DEFAULT_AFTER_HOURS
    opt_out_line: str = "Reply STOP to opt out."  # required for SMS marketing rules in several countries

    def is_open(self, now: datetime) -> bool:
        local = now.astimezone(ZoneInfo(self.timezone))
        return local.weekday() in self.hours.days and self.hours.open <= local.hour < self.hours.close

    def text_back_message(self) -> str:
        body = self.text_back.format(business=self.business, booking_url=self.booking_url)
        return f"{body} {self.opt_out_line}".strip()


def load_tenants(path: Path) -> dict[str, Tenant]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    tenants: dict[str, Tenant] = {}
    for t in raw.get("clients", []):
        h = t.pop("hours", {})
        hours = Hours(
            days=tuple(h.get("days", Hours.days)), open=h.get("open", Hours.open), close=h.get("close", Hours.close)
        )
        tenant = Tenant(hours=hours, **t)
        for label, number in (("twilio_number", tenant.twilio_number), ("owner_phone", tenant.owner_phone)):
            if not E164.match(number):
                raise ValueError(f"{tenant.id}: {label} must be in international format, e.g. +441134960123")
        if tenant.twilio_number == tenant.owner_phone:
            raise ValueError(f"{tenant.id}: owner_phone must differ from twilio_number or calls would loop")
        if not tenant.ops_engine_url.startswith("https://"):
            raise ValueError(f"{tenant.id}: ops_engine_url must be an https URL")
        ZoneInfo(tenant.timezone)  # raises for an unknown timezone
        if tenant.twilio_number in tenants:
            raise ValueError(f"{tenant.id}: number {tenant.twilio_number} is already used by another client")
        tenants[tenant.twilio_number] = tenant
    return tenants
