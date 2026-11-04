# Ops Engine

The client does the work. This runs everything else: enquiries, booking, reminders, quotes, invoices, payment chasing, reviews, rebooking and reporting. It runs on Google Apps Script, so there's no server and no monthly software bill. Everything lives in a Google Sheet that your agency owns and shares with the client.

## The process

Every customer request is one row in the **Jobs** tab, and it moves through these stages:

```
New ─▶ Contacted ─▶ Quoted ─▶ Booked ─▶ Invoiced ─▶ Paid
 │                                 └──▶ Closed (nothing to charge)
 └──────────────▶ Booked (customer picked a slot on the website)
 any stage ─▶ Lost
```

| Step | What happens | Who does it | How fast |
|---|---|---|---|
| Enquiry in | Row created. The customer gets an instant reply (confirmation if they booked a slot, "we'll call you" if not). The owner gets an email with the details. | System | Seconds, 24/7 |
| Not called back | Owner reminded once at 15 min. Escalated to the agency at 2 h (straight to your inbox if urgent). | System → owner → you | 15 min / 2 h |
| Call back | Owner taps **Called**, then **Book** or **Quote** in the jobs app. | Owner | |
| Quote | Quote emailed or texted. Follow-ups go out at day 2 and day 5. | System | |
| Booked | Confirmation sent, then a reminder the day before. Same-slot double booking is blocked. | System | |
| Job happens | Owner taps **Job done** and types the amount. If they forget, they're asked the next morning. | Owner | 10 seconds |
| Invoice | Numbered PDF invoice (with VAT/GST if set) emailed and saved to Drive. | System | Instant |
| Payment | Friendly reminder at 3 days, firmer at 7, final at 14. Escalated to you at 21. Owner taps **Paid** to stop the chasing, and the customer gets a thank-you. | System → you | |
| Review | Review request 2 h after the job, one follow-up 4 days later. Unhappy customers are invited to reply to the owner (every customer still gets the review link). | System | |
| Rebook | When a service is due again (for example 11 months after a boiler service), the customer is invited back. | System | |
| Report | Monthly summary to the owner (and you) on the 1st: enquiries, after-hours share, response time, booked, invoiced, paid, outstanding, reviews. | System | |

No customer messages are sent during **quiet hours** (21:00–08:00). Anything due waits until morning. The one exception is a reply to a customer's own enquiry, which always goes out straight away.

### What the owner does
They use one bookmarked link on their phone (the **jobs app**) and press five buttons: **Called**, **Book**, **Quote**, **Job done**, **Paid**. They also have **Add job** for phone calls and walk-ins.

### What you (the agency) do
You read one email every morning from **HQ**, listing everything across all clients that needs a person. Anything the system couldn't handle is logged in that client's **Exceptions** tab, for example a message that couldn't be delivered, a lead nobody called back, or an invoice unpaid after 21 days.

## Files

| File | Purpose |
|---|---|
| `Config.gs` | **Per-client settings**: name, contacts, payment details, tax, services and rebook intervals, timings. The only file you edit. |
| `Main.gs` | Web endpoints (leads in, slots out, jobs app), owner API and `setup()` |
| `Jobs.gs` | The lifecycle: intake, call, quote, book, complete, paid, lost |
| `Automations.gs` | The 15-minute clock: reminders, chasing, reviews, rebooking, escalations |
| `Messages.gs` | Every customer message (email + SMS + WhatsApp gateway), with quiet hours and logging |
| `Invoices.gs` | Invoice numbering and PDFs |
| `Reports.gs` | Monthly owner report |
| `OwnerApp.html` | The owner's mobile jobs app |
| `hq/HQ.gs` | Agency HQ: one sheet watching every client, with a daily digest |
| `test/run.js` | Offline test of the whole lifecycle: `node ops-engine/test/run.js` |

## Onboard a client (about 20 minutes)

1. **In your agency Google account**, create a Sheet named "<Client> Ops" and share it with the owner (Viewer is enough).
2. Go to **Extensions → Apps Script**. Add one script file for each `.gs` file here, with the same names, and paste in the contents. Add an HTML file named `OwnerApp` and paste in `OwnerApp.html`.
3. Fill in `Config.gs`.
4. Run `setup()` and approve the permissions. This creates the tabs, the owner key, the invoice numbering, the Drive folder and the 15-minute trigger.
5. **Deploy → New deployment → Web app**. Set Execute as: **Me**, Who has access: **Anyone**. Copy the `/exec` URL.
6. Put that URL in `webhookUrl` in `booking-site/config.js` and `chat-receptionist/config.js`.
7. Run `showOwnerLink()`. Text that link to the owner and have them add it to their home screen.
8. Optional texts: set `channels.sms` in Config and add the Script Property `TWILIO_AUTH_TOKEN`. For WhatsApp, point `channels.webhookUrl` at your WhatsApp gateway (Interakt, AiSensy, Twilio WhatsApp, or a Make/Zapier hook).
9. In **your HQ sheet**, add the client's Sheet ID to the Clients tab.
10. Test it: make a booking on the site, then mark it done for an amount of 1. Check that the confirmation, owner alert, invoice email and row history all appear.

After changing any code, use **Deploy → Manage deployments → Edit → New version** to keep the same URL.

## Safety
- The jobs app only opens with the owner's secret key. A wrong key gets nothing.
- Customer-typed text can't inject spreadsheet formulas.
- Every message is logged (Messages tab), and every change to a job is written into that job's History cell.
- Each automation records when it acted, so a customer is never sent the same message twice.
