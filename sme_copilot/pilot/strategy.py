"""Longer-term planning: bounded ideas, owner evidence, deterministic scenarios.

No purchase, borrowing or regulatory clearance is executed by this module.
"""
import re
from math import ceil
from decimal import Decimal

from .calculations import money
from .definitions import q, opts, tr


PLAN_TYPES = opts(
    ("seasonal", "Buy ahead for a season", "মৌসুমের জন্য আগে কিনুন"),
    ("bulk", "Compare a bulk purchase", "বেশি পরিমাণে কেনা তুলনা করুন"),
    ("equipment", "Add equipment", "নতুন যন্ত্র যোগ করুন"),
)


def detail_questions(a, snap):
    initial = [
        q("plan_type", "What would you like to plan?", "কী পরিকল্পনা করতে চান?", "choice", PLAN_TYPES),
    ]
    if a.get("plan_type") not in ("seasonal", "bulk", "equipment"):
        return initial + [q("review_date", "When should you review this plan?", "কবে পরিকল্পনাটি আবার দেখবেন?", "date")]
    equipment = a["plan_type"] == "equipment"
    common = [
        q("item", "Which item, and in what unit or form?", "কোন পণ্য, কী এককে বা অবস্থায়?", "text",
          why=tr("For example: mango pulp in kg, sugar in kg, or one freezer. Compare the same form and unit.",
                 "যেমন: কেজিতে আমের পাল্প, কেজিতে চিনি, বা একটি ফ্রিজার। একই অবস্থা ও এককে তুলনা করুন।")),
        q("evidence", "What have customers needed that you could not supply?", "ক্রেতার কোন চাহিদা মেটাতে পারেননি?", "text",
          why=tr("Use sales records, missed orders or a small test. An estimate is an assumption, not proof of demand.",
                 "বিক্রির হিসাব, ফেরত যাওয়া অর্ডার বা ছোট পরীক্ষার তথ্য দিন। অনুমান চাহিদার প্রমাণ নয়।")),
        q("buy_date", "When would you buy it?", "কবে কিনতে চান?", "date"),
        q("months", "How many months should this plan cover?", "কত মাসের পরিকল্পনা?", "number", min=1, max=36),
        q("quantity", "How many units would you buy?", "কত একক কিনবেন?", "decimal", min=.01, max=100000),
        q("unit_cost", "Quoted price per unit?", "প্রতি এককের প্রস্তাবিত দাম?", min=.01),
        q("quote_source", "Who quoted this price, and when?", "কে ও কবে এই দাম বলেছেন?", "text"),
        q("setup", "Delivery, preparation and installation cost in total?", "পরিবহন, প্রস্তুতি ও বসানোর মোট খরচ?"),
    ]
    if equipment:
        branch = [
            q("needed_capacity", "Capacity needed at your busiest time?", "সবচেয়ে ব্যস্ত সময়ে কত ধারণক্ষমতা দরকার?", "decimal",
              why=tr("Use one unit throughout, such as litres of storage or drinks per hour. Base this on observed or evidenced demand.",
                     "সবখানে একই একক দিন, যেমন লিটার বা ঘণ্টায় পানীয়। দেখা বা প্রমাণিত চাহিদার ভিত্তিতে বলুন।")),
            q("current_capacity", "Usable capacity you already have, in the same unit?", "একই এককে এখন ব্যবহারযোগ্য ধারণক্ষমতা কত?", "decimal"),
            q("added_capacity", "Extra capacity from each new machine, in the same unit?", "একই এককে প্রতিটি নতুন যন্ত্রের বাড়তি ধারণক্ষমতা কত?", "decimal", min=.01),
            q("extra_receipts", "Extra money received each month with this equipment?", "এই যন্ত্রে মাসে বাড়তি কত টাকা হাতে আসবে?"),
            q("extra_costs", "Extra monthly costs, including stock, power, upkeep and finance?", "পণ্য, বিদ্যুৎ, রক্ষণাবেক্ষণ ও অর্থায়নসহ মাসিক বাড়তি খরচ?"),
            q("slow_receipts", "Extra monthly receipts if demand is lower?", "চাহিদা কম হলে মাসে বাড়তি কত টাকা আসবে?"),
            q("capacity_check", "What capacity, space and power would this add?", "কত ধারণক্ষমতা, জায়গা ও বিদ্যুৎ লাগবে?", "text"),
        ]
    else:
        branch = [
            q("later_price", "Price per unit if you keep buying as needed?", "দরকারমতো কিনলে প্রতি এককের দাম?"),
            q("later_source", "What supports that later price?", "পরের দামের অনুমানের ভিত্তি কী?", "text"),
            q("monthly_use", "How many units will you use each month?", "মাসে কত একক ব্যবহার করবেন?", "decimal"),
            q("existing_stock", "How many usable units do you already have?", "এখন কত ব্যবহারযোগ্য একক আছে?", "decimal"),
            q("capacity", "How many extra units can you safely store?", "নিরাপদে আরও কত একক রাখা যাবে?", "decimal"),
            q("safe_months", "Verified storage life in months for this exact product?", "এই পণ্যের যাচাই করা সংরক্ষণকাল কত মাস?", "number", min=1, max=36),
            q("loss_percent", "What percentage could be lost or spoiled?", "কত শতাংশ নষ্ট বা অপচয় হতে পারে?", "decimal", max=100),
            q("monthly_storage", "Extra monthly storage cost, including power and backup?", "বিদ্যুৎ ও বিকল্প ব্যবস্থাসহ মাসিক বাড়তি সংরক্ষণ খরচ?"),
            q("finance_cost", "Total financing or tied-up-money cost for this plan?", "এই পরিকল্পনায় ঋণ বা টাকা আটকে থাকার মোট খরচ?"),
        ]
    return initial + common + branch + [
        q("cash", "How much business money is available now?", "এখন ব্যবসার জন্য কত টাকা আছে?", suggestion=snap["cash"]),
        q("commitments", "Money to protect for bills, debts and home over this period?", "এই সময়ে বিল, ঋণ ও সংসারের জন্য কত টাকা রাখতে হবে?",
          why=tr("Exclude this plan's extra costs. Include existing debts and essential payments; we do not assume future sales will cover them.",
                 "এই পরিকল্পনার বাড়তি খরচ বাদ দিন। চলমান ঋণ ও জরুরি পেমেন্ট ধরুন; ভবিষ্যৎ বিক্রি থেকে এগুলো মিটবে ধরে নেওয়া হয় না।")),
        q("reserve", "Extra money you want to keep untouched?", "আর কত টাকা আলাদা রাখতে চান?"),
        q("storage_plan", "How will you handle storage, breakdowns and quality checks?", "সংরক্ষণ, যন্ত্র নষ্ট হওয়া ও মান যাচাই কীভাবে করবেন?", "text",
          why=tr("A freezer alone does not establish safe shelf life. Check the product form, packaging, cold chain, power cuts and safe disposal.",
                 "শুধু ফ্রিজার থাকলেই নিরাপদ সংরক্ষণকাল জানা যায় না। পণ্যের অবস্থা, প্যাকেট, তাপমাত্রা, বিদ্যুৎ বিভ্রাট ও নষ্ট পণ্য ফেলার ব্যবস্থা যাচাই করুন।")),
        q("rule_notes", "Any licence or storage advice already received?", "লাইসেন্স বা মজুতের কোনো পরামর্শ পেয়েছেন?", "text",
          why=tr("Record the authority, date and reference if known. This is evidence for review, not automatic legal clearance.",
                 "জানা থাকলে কর্তৃপক্ষ, তারিখ ও সূত্র লিখুন। এটি যাচাইয়ের তথ্য, আইনি অনুমোদন নয়।")),
        q("review_date", "When should you review this plan?", "কবে পরিকল্পনাটি আবার দেখবেন?", "date"),
    ]


def strategy_questions(a, snap):
    if a.get("_strategy_flow") == "guided":
        from .strategy_guide import guide_questions
        return guide_questions(a, snap)
    return detail_questions(a, snap)


def assess(a, today):
    if a.get("_strategy_flow") == "guided" and a.get("_strategy_depth") != "costs":
        from .strategy_guide import starter_result
        return starter_result(a)
    required = [x["id"] for x in detail_questions(a, {"cash": 0})
                if x["id"] not in ("rule_notes",)]
    missing = [k for k in required if a.get(k) is None or a.get(k) == ""]
    base = {"review_required": True, "regulatory_status": "needs_review",
            "assumption": tr("Based on your estimates. Future prices, demand and savings are not guaranteed.",
                             "আপনার অনুমানের ভিত্তিতে। ভবিষ্যৎ দাম, চাহিদা ও সাশ্রয় নিশ্চিত নয়।"),
            "checklist": [
                {"label": tr("Storage and quality", "সংরক্ষণ ও মান"),
                 "detail": tr("Check product-specific shelf life, packaging, temperature, power backup and usable capacity.",
                              "পণ্যভেদে সংরক্ষণকাল, প্যাকেট, তাপমাত্রা, বিকল্প বিদ্যুৎ ও ব্যবহারযোগ্য ধারণক্ষমতা যাচাই করুন।")},
                {"label": tr("Current rules for your business", "আপনার ব্যবসার বর্তমান নিয়ম"),
                 "detail": tr("A local reviewer must check the commodity, amount, storage duration, location, licence and current orders. No universal stock limit is assumed.",
                              "স্থানীয় পর্যালোচককে পণ্য, পরিমাণ, সময়, স্থান, লাইসেন্স ও বর্তমান আদেশ যাচাই করতে হবে। সবার জন্য এক মজুতসীমা ধরা হয়নি।")},
            ]}
    if a.get("plan_type") not in ("seasonal", "bulk", "equipment"):
        missing.append("plan_type")
    if a.get("buy_date") and a["buy_date"] < today.isoformat():
        missing.append("buy_date")
    if missing:
        return {**base, "status": "need_information", "missing": sorted(set(missing)), "metrics": {}}
    d = lambda k: Decimal(str(a[k]))
    months, qty = d("months"), d("quantity")
    upfront = qty * d("unit_cost") + d("setup")
    available = d("cash") - d("commitments") - d("reserve")
    equipment = a["plan_type"] == "equipment"
    reasons = []
    if equipment:
        if qty != qty.to_integral_value() or d("slow_receipts") > d("extra_receipts"):
            return {**base, "status": "need_information", "metrics": {},
                    "missing": ["quantity_or_slower_receipts"]}
        ongoing = months * d("extra_costs")
        benefit = months * (d("extra_receipts") - d("extra_costs")) - upfront
        slow = months * (d("slow_receipts") - d("extra_costs")) - upfront
        payback = upfront / (d("extra_receipts") - d("extra_costs")) if d("extra_receipts") > d("extra_costs") else None
        needed = ceil(max(Decimal(0), d("needed_capacity") - d("current_capacity")) / d("added_capacity"))
        extra = {"equipment_units_needed": needed, "payback_months": money(payback) if payback is not None else None}
        if qty > needed:
            reasons.append(tr("Fewer machines cover the capacity need you entered. Ask for a smaller quote.",
                              "আপনার দেওয়া চাহিদা কম যন্ত্রেই মেটে। কম যন্ত্রের দাম জিজ্ঞাসা করুন।"))
        elif qty < needed:
            reasons.append(tr("This quantity does not cover the capacity gap you entered.",
                              "এই সংখ্যক যন্ত্রে আপনার দেওয়া ধারণক্ষমতার ঘাটতি মেটে না।"))
    else:
        ongoing = months * d("monthly_storage") + d("finance_cost")
        usable = qty * (1 - d("loss_percent") / 100)
        demand = max(Decimal(0), months * d("monthly_use") - d("existing_stock"))
        used = min(usable, demand)
        slow_used = min(usable, max(Decimal(0), months * d("monthly_use") / 2 - d("existing_stock")))
        benefit = used * d("later_price") - upfront - ongoing
        slow = slow_used * d("later_price") - upfront - ongoing
        extra = {"usable_units": money(usable), "unused_units": money(usable - used),
                 "effective_unit_cost": money((upfront + ongoing) / used) if used > 0 else None}
        if qty > d("capacity"):
            reasons.append(tr("This batch exceeds your available storage.", "এই চালান রাখার মতো জায়গা নেই।"))
        if months > d("safe_months"):
            reasons.append(tr("The plan lasts longer than the storage life you entered.", "আপনার দেওয়া সংরক্ষণকালের চেয়ে পরিকল্পনার সময় বেশি।"))
    left = available - upfront - ongoing
    if left < 0:
        reasons.append(tr("This leaves too little for protected payments and your reserve.", "জরুরি পেমেন্ট ও আলাদা রাখার টাকা কম পড়বে।"))
    if benefit <= 0:
        reasons.append(tr("Expected benefits do not cover the full cost in this period.", "এই সময়ে সম্ভাব্য সুবিধা পুরো খরচ তুলতে পারছে না।"))
    elif slow < 0:
        reasons.append(tr("The slower-demand case loses money over this period.", "চাহিদা কম হলে এই সময়ে ক্ষতি হবে।"))
    return {**base, "status": "strategy_rethink" if reasons else "strategy_review",
            "reason": reasons[0] if reasons else tr("The estimate is promising. Check the quotes, demand and rules before committing.",
                                                   "অনুমানটি আশাব্যঞ্জক। সিদ্ধান্তের আগে দাম, চাহিদা ও নিয়ম যাচাই করুন।"),
            "reasons": reasons, "metrics": {"needed_now": money(upfront),
                "protected_money_left": money(left), "plan_benefit": money(benefit),
                "slow_benefit": money(slow), "running_cost": money(ongoing), **extra},
            "scenarios": [
                {"label": tr("Your estimate", "আপনার অনুমান"), "value": money(benefit)},
                {"label": tr("Lower demand", "কম চাহিদা"), "value": money(slow)},
                {"label": tr("Keep buying as needed" if not equipment else "Keep current equipment",
                             "দরকারমতো কিনতে থাকুন" if not equipment else "বর্তমান যন্ত্র রাখুন"), "value": 0},
            ],
            "calculation": tr(
                "Incremental receipts minus extra running costs and the entire purchase cost, over your chosen period. Lower demand uses your lower receipts. All extra costs are reserved upfront; no resale value is assumed." if equipment else
                "Cost of buying only the usable units needed later, minus the entire batch, preparation, storage and financing costs. Lower demand halves total usage; existing stock is used first. Unsold or spoiled units have no cash value. All storage costs are reserved upfront.",
                "নির্বাচিত সময়ে বাড়তি আয় থেকে বাড়তি চলতি খরচ ও পুরো ক্রয়মূল্য বাদ। কম চাহিদায় আপনার কম আয়ের অনুমান ব্যবহার করা হয়েছে। সব বাড়তি খরচ আগে আলাদা রাখা; পুনর্বিক্রয়মূল্য ধরা হয়নি।" if equipment else
                "পরে প্রয়োজনীয় ব্যবহারযোগ্য পণ্য কেনার খরচ থেকে পুরো চালান, প্রস্তুতি, সংরক্ষণ ও অর্থায়ন খরচ বাদ। কম চাহিদায় মোট ব্যবহার অর্ধেক, পুরোনো পণ্য আগে ব্যবহার। অবিক্রীত বা নষ্ট পণ্যের নগদ মূল্য ধরা হয়নি। সংরক্ষণ খরচ আগে আলাদা রাখা।")}


def ideas(business):
    """Only approved topics reach the optional local model, never raw business text."""
    from .question_model import select_id
    text = f"{business.sector} {(business.prefs or {}).get('about', '')} {business.name}"
    food = bool(re.search(r"juice|fruit|food|restaurant|grocery|mango|জুস|ফল|খাবার|মুদি|আমের", text, re.I))
    candidates = ["seasonal", "bulk", "equipment"] if food else ["bulk", "equipment", "seasonal"]
    chosen = select_id({"business_category": "food_or_drink" if food else "other",
                        "purpose": "choose a planning topic; no purchase advice"}, candidates)
    order = [chosen] + [k for k in candidates if k != chosen] if chosen else candidates
    return {"source": "model" if chosen else "rules", "food_context": food,
            "juice_context": bool(re.search(r"juice|জুস|শরবত", text, re.I)),
            "business": business.name, "description": (business.prefs or {}).get("about") or business.sector,
            "ideas": [{"id": key, "title": next(x["label"] for x in PLAN_TYPES if x["value"] == key)}
                      for key in order]}
