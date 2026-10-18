"""Which public price series matter to which kind of business, and how to name them.

Keys are WFP commodity names exactly as published. Each basket lists the items a business of that type buys
to sell or to run the business, in order of importance. Labels are reviewed text in English, Bangla and Chinese.
"""
from __future__ import annotations

import re


def tr(en: str, bn: str, zh: str) -> dict[str, str]:
    return {"en": en, "bn": bn, "zh": zh}


ITEMS = {
    "Rice (coarse)": tr("Rice (coarse)", "মোটা চাল", "粗米"),
    "Wheat flour": tr("Wheat flour (atta)", "আটা", "面粉"),
    "Lentils (masur)": tr("Lentils (masoor)", "মসুর ডাল", "红扁豆"),
    "Oil (soybean, fortified)": tr("Soybean oil", "সয়াবিন তেল", "大豆油"),
    "Oil (palm)": tr("Palm oil", "পাম তেল", "棕榈油"),
    "Oil (mustard)": tr("Mustard oil", "সরিষার তেল", "芥子油"),
    "Sugar": tr("Sugar", "চিনি", "白糖"),
    "Onions (imported, India)": tr("Onion (Indian)", "পেঁয়াজ (ভারতীয়)", "洋葱（印度进口）"),
    "Onions (imported, China)": tr("Onion (Chinese)", "পেঁয়াজ (চীনা)", "洋葱（中国进口）"),
    "Garlic (imported, China)": tr("Garlic (Chinese)", "রসুন (চীনা)", "大蒜（中国进口）"),
    "Ginger (imported)": tr("Ginger (imported)", "আদা (আমদানি)", "生姜（进口）"),
    "Potatoes (Holland, white)": tr("Potato", "আলু", "土豆"),
    "Eggs (brown)": tr("Eggs (brown)", "লাল ডিম", "红皮鸡蛋"),
    "Meat (chicken, broiler)": tr("Broiler chicken", "ব্রয়লার মুরগি", "肉鸡"),
    "Meat (beef)": tr("Beef", "গরুর মাংস", "牛肉"),
    "Fish (live, pangasius)": tr("Pangas fish", "পাঙ্গাস মাছ", "巴沙鱼"),
    "Chili (green)": tr("Green chilli", "কাঁচা মরিচ", "青辣椒"),
    "Tomatoes (red)": tr("Tomato", "টমেটো", "番茄"),
    "Chickpeas": tr("Chickpeas", "ছোলা", "鹰嘴豆"),
    "Salt (iodized, Molla)": tr("Iodised salt", "আয়োডিনযুক্ত লবণ", "加碘盐"),
    "Milk (powder)": tr("Powdered milk", "গুঁড়া দুধ", "奶粉"),
    "Bathing soap": tr("Bathing soap", "গায়ে মাখা সাবান", "香皂"),
    "Handwash soap": tr("Handwash", "হ্যান্ডওয়াশ", "洗手液"),
    "Laundry detergent": tr("Laundry detergent", "কাপড় ধোয়ার পাউডার", "洗衣粉"),
    "Toothpaste": tr("Toothpaste", "টুথপেস্ট", "牙膏"),
    "Toilet paper": tr("Toilet paper", "টয়লেট পেপার", "卫生纸"),
    "Sanitary pads": tr("Sanitary pads", "স্যানিটারি প্যাড", "卫生巾"),
    "Fuel (diesel)": tr("Diesel", "ডিজেল", "柴油"),
    "Fuel (petrol)": tr("Petrol", "পেট্রোল", "汽油"),
    "Fuel (gas)": tr("Cooking gas (LPG)", "রান্নার গ্যাস (এলপিজি)", "液化气"),
}

STAPLES = ["Rice (coarse)", "Lentils (masur)", "Oil (soybean, fortified)", "Sugar", "Onions (imported, India)",
           "Potatoes (Holland, white)", "Eggs (brown)", "Fuel (diesel)"]

BASKETS = {
    "retail": ["Rice (coarse)", "Lentils (masur)", "Oil (soybean, fortified)", "Sugar", "Onions (imported, India)",
               "Potatoes (Holland, white)", "Eggs (brown)", "Wheat flour", "Salt (iodized, Molla)", "Bathing soap",
               "Laundry detergent"],
    "pharmacy_grocery": ["Rice (coarse)", "Lentils (masur)", "Oil (soybean, fortified)", "Sugar", "Wheat flour",
                         "Milk (powder)", "Salt (iodized, Molla)", "Toothpaste", "Bathing soap", "Handwash soap",
                         "Sanitary pads", "Toilet paper"],
    "restaurant_food": ["Rice (coarse)", "Meat (chicken, broiler)", "Oil (soybean, fortified)", "Onions (imported, India)",
                        "Potatoes (Holland, white)", "Eggs (brown)", "Fish (live, pangasius)", "Meat (beef)",
                        "Chili (green)", "Lentils (masur)", "Garlic (imported, China)", "Ginger (imported)",
                        "Tomatoes (red)", "Fuel (gas)"],
    "wholesale_trading": ["Rice (coarse)", "Wheat flour", "Lentils (masur)", "Sugar", "Oil (palm)",
                          "Oil (soybean, fortified)", "Onions (imported, India)", "Garlic (imported, China)",
                          "Potatoes (Holland, white)", "Chickpeas"],
    "service_salon": ["Bathing soap", "Handwash soap", "Laundry detergent", "Toilet paper", "Toothpaste", "Fuel (petrol)"],
    # No public series for fabric or trims: show running costs and the staples behind workers' living costs.
    "garments_trims": ["Fuel (diesel)", "Fuel (gas)", "Rice (coarse)", "Oil (soybean, fortified)", "Lentils (masur)", "Sugar"],
    "other": STAPLES,
}

NOTES = {
    "garments_trims": tr("Public price data for fabric and trims is not available. These items affect your running costs "
                         "and your workers' cost of living.",
                         "কাপড় ও ট্রিমসের প্রকাশিত দামের তথ্য পাওয়া যায় না। এই পণ্যগুলো আপনার চলতি খরচ ও "
                         "কর্মীদের জীবনযাত্রার খরচে প্রভাব ফেলে।",
                         "目前没有面料和辅料的公开价格数据。这些商品会影响您的经营成本和员工的生活成本。"),
    "other": tr("Everyday items most businesses and their customers buy.",
                "বেশিরভাগ ব্যবসা ও ক্রেতারা যে নিত্যপণ্য কেনেন।",
                "大多数商家和顾客都会购买的日常商品。"),
}

UNITS = {
    "KG": tr("per kg", "প্রতি কেজি", "每公斤"),
    "L": tr("per litre", "প্রতি লিটার", "每升"),
    "1 piece": tr("each", "প্রতিটি", "每个"),
    "12 KG": tr("per 12 kg cylinder", "প্রতি ১২ কেজি সিলিন্ডার", "每 12 公斤一罐"),
    "500 G": tr("per 500 g", "প্রতি ৫০০ গ্রাম", "每 500 克"),
    "10 pcs": tr("per pack of 10", "প্রতি ১০টির প্যাকেট", "每包 10 片"),
    "1 Roll": tr("per roll", "প্রতি রোল", "每卷"),
}

# Common spellings that differ from the WFP district names (compared as lowercase letters only).
DISTRICT_ALIASES = {
    "dhakasouth": "dhaka", "dhakanorth": "dhaka", "chattogram": "chittagong", "cumilla": "comilla",
    "jashore": "jessore", "barishal": "barisal", "bogura": "bogra", "jhalakathi": "jhalokati",
    "brahmanbaria": "brahamanbaria", "coxsbazar": "coxsbazar", "moulvibazar": "maulvibazar",
}


def basket(business_type: str | None) -> tuple[str, list[str]]:
    key = (business_type or "other").split(":", 1)[0]
    key = key if key in BASKETS else "other"
    return key, BASKETS[key]


def district_key(name: str | None) -> str:
    k = re.sub(r"[^a-z]", "", (name or "").lower())
    return DISTRICT_ALIASES.get(k, k)


def label(commodity: str) -> dict[str, str]:
    return ITEMS.get(commodity) or tr(commodity, commodity, commodity)


def unit_label(unit: str) -> dict[str, str]:
    return UNITS.get(unit) or tr(unit, unit, unit)
