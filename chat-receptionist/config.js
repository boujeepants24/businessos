/* CLIENT CONFIG for the chat receptionist. Load this before widget.js. */
window.RECEPTIONIST = {
  businessName: "Northfield Plumbing & Heating",
  assistantName: "Nia",
  brandColor: "#0F5C8C",
  phone: "+44 113 496 0123",
  whatsapp: "447700900123",          // digits only; "" to hide
  serviceAreas: ["Leeds", "Headingley", "Roundhay", "Horsforth", "Chapel Allerton", "Wetherby", "Otley"],
  hours: { open: 8, close: 18, days: [1, 2, 3, 4, 5, 6] },
  emergencyLine247: true,

  services: [
    { id: "emergency", name: "Emergency / leak", urgent: true, keywords: ["burst", "flood", "leak", "leaking", "emergency", "water everywhere"] },
    { id: "boiler-repair", name: "Boiler repair", keywords: ["boiler", "no heating", "no hot water", "error", "pressure", "radiator"] },
    { id: "boiler-service", name: "Boiler service", keywords: ["service", "servicing", "annual", "certificate", "landlord"] },
    { id: "bathroom", name: "Bathroom fitting", keywords: ["bathroom", "shower", "toilet", "basin", "refit"] },
    { id: "drains", name: "Blocked drain", keywords: ["blocked", "drain", "sink", "clog", "smell"] }
  ],

  faqs: [
    { q: "Which areas do you cover?", keywords: ["area", "cover", "near", "travel"], a: "We cover Leeds and the surrounding areas: Headingley, Roundhay, Horsforth, Chapel Allerton, Wetherby and Otley." },
    { q: "Are you Gas Safe registered?", keywords: ["gas safe", "registered", "qualified", "insured", "certified"], a: "Yes. Every engineer is Gas Safe registered and we're fully insured." },
    { q: "How quickly can you come?", keywords: ["quick", "today", "soon", "fast", "when"], a: "Emergencies get a same-day response. Most other jobs can be booked within one or two working days." },
    { q: "Do you give a quote first?", keywords: ["quote", "cost", "price", "how much", "estimate"], a: "Yes. The engineer diagnoses the problem and explains your options before any work starts, so there are no surprises." }
  ],

  teaser: "Boiler or leak trouble? I can book you in now.",
  teaserDelaySeconds: 6,
  webhookUrl: "",                     // same Apps Script URL as the booking site
  position: "right"                   // "right" or "left"
};
