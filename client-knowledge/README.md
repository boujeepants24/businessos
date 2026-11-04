# Client knowledge folder

The chat receptionist can answer free-form questions ("Do I need a service to keep the warranty?", "Do you cover Otley?") from each client's own documents, using [domain-rag](https://github.com/boujeepants24/domain-rag). It answers only from these files, cites them, and says "I can't find that" rather than guessing.

## What to collect from a client

One Markdown file per topic works best. Write in the client's own words and keep each fact in one place.

| File | What goes in it | Ask the owner |
|---|---|---|
| `services.md` | Each service, what's included, typical duration, what the customer should prepare | "Walk me through each job you do." |
| `areas-and-hours.md` | Towns and postcodes covered, opening hours, emergency hours | "Where won't you go?" |
| `pricing-policy.md` | How pricing works (call-out, quotes, payment terms, deposits). Only what the owner is happy for the assistant to say. | "What do customers ask about cost, and what do you tell them?" |
| `warranty-and-guarantees.md` | Workmanship guarantees, manufacturer warranties, conditions | "What do you promise after a job?" |
| `common-problems.md` | The problems customers describe, what they usually mean, safe first steps | "What are the 10 calls you get every week?" |
| `policies.md` | Cancellations, rescheduling, access, pets, parking, safety | "What causes arguments?" |
| `about.md` | Who they are, accreditations, years trading | "Why should someone pick you?" |

Use headings (`##`) for each question or sub-topic. The pipeline splits files at headings, so a clear heading makes a clear answer.

## Rules

- **Get the owner to approve every file.** The assistant will say whatever is written here.
- **No personal data** about customers or staff.
- **Nothing the owner wouldn't say on the phone.** If a price or promise is uncertain, leave it out; the assistant then hands the question to a person.
- Update the files when something changes, then re-run `domainrag ingest --clients deploy/clients.json`.

## Switch it on for a client

1. Put the approved files in that client's folder on the knowledge server (`clients/<client-id>/knowledge/`).
2. Add the client to `deploy/clients.json` in domain-rag, with the client's website(s) as `allowed_origins`.
3. Run `domainrag ingest --clients deploy/clients.json`.
4. In `chat-receptionist/config.js`, set `knowledgeUrl` to `https://<your-knowledge-server>/v1/clients/<client-id>/ask`.
5. Test: one question the files answer, one they don't. The second must get "I can't find that in our information".
