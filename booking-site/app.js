(function () {
  "use strict";
  const C = window.CLIENT;
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const telHref = (p) => "tel:" + p.replace(/[^\d+]/g, "");
  const waHref = (text) => "https://wa.me/" + C.whatsapp + (text ? "?text=" + encodeURIComponent(text) : "");

  /* ---------- Branding ---------- */
  function readableInk(hex) {
    const n = parseInt(hex.replace("#", ""), 16);
    const [r, g, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.4 ? "#10181D" : "#FFFFFF";
  }
  const root = document.documentElement.style;
  root.setProperty("--brand", C.brandColor);
  root.setProperty("--accent", C.accentColor);
  root.setProperty("--brand-ink", readableInk(C.brandColor));

  document.title = `${C.businessName} | ${C.trade} in ${C.city}`;
  document.querySelector('meta[name="description"]').content = `${C.trade} in ${C.city}. ${C.tagline} Book online in under a minute.`;
  $("bizName").textContent = C.businessName;
  $("mono").innerHTML = C.logoUrl ? `<img src="${esc(C.logoUrl)}" alt="">` : esc(C.logoText);
  $("eyebrow").textContent = `${C.trade} · ${C.city}`;
  $("tagline").textContent = C.tagline;
  $("topPhone").textContent = C.phone;
  $("topCall").href = telHref(C.phone);
  $("mbCall").href = telHref(C.phone);
  if (C.whatsapp) $("mbWa").href = waHref(`Hi ${C.businessName}, I'd like to book a job.`);
  else $("mbWa").remove();

  $("trust").innerHTML = [`${C.yearsTrading} years trading`, ...C.accreditations].map((t) => `<li>${esc(t)}</li>`).join("");
  const stars = (n) => "★★★★★".slice(0, Math.round(n)) + "☆☆☆☆☆".slice(0, 5 - Math.round(n));
  $("rating").innerHTML = `<span class="stars" aria-hidden="true">${stars(C.rating)}</span><b>${C.rating.toFixed(1)}</b><span>from ${C.reviewCount} local reviews</span>`;

  $("svcGrid").innerHTML = C.services.map((s) => `
    <article class="svc"><h3>${esc(s.name)}${s.urgent ? '<span class="badge">Same day</span>' : ""}</h3>
    <p>${esc(s.desc)}</p><button type="button" data-book="${esc(s.id)}">Book this →</button></article>`).join("");
  $("reviews").innerHTML = C.reviews.map((r) => `
    <figure class="review"><span class="stars" aria-label="5 stars">★★★★★</span>
    <blockquote>${esc(r.text)}</blockquote><figcaption>${esc(r.name)} · ${esc(r.area)}</figcaption></figure>`).join("");
  $("areas").innerHTML = C.serviceAreas.map((a) => `<li>${esc(a)}</li>`).join("");
  $("areaList").innerHTML = C.serviceAreas.map((a) => `<option value="${esc(a)}">`).join("");
  $("faqFast").textContent = C.emergencyLine247
    ? `Emergencies are answered 24/7 on ${C.phone}. Standard jobs can usually be booked within one to two working days.`
    : `Most jobs can be booked within one to two working days. Pick the earliest window that suits you above.`;
  $("footName").textContent = C.businessName;
  $("footAddr").textContent = C.address;
  $("footContact").innerHTML = `<a href="${telHref(C.phone)}">${esc(C.phone)}</a><br><a href="mailto:${esc(C.email)}">${esc(C.email)}</a>`;

  // Open / closed pill
  const now = new Date();
  const isOpen = C.hours.days.includes(now.getDay()) && now.getHours() >= C.hours.open && now.getHours() < C.hours.close;
  const pill = $("openPill");
  pill.textContent = isOpen ? "Open now" : C.emergencyLine247 ? "Emergency line open" : "Closed · book online";
  if (!isOpen && !C.emergencyLine247) pill.classList.add("closed");

  // Local SEO: schema.org markup
  const ld = document.createElement("script");
  ld.type = "application/ld+json";
  ld.textContent = JSON.stringify({
    "@context": "https://schema.org", "@type": "LocalBusiness", name: C.businessName, telephone: C.phone, email: C.email,
    address: C.address, areaServed: C.serviceAreas,
    aggregateRating: { "@type": "AggregateRating", ratingValue: C.rating, reviewCount: C.reviewCount }
  });
  document.head.appendChild(ld);

  /* ---------- Booking flow ---------- */
  const state = { step: 1, service: null, date: null, slot: null };
  const fmtDay = new Intl.DateTimeFormat(C.locale, { weekday: "short" });
  const fmtLong = new Intl.DateTimeFormat(C.locale, { weekday: "long", day: "numeric", month: "long" });
  const pad = (n) => String(n).padStart(2, "0");
  const ymd = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const slotLabel = (h) => `${pad(h)}:00–${pad(h + C.slotLengthHours)}:00`;
  let taken = new Set();

  function radio(container, selector, value) {
    container.querySelectorAll(selector).forEach((b) => b.setAttribute("aria-checked", String(b.dataset.v === value)));
  }

  // Step 1: service
  $("svcPick").innerHTML = C.services.map((s) =>
    `<button type="button" role="radio" aria-checked="false" class="svc-opt" data-v="${esc(s.id)}">${esc(s.name)}${s.urgent ? '<span class="tag">Same day</span>' : ""}</button>`).join("");
  $("svcPick").addEventListener("click", (e) => {
    const b = e.target.closest(".svc-opt"); if (!b) return;
    state.service = b.dataset.v; radio($("svcPick"), ".svc-opt", state.service); $("err1").textContent = "";
  });
  document.addEventListener("click", (e) => {
    const b = e.target.closest("[data-book]"); if (!b) return;
    state.service = b.dataset.book; radio($("svcPick"), ".svc-opt", state.service); go(1);
    $("book").scrollIntoView({ block: "start" });
  });

  // Step 2: day + slot
  const days = [];
  for (let i = 0; days.length < C.bookingDaysAhead && i < 31; i++) {
    const d = new Date(); d.setHours(0, 0, 0, 0); d.setDate(d.getDate() + i);
    if (C.hours.days.includes(d.getDay())) days.push(d);
  }
  $("days").innerHTML = days.map((d) =>
    `<button type="button" role="radio" aria-checked="false" class="day" data-v="${ymd(d)}" aria-label="${fmtLong.format(d)}"><span>${fmtDay.format(d)}</span><b>${d.getDate()}</b></button>`).join("");
  $("days").addEventListener("click", (e) => {
    const b = e.target.closest(".day"); if (!b) return;
    state.date = b.dataset.v; state.slot = null; radio($("days"), ".day", state.date); renderSlots(); $("err2").textContent = "";
  });

  function renderSlots() {
    if (!state.date) { $("slots").innerHTML = ""; $("slotHint").textContent = "Pick a day to see arrival windows."; return; }
    const isToday = state.date === ymd(new Date());
    const cutoff = new Date().getHours() + 1;
    const html = [];
    for (let h = C.hours.open; h + C.slotLengthHours <= C.hours.close; h += C.slotLengthHours) {
      const off = (isToday && h < cutoff) || taken.has(`${state.date}|${h}`);
      html.push(`<button type="button" role="radio" aria-checked="${state.slot === h}" class="slot" data-v="${h}" ${off ? "disabled" : ""}>${slotLabel(h)}</button>`);
    }
    $("slots").innerHTML = html.join("");
    const free = $("slots").querySelectorAll(".slot:not(:disabled)").length;
    $("slotHint").textContent = free ? `${free} arrival window${free > 1 ? "s" : ""} left on this day.` : "Fully booked. Try the next day.";
  }
  $("slots").addEventListener("click", (e) => {
    const b = e.target.closest(".slot"); if (!b || b.disabled) return;
    state.slot = Number(b.dataset.v); radio($("slots"), ".slot", b.dataset.v); $("err2").textContent = "";
  });

  // Live availability from the Google Sheet backend; demo mode marks a few windows as taken.
  if (C.webhookUrl) {
    fetch(C.webhookUrl + "?action=slots").then((r) => r.json()).then((j) => { taken = new Set(j.taken || []); renderSlots(); }).catch(() => {});
  } else {
    days.forEach((d, i) => { if (i % 2 === 0) taken.add(`${ymd(d)}|${C.hours.open + C.slotLengthHours * ((i + 1) % 3)}`); });
  }

  // Navigation
  function go(n) {
    state.step = n;
    document.querySelectorAll(".step").forEach((f) => { f.hidden = Number(f.dataset.step) !== n; });
    document.querySelectorAll("#stepDots li").forEach((li, i) => li.classList.toggle("on", i < n));
    if (n === 2) {
      if (!state.date) { const first = $("days").querySelector(".day"); if (first) first.click(); }
      else renderSlots();
    }
  }
  function validate(n) {
    if (n === 1 && !state.service) { $("err1").textContent = "Choose the type of job so we send the right engineer."; return false; }
    if (n === 2 && state.slot == null) { $("err2").textContent = "Pick an arrival window."; return false; }
    return true;
  }
  document.querySelectorAll("[data-next]").forEach((b) => b.addEventListener("click", () => { if (validate(state.step)) go(Number(b.dataset.next)); }));
  document.querySelectorAll("[data-prev]").forEach((b) => b.addEventListener("click", () => go(Number(b.dataset.prev))));

  // Step 3: details + submit
  const phoneOk = (p) => p.replace(/[^\d]/g, "").length >= 10;
  $("bookForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = $("name").value.trim(), phone = $("phone").value.trim(), area = $("area").value.trim();
    const checks = [[$("name"), name.length >= 2], [$("phone"), phoneOk(phone)], [$("area"), area.length >= 2]];
    checks.forEach(([el, ok]) => el.setAttribute("aria-invalid", String(!ok)));
    if (!checks.every(([, ok]) => ok)) {
      $("err3").textContent = !phoneOk(phone) && name && area ? "Enter a mobile number with at least 10 digits." : "Fill in your name, mobile number and area.";
      (checks.find(([, ok]) => !ok) || [])[0]?.focus();
      return;
    }
    $("err3").textContent = "";
    const svc = C.services.find((s) => s.id === state.service);
    const dateObj = new Date(state.date + "T00:00:00");
    const lead = {
      source: "booking-page",
      ref: "BK-" + Date.now().toString(36).toUpperCase().slice(-6),
      createdAt: new Date().toISOString(),
      business: C.businessName,
      service: svc.name,
      urgent: !!svc.urgent,
      date: state.date,
      slot: slotLabel(state.slot),
      slotHour: state.slot,
      name, phone, area,
      email: $("email").value.trim(),
      notes: $("notes").value.trim(),
      smsConsent: $("consent").checked,
      page: location.href
    };

    const btn = $("submitBtn"); btn.disabled = true; btn.textContent = "Booking…";
    try {
      if (C.webhookUrl) {
        if (!navigator.onLine) throw new Error("offline");
        let reply = null;
        try {
          const res = await fetch(C.webhookUrl, { method: "POST", headers: { "Content-Type": "text/plain;charset=utf-8" }, body: JSON.stringify(lead) });
          reply = await res.json();
        } catch (_) { /* request was sent but the reply was unreadable; the sheet still has the lead */ }
        if (reply && reply.error === "slot_taken") {
          taken.add(`${lead.date}|${lead.slotHour}`); state.slot = null; go(2);
          $("err2").textContent = "Someone just booked that window. Pick another one.";
          return;
        }
        if (reply && reply.ok === false) throw new Error(reply.error);
      }
      showDone(lead, dateObj);
    } catch (err) {
      $("err3").textContent = `We couldn't send your booking. Check your connection and try again, or call ${C.phone}.`;
    } finally {
      btn.disabled = false; btn.textContent = "Confirm booking";
    }
  });

  function showDone(lead, dateObj) {
    $("bookForm").hidden = true; $("stepDots").hidden = true; $("done").hidden = false;
    $("doneText").textContent = `Thanks ${lead.name.split(" ")[0]}. We'll text ${lead.phone} to confirm your engineer.`;
    const rows = [["Reference", lead.ref], ["Job", lead.service], ["When", `${fmtLong.format(dateObj)}, ${lead.slot}`], ["Where", lead.area]];
    $("summary").innerHTML = rows.map(([k, v]) => `<dt>${k}</dt><dd>${esc(v)}</dd>`).join("");
    if (C.whatsapp) {
      const a = $("waConfirm"); a.hidden = false;
      a.href = waHref(`New booking ${lead.ref}\n${lead.service}\n${fmtLong.format(dateObj)}, ${lead.slot}\n${lead.name} · ${lead.phone}\n${lead.area}${lead.notes ? "\nNotes: " + lead.notes : ""}`);
    }
    taken.add(`${lead.date}|${lead.slotHour}`);
    toast("Booking received");
  }
  $("again").addEventListener("click", () => {
    $("bookForm").reset(); Object.assign(state, { service: null, date: null, slot: null });
    radio($("svcPick"), ".svc-opt", ""); radio($("days"), ".day", "");
    $("done").hidden = true; $("bookForm").hidden = false; $("stepDots").hidden = false; go(1);
  });

  let tt;
  function toast(msg) { const t = $("toast"); t.textContent = msg; t.classList.add("show"); clearTimeout(tt); tt = setTimeout(() => t.classList.remove("show"), 2600); }

  go(1);
})();
