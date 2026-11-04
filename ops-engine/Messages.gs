/**
 * Every message the system sends, in one place, written the way a good office manager would.
 * {placeholders} are filled from the job. Edit wording freely; keep SMS versions under ~300 characters.
 */
const TEMPLATES = {
  enquiryReceived: {
    subject: "We've got your enquiry ({ref})",
    sms: "Hi {first}, thanks for contacting {business}. We've got your enquiry about {service} (ref {ref}) and will call you shortly. Urgent? Call {phone}.",
    email: "Hi {first},\n\nThanks for getting in touch with {business}. We've received your enquiry about {service} and someone will call you shortly to arrange a time.\n\nYour reference is {ref}.\n\nIf it's urgent, call us on {phone}.\n\n{business}"
  },
  bookingConfirmed: {
    subject: "Booked: {service} on {when}",
    sms: "{business}: you're booked for {service} on {when}. We'll text the day before. Need to change it? Reply or call {phone}. Ref {ref}",
    email: "Hi {first},\n\nYou're booked in.\n\nJob: {service}\nWhen: {when}\nWhere: {area}\nReference: {ref}\n\nWe'll send a reminder the day before. If you need to change the time, reply to this email or call {phone}.\n\n{business}"
  },
  bookingReminder: {
    subject: "Reminder: we're with you {when}",
    sms: "Reminder from {business}: we're with you {when} for {service}. Need to rearrange? Call {phone}. Ref {ref}",
    email: "Hi {first},\n\nA reminder that we're with you {when} for {service}.\n\nIf anything has changed, call {phone} or reply to this email.\n\n{business}"
  },
  quoteSent: {
    subject: "Your quote from {business} ({ref})",
    sms: "Hi {first}, your quote from {business} for {service} is {quoteAmount}. Details are in your email. Reply YES or call {phone} to book. Ref {ref}",
    email: "Hi {first},\n\nThanks for having us look at the job. Here's your quote:\n\n{quoteText}\n\nTotal: {quoteAmount}\n\nReply to this email or call {phone} to book it in.\n\n{business}"
  },
  quoteFollowup: {
    subject: "Following up on your quote ({ref})",
    sms: "Hi {first}, just checking you got our quote for {service} ({quoteAmount}). Any questions, call {phone}. Ref {ref}",
    email: "Hi {first},\n\nJust checking you received our quote for {service} ({quoteAmount}). Happy to answer any questions, or book it in whenever suits.\n\nCall {phone} or reply here.\n\n{business}"
  },
  invoice: {
    subject: "Invoice {invoiceNo} from {business}",
    sms: "Thanks {first}. Your invoice {invoiceNo} from {business} for {total} is in your email{payLinkSms}. Due {due}.",
    email: "Hi {first},\n\nThanks for choosing {business}. Your invoice is attached.\n\nInvoice: {invoiceNo}\nWork: {workDone}\nTotal: {total}\nDue: {due}\n\nHow to pay:\n{payment}{payLinkEmail}\n\nAny questions, just reply.\n\n{business}"
  },
  invoiceChase1: {
    subject: "Friendly reminder: invoice {invoiceNo}",
    sms: "Hi {first}, a friendly reminder that invoice {invoiceNo} ({total}) from {business} is due{payLinkSms}. Already paid? Thank you, please ignore.",
    email: "Hi {first},\n\nA friendly reminder that invoice {invoiceNo} for {total} is now due.\n\n{payment}{payLinkEmail}\n\nIf you've already paid, thank you, and please ignore this.\n\n{business}"
  },
  invoiceChase2: {
    subject: "Invoice {invoiceNo} is overdue",
    sms: "Hi {first}, invoice {invoiceNo} ({total}) from {business} is now overdue{payLinkSms}. Please pay or call {phone} if there's a problem.",
    email: "Hi {first},\n\nInvoice {invoiceNo} for {total} is now overdue.\n\n{payment}{payLinkEmail}\n\nIf there's a problem with the work or the invoice, call {phone} and we'll sort it out.\n\n{business}"
  },
  invoiceChase3: {
    subject: "Final reminder: invoice {invoiceNo}",
    sms: "{business}: final reminder for invoice {invoiceNo} ({total}){payLinkSms}. Please call {phone} today if you can't pay in full.",
    email: "Hi {first},\n\nThis is a final reminder that invoice {invoiceNo} for {total} remains unpaid.\n\n{payment}{payLinkEmail}\n\nIf you can't pay in full, call {phone} today and we'll agree a plan.\n\n{business}"
  },
  paymentThanks: {
    subject: "Payment received, thank you",
    sms: "Thanks {first}, we've received your payment for invoice {invoiceNo}. {business}",
    email: "Hi {first},\n\nWe've received your payment for invoice {invoiceNo}. Thank you.\n\n{business}"
  },
  reviewRequest: {
    subject: "How did we do?",
    sms: "Hi {first}, thanks for choosing {business}. If you were happy with the work, a quick Google review helps us a lot: {reviewUrl}. If anything wasn't right, reply here and {owner} will sort it.",
    email: "Hi {first},\n\nThanks again for choosing {business}. If you were happy with the work, a short Google review really helps a local business like ours:\n\n{reviewUrl}\n\nIf anything wasn't right, reply to this email and {owner} will personally sort it out.\n\n{business}"
  },
  reviewFollowup: {
    subject: "A quick favour?",
    sms: "Hi {first}, if you have 30 seconds, a review for {business} would mean a lot: {reviewUrl}. Thanks!",
    email: "Hi {first},\n\nIf you have 30 seconds, a review would mean a lot to us:\n\n{reviewUrl}\n\nThank you.\n\n{business}"
  },
  rebook: {
    subject: "Time for your {service}?",
    sms: "Hi {first}, it's {business}. It's about time for your next {service}. Want us to book you in? Reply or call {phone}.",
    email: "Hi {first},\n\nIt's been a while since we did your {service}, and it's about time for the next one.\n\nReply to this email or call {phone} and we'll find a time that suits.\n\n{business}"
  }
};

/** Placeholder values for one job. */
function vars_(job, extra) {
  const b = CONFIG.business;
  const start = jobStart_(job);
  const payLink = payLink_(job);
  return Object.assign({
    first: firstName_(job.Name), business: b.name, owner: b.ownerName, phone: b.phone, ref: job.Ref,
    service: String(job.Service || "your job").toLowerCase() === "general enquiry" ? "your enquiry" : job.Service || "your job",
    area: job.Area || "", reviewUrl: b.googleReviewUrl,
    when: start ? Utilities.formatDate(start, CONFIG.timing.timezone, "EEEE d MMMM") + (job.Slot ? ", " + job.Slot : "") : String(job.Slot || "the agreed time"),
    quoteAmount: money_(job.QuoteAmount), quoteText: job.QuoteText || job.Service,
    invoiceNo: job.InvoiceNo, total: money_(job.InvoiceTotal), workDone: job.WorkDone || job.Service,
    due: job.InvoiceSentAt ? Utilities.formatDate(new Date(new Date(job.InvoiceSentAt).getTime() + CONFIG.payment.termsDays * 864e5), CONFIG.timing.timezone, "d MMMM") : "",
    payment: CONFIG.payment.instructions,
    payLinkSms: payLink ? ": " + payLink : "", payLinkEmail: payLink ? "\n\nOr pay online: " + payLink : ""
  }, extra || {});
}
function payLink_(job) {
  const t = CONFIG.payment.payLinkTemplate;
  if (!t || !job.InvoiceNo) return "";
  return t.replace("{invoiceNo}", encodeURIComponent(job.InvoiceNo)).replace("{amount}", encodeURIComponent(job.InvoiceTotal));
}
function fill_(text, v) { return String(text).replace(/\{(\w+)\}/g, (m, k) => (v[k] === undefined || v[k] === null ? "" : String(v[k]))); }

function inQuietHours_(now) {
  const h = Number(Utilities.formatDate(now || new Date(), CONFIG.timing.timezone, "H"));
  const q = CONFIG.timing.quietHours;
  return q.start > q.end ? h >= q.start || h < q.end : h >= q.start && h < q.end;
}

/**
 * Send one template to a job's customer on every channel available.
 * Returns true if at least one channel accepted it. Never throws: failures are logged and raised.
 */
function sendTemplate_(job, key, opts) {
  opts = opts || {};
  const t = TEMPLATES[key];
  const v = vars_(job, opts.vars);
  let delivered = false;
  const phone = phone_(job);

  if (job.Email && /@/.test(job.Email)) {
    try {
      const mail = { to: String(job.Email), subject: fill_(t.subject, v), body: fill_(t.email, v), name: CONFIG.business.name, replyTo: CONFIG.business.email };
      if (opts.attachments) mail.attachments = opts.attachments;
      MailApp.sendEmail(mail);
      logMessage_(job.Ref, key, "email", job.Email, "sent");
      delivered = true;
    } catch (e) { logMessage_(job.Ref, key, "email", job.Email, "failed", e.message); }
  }
  if (phone && CONFIG.channels.sms.provider) {
    const r = sendSms_(phone, fill_(t.sms, v));
    logMessage_(job.Ref, key, "sms", phone, r.ok ? "sent" : "failed", r.detail);
    delivered = delivered || r.ok;
  }
  if (phone && CONFIG.channels.webhookUrl) {
    try {
      const res = UrlFetchApp.fetch(CONFIG.channels.webhookUrl, {
        method: "post", contentType: "application/json", muteHttpExceptions: true,
        payload: JSON.stringify({ template: key, to: phone, text: fill_(t.sms, v), ref: job.Ref, business: CONFIG.business.name })
      });
      const ok = res.getResponseCode() < 300;
      logMessage_(job.Ref, key, "webhook", phone, ok ? "sent" : "failed", String(res.getResponseCode()));
      delivered = delivered || ok;
    } catch (e) { logMessage_(job.Ref, key, "webhook", phone, "failed", e.message); }
  }
  if (!delivered) {
    logMessage_(job.Ref, key, "-", phone || job.Email || "-", "not sent", "No working channel for this customer");
    raiseException_(job.Ref, "normal", `Couldn't send "${key}" to ${job.Name}`, `Contact them by hand on ${phone || "(no phone)"} and check the Messages tab.`);
  }
  return delivered;
}

function sendSms_(to, body) {
  const sms = CONFIG.channels.sms;
  if (sms.provider !== "twilio") return { ok: false, detail: "Unknown SMS provider " + sms.provider };
  const token = PropertiesService.getScriptProperties().getProperty("TWILIO_AUTH_TOKEN");
  if (!token || !sms.accountSid) return { ok: false, detail: "Twilio credentials missing" };
  try {
    const res = UrlFetchApp.fetch(`https://api.twilio.com/2010-04-01/Accounts/${sms.accountSid}/Messages.json`, {
      method: "post", muteHttpExceptions: true,
      headers: { Authorization: "Basic " + Utilities.base64Encode(sms.accountSid + ":" + token) },
      payload: { To: to.replace(/[^\d+]/g, ""), From: sms.from, Body: body }
    });
    const code = res.getResponseCode();
    return { ok: code < 300, detail: code < 300 ? "" : res.getContentText().slice(0, 300) };
  } catch (e) { return { ok: false, detail: e.message }; }
}
