#!/usr/bin/env python3
"""Generate everything a new BusinessOS client needs from one client.toml.

    python3 onboarding/onboard.py onboarding/clients/<id>.toml [--agency-email you@agency.com] [--out onboarding/build]

Writes onboarding/build/<id>/:
    booking-site/          ready to deploy (Netlify, Vercel, Cloudflare Pages, GitHub Pages)
    chat-receptionist/     widget + config + the two script tags to paste into the client's site
    ops-engine/            every Apps Script file, with Config.gs filled in
    comms-gateway.json     this client's entry for the phone gateway's clients file
    domain-rag.json        this client's entry for the knowledge API's clients file
    knowledge/             where the client's approved documents go
    ONBOARDING.md          the remaining steps, with this client's values filled in

Standard library only. Validates everything first and refuses to write anything if a field is wrong,
because a typo here means a broken booking page or texts going to the wrong phone.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

ROOT = Path(__file__).resolve().parent.parent  # the businessos repo
DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
E164 = re.compile(r"^\+[1-9]\d{7,14}$")
HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
ID = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")


class ConfigError(ValueError):
    pass


@dataclass
class Problems:
    items: list[str]

    def check(self, ok: bool, message: str) -> None:
        if not ok:
            self.items.append(message)


# ----------------------------------------------------------------------------- day numbering
# The browser (JavaScript getDay) counts Sunday = 0. Python's weekday() (comms gateway) counts Monday = 0.
# Keeping one list of names in client.toml and converting here stops a client's phone ringing on the wrong days.


def js_days(names: list[str]) -> list[int]:
    return sorted((DAY_NAMES.index(n) + 1) % 7 for n in names)


def py_days(names: list[str]) -> list[int]:
    return sorted(DAY_NAMES.index(n) for n in names)


# ----------------------------------------------------------------------------- validation


def _https(url: str) -> bool:
    p = urlparse(url)
    return p.scheme == "https" and bool(p.netloc)


def _origin(url: str) -> str:
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


def validate(c: dict) -> None:
    p = Problems([])
    req = ["id", "business", "trade", "tagline", "city", "address", "website", "booking_url", "timezone", "locale", "currency"]
    for k in req:
        p.check(bool(str(c.get(k, "")).strip()), f"'{k}' is required")
    p.check(bool(ID.match(str(c.get("id", "")))), "'id' must be lowercase letters, digits and hyphens (2-41 chars)")
    for k in ("website", "booking_url"):
        if c.get(k):
            p.check(_https(c[k]), f"'{k}' must be an https URL")
    try:
        ZoneInfo(str(c.get("timezone", "")))
    except (ZoneInfoNotFoundError, ValueError):
        p.check(False, f"'timezone' {c.get('timezone')!r} is not a known timezone (e.g. Europe/London, Australia/Sydney)")
    p.check(bool(re.fullmatch(r"[A-Z]{3}", str(c.get("currency", "")))), "'currency' must be a 3-letter code like GBP, AUD, NZD, EUR")

    ct = c.get("contact", {})
    for k in ("public_phone", "owner_mobile"):
        p.check(bool(E164.match(str(ct.get(k, "")))), f"contact.{k} must be international format, e.g. +441134960123")
    p.check(ct.get("public_phone") != ct.get("owner_mobile"), "contact.owner_mobile must differ from contact.public_phone (calls would loop)")
    for k in ("owner_email", "reply_email"):
        p.check("@" in str(ct.get(k, "")), f"contact.{k} must be an email address")
    p.check(bool(re.fullmatch(r"\d{8,15}|", str(ct.get("whatsapp", "")))), "contact.whatsapp must be digits only with country code, or empty")

    h = c.get("hours", {})
    days = h.get("days", [])
    p.check(bool(days) and all(d in DAY_NAMES for d in days), f"hours.days must use {', '.join(DAY_NAMES)}")
    p.check(isinstance(h.get("open"), int) and isinstance(h.get("close"), int) and 0 <= h.get("open", -1) < h.get("close", -1) <= 24, "hours.open/close must be whole hours with open < close")
    slot = h.get("slot_length_hours", 2)
    p.check(isinstance(slot, int) and 1 <= slot <= 8, "hours.slot_length_hours must be 1-8")

    b = c.get("brand", {})
    for k in ("color", "accent"):
        p.check(bool(HEX.match(str(b.get(k, "")))), f"brand.{k} must be a colour like #0F5C8C")

    services = c.get("services", [])
    p.check(len(services) > 0, "at least one [[services]] entry is required")
    ids = [s.get("id") for s in services]
    names = [s.get("name") for s in services]
    p.check(len(set(ids)) == len(ids) and all(ids), "every service needs a unique id")
    p.check(len(set(names)) == len(names) and all(names), "every service needs a unique name")
    for s in services:
        p.check(isinstance(s.get("rebook_months", 0), int) and 0 <= s.get("rebook_months", 0) <= 36, f"service {s.get('id')}: rebook_months must be 0-36")

    tax = c.get("tax", {})
    p.check(0 <= float(tax.get("rate", 0)) < 1, "tax.rate is a fraction: 0.2 for 20%")
    p.check(bool(c.get("payment", {}).get("instructions")), "payment.instructions is required (printed on every invoice)")

    dep = c.get("deployed", {})
    if dep.get("ops_engine_url"):
        p.check(dep["ops_engine_url"].startswith("https://script.google.com/") and dep["ops_engine_url"].endswith("/exec"),
                "deployed.ops_engine_url must be the Apps Script web-app URL ending in /exec")
    if dep.get("knowledge_api"):
        p.check(_https(dep["knowledge_api"]), "deployed.knowledge_api must be an https URL")

    if p.items:
        raise ConfigError("client.toml has problems:\n  - " + "\n  - ".join(p.items))


# ----------------------------------------------------------------------------- generators


def booking_config(c: dict) -> dict:
    ct, h, b, t = c["contact"], c["hours"], c["brand"], c.get("trust", {})
    return {
        "businessName": c["business"], "tagline": c["tagline"], "trade": c["trade"], "city": c["city"],
        "serviceAreas": c.get("areas", {}).get("served", []),
        "phone": ct["public_phone"], "whatsapp": ct.get("whatsapp", ""), "email": ct["reply_email"], "address": c["address"],
        "brandColor": b["color"], "accentColor": b["accent"], "logoText": b.get("logo_text", c["business"][:2].upper()), "logoUrl": b.get("logo_url", ""),
        "rating": float(t.get("rating", 5.0)), "reviewCount": int(t.get("review_count", 0)), "yearsTrading": int(t.get("years_trading", 0)),
        "accreditations": t.get("accreditations", []),
        "reviews": [{"name": r["name"], "area": r["area"], "text": r["text"]} for r in t.get("reviews", [])],
        "services": [{"id": s["id"], "name": s["name"], "desc": s.get("description", ""), **({"urgent": True} if s.get("urgent") else {})} for s in c["services"]],
        "hours": {"open": h["open"], "close": h["close"], "days": js_days(h["days"])},
        "slotLengthHours": h.get("slot_length_hours", 2),
        "bookingDaysAhead": 10,
        "emergencyLine247": bool(h.get("emergency_line_24_7", False)),
        "webhookUrl": c.get("deployed", {}).get("ops_engine_url", ""),
        "locale": c["locale"],
    }


def chat_config(c: dict) -> dict:
    ct, h = c["contact"], c["hours"]
    kb = c.get("deployed", {}).get("knowledge_api", "")
    return {
        "businessName": c["business"], "assistantName": c.get("assistant", {}).get("name", "Assistant"), "brandColor": c["brand"]["color"],
        "phone": ct["public_phone"], "whatsapp": ct.get("whatsapp", ""),
        "serviceAreas": c.get("areas", {}).get("served", []),
        "hours": {"open": h["open"], "close": h["close"], "days": js_days(h["days"])},
        "emergencyLine247": bool(h.get("emergency_line_24_7", False)),
        "services": [{"id": s["id"], "name": s["name"], **({"urgent": True} if s.get("urgent") else {}), "keywords": s.get("keywords", [])} for s in c["services"]],
        "faqs": [{"q": f["q"], "keywords": f.get("keywords", []), "a": f["a"]} for f in c.get("faqs", [])],
        "teaser": c.get("assistant", {}).get("teaser", ""), "teaserDelaySeconds": 6,
        "webhookUrl": c.get("deployed", {}).get("ops_engine_url", ""),
        "knowledgeUrl": f"{kb.rstrip('/')}/v1/clients/{c['id']}/ask" if kb else "",
        "knowledgeTimeoutSeconds": 12,
        "position": "right",
    }


def ops_config(c: dict, agency_email: str) -> dict:
    ct, h, tax, pay = c["contact"], c["hours"], c.get("tax", {}), c["payment"]
    return {
        "business": {
            "name": c["business"], "ownerName": ct["owner_name"], "phone": ct["public_phone"], "email": ct["reply_email"],
            "address": c["address"], "website": c["website"], "googleReviewUrl": c.get("trust", {}).get("google_review_url", ""),
            "currency": c["currency"], "locale": c["locale"],
            "taxLabel": tax.get("label", "Tax"), "taxRate": float(tax.get("rate", 0)), "taxNumber": tax.get("number", ""),
        },
        "ownerEmail": ct["owner_email"],
        "agencyEmail": agency_email,
        "payment": {"instructions": pay["instructions"], "payLinkTemplate": pay.get("pay_link_template", ""), "termsDays": int(pay.get("terms_days", 7))},
        "channels": {"sms": {"provider": "", "from": "", "accountSid": ""}, "webhookUrl": ""},
        "services": {s["name"]: {"rebookMonths": int(s.get("rebook_months", 0))} for s in c["services"]},
        "booking": {"open": h["open"], "close": h["close"], "slotLengthHours": h.get("slot_length_hours", 2)},
        "timing": {
            "timezone": c["timezone"], "quietHours": {"start": 21, "end": 8},
            "callbackAlertMinutes": 15, "escalateCallbackMinutes": 120, "bookingReminderHours": 24,
            "quoteFollowupDays": [2, 5], "invoiceChaseDays": [3, 7, 14], "escalateInvoiceDays": 21,
            "reviewDelayHours": 2, "reviewFollowupDays": 4,
        },
    }


def gateway_entry(c: dict) -> dict:
    ct, h = c["contact"], c["hours"]
    return {
        "id": c["id"], "business": c["business"], "twilio_number": ct["public_phone"], "owner_phone": ct["owner_mobile"],
        "ops_engine_url": c.get("deployed", {}).get("ops_engine_url", ""), "booking_url": c["booking_url"], "timezone": c["timezone"],
        "hours": {"days": py_days(h["days"]), "open": h["open"], "close": h["close"]},
        "ring_seconds": 20, "forward_after_hours": False, "voicemail": True,
    }


def knowledge_entry(c: dict) -> dict:
    origins = sorted({_origin(c["website"]), _origin(c["booking_url"])})
    return {
        "id": c["id"],
        "domain": f"{c['business']}: its services, areas covered, opening hours, policies and common {c['trade'].lower()} questions",
        "docs_dir": f"../clients/{c['id']}/knowledge", "db_path": f"../.domainrag/{c['id']}.db",
        "allowed_origins": origins, "daily_limit": 300, "per_ip_limit": 12,
    }


def js_assign(name: str, obj: dict, header: str) -> str:
    return f"/* {header} */\nwindow.{name} = {json.dumps(obj, indent=2, ensure_ascii=False)};\n"


# ----------------------------------------------------------------------------- checklist


def checklist(c: dict, out: Path) -> str:
    dep = c.get("deployed", {})
    ops_done = bool(dep.get("ops_engine_url"))
    kb = dep.get("knowledge_api", "")
    ct = c["contact"]
    tick = lambda done: "x" if done else " "  # noqa: E731
    return f"""# Onboarding: {c['business']}

Generated from `{c['id']}.toml`. Re-run the generator after any change to that file; never edit the generated files by hand.

## 1. Back office (Google Apps Script), about 10 minutes
- [{tick(ops_done)}] In the **agency** Google account, create a Sheet named "{c['business']} Ops" and share it with {ct['owner_email']} (Viewer).
- [{tick(ops_done)}] Extensions → Apps Script. Create one script file per `.gs` file in `{out.name}/ops-engine/` (same names) plus an HTML file `OwnerApp`, and paste each in.
      Faster with Google's `clasp` CLI: `cd {out.name}/ops-engine && clasp create --type sheets --title "{c['business']} Ops" && clasp push`
- [{tick(ops_done)}] Run `setup()` once and approve permissions.
- [{tick(ops_done)}] Deploy → New deployment → Web app (Execute as: Me, Who has access: Anyone). Copy the `/exec` URL.
- [{tick(ops_done)}] Paste it into `[deployed] ops_engine_url` in `{c['id']}.toml` and **re-run the generator** (it wires the URL into the site, chat and gateway).
- [ ] Run `showOwnerLink()` and text the link to {ct['owner_name']} on {ct['owner_mobile']}; ask them to add it to their home screen.

## 2. Booking site, about 5 minutes
- [ ] Deploy `{out.name}/booking-site/` (Netlify drag-and-drop, or `npx netlify deploy --dir {out.name}/booking-site --prod`).
- [ ] Point {urlparse(c['booking_url']).netloc} at it (CNAME at the client's DNS).

## 3. Chat receptionist, about 2 minutes
- [ ] Host `{out.name}/chat-receptionist/` next to the booking site (or any static host).
- [ ] Paste the two lines from `{out.name}/chat-receptionist/INSTALL.html` into {c['website']} before `</body>`.

## 4. Phone (Twilio), about 10 minutes
- [ ] Buy or port {ct['public_phone']} in Twilio (or forward the client's existing number to it when unanswered).
- [ ] Voice webhook: `POST https://<COMMS_PUBLIC_URL>/twilio/voice`; Messaging webhook: `POST https://<COMMS_PUBLIC_URL>/twilio/sms`.
- [ ] Add the object in `{out.name}/comms-gateway.json` to the gateway's `deploy/clients.json` and restart it.
- [ ] Country rules: check `comms-gateway/README.md` → "Country rules" for {c['timezone'].split('/')[0]} before the first text.

## 5. Knowledge answers (optional)
- [{tick(bool(kb))}] Collect and get approval for the client's documents (`client-knowledge/README.md`), put them in `clients/{c['id']}/knowledge/` on the knowledge server.
- [ ] Add `{out.name}/domain-rag.json` to the knowledge API's clients file, run `domainrag ingest --clients ...`, set `[deployed] knowledge_api` and re-run the generator.

## 6. Test end to end (do not skip)
- [ ] Book a slot on the site: confirmation email/text arrives, row appears in the sheet, owner gets an alert.
- [ ] Call {ct['public_phone']} and don't answer: text-back arrives, "Missed caller" lead appears.
- [ ] Mark the test booking done for an amount of 1: invoice arrives. Then mark it paid and delete the test rows.
- [ ] Before onboarding, record {ct['owner_name']}'s weekly admin hours; report hours saved each month.
"""


# ----------------------------------------------------------------------------- main


def generate(toml_path: Path, out_root: Path, agency_email: str) -> Path:
    with toml_path.open("rb") as f:
        c = tomllib.load(f)
    validate(c)
    out = out_root / c["id"]
    if out.exists():
        shutil.rmtree(out)  # always regenerate from the toml, never patch generated files

    site = out / "booking-site"
    site.mkdir(parents=True)
    for name in ("index.html", "styles.css", "app.js"):
        shutil.copy2(ROOT / "booking-site" / name, site / name)
    (site / "config.js").write_text(js_assign("CLIENT", booking_config(c), f"Generated for {c['business']} by onboarding/onboard.py. Do not edit; edit {c['id']}.toml."), encoding="utf-8")

    chat = out / "chat-receptionist"
    chat.mkdir()
    shutil.copy2(ROOT / "chat-receptionist" / "widget.js", chat / "widget.js")
    (chat / "config.js").write_text(js_assign("RECEPTIONIST", chat_config(c), f"Generated for {c['business']}. Do not edit; edit {c['id']}.toml."), encoding="utf-8")
    base = c["booking_url"].rstrip("/") + "/chat"
    (chat / "INSTALL.html").write_text(
        f"<!-- Paste before </body> on {c['website']} (host this folder at {base}/) -->\n"
        f'<script src="{base}/config.js"></script>\n<script src="{base}/widget.js" defer></script>\n', encoding="utf-8")

    ops = out / "ops-engine"
    ops.mkdir()
    for src in sorted((ROOT / "ops-engine").glob("*.gs")):
        if src.name != "Config.gs":
            shutil.copy2(src, ops / src.name)
    shutil.copy2(ROOT / "ops-engine" / "OwnerApp.html", ops / "OwnerApp.html")
    cfg = json.dumps(ops_config(c, agency_email), indent=2, ensure_ascii=False)
    (ops / "Config.gs").write_text(
        f"/**\n * PER-CLIENT SETTINGS for {c['business']}.\n * Generated by onboarding/onboard.py from {c['id']}.toml. Do not edit here; edit the toml and re-run.\n"
        " * Secrets (owner key, SMS token) live in Script Properties, never here. Run setup() once.\n */\n"
        f"const CONFIG = {cfg};\n", encoding="utf-8")

    (out / "comms-gateway.json").write_text(json.dumps(gateway_entry(c), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out / "domain-rag.json").write_text(json.dumps(knowledge_entry(c), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out / "knowledge").mkdir()
    (out / "knowledge" / "README.md").write_text(
        f"Put {c['business']}'s approved documents here (see client-knowledge/README.md in BusinessOS). Nothing is indexed until they are added.\n", encoding="utf-8")
    (out / "ONBOARDING.md").write_text(checklist(c, out), encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("client", type=Path, help="path to the client's .toml")
    ap.add_argument("--out", type=Path, default=ROOT / "onboarding" / "build")
    ap.add_argument("--agency-email", default="", help="where exceptions for this client go (your ops inbox)")
    args = ap.parse_args(argv)
    try:
        out = generate(args.client, args.out, args.agency_email)
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 1
    except (OSError, tomllib.TOMLDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"Generated {out}\nNext: follow {out / 'ONBOARDING.md'}")
    if not args.agency_email:
        print("note: no --agency-email given; the back office won't email you about exceptions for this client", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
