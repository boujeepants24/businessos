/**
 * The clock. runAutomations() runs every 15 minutes (set up by setup()).
 * Each rule is idempotent: it records when it acted, so a job is never messaged twice for the same thing.
 */

function runAutomations(nowOverride) {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(30000)) return; // a previous run is still going
  try {
    const now = nowOverride || new Date();
    const quiet = inQuietHours_(now);
    const T = CONFIG.timing;
    const done = [];

    readJobs_().forEach((job) => {
      try {
        // 1. Nobody has called a new enquiry back.
        if (job.Status === STATUS.NEW) {
          const mins = hoursSince_(job.Created, now) * 60;
          if (mins >= T.callbackAlertMinutes && !job.CallbackAlertAt) {
            MailApp.sendEmail({ to: CONFIG.ownerEmail, subject: `Still waiting for a call back: ${job.Name} (${job.Service})`,
              body: `${job.Name} enquired ${Math.round(mins)} minutes ago and hasn't been called yet.\n\nPhone: ${phone_(job)}\nArea: ${job.Area}\n${job.Notes ? "Notes: " + job.Notes + "\n" : ""}\nCall them, then tap "Called" in your jobs app: ${ownerAppUrl_()}` });
            updateJob_(job, { CallbackAlertAt: now }, "Owner reminded to call back");
            done.push(job.Ref + " callback alert");
          }
          if (mins >= T.escalateCallbackMinutes && !job.CallbackEscalatedAt) {
            raiseException_(job.Ref, job.Urgent ? "urgent" : "normal", `${job.Name} not called back after ${Math.round(mins / 60 * 10) / 10}h${job.Urgent ? " (URGENT job)" : ""}`, `Call ${phone_(job)} or nudge ${CONFIG.business.ownerName}.`);
            updateJob_(job, { CallbackEscalatedAt: now }, "Escalated to agency: no call back");
          }
          return;
        }
        if (quiet) return; // everything below messages customers

        // 2. Day-before booking reminder.
        if (job.Status === STATUS.BOOKED && !job.BookingReminderAt) {
          const start = jobStart_(job);
          const hoursAhead = start ? (start - now) / 36e5 : -1;
          if (hoursAhead > 0 && hoursAhead <= T.bookingReminderHours) {
            sendTemplate_(job, "bookingReminder");
            updateJob_(job, { BookingReminderAt: now }, "Booking reminder sent");
            done.push(job.Ref + " booking reminder");
          }
          // Job time passed but not marked done: remind the owner the next morning.
          if (hoursAhead < -18 && !job.CloseoutReminderAt) {
            MailApp.sendEmail({ to: CONFIG.ownerEmail, subject: `Did the ${job.Service} job for ${job.Name} happen?`,
              body: `It was booked for ${vars_(job).when}. Tap "Job done" in your jobs app so the invoice goes out: ${ownerAppUrl_()}` });
            updateJob_(job, { CloseoutReminderAt: now }, "Owner asked to close out the job");
          }
        }

        // 3. Quote follow-ups.
        if (job.Status === STATUS.QUOTED) {
          const n = Number(job.QuoteFollowups) || 0;
          if (n < T.quoteFollowupDays.length && daysSince_(job.QuoteSentAt, now) >= T.quoteFollowupDays[n]) {
            sendTemplate_(job, "quoteFollowup");
            updateJob_(job, { QuoteFollowups: n + 1 }, `Quote follow-up ${n + 1} sent`);
            done.push(job.Ref + " quote follow-up");
          }
        }

        // 4. Payment chasing, then escalation.
        if (job.Status === STATUS.INVOICED) {
          const n = Number(job.InvoiceChases) || 0;
          const age = daysSince_(job.InvoiceSentAt, now);
          if (n < T.invoiceChaseDays.length && age >= T.invoiceChaseDays[n]) {
            sendTemplate_(job, "invoiceChase" + (n + 1));
            updateJob_(job, { InvoiceChases: n + 1 }, `Payment reminder ${n + 1} sent`);
            done.push(job.Ref + " invoice chase " + (n + 1));
          }
          if (age >= T.escalateInvoiceDays && !job.InvoiceEscalatedAt) {
            raiseException_(job.Ref, "urgent", `Invoice ${job.InvoiceNo} (${money_(job.InvoiceTotal)}) unpaid after ${Math.floor(age)} days`, `Call ${job.Name} on ${phone_(job)}. Agree a payment date or a plan.`);
            updateJob_(job, { InvoiceEscalatedAt: now }, "Escalated to agency: unpaid invoice");
          }
        }

        // 5. Reviews, after the job is finished.
        if ([STATUS.INVOICED, STATUS.PAID, STATUS.CLOSED].includes(job.Status) && job.CompletedAt) {
          if (!job.ReviewRequestedAt && hoursSince_(job.CompletedAt, now) >= T.reviewDelayHours) {
            sendTemplate_(job, "reviewRequest");
            updateJob_(job, { ReviewRequestedAt: now }, "Review requested");
            done.push(job.Ref + " review request");
          } else if (job.ReviewRequestedAt && !job.ReviewFollowupAt && daysSince_(job.ReviewRequestedAt, now) >= T.reviewFollowupDays) {
            sendTemplate_(job, "reviewFollowup");
            updateJob_(job, { ReviewFollowupAt: now }, "Review follow-up sent");
            done.push(job.Ref + " review follow-up");
          }
        }

        // 6. Bring customers back for repeat work.
        if (job.RebookDueAt && !job.RebookSentAt && new Date(job.RebookDueAt) <= now && job.Status !== STATUS.LOST) {
          sendTemplate_(job, "rebook");
          updateJob_(job, { RebookSentAt: now }, "Rebooking invitation sent");
          done.push(job.Ref + " rebook");
        }
      } catch (err) {
        raiseException_(job.Ref, "normal", "Automation error: " + err.message, "Check this job's row in the Jobs tab.");
      }
    });

    maybeSendReports_(now);
    PropertiesService.getScriptProperties().setProperty("LAST_RUN", now.toISOString());
    return done;
  } finally {
    lock.releaseLock();
  }
}
