/**
 * PER-CLIENT SETTINGS. This is the only file you change when onboarding a client.
 * Secrets (owner key, SMS token) live in Script Properties, never here. Run setup() once.
 */
const CONFIG = {
  business: {
    name: "Northfield Plumbing & Heating",
    ownerName: "Dave",
    phone: "+44 113 496 0123",
    email: "jobs@northfieldplumbing.example",       // reply-to on customer emails
    address: "14 Kirkstall Road, Leeds LS3 1LH",
    website: "https://northfieldplumbing.example",
    googleReviewUrl: "https://g.page/r/EXAMPLE/review",
    currency: "GBP",
    locale: "en-GB",
    taxLabel: "VAT",                                // "GST" in India
    taxRate: 0,                                     // 0.2 for 20% VAT, 0.18 for 18% GST
    taxNumber: ""                                   // VAT / GSTIN, printed on invoices when set
  },

  // Who hears about what
  ownerEmail: "dave@northfieldplumbing.example",    // new leads, call-back alerts, monthly report
  agencyEmail: "ops@youragency.example",            // exceptions only

  // How customers pay. Printed on every invoice and chase message.
  payment: {
    instructions: "Bank transfer to Northfield Plumbing Ltd, sort code 00-00-00, account 00000000. Use your invoice number as the reference.",
    payLinkTemplate: "",                            // optional, e.g. "https://pay.example.com/{invoiceNo}?amount={amount}"
    termsDays: 7
  },

  // Channels. Email is free and always on when the customer gave an address.
  channels: {
    sms: { provider: "", from: "", accountSid: "" }, // provider "twilio"; token goes in Script Property TWILIO_AUTH_TOKEN
    webhookUrl: ""                                   // optional: POST every message to a WhatsApp/SMS gateway (Interakt, AiSensy, Make, Zapier…)
  },

  // Services, and when to invite the customer back
  services: {
    "Emergency call-out": { rebookMonths: 0 },
    "Boiler repair": { rebookMonths: 11 },
    "Boiler service": { rebookMonths: 11 },
    "Leak detection & repair": { rebookMonths: 0 },
    "Bathroom fitting": { rebookMonths: 0 },
    "Blocked drains": { rebookMonths: 6 }
  },

  // Arrival windows the owner can book from the app (match booking-site/config.js)
  booking: { open: 8, close: 18, slotLengthHours: 2 },

  timing: {
    timezone: "Europe/London",
    quietHours: { start: 21, end: 8 },   // no automated customer messages in this window
    callbackAlertMinutes: 15,            // un-contacted enquiry → alert owner
    escalateCallbackMinutes: 120,        // still un-contacted → tell the agency
    bookingReminderHours: 24,
    quoteFollowupDays: [2, 5],
    invoiceChaseDays: [3, 7, 14],
    escalateInvoiceDays: 21,
    reviewDelayHours: 2,
    reviewFollowupDays: 4
  }
};
