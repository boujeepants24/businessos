# Client onboarding

Setting up a client used to mean hand-editing about ten config files that all had to agree: the booking site, the chat widget, the Apps Script back office, the phone gateway and the knowledge base. One typo meant a broken booking page or missed calls ringing the wrong phone.

Now there is one file per client:

```bash
cp onboarding/client.example.toml onboarding/clients/acme-plumbing.toml   # fill it in on the onboarding call
python3 onboarding/onboard.py onboarding/clients/acme-plumbing.toml --agency-email ops@youragency.example
```

That writes `onboarding/build/acme-plumbing/`:

| Output | Goes to |
|---|---|
| `booking-site/` | Any static host (Netlify drag-and-drop works) |
| `chat-receptionist/` + `INSTALL.html` | Hosted next to the site; two script tags go on the client's website |
| `ops-engine/` | The client's Apps Script project (paste in, or `clasp push`) |
| `comms-gateway.json` | One entry in the phone gateway's clients file |
| `domain-rag.json` | One entry in the knowledge API's clients file |
| `ONBOARDING.md` | The remaining steps, with this client's names, numbers and URLs filled in |

After deploying the back office, paste its `/exec` URL into `[deployed]` in the toml and run the generator again. That one URL is then wired into the booking site, the chat widget and the phone gateway.

## What it checks before writing anything

- Phone numbers are in international format, and the owner's mobile isn't the business number (which would loop calls).
- The timezone, currency, colours, URLs (https only) and tax rate are valid.
- Every service has a unique id and name; opening hours make sense.
- All problems are reported at once, and nothing is written until the file is valid.

It also converts opening days for each component. The browser counts Sunday as day 0, while the phone gateway counts Monday as day 0. Copying one hours setting between them by hand would make the phone ring on the wrong days.

## Privacy

`clients/` and `build/` are git-ignored: client files contain owners' phone numbers, emails and bank details, and this repository is public. Keep them in a private repository or drive.

## Tests

```bash
python3 -m unittest discover -s onboarding/tests -v
```

12 tests, standard library only, including drift checks. If the booking site or chat widget starts reading a setting the generator doesn't write, or the back office's `Config.gs` gains or loses a setting, the tests fail and name it. They also run the full Ops Engine lifecycle suite against the generated back office.
