"""Short discovery first. A local model selects a relevant, approved follow-up.

Tap answers establish the problem, never fabricate financial inputs or legal facts.
Existing detailed cases and optional exact comparisons retain their strict calculations.
"""
from datetime import date, timedelta

from .definitions import q, opts, tr

META = {"_strategy_flow", "_strategy_depth", "_strategy_followup", "_strategy_question_source"}
FOLLOWUPS = {"storage_setup", "demand_signal", "priority"}


def followups(a):
    drivers = a.get("drivers") or []
    candidates = ["priority"]
    if a.get("plan_type") == "seasonal" or "availability" in drivers or "space" in drivers:
        candidates.insert(0, "storage_setup")
    if a.get("plan_type") == "equipment" or "growth" in drivers:
        candidates.insert(0, "demand_signal")
    return candidates


def prepare(a, changed):
    """Persist routing once per answer revision; reloading never rerolls the question."""
    from .question_model import select_id
    a = dict(a)
    if changed in ("plan_type", "item"):
        # Quotes and quantities for a different purchase must be entered afresh.
        keep = META | FOLLOWUPS | {"plan_type", "item", "drivers", "stage", "review_date"}
        a = {k: v for k, v in a.items() if k in keep}
    if changed in ("plan_type", "item", "drivers", "stage"):
        for key in META - {"_strategy_flow"} | FOLLOWUPS:
            a.pop(key, None)
    if all(k in a for k in ("plan_type", "item", "drivers", "stage")) and not a.get("_strategy_followup"):
        allowed = followups(a)
        # Only reviewed choice IDs go to the shared local model. No item/name/free text.
        selected = select_id({"purpose": "strategy_followup", "goal": a.get("plan_type"), "answers": {
            "drivers": a.get("drivers"), "stage": a.get("stage")},
            "question_intent": {"storage_setup": "Check whether there is safe storage before buying more",
                                "demand_signal": "Find evidence that customer demand is growing",
                                "priority": "Ask about the main worry: bills, waste or supplier terms"},
            "instruction": "Choose the single most useful follow-up for this owner's responses."}, allowed)
        a["_strategy_followup"] = selected if selected in allowed else allowed[0]
        a["_strategy_question_source"] = "model" if selected in allowed else "rules"
    return a


def item_options(a, snap):
    if a.get("plan_type") == "equipment":
        return opts(("Freezer", "Freezer", "ফ্রিজার"), ("Machine", "Another machine", "অন্য যন্ত্র"))
    rows = [{"value": x, "label": tr(x, x)} for x in (snap.get("items") or [])[:3]]
    if rows:
        return rows
    text = str(snap.get("business_context", "")).lower()
    if any(x in text for x in ("juice", "জুস", "fruit", "ফল")):
        return opts(("Mango pulp (kg)", "Mango pulp", "আমের পাল্প"), ("Sugar (kg)", "Sugar", "চিনি"))
    return []  # No invented product list for an unrecognised business.


def guide_questions(a, snap):
    from .strategy import PLAN_TYPES, detail_questions
    qs = [q("plan_type", "What would you like to plan?", "কী পরিকল্পনা করতে চান?", "choice", PLAN_TYPES)]
    if not a.get("plan_type"):
        return qs
    qs.append(q("item", "What are you thinking of buying?", "কী কেনার কথা ভাবছেন?", "suggest", item_options(a, snap)))
    if "item" not in a:
        return qs
    drivers = (opts(("growth", "Customers are waiting", "ক্রেতাকে অপেক্ষা করতে হচ্ছে"),
                    ("space", "I need more storage", "আরও সংরক্ষণের জায়গা দরকার"),
                    ("replace", "Replace an unreliable machine", "বারবার নষ্ট হওয়া যন্ত্র বদলাব"))
               if a.get("plan_type") == "equipment" else
               opts(("lower_cost", "Spend less on buying", "কেনার খরচ কমাব"),
                    ("availability", "Keep it available later", "পরেও পণ্যটি রাখতে চাই"),
                    ("growth", "Serve more customers", "আরও ক্রেতাকে সেবা দেব")))
    qs.append(q("drivers", "What would this help with? Choose any that fit.", "এতে কী সুবিধা হবে? যা মেলে বাছুন।", "multi", drivers))
    if "drivers" not in a:
        return qs
    qs.append(q("stage", "Have you checked any prices yet?", "কোনো দাম কি জেনে নিয়েছেন?", "choice",
                opts(("exploring", "Just exploring", "এখনও ভাবছি"), ("quote", "I have a price or quote", "দাম বা প্রস্তাব আছে"),
                     ("unsure", "Not sure where to start", "কোথা থেকে শুরু করব জানি না"))))
    if "stage" not in a:
        return qs
    follow = a.get("_strategy_followup") or followups(a)[0]
    definitions = {
        "storage_setup": q("storage_setup", "Do you have a safe place to store it?", "নিরাপদে রাখার জায়গা আছে?", "choice",
                           opts(("yes", "Yes, I have a place", "হ্যাঁ, জায়গা আছে"), ("no", "I need storage first", "আগে রাখার ব্যবস্থা দরকার"),
                                ("unsure", "I need to check", "যাচাই করতে হবে"))),
        "demand_signal": q("demand_signal", "What makes you think customers need more?", "ক্রেতার চাহিদা বাড়ছে মনে হওয়ার কারণ?", "choice",
                           opts(("orders", "I have missed orders", "অর্ডার ফিরিয়ে দিতে হয়েছে"), ("sales", "My sales have been growing", "বিক্রি বাড়ছে"),
                                ("guess", "It is an idea to test", "ছোট করে পরীক্ষা করতে চাই"))),
        "priority": q("priority", "What worries you most?", "কোন চিন্তাটা সবচেয়ে বেশি?", "choice",
                      opts(("money", "Keeping enough money for bills", "বিল দেওয়ার টাকা রাখা"), ("waste", "Stock going unused or spoiling", "পণ্য পড়ে থাকা বা নষ্ট হওয়া"),
                           ("supplier", "Getting a fair supplier deal", "সরবরাহকারীর কাছ থেকে ভালো শর্ত পাওয়া"))),
    }
    qs.append({**definitions[follow], "selected_by": a.get("_strategy_question_source", "rules")})
    if follow not in a:
        return qs
    today = date.fromisoformat(snap["today"])
    qs.append(q("review_date", "When would you like to come back to this?", "কবে আবার এটি দেখবেন?", "date",
                options=[{"value": (today + timedelta(days=n)).isoformat(), "label": tr(en, bn)} for n, en, bn in
                         [(1, "Tomorrow", "আগামীকাল"), (7, "In a week", "এক সপ্তাহ পরে"), (30, "In a month", "এক মাস পরে")]],
                optional=True))
    if a.get("_strategy_depth") == "costs":
        # Exact figures are still required for a complete comparison, after an explicit choice.
        qs += [x for x in detail_questions(a, snap) if x["id"] not in {y["id"] for y in qs}]
    return qs


def starter_result(a):
    if a.get("storage_setup") in ("no", "unsure"):
        reason = tr("Check storage before buying a larger batch.", "বেশি কেনার আগে রাখার ব্যবস্থা যাচাই করুন।")
        action = tr("Ask about usable space, power backup and product-specific storage life.", "ব্যবহারযোগ্য জায়গা, বিকল্প বিদ্যুৎ ও পণ্যের সংরক্ষণকাল জিজ্ঞাসা করুন।")
    elif a.get("priority") == "money":
        reason = tr("Keep bill money aside before committing to a bigger purchase.", "বড় কেনাকাটার আগে বিলের টাকা আলাদা রাখুন।")
        action = tr("Get a smaller-order quote and a staged-delivery quote to compare.", "কম পরিমাণ ও ধাপে ধাপে সরবরাহের দাম তুলনা করুন।")
    elif a.get("demand_signal") == "guess":
        reason = tr("Test demand before adding equipment.", "যন্ত্র বাড়ানোর আগে চাহিদা পরীক্ষা করুন।")
        action = tr("Track missed orders for a week or try a small batch first.", "এক সপ্তাহ ফিরিয়ে দেওয়া অর্ডার লিখে রাখুন বা ছোট চালান পরীক্ষা করুন।")
    else:
        reason = tr("Start with one written quote and a small, reversible step.", "একটি লিখিত দাম ও ছোট, বদলানো যায় এমন পদক্ষেপ দিয়ে শুরু করুন।")
        action = tr("Compare a smaller purchase with the full order before committing.", "সিদ্ধান্তের আগে ছোট কেনাকাটার সঙ্গে পুরো অর্ডার তুলনা করুন।")
    return {"status": "strategy_start", "preliminary": True, "metrics": {}, "reason": reason,
            "next_action": action, "review_required": True, "regulatory_status": "needs_review",
            "assumption": tr("An initial direction, not a savings or affordability assessment.", "এটি শুরুর দিকনির্দেশনা; সাশ্রয় বা সামর্থ্যের হিসাব নয়।"),
            "checklist": [{"label": tr("Before a larger purchase", "বেশি কেনার আগে"),
                           "detail": tr("Check actual costs, storage and the current rules for this item and location.",
                                        "আসল খরচ, রাখার ব্যবস্থা ও এই পণ্য ও স্থানের বর্তমান নিয়ম যাচাই করুন।")}]}
