/*
 * CLIENT CONFIG — the only file you edit per client.
 * Change these values, upload the folder, done.
 */
window.CLIENT = {
  businessName: "Northfield Plumbing & Heating",
  tagline: "Leaks, boilers and bathrooms, fixed properly the first time.",
  trade: "Plumbing & Heating",
  city: "Leeds",
  serviceAreas: ["Leeds", "Headingley", "Roundhay", "Horsforth", "Chapel Allerton", "Wetherby", "Otley"],
  phone: "+44 113 496 0123",          // shown + used for tap-to-call
  whatsapp: "447700900123",          // digits only, with country code. "" to hide WhatsApp
  email: "jobs@northfieldplumbing.example",
  address: "14 Kirkstall Road, Leeds LS3 1LH",

  // Brand
  brandColor: "#0F5C8C",            // primary
  accentColor: "#E8A33D",           // highlights / urgent badge
  logoText: "NP",                   // monogram used when no logo image
  logoUrl: "",                      // optional: "assets/logo.svg"

  // Trust signals
  rating: 4.9,
  reviewCount: 212,
  yearsTrading: 14,
  accreditations: ["Gas Safe registered", "WaterSafe approved", "Fully insured"],
  reviews: [
    { name: "Priya K.", area: "Headingley", text: "Boiler died on a Sunday night. Booked online, engineer was here by 9am Monday and it was running by 10." },
    { name: "Tom W.", area: "Roundhay", text: "Clear about what was wrong, tidy, and turned up exactly when the text said he would." },
    { name: "Aisha R.", area: "Horsforth", text: "Third plumber I tried and the only one who actually answered. Booking form took a minute." }
  ],

  // Services shown on the page and in the booking form
  services: [
    { id: "emergency", name: "Emergency call-out", desc: "Burst pipes, major leaks, no water. Same-day response.", urgent: true },
    { id: "boiler-repair", name: "Boiler repair", desc: "No heating or hot water, error codes, pressure loss." },
    { id: "boiler-service", name: "Boiler service", desc: "Annual safety check and service, with certificate." },
    { id: "leak", name: "Leak detection & repair", desc: "Finding and fixing hidden leaks without wrecking walls." },
    { id: "bathroom", name: "Bathroom fitting", desc: "Full refits, showers, toilets and basins." },
    { id: "drains", name: "Blocked drains", desc: "Sinks, toilets and outside drains cleared." }
  ],

  // Booking slots
  hours: { open: 8, close: 18, days: [1, 2, 3, 4, 5, 6] }, // 0=Sun … 6=Sat
  slotLengthHours: 2,
  bookingDaysAhead: 10,
  emergencyLine247: true,

  // Where leads go. Paste the Google Apps Script web-app URL from ops-engine/README.md.
  // Leave "" in demos: leads are then only shown on screen + sent via WhatsApp.
  webhookUrl: "",

  locale: "en-GB"
};
