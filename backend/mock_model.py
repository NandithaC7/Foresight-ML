"""
mock_model.py
=================
There is no trained model wired in yet. This module simulates what the real
pipeline (YOLOv8 detection -> ViT classification/regression -> U-Net segmentation)
will eventually return, so the API and frontend can be built and demoed end to end.

To go live later: replace `simulate_analysis()`'s body with real inference calls,
but KEEP the same return shape (list of dicts with these exact keys) so nothing
else in the backend or frontend needs to change.
"""

import random

CROPS = ["Guava", "Carrot", "Tomato", "Indian Gooseberry", "Banana", "Mango"]

# Approximate nutrition values per 100g — for the demo nutrition-facts feature.
NUTRITION = {
    "Guava": {
        "calories": 68, "carbs": "14g", "fiber": "5.4g", "vitaminC": "228mg", "potassium": "417mg",
        "fact": "One guava can contain over four times the vitamin C of an orange.",
    },
    "Carrot": {
        "calories": 41, "carbs": "10g", "fiber": "2.8g", "vitaminC": "5.9mg", "potassium": "320mg",
        "fact": "The orange color comes from beta-carotene, which your body converts to vitamin A.",
    },
    "Tomato": {
        "calories": 18, "carbs": "3.9g", "fiber": "1.2g", "vitaminC": "14mg", "potassium": "237mg",
        "fact": "Botanically a fruit, tomatoes are rich in lycopene, an antioxidant linked to heart health.",
    },
    "Indian Gooseberry": {
        "calories": 44, "carbs": "10g", "fiber": "4.3g", "vitaminC": "600mg", "potassium": "198mg",
        "fact": "Amla has one of the highest natural vitamin C concentrations of any fruit.",
    },
    "Banana": {
        "calories": 89, "carbs": "23g", "fiber": "2.6g", "vitaminC": "8.7mg", "potassium": "358mg",
        "fact": "Bananas release ethylene gas as they ripen, which speeds up ripening in nearby produce.",
    },
    "Mango": {
        "calories": 60, "carbs": "15g", "fiber": "1.6g", "vitaminC": "36mg", "potassium": "168mg",
        "fact": "Mangoes are a strong source of vitamin A as well as C, supporting skin and eye health.",
    },
}

TIPS = [
    "Store bananas away from other produce — the ethylene gas they release speeds up ripening nearby.",
    "Keep tomatoes at room temperature, not the fridge — cold damages their texture and flavor.",
    "Guavas and mangoes ripen faster near sunlight or warm counters — refrigerate once ripe to extend life.",
    "Carrots last longest with leafy tops removed, stored in a sealed bag in the crisper drawer.",
    "Amla (Indian gooseberry) keeps well refrigerated but its vitamin C content drops the longer it sits — use within a few days.",
    "An item at 60-85% freshness is usually still fine for cooking or smoothies, even if not ideal raw.",
    "Scan your fridge weekly — catching a 70%-fresh item early avoids a 100% loss later.",
]


def tier_for(freshness: int) -> str:
    if freshness >= 85:
        return "good"
    if freshness >= 60:
        return "warn"
    return "bad"


def action_for(tier: str, days: int) -> str:
    if tier == "good":
        return f"Fine to keep as-is — reassess in {days} day{'s' if days != 1 else ''}."
    if tier == "warn":
        return f"Use soon or move to discount / cooking — ~{days} day{'s' if days != 1 else ''} left."
    return "Spoilage advanced — remove from shelf, not recommended for sale or use."


def simulate_analysis() -> list[dict]:
    count = random.randint(1, 3)
    chosen = random.sample(CROPS, count)
    results = []
    for name in chosen:
        freshness = random.randint(30, 98)
        tier = tier_for(freshness)
        if tier == "good":
            days = random.randint(3, 6)
        elif tier == "warn":
            days = random.randint(1, 2)
        else:
            days = 0
        results.append({
            "name": name,
            "freshness": freshness,
            "tier": tier,
            "days": days,
            "decayPct": 100 - freshness,
            "action": action_for(tier, days),
        })
    return results
