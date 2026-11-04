# BusinessOS

**The client does the work. We run the rest of the business.** That means answering every enquiry, booking, reminders, quotes, invoices, chasing payment, reviews, bringing customers back, and reporting. It's built for local service businesses (plumbers, electricians, roofers, HVAC, cleaners, clinics), runs without a server, and each client is set up from one config file.

| Tool | What the client gets |
|---|---|
| [`booking-site/`](booking-site) | A fast, mobile-first booking page. Customers pick a job and a live arrival window and confirm in three taps. It includes local SEO markup, tap-to-call and WhatsApp buttons, and the same slot can never be booked twice. |
| [`chat-receptionist/`](chat-receptionist) | A chat widget installed with one script tag on any website. It answers 24/7, understands plain messages ("my boiler says F28"), separates emergencies from routine jobs, answers FAQs, and collects the name, number, area and problem. |
| [`ops-engine/`](ops-engine) | **The back office.** It takes every job from enquiry to paid: instant replies, reminders, quote follow-ups, PDF invoices, payment chasing, review requests, rebooking and monthly reports. The owner uses a five-button phone app. You get one daily HQ email across all clients. |
| [`comms-gateway/`](comms-gateway) | **Phone front door.** Missed calls get an instant text with the booking link, become leads, and replies and voicemails attach to them. Works internationally via Twilio; one gateway serves every client. |
| [`client-knowledge/`](client-knowledge) | Optional: lets the chat receptionist answer free-form questions from the client's own documents (services, areas, policies, warranty) via [domain-rag](https://github.com/boujeepants24/domain-rag), with sources, and never guessing. |
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
7. Connect their phone number to the [comms gateway](comms-gateway/README.md) so missed calls get an instant text and become leads.
8. Optional: collect the client's knowledge files ([`client-knowledge/README.md`](client-knowledge/README.md)) and set `knowledgeUrl` in the chat config.

## Ideas for custom work

- An AI voice receptionist that answers missed calls and books straight into the Ops Engine
