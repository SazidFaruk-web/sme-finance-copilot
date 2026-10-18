// Deterministic, record-backed guidance. No model call or financial calculation here.
// Keep priority and permission decisions independently testable from the DOM.
import { zh, zhCopy } from "./i18n-zh.js?v=2";

const COPY = {
  en: {
    low_balance: ["Plan for a money shortfall", "Your recorded activity suggests money may run low. Check expected payments before taking on a new cost.", ["Check which customers still need to pay you.", "Check the bills due before the expected shortfall.", "Ask Copilot to compare what can wait before deciding."]],
    overdue_invoice: ["Follow up on an unpaid bill", "A customer's payment is late. A polite follow-up can help you collect money already owed.", ["Open the customer's bill and check the amount still due.", "Review the reminder and recipient.", "Confirm only when the details are correct. This demo saves it to a sandbox outbox."]],
    payable_due: ["Check a supplier bill", "A supplier payment is due soon or already late. Check the bill and the money you need for other essentials.", ["Check the supplier, amount, and due date.", "Check your recorded money before choosing when to pay.", "Any demo payment needs the owner's confirmation."]],
    obligation_due: ["Set aside money for an upcoming bill", "A regular business cost is coming up. Planning for it now can avoid a last-minute rush.", ["Check the bill's amount and due date below.", "Check what money should arrive before then.", "Record the payment after you have actually paid."]],
    spending_spike: ["Take a quick look at spending", "One type of spending is higher than usual in your records. Check whether it was expected.", ["Check the original expenses.", "Look for a one-off purchase or an incorrect entry.", "Ask Copilot what changed before deciding to cut costs."]],
    unusual_spending: ["Check an unexpected expense", "One recorded expense looks unusual. It may be correct; check it before changing anything.", ["Open your records and find the expense.", "Compare it with your receipt or statement.", "Correct it only if the original entry is wrong."]],
    stock_low: ["Check what needs restocking", "A product may run low based on your records. Check the shelf and upcoming orders before buying more.", ["Check the product and quantity in Stock.", "Check what is already on order.", "Plan a small restock that fits your available money."]],
    stock_out: ["Check an out-of-stock product", "Your records show a product has run out. Check the actual stock before promising it to a customer.", ["Check the shelf and the recorded quantity.", "Check upcoming customer orders.", "Choose a restock amount after checking your money."]],
    stock_cash: ["Check the cost of restocking", "Restocking may put pressure on your money. Review essential bills before placing an order.", ["Check the suggested stock purchase.", "Compare it with the bills due soon.", "Ask Copilot about a smaller order or a later purchase."]],
    compliance_due: ["Check a business deadline", "A possible business deadline is approaching. Verify the rule and date with the relevant authority.", ["Read the original reminder below.", "Verify whether the rule applies to your business.", "Confirm the current deadline before acting."]],
    seasonal_prep: ["Prepare for the coming busy period", "Your records suggest a seasonal change may be coming. Check likely orders and costs first.", ["Review the upcoming event below.", "Check customer orders and stock.", "Plan only the purchases you can afford."]],
    custom: ["Your reminder", "You asked to be reminded about this in the app.", ["Review your note below.", "Complete the task when you are ready.", "Mark it done to remove the reminder."]],
    fallback: ["Review this business update", "There is an update in your recorded business information.", ["Read the details below.", "Check the relevant records.", "Ask Copilot if you need help choosing a next step."]],
    check: "Check bills", records: "View records", stock: "Check stock", ask: "Ask Copilot", reminder: "Review reminder", note: "Read reminder",
    first: "Start with one sale or expense", firstWhy: "Add what happened in your business. You can write it in everyday English, Bangla, or Banglish.",
    daily: "Keep today's records up to date", dailyWhy: "No urgent issue was found in the available records. Add any missing sales or costs so the next suggestion is useful.",
    add: "Add a record", readOnly: "Review the business records", readOnlyWhy: "You have read-only access. You can check records and ask Copilot; an owner or accountant can make changes.",
    entrySteps: ["Write what you sold or paid for, with the amount.", "Check the preview and save the entry.", "Add another record whenever money comes in or goes out."],
    question: "Help me with this next step, using my business records. Explain what to do, why it matters, and at most three practical steps: ",
  },
  bn: {
    low_balance: ["টাকার ঘাটতির জন্য প্রস্তুতি নিন", "আপনার হিসাব অনুযায়ী সামনে টাকা কম পড়তে পারে। নতুন খরচের আগে পাওনা ও বিল দেখুন।", ["কোন ক্রেতার কাছে টাকা পাবেন তা দেখুন।", "ঘাটতির আগে কোন বিল দিতে হবে দেখুন।", "কোন খরচ পরে করা যায়, কোপাইলটের কাছে জানতে চান।"]],
    overdue_invoice: ["বকেয়া বিলের খোঁজ নিন", "একজন ক্রেতার টাকা দেওয়ার তারিখ পেরিয়ে গেছে। ভদ্রভাবে মনে করিয়ে দিলে পাওনা আদায়ে সাহায্য হতে পারে।", ["ক্রেতার বিল ও বাকি টাকার পরিমাণ দেখুন।", "রিমাইন্ডারের লেখা ও প্রাপক যাচাই করুন।", "সব ঠিক থাকলে নিশ্চিত করুন। এই ডেমোতে এটি স্যান্ডবক্স আউটবক্সে থাকবে।"]],
    payable_due: ["সরবরাহকারীর বিল দেখুন", "একটি বিল দেওয়ার সময় হয়েছে বা পেরিয়ে গেছে। টাকা দেওয়ার আগে জরুরি খরচগুলো দেখুন।", ["সরবরাহকারী, পরিমাণ ও তারিখ যাচাই করুন।", "হিসাবের টাকা ও অন্য জরুরি বিল দেখুন।", "ডেমো পেমেন্টের জন্য মালিকের অনুমোদন লাগবে।"]],
    obligation_due: ["আসন্ন বিলের জন্য টাকা রাখুন", "নিয়মিত ব্যবসার একটি খরচ সামনে আসছে। আগে থেকে প্রস্তুতি নিন।", ["নিচে বিলের পরিমাণ ও তারিখ দেখুন।", "তার আগে কত টাকা পাওয়ার কথা আছে দেখুন।", "আসল টাকা দেওয়ার পর খরচের হিসাব লিখুন।"]],
    spending_spike: ["খরচ একটু যাচাই করুন", "এক ধরনের খরচ স্বাভাবিকের চেয়ে বেশি হয়েছে। খরচটি প্রত্যাশিত ছিল কি না দেখুন।", ["মূল খরচের হিসাব দেখুন।", "এককালীন কেনাকাটা বা ভুল হিসাব আছে কি না দেখুন।", "খরচ কমানোর আগে কী বদলেছে জানতে চান।"]],
    unusual_spending: ["অপ্রত্যাশিত খরচটি দেখুন", "একটি খরচ অন্যগুলোর চেয়ে আলাদা। বদলানোর আগে মূল রসিদের সঙ্গে মিলিয়ে নিন।", ["হিসাব থেকে খরচটি খুঁজুন।", "রসিদ বা স্টেটমেন্টের সঙ্গে মিলিয়ে নিন।", "ভুল থাকলেই কেবল সংশোধন করুন।"]],
    stock_low: ["কোন পণ্য আনতে হবে দেখুন", "হিসাব অনুযায়ী একটি পণ্য কমে আসছে। কেনার আগে দোকানের পণ্য ও অর্ডার দেখুন।", ["পণ্যের পরিমাণ দেখুন।", "আগে থেকে অর্ডার করা আছে কি না দেখুন।", "টাকার সঙ্গে মিলিয়ে অল্প করে কেনার পরিকল্পনা করুন।"]],
    stock_out: ["শেষ হয়ে যাওয়া পণ্য দেখুন", "হিসাব অনুযায়ী একটি পণ্য শেষ। ক্রেতাকে কথা দেওয়ার আগে দোকানে মিলিয়ে নিন।", ["দোকানের পণ্য ও হিসাব মিলিয়ে দেখুন।", "সামনের অর্ডারগুলো দেখুন।", "টাকা দেখে নতুন পণ্য কেনার সিদ্ধান্ত নিন।"]],
    stock_cash: ["পণ্য কেনার খরচ দেখুন", "নতুন পণ্য কিনলে টাকায় চাপ পড়তে পারে। আগে জরুরি বিলগুলো দেখুন।", ["কী পণ্য কেনা দরকার দেখুন।", "সামনের বিলের সঙ্গে খরচ মিলিয়ে নিন।", "অল্প বা পরে কেনা যায় কি না জানতে চান।"]],
    compliance_due: ["ব্যবসার একটি সময়সীমা যাচাই করুন", "একটি সম্ভাব্য সময়সীমা সামনে আসছে। সংশ্লিষ্ট কর্তৃপক্ষের কাছে নিয়ম ও তারিখ যাচাই করুন।", ["নিচের মূল তথ্য পড়ুন।", "নিয়মটি আপনার ব্যবসায় প্রযোজ্য কি না যাচাই করুন।", "কাজ করার আগে বর্তমান তারিখ নিশ্চিত করুন।"]],
    seasonal_prep: ["সামনের ব্যস্ত সময়ের প্রস্তুতি নিন", "সামনে মৌসুমি পরিবর্তন আসতে পারে। আগে অর্ডার ও খরচ দেখে নিন।", ["সামনের উপলক্ষ দেখুন।", "অর্ডার ও পণ্যের হিসাব দেখুন।", "সামর্থ্যের মধ্যে কেনার পরিকল্পনা করুন।"]],
    custom: ["আপনার রিমাইন্ডার", "এই কাজটি অ্যাপের মধ্যে মনে করিয়ে দিতে বলেছিলেন।", ["নিচে আপনার নোট পড়ুন।", "সুবিধামতো কাজটি শেষ করুন।", "শেষ হলে সম্পন্ন হিসেবে চিহ্নিত করুন।"]],
    fallback: ["ব্যবসার এই তথ্যটি দেখুন", "আপনার ব্যবসার হিসাবে একটি নতুন তথ্য আছে।", ["নিচের তথ্য পড়ুন।", "সংশ্লিষ্ট হিসাব দেখুন।", "সিদ্ধান্ত নিতে সাহায্য লাগলে কোপাইলটকে জিজ্ঞাসা করুন।"]],
    check: "বিল দেখুন", records: "হিসাব দেখুন", stock: "পণ্য দেখুন", ask: "কোপাইলটকে জিজ্ঞাসা করুন", reminder: "রিমাইন্ডার দেখুন", note: "নোট পড়ুন",
    first: "একটি বিক্রি বা খরচ দিয়ে শুরু করুন", firstWhy: "ব্যবসায় যা হয়েছে লিখুন। সহজ বাংলা, ইংরেজি বা বাংলিশ ব্যবহার করতে পারেন।",
    daily: "আজকের হিসাব হালনাগাদ রাখুন", dailyWhy: "বর্তমান হিসাবে জরুরি কোনো সমস্যা পাওয়া যায়নি। বাদ পড়া বিক্রি ও খরচ যোগ করুন।",
    add: "হিসাব যোগ করুন", readOnly: "ব্যবসার হিসাব দেখুন", readOnlyWhy: "আপনি শুধু হিসাব দেখতে পারবেন ও প্রশ্ন করতে পারবেন। পরিবর্তনের জন্য মালিক বা হিসাবরক্ষককে বলুন।",
    entrySteps: ["কী বিক্রি করেছেন বা কী খরচ হয়েছে, পরিমাণসহ লিখুন।", "আগে হিসাব মিলিয়ে তারপর সেভ করুন।", "টাকা এলে বা গেলে একটি করে হিসাব যোগ করুন।"],
    question: "আমার ব্যবসার হিসাব দিয়ে এই কাজে সাহায্য করুন। কী করব, কেন করব এবং সর্বোচ্চ তিনটি সহজ ধাপ বলুন: ",
  },
};
COPY.zh = zhCopy(COPY.en);
const KIND_ORDER = ["low_balance", "overdue_invoice", "payable_due", "obligation_due", "custom", "stock_out", "stock_cash", "stock_low", "compliance_due", "unusual_spending", "spending_spike", "seasonal_prep"];

export function buildGuidance({ alerts = [], recordCount = 0, asOf, canWrite = false, language = "en" }) {
  const c = COPY[language] || COPY.en;
  const pick = (en, bn) => language === "bn" ? bn : language === "zh" ? zh(en) : en;
  const unique = [...new Map(alerts.map(a => [a.id, a])).values()];
  const active = unique.filter(a => ["open", "scheduled"].includes(a.status || "open"));
  const reminders = active.filter(a => a.kind === "custom" && a.due_date > asOf)
    .sort((a, b) => a.due_date.localeCompare(b.due_date));
  const ranked = active.filter(a => !reminders.includes(a) && (recordCount > 0 || !["low_balance", "spending_spike", "unusual_spending"].includes(a.kind))).sort((a, b) => {
    const sev = s => ({ critical: 0, warning: 1, info: 2 }[s] ?? 3);
    return Number(Boolean(b.data?.reconciliation)) - Number(Boolean(a.data?.reconciliation)) || sev(a.severity) - sev(b.severity)
      || (KIND_ORDER.indexOf(a.kind) < 0 ? 99 : KIND_ORDER.indexOf(a.kind)) - (KIND_ORDER.indexOf(b.kind) < 0 ? 99 : KIND_ORDER.indexOf(b.kind))
      || (a.due_date || "9999").localeCompare(b.due_date || "9999") || a.id - b.id;
  });
  const tasks = ranked.map(a => {
    let [title, why, steps] = c[a.kind] || c.fallback;
    let action = { label: c.ask, href: "#chat" };
    if (["overdue_invoice", "payable_due", "obligation_due"].includes(a.kind)) action = { label: c.check, href: "#invoices" };
    if (["unusual_spending", "spending_spike"].includes(a.kind)) action = { label: c.records, href: "#data" };
    if (a.kind.startsWith("stock_")) action = { label: c.stock, href: "#stock" };
    // Only reminders can be prepared here. Payments always open bills for deliberate review.
    const st = a.data?.suggested_tool;
    if (canWrite && a.kind === "overdue_invoice" && st?.name === "create_payment_reminder") action = { label: c.reminder, tool: st.name, args: st.args };
    if (a.kind === "custom") action = { label: c.note, details: true };
    if (a.data?.case_id) action = { label: pick("Open task", "কাজ খুলুন"), href: `#chat?case=${a.data.case_id}` };
    if (a.data?.reconciliation) {
      title = pick("Check the money records first", "আগে টাকার হিসাব মিলিয়ে নিন");
      why = pick("Your counted money differs from the records. Check missing or incorrect entries before relying on a money decision.", "গুনে পাওয়া টাকা হিসাবের সঙ্গে মেলেনি। সিদ্ধান্তের আগে বাদ পড়া বা ভুল হিসাব ঠিক করুন।");
      steps = [];
    }
    return { id: a.id, kind: a.kind, title: a.data?.reconciliation ? title : a.kind === "custom" ? a.data?.task_title?.[language] || a.title : title, why, steps, action, source: a,
      question: c.question + a.title + (a.message ? "\n" + a.message : "") };
  });
  const routine = { id: "routine", kind: "routine", title: canWrite ? (recordCount ? c.daily : c.first) : c.readOnly,
    why: canWrite ? (recordCount ? c.dailyWhy : c.firstWhy) : c.readOnlyWhy,
    steps: canWrite ? c.entrySteps : [], action: { label: canWrite ? c.add : c.records, href: "#data" }, question: c.question + (recordCount ? c.daily : c.first) };
  // With no transaction history, start with recording rather than inventing a healthy cash assessment.
  if (!recordCount && canWrite && !ranked.some(a => a.data?.reconciliation)) tasks.unshift(routine);
  if (!tasks.length) tasks.push(routine);
  // Home receives one recommendation. The complete priority order belongs on the Tasks page.
  return { primary: tasks[0], tasks, reminders, count: tasks.filter(t => t.kind !== "routine").length };
}

export function upcomingItems({ scheduled = [], reminders = [], asOf, limit = 4 }) {
  const end = new Date(asOf + "T12:00:00Z"); end.setUTCDate(end.getUTCDate() + 14);
  const until = end.toISOString().slice(0, 10);
  const events = scheduled.filter(x => x.date >= asOf && x.date <= until)
    .map(x => ({ date: x.date, title: x.label, amount: x.amount, kind: x.kind, estimated: true }));
  const personal = reminders.filter(a => a.due_date >= asOf).map(a => ({ date: a.due_date, title: a.title, note: a.message, kind: "reminder", id: a.id }));
  return [...personal, ...events].sort((a, b) => a.date.localeCompare(b.date) || Number(b.kind === "reminder") - Number(a.kind === "reminder")).slice(0, limit);
}
