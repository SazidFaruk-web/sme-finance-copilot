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
    # The rest of the published series, so an owner can add any of them to their own price list.
    "Gourd (bitter)": tr("Bitter gourd", "করলা", "苦瓜"),
    "Hyacinth (sim)": tr("Hyacinth beans (shim)", "শিম", "扁豆"),
    "Lemon (medium size)": tr("Lemon", "লেবু", "柠檬"),
    "Turmeric (powder, Fresh)": tr("Turmeric powder", "হলুদ গুঁড়া", "姜黄粉"),
    "Meat (chicken, sonali)": tr("Sonali chicken", "সোনালি মুরগি", "索纳利鸡"),
    "Milk": tr("Milk (loose)", "দুধ (খোলা)", "散装牛奶"),
    "Milk (cow, pasteurized)": tr("Pasteurised milk", "পাস্তুরিত দুধ", "巴氏杀菌牛奶"),
    "Rice (Gazi)": tr("Rice (Gazi)", "চাল (গাজী)", "大米（Gazi）"),
    "Rice (Nurjahan)": tr("Rice (Nurjahan)", "চাল (নূরজাহান)", "大米（Nurjahan）"),
    "Rice (BRRI-28)": tr("Rice (BRRI-28)", "চাল (ব্রি-২৮)", "大米（BRRI-28）"),
    "Rice (BRRI-29)": tr("Rice (BRRI-29)", "চাল (ব্রি-২৯)", "大米（BRRI-29）"),
    "Rice (BRRI-49)": tr("Rice (BRRI-49)", "চাল (ব্রি-৪৯)", "大米（BRRI-49）"),
    "Rice (Kajla)": tr("Rice (Kajla)", "চাল (কাজলা)", "大米（Kajla）"),
    "Oranges (malta)": tr("Malta orange", "মাল্টা", "马尔他橙"),
    "Apples (royal gala)": tr("Apple", "আপেল", "苹果"),
    "Bananas (green)": tr("Green banana", "কাঁচা কলা", "青香蕉"),
    "Bananas (ripe)": tr("Ripe banana", "পাকা কলা", "熟香蕉"),
    "Papaya (green)": tr("Green papaya", "কাঁচা পেঁপে", "青木瓜"),
    "Pumpkin": tr("Pumpkin", "মিষ্টি কুমড়া", "南瓜"),
    "Beans (mung, large grain)": tr("Mung beans", "মুগ ডাল", "绿豆"),
    "Cabbage": tr("Cabbage", "বাঁধাকপি", "卷心菜"),
    "Carrots": tr("Carrot", "গাজর", "胡萝卜"),
    "Cauliflower": tr("Cauliflower", "ফুলকপি", "花椰菜"),
    "Eggplants": tr("Eggplant (brinjal)", "বেগুন", "茄子"),
    "Cucumber (short, khira)": tr("Cucumber", "শসা (খিরা)", "黄瓜"),
    "Gourd (bottle)": tr("Bottle gourd", "লাউ", "葫芦瓜"),
    "Snake gourd": tr("Snake gourd", "চিচিঙ্গা", "蛇瓜"),
    "Spinach (red)": tr("Red spinach", "লাল শাক", "红苋菜"),
    "Spinach (malabar)": tr("Malabar spinach", "পুঁই শাক", "木耳菜"),
    "Chili (whole, dry, Indian Teja)": tr("Dry chilli", "শুকনা মরিচ", "干辣椒"),
    "Eggs (white)": tr("Eggs (white)", "সাদা ডিম", "白皮鸡蛋"),
    "Fish (live, tilapia)": tr("Tilapia fish", "তেলাপিয়া মাছ", "罗非鱼"),
    'Fish (dry, belt 10-12")': tr("Dried ribbon fish", "ছুরি শুঁটকি", "带鱼干"),
    "Dishwashing liquid": tr("Dishwashing liquid", "থালাবাসন ধোয়ার তরল", "洗洁精"),
    "Firewood": tr("Firewood", "জ্বালানি কাঠ", "柴火"),
    "Fuel (kerosene)": tr("Kerosene", "কেরোসিন", "煤油"),
}

# What a business name or description says about what it buys. Used when the model is unavailable, and to
# check the model's choice is not empty. Matched on lowercase words in English, Banglish and Bangla.
KEYWORD_BASKETS = [
    (("cake", "bakery", "baker", "pastry", "sweet", "mishti", "misti", "confection", "biscuit", "dessert",
      "কেক", "বেকারি", "মিষ্টি", "পেস্ট্রি"),
     ["Wheat flour", "Sugar", "Eggs (brown)", "Eggs (white)", "Milk (powder)", "Milk (cow, pasteurized)",
      "Oil (soybean, fortified)", "Fuel (gas)"]),
    (("tea", "cafe", "coffee", "চা স্টল", "চায়ের", "ক্যাফে"),
     ["Sugar", "Milk (powder)", "Milk (cow, pasteurized)", "Ginger (imported)", "Fuel (gas)", "Bananas (ripe)", "Eggs (brown)"]),
    (("biryani", "kitchen", "food", "restaurant", "hotel", "catering", "tiffin", "lunch", "খাবার", "রান্না"),
     ["Meat (chicken, broiler)", "Rice (coarse)", "Oil (soybean, fortified)", "Onions (imported, India)", "Potatoes (Holland, white)",
      "Eggs (brown)", "Fuel (gas)", "Ginger (imported)"]),
    (("fruit", "ফল"), ["Apples (royal gala)", "Oranges (malta)", "Bananas (ripe)", "Papaya (green)", "Lemon (medium size)"]),
    (("vegetable", "sabji", "sobji", "সবজি", "kacha bazar"),
     ["Potatoes (Holland, white)", "Onions (imported, India)", "Tomatoes (red)", "Eggplants", "Cabbage", "Cauliflower",
      "Carrots", "Chili (green)"]),
    (("fish", "mach", "মাছ"), ["Fish (live, pangasius)", "Fish (live, tilapia)", 'Fish (dry, belt 10-12")', "Oil (soybean, fortified)"]),
    (("chicken", "poultry", "murgi", "মুরগি", "egg", "ডিম"),
     ["Meat (chicken, broiler)", "Meat (chicken, sonali)", "Eggs (brown)", "Eggs (white)"]),
    (("meat", "beef", "butcher", "mangsho", "মাংস"), ["Meat (beef)", "Meat (chicken, broiler)", "Onions (imported, India)", "Ginger (imported)", "Garlic (imported, China)"]),
    (("dairy", "milk", "doodh", "dudh", "দুধ"), ["Milk", "Milk (cow, pasteurized)", "Milk (powder)", "Sugar"]),
]


# Goods with no public price series at all. For these shops the drawer says so and follows running and living costs
# instead of guessing (the 2026-10-19 persona test got soap and toothpaste for a bookshop and a phone shop).
NO_PRICE_WORDS = ("phone", "mobile", "electronic", "gadget", "accessor", "charger", "computer", "laptop", "book", "stationer",
                  "cloth", "fashion", "garment", "t-shirt", "panjabi", "saree", "shoe", "cosmetic", "jewel", "furniture",
                  "hardware", "toy", "watch", "পোশাক", "বই", "মোবাইল")
RUNNING_COSTS = ["Fuel (petrol)", "Fuel (diesel)", "Fuel (gas)", "Rice (coarse)", "Oil (soybean, fortified)", "Sugar"]
NO_PRICE_NOTE = tr("Public market prices cover food, household goods and fuel, not what your shop sells. These are running "
                   "and living costs that still affect your business and your customers.",
                   "প্রকাশিত বাজারদরে খাবার, গৃহস্থালি পণ্য ও জ্বালানির দাম থাকে, আপনার দোকানের পণ্যের নয়। এগুলো চলতি ও জীবনযাত্রার খরচ।",
                   "公开市场价格只包括食品、日用品和燃料，不包括您店里卖的商品。这些是仍会影响您生意的经营和生活成本。")


def goods_without_prices(*texts: str) -> bool:
    """True when the business sells things no public series covers and none of the food/household words match."""
    blob = " ".join(t or "" for t in texts).lower()
    return not keyword_basket(*texts) and any(w in blob for w in NO_PRICE_WORDS)


def keyword_basket(*texts: str) -> list[str]:
    """Items suggested by words in the business name or description, in order; empty when nothing matches."""
    blob = " ".join(t or "" for t in texts).lower()
    # Latin words match whole words or their start ("bakery" in "bakeryhouse"); Bangla words match anywhere.
    hit = lambda w: (w in blob) if not w.isascii() else re.search(r"\b" + re.escape(w.strip()), blob) is not None  # noqa: E731
    out: list[str] = []
    for words, items in KEYWORD_BASKETS:
        if any(hit(w) for w in words):
            out += [i for i in items if i not in out]
    return out

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
