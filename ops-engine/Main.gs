/**
 * Entry points. Deploy as a Web app (Execute as: Me, Who has access: Anyone).
 *   POST  /exec                         ← booking site and chat receptionist send leads here
 *   GET   /exec?action=slots            ← booking site reads taken arrival windows
 *   GET   /exec?app=owner&key=SECRET    ← the owner's jobs app (bookmark it on their phone)
 */

function doPost(e) {
  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    return json_(intakeLead_(JSON.parse(e.postData.contents)));
  } catch (err) {
    console.error(err);
    return json_({ ok: false, error: String(err.message || err) });
  } finally {
    lock.releaseLock();
  }
}

function doGet(e) {
  const p = (e && e.parameter) || {};
  if (p.action === "slots") return json_({ taken: Array.from(takenSlots_()) });
  if (p.app === "owner") {
    if (!validKey_(p.key)) return HtmlService.createHtmlOutput("<p style='font:16px system-ui;padding:24px'>This link isn't valid. Ask your account manager for your jobs app link.</p>");
    const t = HtmlService.createTemplateFromFile("OwnerApp");
    t.key = p.key;
    t.businessName = CONFIG.business.name;
    return t.evaluate().setTitle(CONFIG.business.name + " · Jobs").addMetaTag("viewport", "width=device-width, initial-scale=1, viewport-fit=cover");
  }
  return json_({ ok: true, service: "ops-engine", business: CONFIG.business.name });
}

/** The owner app's only door into the system. Every call carries the owner key. */
function ownerApi(key, action, args) {
  if (!validKey_(key)) throw new Error("Not authorised");
  args = args || {};
  const lock = LockService.getScriptLock();
  lock.waitLock(15000);
  try {
    switch (action) {
      case "state": break;
      case "called": markContacted_(args.ref); break;
      case "book": bookJob_(args.ref, args.date, args.slotHour, slotLabel_(args.slotHour)); break;
      case "quote": sendQuote_(args.ref, args.amount, args.text); break;
      case "done": completeJob_(args.ref, args.amount, args.workDone); break;
      case "paid": markPaid_(args.ref); break;
      case "lost": markLost_(args.ref, args.reason); break;
      case "add": addManualJob_(Object.assign({}, args, { slot: args.date ? slotLabel_(args.slotHour) : "" })); break;
      default: throw new Error("Unknown action " + action);
    }
    return ownerState_();
  } finally {
    lock.releaseLock();
  }
}

function ownerState_() {
  const jobs = readJobs_();
  const today = ymd_(new Date());
  const card = (j) => ({
    ref: j.Ref, name: j.Name, phone: phone_(j), area: j.Area, service: j.Service, urgent: !!j.Urgent, notes: j.Notes,
    date: ymd_(j.Date), slot: j.Slot, slotHour: j.SlotHour, status: j.Status,
    quote: j.QuoteAmount ? money_(j.QuoteAmount) : "", total: j.InvoiceTotal ? money_(j.InvoiceTotal) : "",
    invoiceNo: j.InvoiceNo, invoiceAgeDays: j.InvoiceSentAt ? Math.floor(daysSince_(j.InvoiceSentAt)) : null,
    waitingMins: j.Status === STATUS.NEW ? Math.round(hoursSince_(j.Created) * 60) : null
  });
  const booked = jobs.filter((j) => j.Status === STATUS.BOOKED).sort((a, b) => (ymd_(a.Date) + String(a.SlotHour).padStart(2, "0")).localeCompare(ymd_(b.Date) + String(b.SlotHour).padStart(2, "0")));
  const h = CONFIG.booking;
  const slots = [];
  for (let s = h.open; s + h.slotLengthHours <= h.close; s += h.slotLengthHours) slots.push({ hour: s, label: slotLabel_(s) });
  return {
    business: CONFIG.business.name, currency: CONFIG.business.currency, today,
    callBack: jobs.filter((j) => j.Status === STATUS.NEW || j.Status === STATUS.CONTACTED).map(card),
    quoted: jobs.filter((j) => j.Status === STATUS.QUOTED).map(card),
    overdue: booked.filter((j) => ymd_(j.Date) < today).map(card),
    today: booked.filter((j) => ymd_(j.Date) === today).map(card),
    upcoming: booked.filter((j) => ymd_(j.Date) > today).slice(0, 30).map(card),
    unpaid: jobs.filter((j) => j.Status === STATUS.INVOICED).map(card),
    services: Object.keys(CONFIG.services), slots, taken: Array.from(takenSlots_())
  };
}

function slotLabel_(hour) {
  const h = Number(hour), pad = (n) => String(n).padStart(2, "0");
  return `${pad(h)}:00–${pad(h + CONFIG.booking.slotLengthHours)}:00`;
}

function validKey_(key) {
  const real = PropertiesService.getScriptProperties().getProperty("OWNER_KEY");
  if (!real || !key || String(key).length !== real.length) return false;
  let diff = 0;
  for (let i = 0; i < real.length; i++) diff |= real.charCodeAt(i) ^ String(key).charCodeAt(i);
  return diff === 0;
}

function ownerAppUrl_() {
  let base = "";
  try { base = ScriptApp.getService().getUrl() || ""; } catch (_) {}
  const key = PropertiesService.getScriptProperties().getProperty("OWNER_KEY");
  return base ? `${base}?app=owner&key=${key}` : "(deploy the web app to get the link)";
}

function json_(obj) { return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON); }

/* ---------- One-time setup: run from the editor ---------- */

function setup() {
  const props = PropertiesService.getScriptProperties();
  if (!props.getProperty("OWNER_KEY")) props.setProperty("OWNER_KEY", Utilities.getUuid().replace(/-/g, ""));
  if (!props.getProperty("INVOICE_PREFIX")) {
    const initials = CONFIG.business.name.split(/\s+/).filter((w) => /^[A-Za-z]/.test(w)).map((w) => w[0].toUpperCase()).join("").slice(0, 3);
    props.setProperty("INVOICE_PREFIX", initials || "INV");
  }
  const jobs = jobsSheet_();
  const statusCol = JOB_COLUMNS.indexOf("Status") + 1;
  jobs.getRange(2, statusCol, 2000).setDataValidation(SpreadsheetApp.newDataValidation().requireValueInList(Object.values(STATUS), true).build());
  sheetByName_("Messages", LOG_COLUMNS, "#4B5563");
  sheetByName_("Exceptions", EXCEPTION_COLUMNS, "#B4420F");
  invoiceFolder_();

  ScriptApp.getProjectTriggers().forEach((t) => { if (t.getHandlerFunction() === "runAutomations") ScriptApp.deleteTrigger(t); });
  ScriptApp.newTrigger("runAutomations").timeBased().everyMinutes(15).create();

  console.log("Setup done. Next: Deploy → New deployment → Web app (Execute as: Me, Who has access: Anyone).");
  console.log("Then run showOwnerLink() to get the owner's jobs-app link.");
}

function showOwnerLink() { console.log(ownerAppUrl_()); }
