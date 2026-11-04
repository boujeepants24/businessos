# Lead backend (Google Sheet)

This backend is free and needs no server or database. It runs on the client's own Google account and gives them:

- A **Leads** sheet that works as a simple CRM. Status moves New → Contacted → Booked → Completed / Lost. Urgent jobs are highlighted in red.
- An **instant email alert** for every booking or chat lead.
- **Live availability**: arrival windows that are already booked disappear from the booking page, and the same window can't be booked twice.
- **Automatic chasing**: if a lead is still "New" after 30 minutes, the owner gets a reminder email.

## Setup per client (about 5 minutes)

1. In the client's Google account, create a blank Google Sheet named "<Business> Leads".
2. Go to **Extensions → Apps Script**. Delete the starter code and paste in all of `Code.gs`.
3. Edit `SETTINGS` at the top: `businessName`, and `ownerEmail` if alerts should go to an address other than the account's own.
4. Choose `setup` in the function dropdown and click **Run**. Approve the permissions. This creates the sheet, the status dropdown and the 15-minute chase reminder.
5. **Deploy → New deployment → Web app**. Set Execute as: **Me** and Who has access: **Anyone**. Copy the URL that ends in `/exec`.
6. Paste that URL into `webhookUrl` in both `booking-site/config.js` and `chat-receptionist/config.js`.

Test it by making one booking on the live site. The row should appear in the sheet, and the alert email should arrive within a few seconds.

## Notes

- After you change `Code.gs`, use **Deploy → Manage deployments → Edit → New version**. That keeps the same URL.
- Spreadsheet formula injection is blocked: any field that starts with `=`, `+`, `-` or `@` is saved as plain text.
- Gmail sending limits are generous for this use: 100 emails a day on free accounts and 1,500 on Workspace.
