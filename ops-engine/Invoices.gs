/**
 * Invoices: sequential numbers, a clean PDF saved to the client's Drive folder, attached to the email.
 */

// Callers (ownerApi) already hold the script lock, so numbers can't collide.
function nextInvoiceNo_() {
  {
    const props = PropertiesService.getScriptProperties();
    const n = Number(props.getProperty("INVOICE_SEQ") || "0") + 1;
    props.setProperty("INVOICE_SEQ", String(n));
    const prefix = props.getProperty("INVOICE_PREFIX") || "INV";
    return `${prefix}-${String(n).padStart(4, "0")}`;
  }
}

function invoiceFolder_() {
  const props = PropertiesService.getScriptProperties();
  const id = props.getProperty("INVOICE_FOLDER_ID");
  if (id) { try { return DriveApp.getFolderById(id); } catch (_) { /* folder deleted; make a new one */ } }
  const folder = DriveApp.createFolder(CONFIG.business.name + " · Invoices");
  props.setProperty("INVOICE_FOLDER_ID", folder.getId());
  return folder;
}

function buildInvoicePdf_(job) {
  const b = CONFIG.business;
  const e = (s) => String(s === undefined || s === null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const issued = new Date(job.InvoiceSentAt || new Date());
  const due = new Date(issued.getTime() + CONFIG.payment.termsDays * 864e5);
  const fmt = (d) => Utilities.formatDate(d, CONFIG.timing.timezone, "d MMMM yyyy");
  const link = payLink_(job);
  const html = `<!doctype html><html><head><meta charset="utf-8"><style>
    body { font-family: Helvetica, Arial, sans-serif; color: #1A1E1C; font-size: 11pt; margin: 40px; }
    .top { display: flex; justify-content: space-between; border-bottom: 2px solid #1A1E1C; padding-bottom: 16px; }
    h1 { font-size: 22pt; margin: 0 0 4px; letter-spacing: 1px; }
    .muted { color: #5E6661; }
    table { width: 100%; border-collapse: collapse; margin-top: 28px; }
    th { text-align: left; font-size: 9pt; text-transform: uppercase; letter-spacing: 1px; color: #5E6661; border-bottom: 1px solid #CDD2CB; padding: 6px 0; }
    td { padding: 10px 0; border-bottom: 1px solid #EEF0EC; vertical-align: top; }
    .num { text-align: right; white-space: nowrap; }
    .total td { border: 0; font-weight: bold; font-size: 13pt; padding-top: 14px; }
    .pay { margin-top: 32px; padding: 14px 16px; background: #EEF0EC; }
  </style></head><body>
    <div class="top">
      <div><h1>INVOICE</h1><div class="muted">${e(job.InvoiceNo)}</div></div>
      <div style="text-align:right"><b>${e(b.name)}</b><br>${e(b.address)}<br>${e(b.phone)}<br>${e(b.email)}${b.taxNumber ? `<br>${e(b.taxLabel)} no. ${e(b.taxNumber)}` : ""}</div>
    </div>
    <table style="margin-top:20px"><tr>
      <td style="border:0;width:50%"><span class="muted">Bill to</span><br><b>${e(job.Name)}</b><br>${e(job.Area)}<br>${e(phone_(job))}${job.Email ? "<br>" + e(job.Email) : ""}</td>
      <td style="border:0" class="num"><span class="muted">Issued</span> ${fmt(issued)}<br><span class="muted">Due</span> ${fmt(due)}<br><span class="muted">Job ref</span> ${e(job.Ref)}</td>
    </tr></table>
    <table>
      <tr><th>Description</th><th class="num">Amount</th></tr>
      <tr><td>${e(job.WorkDone || job.Service)}${job.Date ? `<br><span class="muted">${e(ymd_(job.Date))}</span>` : ""}</td><td class="num">${money_(job.InvoiceNet)}</td></tr>
      ${b.taxRate ? `<tr><td>${e(b.taxLabel)} at ${Math.round(b.taxRate * 1000) / 10}%</td><td class="num">${money_(job.InvoiceTax)}</td></tr>` : ""}
      <tr class="total"><td>Total due</td><td class="num">${money_(job.InvoiceTotal)}</td></tr>
    </table>
    <div class="pay"><b>How to pay</b><br>${e(CONFIG.payment.instructions)}${link ? `<br>Pay online: ${e(link)}` : ""}</div>
    <p class="muted" style="margin-top:28px">Thank you for your business.</p>
  </body></html>`;
  const blob = Utilities.newBlob(html, "text/html", job.InvoiceNo + ".html").getAs("application/pdf").setName(`${job.InvoiceNo} ${job.Name}.pdf`);
  const file = invoiceFolder_().createFile(blob);
  return { blob, url: file.getUrl() };
}
