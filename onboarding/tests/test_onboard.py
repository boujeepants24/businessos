"""Tests for the onboarding generator. Standard library only: python3 -m unittest discover onboarding/tests"""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
EXAMPLE = ROOT / "onboarding" / "client.example.toml"

spec = importlib.util.spec_from_file_location("onboard", ROOT / "onboarding" / "onboard.py")
onboard = importlib.util.module_from_spec(spec)
sys.modules["onboard"] = onboard
spec.loader.exec_module(onboard)

NODE = shutil.which("node")


def node_eval(js: str) -> object:
    out = subprocess.run([NODE, "-e", js], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def load_window_config(path: Path, name: str) -> dict:
    return node_eval(f"const window={{}}; {path.read_text()}; process.stdout.write(JSON.stringify(window.{name}))")


def fields_used(source: Path) -> set[str]:
    """Top-level config fields a component reads, e.g. C.businessName -> businessName."""
    return set(re.findall(r"\bC\.([A-Za-z0-9_]+)", source.read_text()))


class GeneratorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.out = onboard.generate(EXAMPLE, self.tmp, "ops@agency.example")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def test_writes_every_artifact(self) -> None:
        for rel in ("booking-site/index.html", "booking-site/app.js", "booking-site/config.js", "chat-receptionist/widget.js",
                    "chat-receptionist/config.js", "chat-receptionist/INSTALL.html", "ops-engine/Config.gs", "ops-engine/Jobs.gs",
                    "ops-engine/OwnerApp.html", "comms-gateway.json", "domain-rag.json", "knowledge/README.md", "ONBOARDING.md"):
            self.assertTrue((self.out / rel).is_file(), rel)
        self.assertFalse((self.out / "ops-engine" / "test").exists(), "tests are not deployed to the client")

    @unittest.skipUnless(NODE, "node not installed")
    def test_booking_config_provides_every_field_the_site_reads(self) -> None:
        cfg = load_window_config(self.out / "booking-site" / "config.js", "CLIENT")
        missing = fields_used(ROOT / "booking-site" / "app.js") - set(cfg)
        self.assertEqual(missing, set(), "booking-site/app.js reads fields the generator doesn't write")
        self.assertEqual(cfg["businessName"], "Northfield Plumbing & Heating")

    @unittest.skipUnless(NODE, "node not installed")
    def test_chat_config_provides_every_field_the_widget_reads(self) -> None:
        cfg = load_window_config(self.out / "chat-receptionist" / "config.js", "RECEPTIONIST")
        missing = fields_used(ROOT / "chat-receptionist" / "widget.js") - set(cfg)
        self.assertEqual(missing, set(), "chat-receptionist/widget.js reads fields the generator doesn't write")
        self.assertEqual(cfg["knowledgeUrl"], "", "no knowledge API configured in the example")

    @unittest.skipUnless(NODE, "node not installed")
    def test_ops_config_has_the_same_shape_as_the_template(self) -> None:
        shape = "const s=(o)=>o&&typeof o==='object'&&!Array.isArray(o)?Object.fromEntries(Object.keys(o).sort().map(k=>[k,s(o[k])])):typeof o;"
        tmpl = node_eval(f"{(ROOT / 'ops-engine' / 'Config.gs').read_text()}; {shape} process.stdout.write(JSON.stringify(s(CONFIG)))")
        gen = node_eval(f"{(self.out / 'ops-engine' / 'Config.gs').read_text()}; {shape} process.stdout.write(JSON.stringify(s(CONFIG)))")
        tmpl.pop("services"), gen.pop("services")  # keys are the client's own service names
        self.assertEqual(gen, tmpl, "generated Config.gs is missing or adding settings compared with ops-engine/Config.gs")

    def test_day_numbering_is_converted_per_component(self) -> None:
        # Mon-Sat: JavaScript getDay() counts Sunday = 0; Python weekday() counts Monday = 0.
        booking = json.loads(re.search(r"= (\{.*\});", (self.out / "booking-site" / "config.js").read_text(), re.S).group(1))
        gateway = json.loads((self.out / "comms-gateway.json").read_text())
        self.assertEqual(booking["hours"]["days"], [1, 2, 3, 4, 5, 6])
        self.assertEqual(gateway["hours"]["days"], [0, 1, 2, 3, 4, 5])
        self.assertEqual(onboard.js_days(["Sun"]), [0])
        self.assertEqual(onboard.py_days(["Sun"]), [6])

    def test_gateway_entry_is_accepted_by_the_gateway(self) -> None:
        sys.path.insert(0, str(ROOT / "comms-gateway" / "src"))
        try:
            from commsgateway.config import load_tenants
        finally:
            sys.path.pop(0)
        entry = json.loads((self.out / "comms-gateway.json").read_text())
        entry["ops_engine_url"] = "https://script.google.com/macros/s/X/exec"  # filled after the Apps Script deploy
        f = self.tmp / "gw.json"
        f.write_text(json.dumps({"clients": [entry]}))
        tenant = load_tenants(f)["+441134960123"]
        self.assertEqual((tenant.owner_phone, tenant.timezone, tenant.hours.days), ("+447700900500", "Europe/London", (0, 1, 2, 3, 4, 5)))

    def test_knowledge_entry_allows_only_the_clients_sites(self) -> None:
        entry = json.loads((self.out / "domain-rag.json").read_text())
        self.assertEqual(entry["allowed_origins"], ["https://book.northfieldplumbing.example", "https://northfieldplumbing.example"])
        self.assertEqual(entry["docs_dir"], "../clients/northfield/knowledge")

    def test_deployed_urls_flow_everywhere(self) -> None:
        data = tomllib.loads(EXAMPLE.read_text())
        data["deployed"] = {"ops_engine_url": "https://script.google.com/macros/s/ABC/exec", "knowledge_api": "https://kb.agency.example/"}
        toml = self.tmp / "deployed.toml"
        toml.write_text(_dump_toml(data))
        out = onboard.generate(toml, self.tmp / "b2", "")
        booking = (out / "booking-site" / "config.js").read_text()
        chat = (out / "chat-receptionist" / "config.js").read_text()
        self.assertIn('"webhookUrl": "https://script.google.com/macros/s/ABC/exec"', booking)
        self.assertIn('"knowledgeUrl": "https://kb.agency.example/v1/clients/northfield/ask"', chat)
        self.assertEqual(json.loads((out / "comms-gateway.json").read_text())["ops_engine_url"], "https://script.google.com/macros/s/ABC/exec")
        self.assertIn("[x] Run `setup()`", (out / "ONBOARDING.md").read_text())

    @unittest.skipUnless(NODE, "node not installed")
    def test_generated_back_office_passes_the_full_lifecycle_suite(self) -> None:
        test_dir = self.out / "ops-engine" / "test"
        test_dir.mkdir()
        shutil.copy2(ROOT / "ops-engine" / "test" / "run.js", test_dir / "run.js")
        r = subprocess.run([NODE, str(test_dir / "run.js")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout[-2000:] + r.stderr[-2000:])
        self.assertRegex(r.stdout, r"\n(\d+) passed")

    def test_values_are_escaped_not_injected(self) -> None:
        data = tomllib.loads(EXAMPLE.read_text())
        data["business"] = 'Evil "Co"</script><script>alert(1)</script>'
        toml = self.tmp / "evil.toml"
        toml.write_text(_dump_toml(data))
        out = onboard.generate(toml, self.tmp / "b3", "")
        js = (out / "booking-site" / "config.js").read_text()
        self.assertIn(json.dumps(data["business"]), js, "strings are JSON-encoded, so quotes can't end the string early")
        if NODE:
            self.assertEqual(load_window_config(out / "booking-site" / "config.js", "CLIENT")["businessName"], data["business"])


class ValidationTest(unittest.TestCase):
    def bad(self, mutate) -> str:
        data = tomllib.loads(EXAMPLE.read_text())
        mutate(data)
        tmp = Path(tempfile.mkdtemp())
        try:
            toml = tmp / "c.toml"
            toml.write_text(_dump_toml(data))
            with self.assertRaises(onboard.ConfigError) as ctx:
                onboard.generate(toml, tmp / "out", "")
            self.assertFalse((tmp / "out").exists(), "nothing is written when validation fails")
            return str(ctx.exception)
        finally:
            shutil.rmtree(tmp)

    def test_rejects_the_mistakes_that_break_a_client(self) -> None:
        cases = {
            "international format": lambda d: d["contact"].update(public_phone="0113 496 0123"),
            "calls would loop": lambda d: d["contact"].update(owner_mobile=d["contact"]["public_phone"]),
            "not a known timezone": lambda d: d.update(timezone="London"),
            "must be a colour": lambda d: d["brand"].update(color="blue"),
            "unique id": lambda d: d["services"].append(dict(d["services"][0], name="Other")),
            "hours.days": lambda d: d["hours"].update(days=["Monday"]),
            "open < close": lambda d: d["hours"].update(open=18, close=8),
            "https URL": lambda d: d.update(booking_url="http://insecure.example"),
            "ending in /exec": lambda d: d.setdefault("deployed", {}).update(ops_engine_url="https://example.com/hook"),
            "tax.rate": lambda d: d["tax"].update(rate=20),
            "'id'": lambda d: d.update(id="Northfield Plumbing"),
        }
        for expected, mutate in cases.items():
            with self.subTest(expected):
                self.assertIn(expected, self.bad(mutate))

    def test_reports_all_problems_at_once(self) -> None:
        msg = self.bad(lambda d: (d["contact"].update(public_phone="x"), d["brand"].update(accent="red")))
        self.assertIn("public_phone", msg)
        self.assertIn("brand.accent", msg)


def _dump_toml(data: dict) -> str:
    """Minimal TOML writer for the tests (tomllib only reads)."""

    def val(v: object) -> str:
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, (int, float)):
            return repr(v)
        if isinstance(v, str):
            return json.dumps(v)
        if isinstance(v, list):
            return "[" + ", ".join(val(x) for x in v) + "]"
        raise TypeError(v)

    lines: list[str] = []
    tables: list[tuple[str, dict]] = []
    arrays: list[tuple[str, list]] = []

    def emit(prefix: str, table: dict) -> None:
        for k, v in table.items():
            if isinstance(v, dict):
                tables.append((f"{prefix}{k}", v))
            elif isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
                arrays.append((f"{prefix}{k}", v))
            else:
                lines.append(f"{k} = {val(v)}")

    emit("", data)
    while tables or arrays:
        if tables:
            name, t = tables.pop(0)
            lines.append(f"\n[{name}]")
            emit(f"{name}.", t)
            continue
        name, items = arrays.pop(0)
        for item in items:
            lines.append(f"\n[[{name}]]")
            for k, v in item.items():
                if isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
                    for sub in v:
                        lines.append(f"\n[[{name}.{k}]]")
                        lines.extend(f"{sk} = {val(sv)}" for sk, sv in sub.items())
                else:
                    lines.append(f"{k} = {val(v)}")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    unittest.main()
