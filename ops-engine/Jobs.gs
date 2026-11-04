/**
 * The job lifecycle. Each function is one thing that happens to a job,
 * whether it's triggered by a customer (intake), the owner (owner app) or the clock (Automations.gs).
 */

/** A new enquiry from the booking site or chat receptionist. */
function intakeLead_(lead) {
  if (!lead || !lead.name || !lead.phone) throw new Error("Name and phone are required");
  if (String(lead.phone).replace(/\D/g, "").length < 10) throw new Error("Phone number too short");

  const hasSlot = lead.date && lead.slotHour !== undefined && lead.slotHour !== "";
  if (hasSlot && takenSlots_().has(lead.date + "|" + Number(lead.slotHour))) return { ok: false, error: "slot_taken" };

  const now = new Date();
  const job = appendJob_({
    Ref: clean_(lead.ref) || newRef_(lead.source === "chat" ? "CH" : "BK"),
    Created: now,
    Status: hasSlot ? STATUS.BOOKED : STATUS.NEW,
    Source: clean_(lead.source || "web"),
    Service: clean_(lead.service), Urgent: lead.urgent ? "YES" : "",
    Name: clean_(lead.name), Phone: "'" + String(lead.phone).slice(0, 40), Email: clean_(lead.email || ""),
    Area: clean_(lead.area), Notes: clean_(lead.notes),
    Date: hasSlot ? "'" + String(lead.date).slice(0, 10) : "", SlotHour: hasSlot ? Number(lead.slotHour) : "", Slot: clean_(lead.slot || ""),
    Transcript: clean_(lead.transcript || ""), Page: clean_(lead.page || ""),
    QuoteFollowups: 0, InvoiceChases: 0,
    History: stamp_(now) + "  Enquiry received via " + (lead.source || "web")
  });
  job.Phone = String(lead.phone);
  job.Date = hasSlot ? String(lead.date).slice(0, 10) : "";

  // Customer hears back within seconds, even at 2am: it's their own enquiry, so quiet hours don't apply.
  if (hasSlot) {
    if (sendTemplate_(job, "bookingConfirmed")) updateJob_(job, { BookingConfirmedAt: now }, "Booking confirmation sent");
  } else {
    sendTemplate_(job, "enquiryReceived");
  }
  alertOwnerNewLead_(job);
  return { ok: true, ref: job.Ref, status: job.Status };
}

function alertOwnerNewLead_(job) {
  if (!CONFIG.ownerEmail) return;
  const booked = job.Status === STATUS.BOOKED;
  MailApp.sendEmail({
    to: CONFIG.ownerEmail,
    subject: `${job.Urgent ? "URGENT " : ""}${booked ? "New booking" : "Call back"}: ${job.Service} · ${job.Area}`,
    body: [
      `${job.Name} · ${job.Phone}${job.Email ? " · " + job.Email : ""}`,
      `${job.Service}${job.Urgent ? " (URGENT)" : ""}`,
      booked ? `Booked: ${vars_(job).when}` : "Not booked yet. Please call them back.",
      `Area: ${job.Area}`,
      job.Notes ? `Notes: ${job.Notes}` : "",
      job.Transcript ? `\nChat:\n${job.Transcript}` : "",
      `\nRef ${job.Ref}`,
      `Your jobs app: ${ownerAppUrl_()}`
    ].filter(Boolean).join("\n")
  });
}

/** Taken arrival windows, for the booking page and double-booking checks. */
function takenSlots_() {
  const out = new Set();
  readJobs_().forEach((j) => {
    if (j.Status === STATUS.LOST || !j.Date || j.SlotHour === "") return;
    out.add(ymd_(j.Date) + "|" + Number(j.SlotHour));
  });
  return out;
}

/* ---------- Owner actions (called from the owner app) ---------- */

function markContacted_(ref) {
  const job = findJob_(ref);
  if (job.Status !== STATUS.NEW) return job;
  return updateJob_(job, { Status: STATUS.CONTACTED, ContactedAt: new Date() }, "Owner called the customer");
}

function bookJob_(ref, date, slotHour, slotLabel) {
  const job = findJob_(ref);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) throw new Error("Pick a date");
  const key = date + "|" + Number(slotHour);
  if (ymd_(job.Date) + "|" + Number(job.SlotHour) !== key && takenSlots_().has(key)) throw new Error("That arrival window is already booked");
  updateJob_(job, {
    Status: STATUS.BOOKED, Date: "'" + date, SlotHour: Number(slotHour), Slot: slotLabel,
    ContactedAt: job.ContactedAt || new Date(), BookingReminderAt: ""
  }, `Booked for ${date} ${slotLabel}`);
  job.Date = date;
  if (sendTemplate_(job, "bookingConfirmed")) updateJob_(job, { BookingConfirmedAt: new Date() });
  return job;
}

function sendQuote_(ref, amount, text) {
  const job = findJob_(ref);
  amount = Number(amount);
  if (!(amount > 0)) throw new Error("Enter the quote amount");
  updateJob_(job, { Status: STATUS.QUOTED, QuoteAmount: amount, QuoteText: clean_(text), QuoteSentAt: new Date(), QuoteFollowups: 0, ContactedAt: job.ContactedAt || new Date() }, "Quote sent: " + money_(amount));
  sendTemplate_(job, "quoteSent");
  return job;
}

/**
 * The owner taps "Job done". Amount 0 closes the job with nothing to collect.
 * Otherwise an invoice is created, saved to Drive and sent to the customer.
 */
function completeJob_(ref, amount, workDone) {
  const job = findJob_(ref);
  if ([STATUS.INVOICED, STATUS.PAID, STATUS.CLOSED].includes(job.Status)) throw new Error("This job is already completed");
  const now = new Date();
  const rebookMonths = serviceConfig_(job.Service).rebookMonths || 0;
  const rebookDue = rebookMonths ? new Date(now.getFullYear(), now.getMonth() + rebookMonths, now.getDate(), 10) : "";
  const net = Math.round(Number(amount) * 100) / 100;
  if (!(net >= 0)) throw new Error("Enter the amount charged, or 0 if there's nothing to pay");

  updateJob_(job, { CompletedAt: now, WorkDone: clean_(workDone || job.Service), RebookDueAt: rebookDue }, "Job completed");
  if (net === 0) {
    updateJob_(job, { Status: STATUS.CLOSED }, "Closed with nothing to invoice");
    return job;
  }
  const tax = Math.round(net * (CONFIG.business.taxRate || 0) * 100) / 100;
  updateJob_(job, { InvoiceNo: nextInvoiceNo_(), InvoiceNet: net, InvoiceTax: tax, InvoiceTotal: net + tax, InvoiceSentAt: now, InvoiceChases: 0, Status: STATUS.INVOICED });
  const pdf = buildInvoicePdf_(job);
  updateJob_(job, { InvoiceUrl: pdf.url }, `Invoice ${job.InvoiceNo} for ${money_(job.InvoiceTotal)} sent`);
  sendTemplate_(job, "invoice", { attachments: [pdf.blob] });
  return job;
}

function markPaid_(ref) {
  const job = findJob_(ref);
  if (job.Status !== STATUS.INVOICED) throw new Error("Only invoiced jobs can be marked paid");
  updateJob_(job, { Status: STATUS.PAID, PaidAt: new Date() }, "Payment received");
  sendTemplate_(job, "paymentThanks");
  return job;
}

function markLost_(ref, reason) {
  const job = findJob_(ref);
  return updateJob_(job, { Status: STATUS.LOST, LostReason: clean_(reason || "") }, "Marked lost" + (reason ? ": " + reason : ""));
}

/** For phone calls and walk-ins: the owner adds a job by hand from the app. */
function addManualJob_(f) {
  return intakeLead_({ source: "phone", name: f.name, phone: f.phone, email: f.email, area: f.area, service: f.service, notes: f.notes,
    date: f.date || undefined, slotHour: f.date ? f.slotHour : undefined, slot: f.slot });
}
