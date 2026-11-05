# BusinessOS

**The client does the work. We run the rest of the business.** That means answering every enquiry, booking, reminders, quotes, invoices, chasing payment, reviews, bringing customers back, and reporting. It's built for local service businesses (plumbers, electricians, roofers, HVAC, cleaners, clinics), runs without a server, and each client is set up from one config file.

| Tool | What the client gets |
|---|---|
| [`booking-site/`](booking-site) | A fast, mobile-first booking page. Customers pick a job and a live arrival window and confirm in three taps. It includes local SEO markup, tap-to-call and WhatsApp buttons, and the same slot can never be booked twice. |
| [`chat-receptionist/`](chat-receptionist) | A chat widget installed with one script tag on any website. It answers 24/7, understands plain messages ("my boiler says F28"), separates emergencies from routine jobs, answers FAQs, and collects the name, number, area and problem. |
| [`ops-engine/`](ops-engine) | **The back office.** It takes every job from enquiry to paid: instant replies, reminders, quote follow-ups, PDF invoices, payment chasing, review requests, rebooking and monthly reports. The owner uses a five-button phone app. You get one daily HQ email across all clients. |
| [`comms-gateway/`](comms-gateway) | **Phone front door.** Missed calls get an instant text with the booking link, become leads, and replies and voicemails attach to them. Works internationally via Twilio; one gateway serves every client. |
| [`domain-rag/`](domain-rag) | **Knowledge engine.** Retrieval-augmented answers over each client's own documents: hybrid search, cited answers from Claude, prompt-injection defences, an evaluation harness. Runs as a multi-client web API for the chat widget and as an MCP server. |
| [`onchain-escrow/`](onchain-escrow) | **Milestone escrow (Solidity).** Clients lock a budget; providers are paid per approved milestone; an arbiter settles disputes. Foundry unit, fuzz, adversarial and invariant tests. Not audited, testnet only. |
| [`client-knowledge/`](client-knowledge) | Optional: lets the chat receptionist answer free-form questions from the client's own documents (services, areas, policies, warranty) via [`domain-rag/`](domain-rag), with sources, and never guessing. |
| [`pipeline/`](pipeline) | Your own private sales board, from prospect to live client, with each stage's checklist already written. |
| [`roi-proposal/`](roi-proposal) | A discovery-call tool. Fill it in with the owner using their own numbers to show the work they're losing, then copy the follow-up email it writes. |

## Try it locally

```bash
python3 -m http.server 8000
# open http://localhost:8000/booking-site/
# open http://localhost:8000/chat-receptionist/demo.html
```

## Set up a new client

1. Fill in one file per client: copy `onboarding/client.example.toml` (business details, phones, hours, services, branding, payment details).
2. Run `python3 onboarding/onboard.py onboarding/clients/<id>.toml --agency-email you@agency.example`. It validates everything and generates the booking site, chat widget, back office, phone and knowledge config, plus a checklist with the client's values filled in.
3. Follow the generated `ONBOARDING.md`: deploy the back office, paste its URL into the toml and re-run, deploy the site, connect the phone number, test end to end.

Details: [`onboarding/README.md`](onboarding/README.md).

## Ideas for custom work

- An AI voice receptionist that answers missed calls and books straight into the Ops Engine
