/**
 * Reporting. The owner gets a plain monthly summary on the 1st, showing what the system did for them.
 * computeMetrics_ is also what HQ uses (it reads the same Jobs tab).
 */

function computeMetrics_(jobs, from, to) {
  const inRange = (d) => d && new Date(d) >= from && new Date(d) < to;
  const created = jobs.filter((j) => inRange(j.Created));
  const responseMins = created.filter((j) => j.ContactedAt || j.BookingConfirmedAt)
    .map((j) => (new Date(j.ContactedAt || j.BookingConfirmedAt) - new Date(j.Created)) / 6e4);
  const afterHours = created.filter((j) => {
    const h = Number(Utilities.formatDate(new Date(j.Created), CONFIG.timing.timezone, "H"));
    return h < 8 || h >= 18;
  });
  const invoiced = jobs.filter((j) => inRange(j.InvoiceSentAt));
  const paid = jobs.filter((j) => inRange(j.PaidAt));
  const outstanding = jobs.filter((j) => j.Status === STATUS.INVOICED);
  return {
    enquiries: created.length,
    afterHours: afterHours.length,
    autoBooked: created.filter((j) => j.Source === "booking-page").length,
    booked: jobs.filter((j) => inRange(j.BookingConfirmedAt)).length,
    completed: jobs.filter((j) => inRange(j.CompletedAt)).length,
    invoicedCount: invoiced.length,
    invoicedTotal: invoiced.reduce((s, j) => s + (Number(j.InvoiceTotal) || 0), 0),
    paidTotal: paid.reduce((s, j) => s + (Number(j.InvoiceTotal) || 0), 0),
    outstandingCount: outstanding.length,
    outstandingTotal: outstanding.reduce((s, j) => s + (Number(j.InvoiceTotal) || 0), 0),
    reviewsRequested: jobs.filter((j) => inRange(j.ReviewRequestedAt)).length,
    rebooksSent: jobs.filter((j) => inRange(j.RebookSentAt)).length,
    lost: jobs.filter((j) => j.Status === STATUS.LOST && inRange(j.Created)).length,
    medianResponseMins: responseMins.length ? responseMins.sort((a, b) => a - b)[Math.floor(responseMins.length / 2)] : null
  };
}

function maybeSendReports_(now) {
  const props = PropertiesService.getScriptProperties();
  const month = Utilities.formatDate(now, CONFIG.timing.timezone, "yyyy-MM");
  const day = Number(Utilities.formatDate(now, CONFIG.timing.timezone, "d"));
  const hour = Number(Utilities.formatDate(now, CONFIG.timing.timezone, "H"));
  if (day !== 1 || hour < 8 || props.getProperty("LAST_MONTHLY") === month) return;

  const to = new Date(now.getFullYear(), now.getMonth(), 1);
  const from = new Date(now.getFullYear(), now.getMonth() - 1, 1);
  sendMonthlyReport_(from, to);
  props.setProperty("LAST_MONTHLY", month);
}

function sendMonthlyReport_(from, to) {
  const m = computeMetrics_(readJobs_(), from, to);
  const label = Utilities.formatDate(from, CONFIG.timing.timezone, "MMMM yyyy");
  const lines = [
    `Hi ${CONFIG.business.ownerName},`,
    ``,
    `Here's what happened in ${label}.`,
    ``,
    `Enquiries handled: ${m.enquiries}`,
    `  of which came in outside office hours: ${m.afterHours}`,
    `  booked straight from the website: ${m.autoBooked}`,
    m.medianResponseMins === null ? null : `Typical time to first response: ${m.medianResponseMins < 1 ? "under a minute" : Math.round(m.medianResponseMins) + " minutes"}`,
    `Jobs booked: ${m.booked}`,
    `Jobs completed: ${m.completed}`,
    ``,
    `Invoiced: ${money_(m.invoicedTotal)} across ${m.invoicedCount} invoices`,
    `Paid: ${money_(m.paidTotal)}`,
    `Still outstanding: ${money_(m.outstandingTotal)} on ${m.outstandingCount} invoices (being chased automatically)`,
    ``,
    `Review requests sent: ${m.reviewsRequested}`,
    `Past customers invited back: ${m.rebooksSent}`,
    ``,
    `Full detail is in your sheet: ${SpreadsheetApp.getActive().getUrl()}`
  ].filter((l) => l !== null);
  MailApp.sendEmail({ to: CONFIG.ownerEmail, cc: CONFIG.agencyEmail, subject: `${CONFIG.business.name}: ${label} summary`, body: lines.join("\n") });
}
