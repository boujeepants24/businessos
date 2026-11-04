/*
 * Offline test of the ops engine: fakes Apps Script services and a controllable clock,
 * then walks real jobs through their whole life. Run: node ops-engine/test/run.js
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

/* ---------- Clock ---------- */
const clock = { now: Date.parse("2026-11-04T10:00:00Z") }; // Wed 4 Nov 2026, 10:00 London
class FakeDate extends Date {
  constructor(...a) { if (a.length === 0) super(clock.now); else super(...a); }
  static now() { return clock.now; }
}
const advance = (h) => { clock.now += h * 36e5; };
const at = (iso) => { clock.now = Date.parse(iso); };

/* ---------- Spreadsheet ---------- */
const strip = (v) => (typeof v === "string" && v.startsWith("'") ? v.slice(1) : v);
function makeSheet(name) {
  const rows = [], raw = [];
  const range = (r, c, nr = 1, nc = 1) => ({
    setValue(v) { while (rows.length < r) rows.push([]); rows[r - 1][c - 1] = strip(v); return this; },
    getValues() { const out = []; for (let i = 0; i < nr; i++) { const row = []; for (let j = 0; j < nc; j++) row.push(rows[r - 1 + i] && rows[r - 1 + i][c - 1 + j] !== undefined ? rows[r - 1 + i][c - 1 + j] : ""); out.push(row); } return out; },
    setFontWeight() { return this; }, setBackground() { return this; }, setFontColor() { return this; }, setDataValidation() { return this; }
  });
  return {
    name, rows, raw,
    appendRow(vals) { raw.push(vals); rows.push(vals.map(strip)); },
    getRange: range,
    getDataRange() { const nc = Math.max(0, ...rows.map((r) => r.length)); return range(1, 1, rows.length, nc); },
    getLastRow() { return rows.length; },
    getLastColumn() { return rows[0] ? rows[0].length : 0; },
    setFrozenRows() {}, hideColumns() {}
  };
}
const sheets = {};
const SpreadsheetApp = {
  getActive: () => ({
    getSheetByName: (n) => sheets[n] || null,
    insertSheet: (n) => (sheets[n] = makeSheet(n)),
    getUrl: () => "https://docs.google.com/spreadsheets/d/TEST"
  }),
  newDataValidation: () => ({ requireValueInList() { return this; }, build() { return {}; } })
};

/* ---------- Other services ---------- */
const mail = [], fetches = [], files = [];
const props = {};
const tzParts = (d, tz) => Object.fromEntries(new Intl.DateTimeFormat("en-GB", { timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23", weekday: "long" }).formatToParts(d).map((p) => [p.type, p.value]));
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const Utilities = {
  formatDate(d, tz, pat) {
    const p = tzParts(new Date(d), tz);
    const map = { yyyy: p.year, MMMM: MONTHS[Number(p.month) - 1], MMM: MONTHS[Number(p.month) - 1].slice(0, 3), MM: p.month, dd: p.day, d: String(Number(p.day)), EEEE: p.weekday, EEE: p.weekday.slice(0, 3), HH: p.hour, H: String(Number(p.hour)), mm: p.minute };
    return pat.replace(/yyyy|MMMM|MMM|MM|dd|EEEE|EEE|HH|mm|d|H/g, (t) => map[t]);
  },
  parseDate(s, tz) {
    const [date, time] = s.split(" "); const [y, m, d] = date.split("-").map(Number); const [hh, mm] = time.split(":").map(Number);
    const guess = Date.UTC(y, m - 1, d, hh, mm);
    const p = tzParts(new Date(guess), tz);
    const shown = Date.UTC(+p.year, +p.month - 1, +p.day, +p.hour, +p.minute);
    return new FakeDate(guess - (shown - guess));
  },
  newBlob: (content, type, name) => ({ content, type, name, getAs() { return this; }, setName(n) { this.name = n; return this; } }),
  base64Encode: (s) => Buffer.from(s).toString("base64"),
  getUuid: () => "0123456789abcdef0123456789abcdef"
};
const ctx = {
  console, JSON, Math, Number, String, Object, Array, Set, Intl, Error, RegExp, encodeURIComponent, parseInt,
  Date: FakeDate,
  SpreadsheetApp, Utilities,
  MailApp: { sendEmail: (m) => mail.push(m) },
  UrlFetchApp: { fetch: (url, opts) => { fetches.push({ url, opts }); return { getResponseCode: () => 201, getContentText: () => "{}" }; } },
  PropertiesService: { getScriptProperties: () => ({ getProperty: (k) => (k in props ? props[k] : null), setProperty: (k, v) => (props[k] = String(v)) }) },
  LockService: { getScriptLock: () => ({ waitLock() {}, tryLock: () => true, releaseLock() {} }) },
  Session: { getScriptTimeZone: () => "Europe/London", getEffectiveUser: () => ({ getEmail: () => "agency@example.com" }) },
  ScriptApp: { getService: () => ({ getUrl: () => "https://script.google.com/macros/s/TEST/exec" }), getProjectTriggers: () => [], deleteTrigger() {}, newTrigger: () => ({ timeBased() { return this; }, everyMinutes() { return this; }, create() {} }) },
  DriveApp: { createFolder: () => ({ getId: () => "FOLDER", createFile: (b) => { files.push(b); return { getUrl: () => "https://drive.google.com/file/" + b.name }; } }), getFolderById: () => ({ createFile: (b) => { files.push(b); return { getUrl: () => "https://drive.google.com/file/" + b.name }; } }) },
  HtmlService: { createHtmlOutput: (h) => ({ html: h }), createTemplateFromFile: () => ({ evaluate() { return { setTitle() { return { addMetaTag() { return { ok: true }; } }; } }; } }) },
  ContentService: { MimeType: { JSON: "json" }, createTextOutput: (t) => ({ text: t, setMimeType() { return this; } }) }
};
vm.createContext(ctx);
const dir = path.join(__dirname, "..");
// Apps Script shares one global scope across files; concatenate to mimic it.
const src = ["Config.gs", "Data.gs", "Messages.gs", "Jobs.gs", "Invoices.gs", "Automations.gs", "Reports.gs", "Main.gs"].map((f) => fs.readFileSync(path.join(dir, f), "utf8")).join("\n");
vm.runInContext(src + "\n;globalThis.__api = { CONFIG, STATUS, setup, doPost, doGet, ownerApi, runAutomations, readJobs_, findJob_, sendMonthlyReport_ };", ctx);
const G = ctx.__api;

/* ---------- Helpers ---------- */
let passed = 0;
function test(name, fn) { fn(); passed++; console.log("  ✓ " + name); }
console.error = () => {}; // rejected test leads log errors on purpose
const post = (lead) => JSON.parse(G.doPost({ postData: { contents: JSON.stringify(lead) } }).text);
const job = (ref) => G.findJob_(ref);
const mailsTo = (to) => mail.filter((m) => m.to === to);
const lastMail = () => mail[mail.length - 1];
const exceptions = () => (sheets.Exceptions ? sheets.Exceptions.rows.slice(1) : []);
const KEY = () => props.OWNER_KEY;
const C = G.CONFIG;

console.log("Ops engine lifecycle");

test("setup creates sheets, owner key and invoice prefix", () => {
  G.setup();
  assert(sheets.Jobs && sheets.Messages && sheets.Exceptions);
  assert.strictEqual(KEY().length, 32);
  assert.strictEqual(props.INVOICE_PREFIX, "NPH");
});

const tomorrow = "2026-11-05";
test("website booking is confirmed instantly and the owner is alerted", () => {
  const r = post({ source: "booking-page", ref: "BK-1", name: "Priya Kaur", phone: "07700 900111", email: "priya@example.com", area: "Headingley", service: "Boiler service", date: tomorrow, slotHour: 10, slot: "10:00–12:00" });
  assert.deepStrictEqual([r.ok, r.status], [true, "Booked"]);
  assert(mailsTo("priya@example.com").some((m) => /Booked: Boiler service on Thursday 5 November, 10:00–12:00/.test(m.subject)), "customer confirmation");
  assert(mailsTo(C.ownerEmail).some((m) => /New booking: Boiler service/.test(m.subject)), "owner alert");
  assert(job("BK-1").BookingConfirmedAt);
});

test("the same arrival window can't be booked twice", () => {
  const r = post({ source: "booking-page", name: "Tom W", phone: "07700900222", area: "Roundhay", service: "Boiler repair", date: tomorrow, slotHour: 10 });
  assert.deepStrictEqual(r, { ok: false, error: "slot_taken" });
});

test("bad leads are rejected", () => {
  assert.strictEqual(post({ name: "X", phone: "123" }).ok, false);
  assert.strictEqual(post({ phone: "07700900333" }).ok, false);
});

test("a chat enquiry without a slot waits for a call back; no channel raises an exception", () => {
  const r = post({ source: "chat", ref: "CH-1", name: "Aisha Rahman", phone: "07700900444", area: "Horsforth", service: "Blocked drain", urgent: false, notes: "Kitchen sink" });
  assert.strictEqual(r.status, "New");
  assert(exceptions().some((e) => e[1] === "CH-1" && /Couldn't send "enquiryReceived"/.test(e[3])), "no email and no SMS → flagged");
});

test("with SMS configured, the chat lead gets an instant text", () => {
  C.channels.sms = { provider: "twilio", from: "+447700900000", accountSid: "AC123" }; props.TWILIO_AUTH_TOKEN = "tok";
  post({ source: "chat", ref: "CH-2", name: "Ben Ade", phone: "+44 7700 900555", area: "Otley", service: "Boiler repair", urgent: true });
  const f = fetches[fetches.length - 1];
  assert(/api\.twilio\.com/.test(f.url) && /Hi Ben, thanks for contacting Northfield/.test(f.opts.payload.Body));
});

test("15 minutes without a call back → owner reminded once", () => {
  advance(0.3);
  G.runAutomations();
  assert.strictEqual(mailsTo(C.ownerEmail).filter((m) => /Still waiting for a call back: Aisha/.test(m.subject)).length, 1);
  G.runAutomations();
  assert.strictEqual(mailsTo(C.ownerEmail).filter((m) => /Still waiting for a call back: Aisha/.test(m.subject)).length, 1, "not repeated");
});

test("2 hours without a call back → agency told; urgent jobs emailed straight away", () => {
  advance(2);
  G.runAutomations();
  assert(exceptions().some((e) => e[1] === "CH-1" && e[2] === "normal"));
  assert(mailsTo(C.agencyEmail).some((m) => /Ben Ade not called back.*URGENT/.test(m.subject)));
});

test("owner app: bad key is refused", () => {
  assert.throws(() => G.ownerApi("nope", "state"), /Not authorised/);
  assert(/isn't valid/.test(G.doGet({ parameter: { app: "owner", key: "nope" } }).html));
});

test("owner app: call, quote, quote follow-ups, then book", () => {
  let s = G.ownerApi(KEY(), "state");
  assert.strictEqual(s.callBack.length, 2);
  s = G.ownerApi(KEY(), "called", { ref: "CH-1" });
  assert.strictEqual(job("CH-1").Status, "Contacted");
  G.ownerApi(KEY(), "quote", { ref: "CH-1", amount: 95, text: "Clear kitchen drain" });
  assert.strictEqual(job("CH-1").Status, "Quoted");
  advance(48); G.runAutomations();
  assert.strictEqual(Number(job("CH-1").QuoteFollowups), 1);
  advance(72); G.runAutomations();
  assert.strictEqual(Number(job("CH-1").QuoteFollowups), 2);
  advance(72); G.runAutomations();
  assert.strictEqual(Number(job("CH-1").QuoteFollowups), 2, "stops after the configured follow-ups");
  assert.throws(() => G.ownerApi(KEY(), "book", { ref: "CH-1", date: tomorrow, slotHour: 10 }), /already booked/);
  G.ownerApi(KEY(), "book", { ref: "CH-1", date: "2026-11-12", slotHour: 14 });
  assert.strictEqual(job("CH-1").Status, "Booked");
});

test("day-before reminder is sent, but never during quiet hours", () => {
  at("2026-11-11T22:30:00Z"); G.runAutomations();
  assert(!job("CH-1").BookingReminderAt, "quiet hours respected");
  at("2026-11-12T08:15:00Z"); G.runAutomations();
  assert(job("CH-1").BookingReminderAt, "sent in the morning");
});

test("job done → numbered invoice PDF emailed and saved to Drive", () => {
  at("2026-11-12T15:00:00Z");
  C.business.taxRate = 0.2;
  G.ownerApi(KEY(), "done", { ref: "CH-1", amount: 95, workDone: "Cleared kitchen drain, jetted outside gully" });
  const j = job("CH-1");
  assert.deepStrictEqual([j.Status, j.InvoiceNo, j.InvoiceNet, j.InvoiceTax, j.InvoiceTotal], ["Invoiced", "NPH-0001", 95, 19, 114]);
  assert(/INVOICE[\s\S]*Cleared kitchen drain[\s\S]*£114\.00/.test(files[files.length - 1].content), "PDF content");
  assert(/drive\.google\.com/.test(j.InvoiceUrl));
  assert(j.RebookDueAt, "drains rebook in 6 months");
});

test("review request after 2 hours, follow-up after 4 days", () => {
  advance(2.5); G.runAutomations();
  assert(job("CH-1").ReviewRequestedAt);
  advance(96); G.runAutomations();
  assert(job("CH-1").ReviewFollowupAt);
});

test("unpaid invoice: chased at 3, 7 and 14 days, escalated at 21", () => {
  at("2026-11-15T16:00:00Z"); G.runAutomations(); assert.strictEqual(Number(job("CH-1").InvoiceChases), 1);
  at("2026-11-19T16:00:00Z"); G.runAutomations(); assert.strictEqual(Number(job("CH-1").InvoiceChases), 2);
  at("2026-11-26T16:00:00Z"); G.runAutomations(); assert.strictEqual(Number(job("CH-1").InvoiceChases), 3);
  at("2026-12-03T16:00:00Z"); G.runAutomations();
  assert(mailsTo(C.agencyEmail).some((m) => /Invoice NPH-0001 \(£114\.00\) unpaid after 21 days/.test(m.subject)));
  at("2026-12-10T16:00:00Z"); G.runAutomations(); assert.strictEqual(Number(job("CH-1").InvoiceChases), 3, "no 4th chase");
});

test("marking paid sends a thank-you and stops chasing", () => {
  G.ownerApi(KEY(), "paid", { ref: "CH-1" });
  assert.strictEqual(job("CH-1").Status, "Paid");
  assert(fetches.some((f) => f.opts.payload && /received your payment for invoice NPH-0001/.test(f.opts.payload.Body)));
});

test("first website job: completed with nothing to charge is closed, no invoice", () => {
  G.ownerApi(KEY(), "done", { ref: "BK-1", amount: 0 });
  const j = job("BK-1");
  assert.strictEqual(j.Status, "Closed"); assert(!j.InvoiceNo);
});

test("owner forgets to close a job → asked once the next day", () => {
  at("2026-12-10T09:00:00Z");
  post({ source: "booking-page", ref: "BK-2", name: "Sam Lee", phone: "07700900666", email: "sam@example.com", area: "Leeds", service: "Boiler repair", date: "2026-12-10", slotHour: 12, slot: "12:00–14:00" });
  at("2026-12-11T09:00:00Z"); G.runAutomations();
  assert(mailsTo(C.ownerEmail).some((m) => /Did the Boiler repair job for Sam Lee happen/.test(m.subject)));
});

test("past customers are invited back when their service is due", () => {
  at("2027-05-13T10:00:00Z"); G.runAutomations();
  assert(job("CH-1").RebookSentAt, "6-month drain rebook");
  assert(!job("BK-1").RebookSentAt, "boiler service not due until month 11");
  at("2027-11-10T12:00:00Z"); G.runAutomations();
  assert(job("BK-1").RebookSentAt);
});

test("monthly report goes to the owner on the 1st, once", () => {
  at("2026-12-01T09:00:00Z"); const before = mail.length;
  G.runAutomations(); G.runAutomations();
  const reports = mail.slice(before).filter((m) => /November 2026 summary/.test(m.subject));
  assert.strictEqual(reports.length, 1);
  assert(/Enquiries handled: 3/.test(reports[0].body) && /Invoiced: £114\.00/.test(reports[0].body), reports[0].body);
});

test("formula injection in customer fields is neutralised", () => {
  at("2027-11-01T12:00:00Z");
  post({ source: "chat", ref: "CH-9", name: "=HYPERLINK(\"http://x\")", phone: "07700900777", area: "+cmd", service: "Boiler repair" });
  const written = sheets.Jobs.raw.find((r) => r[0] === "CH-9");
  assert(written[6].startsWith("'=") && written[9].startsWith("'+"), "name and area written as text, not formulas");
});

test("every customer message is logged", () => {
  const log = sheets.Messages.rows.slice(1);
  assert(log.length > 20 && log.every((r) => r[1] && r[2]));
});


test("missed call from the comms gateway: one lead, no second auto-text, repeat calls merge", () => {
  at("2027-11-02T10:00:00Z");
  const before = fetches.length;
  const r1 = post({ source: "missed-call", ref: "MC-AAAA1111", name: "Missed caller", phone: "+447700900888", service: "Call back", notes: "Missed call. Text-back sent.", skipAutoReply: true });
  assert.strictEqual(r1.status, "New");
  assert.strictEqual(fetches.length, before, "gateway already texted: Ops Engine must not text again");
  assert(mailsTo(C.ownerEmail).some((m) => /Call back: Call back/.test(m.subject)), "owner alerted");
  advance(0.5);
  const r2 = post({ source: "missed-call", ref: "MC-BBBB2222", name: "Missed caller", phone: "+447700900888", service: "Call back", skipAutoReply: true });
  assert.deepStrictEqual([r2.merged, r2.ref], [true, "MC-AAAA1111"]);
  assert.strictEqual(G.readJobs_().filter((j) => String(j.Phone).endsWith("7700900888")).length, 1);
  assert(/Called again \(missed\)/.test(job("MC-AAAA1111").History));
});

test("a text reply is attached to the caller's open lead and the owner is told", () => {
  const before = mailsTo(C.ownerEmail).length;
  const r = post({ type: "message", channel: "sms", phone: "+447700900888", text: "Hi, it's Raj. Kitchen tap leaking, can you come Friday?" });
  assert.deepStrictEqual([r.ok, r.ref], [true, "MC-AAAA1111"]);
  assert(/\[Text .*\] Hi, it's Raj\. Kitchen tap leaking/.test(job("MC-AAAA1111").Notes));
  const m = mailsTo(C.ownerEmail).slice(before);
  assert(m.some((x) => /^Text from Missed caller: Hi, it's Raj/.test(x.subject)));
});

test("numbers match however they were typed (local vs international format)", () => {
  post({ source: "booking-page", ref: "BK-LOCAL", name: "Priya K", phone: "07700 900999", area: "Leeds", service: "Boiler repair", date: "2027-11-09", slotHour: 10, slot: "10:00–12:00" });
  const r = post({ type: "message", channel: "voicemail", phone: "+447700900999", text: "Voicemail (14s): https://api.twilio.com/rec/RE1" });
  assert.strictEqual(r.ref, "BK-LOCAL");
  assert(/\[Voicemail .*\] Voicemail \(14s\)/.test(job("BK-LOCAL").Notes));
});

test("a text from an unknown number starts a new enquiry without an auto-reply", () => {
  const before = fetches.length;
  const r = post({ type: "message", channel: "sms", phone: "+15125550123", text: "Do you service Worcester boilers?" });
  assert.strictEqual(r.created, true);
  const j = G.readJobs_().find((x) => String(x.Phone).endsWith("5125550123"));
  assert.deepStrictEqual([j.Name, j.Status, j.Notes], ["Text enquiry", "New", "Do you service Worcester boilers?"]);
  assert.strictEqual(fetches.length, before, "no automatic text back to an inbound text");
});

test("a text after a finished job starts a fresh enquiry instead of reopening it", () => {
  // CH-1 was paid earlier in this suite.
  const r = post({ type: "message", channel: "sms", phone: "+44 7700 900444", text: "Drain blocked again" });
  assert.strictEqual(r.created, true);
});

test("message events are validated", () => {
  assert.strictEqual(post({ type: "message", phone: "", text: "hi" }).ok, false);
  assert.strictEqual(post({ type: "message", phone: "+447700900111", text: "" }).ok, false);
});

console.log(`\n${passed} passed`);
