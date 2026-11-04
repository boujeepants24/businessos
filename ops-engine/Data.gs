/**
 * Data layer. One row per customer request, followed from enquiry to rebooking.
 * Columns are looked up by header name, so reordering columns in the sheet is safe.
 */

const STATUS = {
  NEW: "New",               // enquiry in, nobody has spoken to the customer yet
  CONTACTED: "Contacted",   // spoken to, not booked yet
  QUOTED: "Quoted",         // quote sent, waiting for a yes
  BOOKED: "Booked",         // date and arrival window agreed
  INVOICED: "Invoiced",     // job done, invoice sent, waiting for payment
  PAID: "Paid",             // money in
  CLOSED: "Closed",         // done with nothing to collect (warranty, free call-back)
  LOST: "Lost"
};
const OPEN_STATUSES = [STATUS.NEW, STATUS.CONTACTED, STATUS.QUOTED, STATUS.BOOKED];

const JOB_COLUMNS = [
  "Ref", "Created", "Status", "Source", "Service", "Urgent", "Name", "Phone", "Email", "Area", "Notes",
  "Date", "SlotHour", "Slot",
  "ContactedAt", "CallbackAlertAt", "CallbackEscalatedAt",
  "QuoteAmount", "QuoteText", "QuoteSentAt", "QuoteFollowups",
  "BookingConfirmedAt", "BookingReminderAt", "CloseoutReminderAt",
  "CompletedAt", "WorkDone", "InvoiceNo", "InvoiceNet", "InvoiceTax", "InvoiceTotal", "InvoiceUrl", "InvoiceSentAt", "InvoiceChases", "InvoiceEscalatedAt",
  "PaidAt", "ReviewRequestedAt", "ReviewFollowupAt",
  "RebookDueAt", "RebookSentAt",
  "LostReason", "Transcript", "Page", "History"
];
const LOG_COLUMNS = ["Time", "Ref", "Template", "Channel", "To", "Result", "Detail"];
const EXCEPTION_COLUMNS = ["Time", "Ref", "Severity", "What happened", "Suggested action", "Resolved"];

function sheetByName_(name, columns, headerColor) {
  const ss = SpreadsheetApp.getActive();
  let sh = ss.getSheetByName(name);
  if (!sh) {
    sh = ss.insertSheet(name);
    sh.appendRow(columns);
    sh.getRange(1, 1, 1, columns.length).setFontWeight("bold").setBackground(headerColor || "#23408E").setFontColor("#FFFFFF");
    sh.setFrozenRows(1);
  }
  return sh;
}
function jobsSheet_() { return sheetByName_("Jobs", JOB_COLUMNS); }

/** All jobs as objects: { _row, Ref, Status, ... } */
function readJobs_() {
  const sh = jobsSheet_();
  const values = sh.getDataRange().getValues();
  const head = values[0];
  const out = [];
  for (let i = 1; i < values.length; i++) {
    if (!values[i][0]) continue;
    const job = { _row: i + 1 };
    head.forEach((h, c) => { job[h] = values[i][c]; });
    out.push(job);
  }
  return out;
}
function findJob_(ref) {
  const job = readJobs_().find((j) => String(j.Ref) === String(ref));
  if (!job) throw new Error("No job with reference " + ref);
  return job;
}

/** Write only the changed fields of one job, and note it in the job's history. */
function updateJob_(job, patch, note) {
  const sh = jobsSheet_();
  const head = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0];
  if (note) patch.History = (job.History ? job.History + "\n" : "") + stamp_(new Date()) + "  " + note;
  Object.keys(patch).forEach((k) => {
    const c = head.indexOf(k);
    if (c === -1) throw new Error("Unknown column " + k);
    sh.getRange(job._row, c + 1).setValue(patch[k]);
    job[k] = patch[k];
  });
  return job;
}

function appendJob_(fields) {
  const sh = jobsSheet_();
  const head = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0];
  sh.appendRow(head.map((h) => (fields[h] === undefined ? "" : fields[h])));
  const job = Object.assign({ _row: sh.getLastRow() }, fields);
  if (fields.Urgent) sh.getRange(job._row, 1, 1, head.length).setBackground("#FBE3D8");
  return job;
}

function logMessage_(ref, template, channel, to, result, detail) {
  sheetByName_("Messages", LOG_COLUMNS, "#4B5563").appendRow([new Date(), ref, template, channel, to, result, detail || ""]);
}

/** Something a human at the agency should look at. Emailed straight away when urgent. */
function raiseException_(ref, severity, what, action) {
  sheetByName_("Exceptions", EXCEPTION_COLUMNS, "#B4420F").appendRow([new Date(), ref, severity, what, action, ""]);
  if (severity === "urgent" && CONFIG.agencyEmail) {
    MailApp.sendEmail({ to: CONFIG.agencyEmail, subject: `[${CONFIG.business.name}] ${what}`, body: `${what}\n\nSuggested action: ${action}\nRef: ${ref}\nSheet: ${SpreadsheetApp.getActive().getUrl()}` });
  }
}

/* ---------- Small helpers ---------- */
function clean_(v) {
  if (v === undefined || v === null) return "";
  const s = String(v).slice(0, 4000);
  return /^[=+\-@]/.test(s) ? "'" + s : s;
}
function ymd_(v) {
  if (!v) return "";
  if (v instanceof Date) return Utilities.formatDate(v, CONFIG.timing.timezone, "yyyy-MM-dd");
  return String(v).replace(/^'/, "").slice(0, 10);
}
function stamp_(d) { return Utilities.formatDate(d, CONFIG.timing.timezone, "d MMM HH:mm"); }
function hoursSince_(d, now) { return d ? ((now || new Date()) - new Date(d)) / 36e5 : Infinity; }
function daysSince_(d, now) { return hoursSince_(d, now) / 24; }
function money_(n) {
  return new Intl.NumberFormat(CONFIG.business.locale, { style: "currency", currency: CONFIG.business.currency }).format(Number(n) || 0);
}
/** Start of the job's arrival window as a Date in the business's timezone. */
function jobStart_(job) {
  const date = ymd_(job.Date);
  if (!date || job.SlotHour === "" || job.SlotHour === undefined) return null;
  const hh = String(Number(job.SlotHour)).padStart(2, "0");
  return Utilities.parseDate(`${date} ${hh}:00`, CONFIG.timing.timezone, "yyyy-MM-dd HH:mm");
}
/** Settings for a service, tolerant of wording differences ("Blocked drain" vs "Blocked drains"). */
function serviceConfig_(name) {
  const key = (s) => String(s || "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim().split(" ").map((w) => w.replace(/s$/, "")).join(" ");
  const want = key(name);
  const hit = Object.keys(CONFIG.services).find((k) => key(k) === want) ||
              Object.keys(CONFIG.services).find((k) => key(k).startsWith(want) || want.startsWith(key(k)));
  return hit ? CONFIG.services[hit] : {};
}
function phone_(job) { return String(job.Phone || "").replace(/^'/, ""); }
function firstName_(name) { return String(name || "").trim().split(/\s+/)[0] || "there"; }
function newRef_(prefix) { return (prefix || "J") + "-" + Date.now().toString(36).toUpperCase().slice(-6); }
