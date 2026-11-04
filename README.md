# BusinessOS

**The client does the work. We run the rest of the business.** That means answering every enquiry, booking, reminders, quotes, invoices, chasing payment, reviews, bringing customers back, and reporting. It's built for local service businesses (plumbers, electricians, roofers, HVAC, cleaners, clinics), runs without a server, and each client is set up from one config file.

| Tool | What the client gets |
|---|---|
| [`booking-site/`](booking-site) | A fast, mobile-first booking page. Customers pick a job and a live arrival window and confirm in three taps. It includes local SEO markup, tap-to-call and WhatsApp buttons, and the same slot can never be booked twice. |
| [`chat-receptionist/`](chat-receptionist) | A chat widget installed with one script tag on any website. It answers 24/7, understands plain messages ("my boiler says F28"), separates emergencies from routine jobs, answers FAQs, and collects the name, number, area and problem. |
| [`ops-engine/`](ops-engine) | **The back office.** It takes every job from enquiry to paid: instant replies, reminders, quote follow-ups, PDF invoices, payment chasing, review requests, rebooking and monthly reports. The owner uses a five-button phone app. You get one daily HQ email across all clients. |
| [`pipeline/`](pipeline) | Your own private sales board, from prospect to live client, with each stage's checklist already written. |
| [`roi-proposal/`](roi-proposal) | A discovery-call tool. Fill it in with the owner using their own numbers to show the work they're losing, then copy the follow-up email it writes. |

## Try it locally

```bash
python3 -m http.server 8000
# open http://localhost:8000/booking-site/
# open http://localhost:8000/chat-receptionist/demo.html
```

## Set up a new client

1. Copy `booking-site/` and `chat-receptionist/`, then edit the two `config.js` files: name, phone, WhatsApp, colours, services, areas, hours and reviews.
2. Set up the Ops Engine for the client by following [`ops-engine/README.md`](ops-engine/README.md). Paste its web-app URL into both configs as `webhookUrl`.
3. Deploy the booking site to Netlify, Vercel, Cloudflare Pages or GitHub Pages (drag and drop the folder), and point a subdomain like `book.clientsite.com` at it.
4. Paste the two chat `<script>` tags into the client's existing website.
5. Make one test booking and one test chat, then mark the booking done. Check the confirmation, the alerts and the invoice.
6. Send the owner their jobs-app link and add the client to your HQ sheet.

## Ideas for custom work

- Missed-call text-back: when a call goes unanswered, the customer gets an automatic text with the booking link
- An AI upgrade for the chat receptionist that answers free-form questions from the client's own price list and FAQs
- An AI voice receptionist that answers missed calls and books straight into the Ops Engine
