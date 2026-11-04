/**
 * AGENCY HQ: one Google Sheet in the agency account that watches every client.
 * Tabs: "Clients" (you fill in) and "Overview" (rebuilt every morning).
 * Every morning you get one email: what needs a human today, across all clients.
 *
 * Setup: new Sheet → Extensions → Apps Script → paste this file → run setupHq().
 */

const HQ = {
  agencyEmail: "ops@youragency.example",
  timezone: "Europe/London",
  digestHour: 8
};

function setupHq() {
  const ss = SpreadsheetApp.getActive();
  if (!ss.getSheetByName("Clients")) {
    const sh = ss.insertSheet("Clients");
    sh.appendRow(["Client", "Sheet ID", "Owner", "Active"]);
    sh.appendRow(["Northfield Plumbing & Heating", "paste-the-client-sheet-id-here", "Dave", "yes"]);
    sh.getRange(1, 1, 1, 4).setFontWeight("bold");
    sh.setFrozenRows(1);
  }
  ScriptApp.getProjectTriggers().forEach((t) => ScriptApp.deleteTrigger(t));
  ScriptApp.newTrigger("dailyHq").timeBased().everyDays(1).atHour(HQ.digestHour).inTimezone(HQ.timezone).create();
  console.log("Add each client's sheet ID to the Clients tab, then run dailyHq() once to test.");
}

function dailyHq() {
  const ss = SpreadsheetApp.getActive();
  const clients = ss.getSheetByName("Clients").getDataRange().getValues().slice(1).filter((r) => r[1] && String(r[3]).toLowerCase() !== "no");
  const now = new Date();
  const weekAgo = new Date(now.getTime() - 7 * 864e5);
  const rows = [], actions = [];

  clients.forEach(([name, id, owner]) => {
    try {
      const cs = SpreadsheetApp.openById(id);
      const jobs = table_(cs.getSheetByName("Jobs"));
      const exc = table_(cs.getSheetByName("Exceptions"));
      const msgs = table_(cs.getSheetByName("Messages"));
      const since = (k) => jobs.filter((j) => j[k] && new Date(j[k]) >= weekAgo).length;
      const unpaid = jobs.filter((j) => j.Status === "Invoiced");
      const waiting = jobs.filter((j) => j.Status === "New");
      const openExc = exc.filter((e) => !e.Resolved);
      const lastMsg = msgs.length ? new Date(msgs[msgs.length - 1].Time) : null;
      const failed7 = msgs.filter((m) => new Date(m.Time) >= weekAgo && m.Result !== "sent").length;

      const health = openExc.some((e) => e.Severity === "urgent") || waiting.some((j) => hrs_(j.Created, now) > 2) ? "Needs attention"
        : failed7 > 3 ? "Check messaging" : "Healthy";
      rows.push([name, health, since("Created"), since("BookingConfirmedAt"), since("CompletedAt"), sum_(jobs.filter((j) => j.PaidAt && new Date(j.PaidAt) >= weekAgo)),
        unpaid.length, sum_(unpaid), waiting.length, openExc.length, failed7, lastMsg ? Utilities.formatDate(lastMsg, HQ.timezone, "d MMM HH:mm") : "never", cs.getUrl()]);

      waiting.filter((j) => hrs_(j.Created, now) > 2).forEach((j) => actions.push(`${name}: ${j.Name} (${j.Service}) has waited ${Math.round(hrs_(j.Created, now))}h for a call back. Nudge ${owner} or call ${String(j.Phone).replace(/^'/, "")}.`));
      openExc.forEach((e) => actions.push(`${name}: ${e["What happened"]}. ${e["Suggested action"]}`));
      if (failed7 > 3) actions.push(`${name}: ${failed7} messages failed this week. Check SMS credits and the Messages tab.`);
    } catch (err) {
      rows.push([name, "Can't open sheet", "", "", "", "", "", "", "", "", "", "", ""]);
      actions.push(`${name}: HQ can't open their sheet (${err.message}). Check the Sheet ID and that it's shared with this account.`);
    }
  });

  let ov = ss.getSheetByName("Overview");
  if (!ov) ov = ss.insertSheet("Overview", 0);
  ov.clear();
  ov.appendRow(["Client", "Health", "Enquiries (7d)", "Booked (7d)", "Completed (7d)", "Paid in (7d)", "Unpaid invoices", "Unpaid value", "Waiting for call back", "Open exceptions", "Failed messages (7d)", "Last message sent", "Sheet"]);
  rows.forEach((r) => ov.appendRow(r));
  ov.getRange(1, 1, 1, 13).setFontWeight("bold").setBackground("#1A1E1C").setFontColor("#FFFFFF");
  ov.setFrozenRows(1);
  rows.forEach((r, i) => ov.getRange(i + 2, 2).setBackground(r[1] === "Healthy" ? "#DCEBDD" : "#F6E1D6"));

  const body = actions.length
    ? `${actions.length} thing${actions.length > 1 ? "s" : ""} need a human today:\n\n${actions.map((a) => "• " + a).join("\n")}`
    : "Nothing needs you today. Every client's system is running on its own.";
  MailApp.sendEmail({ to: HQ.agencyEmail, subject: `HQ ${Utilities.formatDate(now, HQ.timezone, "EEE d MMM")}: ${actions.length ? actions.length + " to action" : "all clear"} across ${clients.length} clients`,
    body: `${body}\n\nOverview: ${ss.getUrl()}` });
}

function table_(sh) {
  if (!sh) return [];
  const v = sh.getDataRange().getValues();
  return v.slice(1).map((r) => Object.fromEntries(v[0].map((h, i) => [h, r[i]])));
}
function sum_(jobs) { return jobs.reduce((s, j) => s + (Number(j.InvoiceTotal) || 0), 0); }
function hrs_(d, now) { return (now - new Date(d)) / 36e5; }
