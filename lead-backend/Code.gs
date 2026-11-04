/**
 * Lead backend for the booking site and chat receptionist.
 * Runs free on Google Apps Script, stores leads in a Google Sheet,
 * alerts the owner instantly and chases leads nobody has called back.
 *
 * Setup: see README.md in this folder (about 5 minutes per client).
 */

const SETTINGS = {
  sheetName: "Leads",
  ownerEmail: "",            // where new-lead alerts go. "" = the script owner's address
  businessName: "Northfield Plumbing & Heating",
  staleAfterMinutes: 30,     // leads still "New" after this get a reminder
  timezone: Session.getScriptTimeZone()
};

const COLUMNS = [
  "Received", "Ref", "Status", "Source", "Service", "Urgent", "Date", "Slot",
  "Name", "Phone", "Area", "Notes", "SMS consent", "Transcript", "Page", "Reminded", "SlotHour"
];

/* ---------- Web endpoints ---------- */

function doPost(e) {
  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    const lead = JSON.parse(e.postData.contents);
    validate_(lead);

    // Refuse double-booking of the same arrival window.
    if (lead.date && lead.slotHour !== undefined && takenSlots_().has(lead.date + "|" + lead.slotHour)) {
      return json_({ ok: false, error: "slot_taken" });
    }

    const sheet = sheet_();
    sheet.appendRow([
      new Date(), clean_(lead.ref), "New", clean_(lead.source), clean_(lead.service), lead.urgent ? "YES" : "",
      clean_(lead.date), clean_(lead.slot), clean_(lead.name), "'" + String(lead.phone).slice(0, 40), clean_(lead.area),
      clean_(lead.notes), lead.smsConsent ? "yes" : "no", clean_(lead.transcript), clean_(lead.page), "",
      lead.slotHour === undefined ? "" : lead.slotHour
    ]);
    if (lead.urgent) sheet.getRange(sheet.getLastRow(), 1, 1, COLUMNS.length).setBackground("#FDECEA");

    alertOwner_(lead);
    return json_({ ok: true, ref: lead.ref });
  } catch (err) {
    console.error(err);
    return json_({ ok: false, error: String(err.message || err) });
  } finally {
    lock.releaseLock();
  }
}

function doGet(e) {
  if (e && e.parameter && e.parameter.action === "slots") {
    return json_({ taken: Array.from(takenSlots_()) });
  }
  return json_({ ok: true, service: "lead-backend" });
}

/* ---------- Time-driven: chase leads nobody has contacted ---------- */

function remindStaleLeads() {
  const sheet = sheet_();
  const rows = sheet.getDataRange().getValues();
  const col = (name) => COLUMNS.indexOf(name);
  const cutoff = Date.now() - SETTINGS.staleAfterMinutes * 60 * 1000;
  const stale = [];

  for (let i = 1; i < rows.length; i++) {
    const r = rows[i];
    if (r[col("Status")] === "New" && !r[col("Reminded")] && new Date(r[col("Received")]).getTime() < cutoff) {
      stale.push(r);
      sheet.getRange(i + 1, col("Reminded") + 1).setValue(new Date());
    }
  }
  if (!stale.length) return;

  const lines = stale.map((r) => `• ${r[col("Name")]} (${r[col("Phone")]}), ${r[col("Service")]}, ${r[col("Area")]}. Waiting since ${fmt_(r[col("Received")])}`);
  MailApp.sendEmail({
    to: owner_(),
    subject: `${stale.length} lead${stale.length > 1 ? "s" : ""} still waiting for a call back`,
    body: `These enquiries are still marked New after ${SETTINGS.staleAfterMinutes} minutes:\n\n${lines.join("\n")}\n\n` +
      `Change Status to "Contacted" in the sheet once you've called:\n${SpreadsheetApp.getActive().getUrl()}`
  });
}

/* ---------- One-time setup (run from the editor) ---------- */

function setup() {
  const sheet = sheet_();
  const status = SpreadsheetApp.newDataValidation().requireValueInList(["New", "Contacted", "Booked", "Completed", "Lost"], true).build();
  sheet.getRange(2, COLUMNS.indexOf("Status") + 1, 1000).setDataValidation(status);

  ScriptApp.getProjectTriggers().forEach((t) => { if (t.getHandlerFunction() === "remindStaleLeads") ScriptApp.deleteTrigger(t); });
  ScriptApp.newTrigger("remindStaleLeads").timeBased().everyMinutes(15).create();
  console.log("Ready. Now Deploy → New deployment → Web app (Execute as: Me, Who has access: Anyone).");
}

/* ---------- Helpers ---------- */

function sheet_() {
  const ss = SpreadsheetApp.getActive();
  let sheet = ss.getSheetByName(SETTINGS.sheetName);
  if (!sheet) {
    sheet = ss.insertSheet(SETTINGS.sheetName);
    sheet.appendRow(COLUMNS);
    sheet.getRange(1, 1, 1, COLUMNS.length).setFontWeight("bold").setBackground("#0F5C8C").setFontColor("#FFFFFF");
    sheet.setFrozenRows(1);
    sheet.hideColumns(COLUMNS.indexOf("SlotHour") + 1);
  }
  return sheet;
}

function takenSlots_() {
  const rows = sheet_().getDataRange().getValues();
  const d = COLUMNS.indexOf("Date"), h = COLUMNS.indexOf("SlotHour"), s = COLUMNS.indexOf("Status");
  const out = new Set();
  for (let i = 1; i < rows.length; i++) {
    if (rows[i][d] !== "" && rows[i][h] !== "" && rows[i][s] !== "Lost") {
      const date = rows[i][d] instanceof Date ? Utilities.formatDate(rows[i][d], SETTINGS.timezone, "yyyy-MM-dd") : String(rows[i][d]);
      out.add(date + "|" + Number(rows[i][h]));
    }
  }
  return out;
}

function alertOwner_(lead) {
  const subject = `${lead.urgent ? "URGENT " : ""}New ${lead.source === "chat" ? "chat" : "booking"} lead: ${lead.service} in ${lead.area}`;
  const body = [
    `${lead.name} · ${lead.phone}`,
    `${lead.service}${lead.urgent ? " (urgent)" : ""}`,
    lead.date ? `When: ${lead.date}, ${lead.slot}` : `When: ${lead.slot || "asked for a call back"}`,
    `Area: ${lead.area}`,
    lead.notes ? `Notes: ${lead.notes}` : "",
    lead.transcript ? `\nChat transcript:\n${lead.transcript}` : "",
    `\nRef ${lead.ref}. Open the lead sheet: ${SpreadsheetApp.getActive().getUrl()}`
  ].filter(Boolean).join("\n");
  MailApp.sendEmail({ to: owner_(), subject, body });
}

function validate_(lead) {
  if (!lead || typeof lead !== "object") throw new Error("Empty lead");
  if (!lead.name || !lead.phone) throw new Error("Name and phone are required");
  if (String(lead.phone).replace(/\D/g, "").length < 10) throw new Error("Phone number too short");
}

// Stops formula injection when a lead types "=..." into a field.
function clean_(v) {
  if (v === undefined || v === null) return "";
  const s = String(v).slice(0, 4000);
  return /^[=+\-@]/.test(s) ? "'" + s : s;
}

function owner_() { return SETTINGS.ownerEmail || Session.getEffectiveUser().getEmail(); }
function fmt_(d) { return Utilities.formatDate(new Date(d), SETTINGS.timezone, "EEE d MMM, HH:mm"); }
function json_(obj) { return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON); }
