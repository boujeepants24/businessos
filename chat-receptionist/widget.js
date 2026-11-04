/*!
 * Chat Receptionist widget. One script tag, no dependencies.
 * Qualifies enquiries 24/7, books jobs, answers FAQs and hands off to call/WhatsApp.
 * Usage:
 *   <script src="config.js"></script>
 *   <script src="widget.js" defer></script>
 */
(function () {
  "use strict";
  if (window.__receptionistLoaded) return;
  window.__receptionistLoaded = true;

  const C = window.RECEPTIONIST;
  if (!C) { console.warn("[receptionist] window.RECEPTIONIST config missing"); return; }

  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const reduced = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
  const norm = (s) => s.toLowerCase().replace(/[^a-z0-9\s]/g, " ");
  const tel = C.phone.replace(/[^\d+]/g, "");
  const side = C.position === "left" ? "left" : "right";

  function isOpenNow() {
    const n = new Date();
    return C.hours.days.includes(n.getDay()) && n.getHours() >= C.hours.open && n.getHours() < C.hours.close;
  }
  function readableInk(hex) {
    const n = parseInt(hex.replace("#", ""), 16);
    const l = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; });
    return 0.2126 * l[0] + 0.7152 * l[1] + 0.0722 * l[2] > 0.4 ? "#10181D" : "#FFFFFF";
  }

  /* ---------- DOM (shadow root so the host site's CSS can't break it) ---------- */
  const host = document.createElement("div");
  host.setAttribute("data-receptionist", "");
  document.body.appendChild(host);
  const root = host.attachShadow({ mode: "open" });
  root.innerHTML = `
<style>
:host { all: initial; }
* { box-sizing: border-box; }
.w { --brand: ${C.brandColor}; --ink: ${readableInk(C.brandColor)}; --bg: #FFFFFF; --soft: #F1F4F6; --text: #142028; --muted: #5F6E77; --line: #DDE4E8;
  font: 15px/1.45 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; color: var(--text); position: fixed; ${side}: max(16px, env(safe-area-inset-${side}, 0px)); bottom: calc(16px + env(safe-area-inset-bottom, 0px)); z-index: 2147483000; }
@media (prefers-color-scheme: dark) { .w { --bg: #151E23; --soft: #1F2A30; --text: #E6EDF1; --muted: #9AAAB3; --line: #2A3740; } }
.fab { width: 60px; height: 60px; border-radius: 50%; border: 0; cursor: pointer; background: var(--brand); color: var(--ink); box-shadow: 0 10px 28px -8px rgb(0 0 0 / .45); display: grid; place-items: center; margin-${side}: 0; margin-left: auto; position: relative; }
.w.left .fab { margin-left: 0; }
.fab svg { width: 28px; height: 28px; fill: currentColor; }
.fab .dot { position: absolute; top: 4px; right: 4px; width: 14px; height: 14px; border-radius: 50%; background: #E5484D; border: 2px solid var(--bg); }
.teaser { position: absolute; bottom: 72px; ${side}: 0; width: max-content; max-width: min(280px, calc(100vw - 32px)); background: var(--bg); color: var(--text); border: 1px solid var(--line); border-radius: 14px; padding: 12px 34px 12px 14px; box-shadow: 0 12px 30px -12px rgb(0 0 0 / .35); cursor: pointer; animation: pop .25s ease-out; }
.teaser b { display: block; font-size: 13px; color: var(--muted); font-weight: 600; margin-bottom: 2px; }
.teaser .x { position: absolute; top: 6px; right: 6px; border: 0; background: none; color: var(--muted); font-size: 18px; cursor: pointer; line-height: 1; padding: 4px; }
.panel { position: absolute; bottom: 72px; ${side}: 0; width: min(380px, calc(100vw - 32px)); height: min(600px, calc(100vh - 110px)); background: var(--bg); border: 1px solid var(--line); border-radius: 18px; box-shadow: 0 24px 60px -18px rgb(0 0 0 / .45); display: flex; flex-direction: column; overflow: hidden; animation: pop .22s ease-out; }
@keyframes pop { from { opacity: 0; transform: translateY(8px) scale(.98); } }
@media (prefers-reduced-motion: reduce) { .panel, .teaser, .msg { animation: none !important; } }
.head { background: var(--brand); color: var(--ink); padding: 14px 16px; display: flex; align-items: center; gap: 12px; }
.av { width: 38px; height: 38px; border-radius: 50%; background: rgb(255 255 255 / .2); display: grid; place-items: center; font-weight: 700; flex: none; }
.head-t { flex: 1; min-width: 0; }
.head-t b { display: block; font-size: 15px; }
.head-t span { font-size: 12.5px; opacity: .85; display: flex; align-items: center; gap: 6px; }
.head-t span::before { content: ""; width: 8px; height: 8px; border-radius: 50%; background: #4ADE80; }
.icon-btn { border: 0; background: rgb(255 255 255 / .15); color: inherit; width: 34px; height: 34px; border-radius: 50%; cursor: pointer; display: grid; place-items: center; text-decoration: none; flex: none; }
.icon-btn svg { width: 18px; height: 18px; fill: currentColor; }
.log { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 8px; background: var(--soft); }
.msg { max-width: 85%; padding: 9px 13px; border-radius: 16px; white-space: pre-wrap; overflow-wrap: anywhere; animation: pop .18s ease-out; }
.bot { background: var(--bg); border: 1px solid var(--line); border-bottom-left-radius: 4px; align-self: flex-start; }
.me { background: var(--brand); color: var(--ink); border-bottom-right-radius: 4px; align-self: flex-end; }
.typing { display: inline-flex; gap: 4px; padding: 13px 14px; }
.typing i { width: 7px; height: 7px; border-radius: 50%; background: var(--muted); animation: blink 1s infinite; }
.typing i:nth-child(2) { animation-delay: .15s; } .typing i:nth-child(3) { animation-delay: .3s; }
@keyframes blink { 50% { opacity: .25; } }
.chips { display: flex; flex-wrap: wrap; gap: 6px; align-self: flex-start; max-width: 100%; }
.chip { border: 1.5px solid var(--brand); background: var(--bg); color: var(--text); border-radius: 99px; padding: 7px 13px; font: inherit; font-size: 14px; cursor: pointer; }
.chip:hover, .chip:focus-visible { background: var(--brand); color: var(--ink); outline: none; }
.chip.urgent { border-color: #E5484D; }
.card { align-self: stretch; background: var(--bg); border: 1px solid var(--line); border-radius: 12px; padding: 12px 14px; display: grid; grid-template-columns: auto 1fr; gap: 4px 12px; font-size: 14px; }
.card dt { color: var(--muted); } .card dd { margin: 0; font-weight: 600; overflow-wrap: anywhere; }
.cta { display: block; text-align: center; text-decoration: none; padding: 11px; border-radius: 10px; font-weight: 600; align-self: stretch; }
.cta.call { background: var(--brand); color: var(--ink); }
.cta.wa { background: #1DA851; color: #fff; }
.composer { display: flex; gap: 8px; padding: 10px; border-top: 1px solid var(--line); background: var(--bg); }
.composer input { flex: 1; min-width: 0; font: inherit; color: var(--text); background: var(--soft); border: 1.5px solid transparent; border-radius: 99px; padding: 10px 14px; }
.composer input:focus { outline: none; border-color: var(--brand); }
.composer button { border: 0; width: 42px; height: 42px; border-radius: 50%; background: var(--brand); color: var(--ink); cursor: pointer; display: grid; place-items: center; flex: none; }
.composer button svg { width: 18px; height: 18px; fill: currentColor; }
.err { color: #E5484D; font-size: 13px; align-self: flex-start; }
.foot { text-align: center; font-size: 11px; color: var(--muted); padding: 0 0 8px; background: var(--bg); }
:focus-visible { outline: 2px solid var(--brand); outline-offset: 2px; }
</style>
<div class="w ${side}">
  <div class="panel" hidden role="dialog" aria-label="Chat with ${esc(C.businessName)}">
    <div class="head">
      <div class="av">${esc(C.assistantName[0])}</div>
      <div class="head-t"><b>${esc(C.assistantName)} · ${esc(C.businessName)}</b><span>Replies instantly</span></div>
      <a class="icon-btn" href="tel:${esc(tel)}" aria-label="Call ${esc(C.phone)}"><svg viewBox="0 0 24 24"><path d="M6.6 10.8a15.1 15.1 0 0 0 6.6 6.6l2.2-2.2a1 1 0 0 1 1-.25 11.4 11.4 0 0 0 3.6.57 1 1 0 0 1 1 1V20a1 1 0 0 1-1 1A17 17 0 0 1 3 4a1 1 0 0 1 1-1h3.5a1 1 0 0 1 1 1c0 1.25.2 2.45.57 3.57a1 1 0 0 1-.25 1z"/></svg></a>
      <button class="icon-btn close" aria-label="Close chat"><svg viewBox="0 0 24 24"><path d="M18.3 5.7 12 12l6.3 6.3-1.4 1.4L10.6 13.4 4.3 19.7l-1.4-1.4L9.2 12 2.9 5.7l1.4-1.4 6.3 6.3 6.3-6.3z"/></svg></button>
    </div>
    <div class="log" role="log" aria-live="polite"></div>
    <form class="composer"><input aria-label="Type a message" placeholder="Type a message…" autocomplete="off" maxlength="500"><button aria-label="Send"><svg viewBox="0 0 24 24"><path d="M3 20.5v-7l9-1.5-9-1.5v-7L22 12z"/></svg></button></form>
    <div class="foot">Your details only go to ${esc(C.businessName)}.</div>
  </div>
  <div class="teaser" hidden><button class="x" aria-label="Dismiss">×</button><b>${esc(C.assistantName)} · ${esc(C.businessName)}</b>${esc(C.teaser)}</div>
  <button class="fab" aria-label="Open chat"><svg viewBox="0 0 24 24"><path d="M4 4h16a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H8l-4 4V6a2 2 0 0 1 2-2z"/></svg></button>
</div>`;

  const $ = (s) => root.querySelector(s);
  const panel = $(".panel"), log = $(".log"), form = $(".composer"), input = $(".composer input"), fab = $(".fab"), teaser = $(".teaser");
  const transcript = [];
  let started = false;

  /* ---------- Rendering ---------- */
  function scroll() { log.scrollTop = log.scrollHeight; }
  function bubble(text, who) {
    const d = document.createElement("div");
    d.className = "msg " + who; d.textContent = text; log.appendChild(d); scroll();
    transcript.push((who === "me" ? "Customer: " : C.assistantName + ": ") + text);
  }
  async function say(text) {
    const t = document.createElement("div");
    t.className = "msg bot typing"; t.innerHTML = "<i></i><i></i><i></i>"; log.appendChild(t); scroll();
    await wait(reduced ? 0 : Math.min(1100, 350 + text.length * 12));
    t.remove(); bubble(text, "bot");
  }
  function html(markup) { const d = document.createElement("div"); d.innerHTML = markup; const el = d.firstElementChild; log.appendChild(el); scroll(); return el; }

  /* ---------- Input plumbing: one pending question at a time ---------- */
  let pending = null;
  function clearChips() { log.querySelectorAll(".chips").forEach((c) => c.remove()); }

  // Offer buttons; typed text is matched against each option's keywords.
  function choose(options) {
    return new Promise((resolve) => {
      const wrap = html(`<div class="chips">${options.map((o, i) => `<button class="chip${o.urgent ? " urgent" : ""}" data-i="${i}">${esc(o.label)}</button>`).join("")}</div>`);
      wrap.addEventListener("click", (e) => {
        const b = e.target.closest(".chip"); if (!b) return;
        const o = options[Number(b.dataset.i)]; finish(o, o.label);
      });
      function finish(o, shown) { clearChips(); pending = null; bubble(shown, "me"); resolve(o); }
      pending = {
        onText(text) {
          const t = norm(text);
          const hit = options.find((o) => norm(o.label) === t) ||
                      options.find((o) => (o.keywords || []).some((k) => t.includes(norm(k)))) ||
                      options.find((o) => t.length > 2 && norm(o.label).includes(t));
          if (hit) return finish(Object.assign({}, hit, { typed: text }), text);
          finish({ value: "__free", text }, text);
        }
      };
    });
  }
  // Free-text question with validation.
  function ask(placeholder, validate, type) {
    input.placeholder = placeholder; input.type = type || "text"; input.focus({ preventScroll: true });
    return new Promise((resolve) => {
      pending = {
        onText(text) {
          bubble(text, "me");
          const problem = validate ? validate(text) : null;
          if (problem) { say(problem); return; }
          pending = null; input.placeholder = "Type a message…"; input.type = "text"; resolve(text.trim());
        }
      };
    });
  }
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const v = input.value.trim(); if (!v) return; input.value = "";
    if (pending) pending.onText(v);
    else { bubble(v, "me"); route(v); }
  });

  /* ---------- Conversation ---------- */
  const lead = {};
  const svcOptions = () => C.services.map((s) => ({ label: s.name, value: s.id, urgent: s.urgent, keywords: s.keywords }));

  function detectService(text) {
    const t = norm(text);
    return C.services.find((s) => (s.keywords || []).some((k) => t.includes(norm(k))));
  }
  function detectFaq(text) {
    const t = norm(text);
    return C.faqs.find((f) => (f.keywords || []).some((k) => t.includes(norm(k))));
  }

  async function start() {
    started = true;
    const open = isOpenNow();
    await say(`Hi, I'm ${C.assistantName}, the assistant for ${C.businessName}. ${open ? "The team's on now." : "The office is closed right now, but I can still get you booked in."}`);
    await menu("What can I help you with?");
  }

  async function menu(prompt) {
    await say(prompt);
    const pick = await choose([
      { label: "Book a job", value: "book", keywords: ["book", "appointment", "visit", "come out"] },
      { label: "It's an emergency", value: "emergency", urgent: true, keywords: ["emergency", "urgent", "burst", "flood", "asap"] },
      { label: "I have a question", value: "faq", keywords: ["question", "ask", "info"] },
      { label: "Talk to a person", value: "human", keywords: ["person", "human", "call", "someone", "speak", "talk"] }
    ]);
    if (pick.value === "__free") return route(pick.text);
    return ({ book: () => (pick.typed && detectService(pick.typed) ? route(pick.typed) : book()), emergency: () => emergency(pick.typed), faq: () => faq(), human: () => human() })[pick.value]();
  }

  // Free text typed outside a question: work out what they want.
  async function route(text) {
    const svc = detectService(text);
    if (svc && svc.urgent) return emergency(text);
    if (svc) { lead.notes = text; return book(svc); }
    const f = detectFaq(text);
    if (f) { await say(f.a); return menu("Anything else I can help with?"); }
    if (/\b(hi|hello|hey|hiya)\b/i.test(text)) return menu("Hello! What can I help you with?");
    lead.notes = text;
    await say("Thanks, I've noted that. The quickest way to sort it is to book a visit. An engineer will look and explain your options.");
    return book();
  }

  async function book(preset) {
    let svc = preset;
    if (!svc) {
      await say("What does the job involve?");
      const p = await choose(svcOptions());
      svc = p.value === "__free" ? (detectService(p.text) || { name: "Other: " + p.text }) : C.services.find((s) => s.id === p.value);
      if (p.value === "__free") lead.notes = p.text;
    }
    lead.service = svc.name; lead.urgent = !!svc.urgent;
    if (svc.urgent) return emergency();

    if (!lead.notes) {
      await say(`Got it, ${svc.name.toLowerCase()}. Can you describe what's happening? (Type "skip" if you'd rather explain on the phone.)`);
      const n = await ask("e.g. boiler shows F28, no hot water");
      if (!/^skip$/i.test(n)) lead.notes = n;
    }
    await areaStep();
    await say("When would you like us to come?");
    const when = await choose([
      { label: "As soon as possible", keywords: ["asap", "soon", "today"] },
      { label: "Tomorrow", keywords: ["tomorrow"] },
      { label: "This week", keywords: ["week"] },
      { label: "I'm flexible", keywords: ["flexible", "any", "whenever"] }
    ]);
    lead.slot = when.value === "__free" ? when.text : when.label;
    await contactStep();
    await confirm();
  }

  async function emergency(text) {
    lead.urgent = true; lead.service = lead.service || "Emergency call-out";
    if (text) lead.notes = text;
    await say(C.emergencyLine247 || isOpenNow()
      ? `For an emergency, calling is fastest. The line is staffed${C.emergencyLine247 ? " 24/7" : " now"}:`
      : `The office is closed, but I'll flag this as urgent so the first engineer on shift calls you back.`);
    if (C.emergencyLine247 || isOpenNow()) {
      html(`<a class="cta call" href="tel:${esc(tel)}">Call ${esc(C.phone)}</a>`);
      await say("Can't talk right now? Leave your details and we'll call you within 15 minutes.");
    }
    if (!lead.notes) {
      await say("Quickly, what's happening? For example \"burst pipe under the sink\".");
      lead.notes = await ask("Describe the emergency");
    }
    await say("If water is leaking, turn off the stopcock (usually under the kitchen sink) while you wait.");
    lead.slot = "URGENT call back";
    await areaStep();
    await contactStep();
    await confirm();
  }

  async function areaStep() {
    await say("Which area or postcode are you in?");
    const area = await ask("e.g. Headingley or LS6", (t) => t.trim().length < 2 ? "Could you type your area or postcode?" : null);
    lead.area = area;
    const covered = C.serviceAreas.some((a) => norm(area).includes(norm(a)) || norm(a).includes(norm(area)));
    if (!covered) await say(`I'll check ${area} with the team. We usually cover ${C.serviceAreas.slice(0, 3).join(", ")} and nearby.`);
  }

  async function contactStep() {
    await say("What's your name?");
    lead.name = await ask("Your name", (t) => t.trim().length < 2 ? "Could you give me your name?" : null);
    await say(`Thanks ${lead.name.split(" ")[0]}. What's the best mobile number to reach you on?`);
    lead.phone = await ask("Mobile number", (t) => t.replace(/\D/g, "").length < 10 ? "That number looks too short. Please include the full number." : null, "tel");
  }

  async function confirm() {
    await say("Here's what I've got:");
    const rows = [["Job", lead.service], ["When", lead.slot], ["Area", lead.area], ["Name", lead.name], ["Phone", lead.phone]];
    if (lead.notes) rows.splice(1, 0, ["Details", lead.notes]);
    html(`<dl class="card">${rows.map(([k, v]) => `<dt>${k}</dt><dd>${esc(v)}</dd>`).join("")}</dl>`);
    const ok = await choose([{ label: "Yes, send it", value: "yes", keywords: ["yes", "yep", "correct", "send", "ok"] }, { label: "Start again", value: "no", keywords: ["no", "wrong", "again", "change"] }]);
    if (ok.value === "no") { Object.keys(lead).forEach((k) => delete lead[k]); return menu("No problem. What do you need?"); }
    await submit();
  }

  async function submit() {
    const payload = {
      source: "chat", ref: "CH-" + Date.now().toString(36).toUpperCase().slice(-6), createdAt: new Date().toISOString(),
      business: C.businessName, service: lead.service, urgent: !!lead.urgent, slot: lead.slot, name: lead.name, phone: lead.phone,
      area: lead.area, notes: lead.notes || "", smsConsent: true, transcript: transcript.join("\n"), page: location.href
    };
    let sent = !C.webhookUrl;
    if (C.webhookUrl) {
      try {
        await fetch(C.webhookUrl, { method: "POST", mode: "no-cors", headers: { "Content-Type": "text/plain;charset=utf-8" }, body: JSON.stringify(payload) });
        sent = true;
      } catch (_) { sent = false; }
    }
    if (!sent) {
      await say(`I couldn't send that. Your connection may have dropped. Please call ${C.phone} and quote what you told me.`);
      html(`<a class="cta call" href="tel:${esc(tel)}">Call ${esc(C.phone)}</a>`);
      return;
    }
    await say(lead.urgent
      ? `Sent as URGENT (ref ${payload.ref}). Someone will call ${lead.phone} within 15 minutes.`
      : `Done! Your reference is ${payload.ref}. The team will text ${lead.phone} to confirm a time${isOpenNow() ? " shortly" : " first thing when the office opens"}.`);
    if (C.whatsapp) {
      const msg = `Hi, it's ${lead.name} (ref ${payload.ref}). ${lead.service} in ${lead.area}. ${lead.notes || ""}`.trim();
      html(`<a class="cta wa" target="_blank" rel="noopener" href="https://wa.me/${esc(C.whatsapp)}?text=${encodeURIComponent(msg)}">Send photos on WhatsApp</a>`);
      await say("If you can, send a photo of the problem on WhatsApp. It helps the engineer bring the right parts.");
    }
    Object.keys(lead).forEach((k) => delete lead[k]);
  }

  async function faq() {
    await say("Sure, what would you like to know?");
    const p = await choose(C.faqs.map((f) => ({ label: f.q, value: f.q, keywords: f.keywords })).concat([{ label: "Something else", value: "other" }]));
    if (p.value === "__free") return route(p.text);
    if (p.value === "other") {
      await say("Type your question and I'll do my best. If I can't answer, I'll get someone to call you.");
      const q = await ask("Your question");
      const f = detectFaq(q);
      if (f) { await say(f.a); return menu("Anything else?"); }
      lead.notes = "Question: " + q; lead.service = "General enquiry"; lead.slot = "Call back";
      await say("Good question. That's one for the team. I'll ask them to call you.");
      await areaStep(); await contactStep(); return confirm();
    }
    await say(C.faqs.find((f) => f.q === p.value).a);
    return menu("Anything else I can help with?");
  }

  async function human() {
    if (isOpenNow()) {
      await say(`The team's in now. Call ${C.phone} and someone will pick up.`);
      html(`<a class="cta call" href="tel:${esc(tel)}">Call ${esc(C.phone)}</a>`);
      if (C.whatsapp) html(`<a class="cta wa" target="_blank" rel="noopener" href="https://wa.me/${esc(C.whatsapp)}">Message on WhatsApp</a>`);
      return menu("Or I can take your details and get someone to call you. What would you like to do?");
    }
    await say("The office is closed right now. Leave your details and someone will call you first thing.");
    lead.service = "Call back request"; lead.slot = "Call back";
    await areaStep(); await contactStep(); return confirm();
  }

  /* ---------- Open / close ---------- */
  function open() {
    teaser.hidden = true; panel.hidden = false; fab.setAttribute("aria-expanded", "true");
    fab.querySelector(".dot")?.remove();
    if (!started) start();
    setTimeout(() => input.focus({ preventScroll: true }), 50);
  }
  function close() { panel.hidden = true; fab.setAttribute("aria-expanded", "false"); fab.focus(); }
  fab.addEventListener("click", () => (panel.hidden ? open() : close()));
  $(".close").addEventListener("click", close);
  root.addEventListener("keydown", (e) => { if (e.key === "Escape" && !panel.hidden) close(); });
  teaser.addEventListener("click", (e) => { if (e.target.closest(".x")) { teaser.hidden = true; return; } open(); });

  let dismissed = false;
  try { dismissed = sessionStorage.getItem("rcp-teaser") === "1"; } catch (_) {}
  if (!dismissed && C.teaser) {
    setTimeout(() => {
      if (!panel.hidden || started) return;
      teaser.hidden = false;
      const dot = document.createElement("span"); dot.className = "dot"; fab.appendChild(dot);
      try { sessionStorage.setItem("rcp-teaser", "1"); } catch (_) {}
    }, (C.teaserDelaySeconds || 6) * 1000);
  }

  window.Receptionist = { open, close };
})();
