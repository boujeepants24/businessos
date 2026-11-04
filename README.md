# Business Offer Kit

Three tools that stop local service businesses (plumbers, electricians, roofers, HVAC, cleaners, clinics) from losing work to missed calls and slow replies. Each tool can be rebranded for a client in about 10 minutes and runs free with no server.

| Tool | What the client gets |
|---|---|
| [`booking-site/`](booking-site) | A fast, mobile-first booking page. Customers pick a job and a live arrival window and confirm in three taps. It includes local SEO markup, tap-to-call and WhatsApp buttons, and the same slot can never be booked twice. |
| [`chat-receptionist/`](chat-receptionist) | A chat widget installed with one script tag on any website. It answers 24/7, understands plain messages ("my boiler says F28"), separates emergencies from routine jobs, answers FAQs, and collects the name, number, area and problem. |
| [`lead-backend/`](lead-backend) | A Google Sheet that works as a CRM. It sends an instant email alert for every lead, keeps live availability for the booking page, and chases any lead nobody has called back within 30 minutes. |
| [`roi-proposal/`](roi-proposal) | A discovery-call tool. Fill it in with the owner using their own numbers to show the work they're losing, then copy the follow-up email it writes. |

## Try it locally

```bash
python3 -m http.server 8000
# open http://localhost:8000/booking-site/
# open http://localhost:8000/chat-receptionist/demo.html
```

## Set up a new client

1. Copy `booking-site/` and `chat-receptionist/`, then edit the two `config.js` files: name, phone, WhatsApp, colours, services, areas, hours and reviews.
2. Set up the Google Sheet backend in the client's own Google account by following [`lead-backend/README.md`](lead-backend/README.md). Paste the web-app URL into both configs as `webhookUrl`.
3. Deploy the booking site to Netlify, Vercel, Cloudflare Pages or GitHub Pages (drag and drop the folder), and point a subdomain like `book.clientsite.com` at it.
4. Paste the two chat `<script>` tags into the client's existing website.
5. Make one test booking and one test chat. Check that both rows appear in the sheet and that both alert emails arrive.

## Ideas for custom work

- SMS confirmations and reminders (Twilio or MSG91) to cut no-shows
- Missed-call text-back: when a call goes unanswered, the customer gets an automatic text with the booking link
- Automated Google review requests after jobs marked Completed
- An AI upgrade for the chat receptionist that answers free-form questions from the client's own price list and FAQs
- A weekly report email: leads, response times, bookings and estimated revenue recovered
