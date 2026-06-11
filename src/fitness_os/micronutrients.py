from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .menu import FoodItem


NUTRIENT_KEYS = [
    "calcium_mg",
    "iron_mg",
    "magnesium_mg",
    "potassium_mg",
    "zinc_mg",
    "selenium_mcg",
    "folate_mcg",
    "choline_mg",
    "vitamin_a_mcg",
    "vitamin_c_mg",
    "vitamin_d_iu",
    "vitamin_e_mg",
    "vitamin_k_mcg",
    "b1_mg",
    "b2_mg",
    "b3_mg",
    "b5_mg",
    "b6_mg",
    "b12_mcg",
]


@dataclass(frozen=True)
class NutrientProfile:
    patterns: tuple[str, ...]
    nutrients: dict[str, float]
    confidence: float
    reason: str


# Heuristic contribution per visible menu serving. These are deliberately
# conservative estimates meant to catch gaps, not replace a lab-grade tracker.
PROFILES = [
    NutrientProfile(
        ("evolve protein shake",),
        {
            "calcium_mg": 260,
            "iron_mg": 4,
            "potassium_mg": 400,
            "vitamin_d_iu": 100,
            "b12_mcg": 1.2,
            "magnesium_mg": 45,
        },
        0.75,
        "packaged protein shake label estimate",
    ),
    NutrientProfile(
        ("turkey", "chicken", "pollo", "pork", "beef", "lamb"),
        {
            "iron_mg": 1.2,
            "zinc_mg": 2.2,
            "selenium_mcg": 24,
            "choline_mg": 75,
            "b3_mg": 7,
            "b5_mg": 1.0,
            "b6_mg": 0.45,
            "b2_mg": 0.15,
            "b12_mcg": 0.5,
            "potassium_mg": 260,
            "phosphorus_mg": 180,
        },
        0.55,
        "meat/poultry ingredient",
    ),
    NutrientProfile(
        ("shrimp", "salmon", "tuna", "fish"),
        {
            "selenium_mcg": 35,
            "iodine_mcg": 25,
            "zinc_mg": 1.2,
            "b12_mcg": 1.5,
            "choline_mg": 80,
            "b3_mg": 4.5,
            "b5_mg": 0.9,
            "b6_mg": 0.25,
            "potassium_mg": 220,
            "vitamin_d_iu": 80,
        },
        0.55,
        "seafood ingredient",
    ),
    NutrientProfile(
        ("egg",),
        {
            "choline_mg": 140,
            "selenium_mcg": 15,
            "b12_mcg": 0.5,
            "vitamin_d_iu": 40,
            "vitamin_a_mcg": 80,
            "b2_mg": 0.25,
            "b5_mg": 0.7,
        },
        0.6,
        "egg ingredient",
    ),
    NutrientProfile(
        ("greek yogurt", "yogurt", "milk", "cheese", "mozzarella", "brie", "queso", "cream"),
        {
            "calcium_mg": 180,
            "potassium_mg": 180,
            "b2_mg": 0.25,
            "b5_mg": 0.7,
            "b12_mcg": 0.7,
            "vitamin_a_mcg": 70,
            "choline_mg": 35,
        },
        0.55,
        "dairy ingredient",
    ),
    NutrientProfile(
        ("bean", "beans", "chickpea", "garbanzo", "lentil", "pinto", "black beans", "tempeh", "tofu", "soy"),
        {
            "iron_mg": 2.2,
            "magnesium_mg": 70,
            "potassium_mg": 450,
            "zinc_mg": 1.3,
            "folate_mcg": 90,
            "b1_mg": 0.25,
            "b5_mg": 0.4,
            "b6_mg": 0.15,
            "choline_mg": 35,
        },
        0.45,
        "legume/soy ingredient",
    ),
    NutrientProfile(
        ("whole grain", "oat", "oats", "brown rice", "wild rice", "whole wheat", "whole grain pasta", "cereal", "raisin bran", "farro", "quinoa"),
        {
            "magnesium_mg": 55,
            "iron_mg": 1.4,
            "zinc_mg": 1.2,
            "b1_mg": 0.25,
            "b3_mg": 2.5,
            "b5_mg": 0.5,
            "b6_mg": 0.12,
            "folate_mcg": 35,
        },
        0.45,
        "whole grain ingredient",
    ),
    NutrientProfile(
        ("bagel", "bread", "bialy", "brioche", "pasta", "orzo", "tortilla", "flour tortilla", "polenta", "rice", "english muffin"),
        {
            "iron_mg": 1.2,
            "b1_mg": 0.2,
            "b2_mg": 0.12,
            "b3_mg": 2,
            "folate_mcg": 45,
            "selenium_mcg": 10,
        },
        0.35,
        "grain/starch ingredient",
    ),
    NutrientProfile(
        ("potato", "sweet potato", "sunchoke"),
        {
            "potassium_mg": 520,
            "vitamin_c_mg": 18,
            "b6_mg": 0.35,
            "b5_mg": 0.5,
            "magnesium_mg": 35,
            "iron_mg": 0.8,
        },
        0.45,
        "potato/root vegetable ingredient",
    ),
    NutrientProfile(
        ("sweet potato", "yam"),
        {
            "vitamin_a_mcg": 700,
            "potassium_mg": 420,
            "vitamin_c_mg": 18,
            "b6_mg": 0.25,
            "b5_mg": 0.4,
        },
        0.5,
        "orange root vegetable ingredient",
    ),
    NutrientProfile(
        ("walnut", "walnuts", "almond", "almonds", "cashew", "cashews", "hazelnut", "hazelnuts", "pecan", "pecans", "pistachio", "pistachios", "peanut", "peanuts", "pumpkin seed", "chia seed", "chia seeds", "sesame", "tahini"),
        {
            "magnesium_mg": 75,
            "vitamin_e_mg": 3.5,
            "zinc_mg": 1.1,
            "iron_mg": 1.0,
            "b1_mg": 0.15,
            "folate_mcg": 25,
        },
        0.55,
        "nuts/seeds ingredient",
    ),
    NutrientProfile(
        ("spinach", "kale", "lettuce", "frisee", "greens", "bok choy", "broccoli", "broccolini", "cabbage", "cauliflower", "brussels sprout", "brussels sprouts"),
        {
            "vitamin_k_mcg": 90,
            "vitamin_a_mcg": 250,
            "vitamin_c_mg": 25,
            "folate_mcg": 70,
            "potassium_mg": 250,
            "magnesium_mg": 30,
            "calcium_mg": 70,
        },
        0.4,
        "leafy/cruciferous vegetable ingredient",
    ),
    NutrientProfile(
        ("pepper", "peppers", "tomato", "tomatoes", "zucchini", "squash", "eggplant", "mushroom", "mushrooms", "onion", "onions", "carrot", "carrots", "corn", "peas", "artichoke", "artichokes", "cucumber", "celery"),
        {
            "vitamin_c_mg": 18,
            "vitamin_a_mcg": 80,
            "potassium_mg": 230,
            "folate_mcg": 25,
            "b5_mg": 0.25,
            "b6_mg": 0.12,
        },
        0.35,
        "mixed vegetable ingredient",
    ),
    NutrientProfile(
        ("berries", "blueberry", "blueberries", "blackberry", "blackberries", "strawberry", "strawberries", "raspberry", "raspberries", "cherry", "cherries", "peach", "peaches", "banana", "pear", "orange", "lemon", "lime", "fruit"),
        {
            "vitamin_c_mg": 18,
            "potassium_mg": 220,
            "folate_mcg": 20,
            "vitamin_k_mcg": 15,
        },
        0.35,
        "fruit ingredient",
    ),
    NutrientProfile(
        ("oat milk", "almond milk", "soy milk"),
        {
            "calcium_mg": 250,
            "vitamin_d_iu": 100,
            "b12_mcg": 0.8,
            "vitamin_a_mcg": 70,
        },
        0.45,
        "fortified plant milk ingredient",
    ),
    NutrientProfile(
        ("olive oil", "oil", "avocado"),
        {
            "vitamin_e_mg": 1.5,
            "vitamin_k_mcg": 8,
        },
        0.35,
        "fat source ingredient",
    ),
]


GAP_FIXES = {
    "calcium_mg": "Add Greek yogurt, milk, cheese, or an Evolve shake.",
    "iron_mg": "Add turkey/chicken, beef, shrimp, beans, tempeh, or whole grains.",
    "magnesium_mg": "Add beans, nuts/seeds, whole grains, oats, or whole grain pasta.",
    "potassium_mg": "Add beans, potatoes, bananas/fruit, leafy greens, or vegetable-heavy entrees.",
    "zinc_mg": "Add meat, seafood, dairy, beans, nuts, or seeds.",
    "selenium_mcg": "Add seafood, turkey/chicken, eggs, or enriched grains.",
    "folate_mcg": "Add beans, leafy greens, citrus/fruit, or enriched grains.",
    "choline_mg": "Add eggs, chicken/turkey, seafood, or dairy.",
    "vitamin_a_mcg": "Add leafy greens, carrots, peppers, squash, eggs, or dairy.",
    "vitamin_c_mg": "Add fruit, peppers, tomatoes, broccoli/cabbage, or citrus-heavy dishes.",
    "vitamin_d_iu": "Hard to hit from cafeteria food; use D3 supplement or fatty fish.",
    "vitamin_e_mg": "Add almonds, walnuts, seeds, avocado, or olive-oil based foods.",
    "vitamin_k_mcg": "Add leafy greens, cabbage, broccoli, or salad greens.",
    "b1_mg": "Add whole grains, beans, pork, or enriched grains.",
    "b2_mg": "Add dairy, eggs, meats, or fortified foods.",
    "b3_mg": "Add chicken/turkey, fish, meat, or enriched grains.",
    "b5_mg": "Add chicken/turkey, eggs, dairy, mushrooms, or legumes.",
    "b6_mg": "Add poultry, fish, beans, potatoes, bananas, or vegetables.",
    "b12_mcg": "Add meat, seafood, dairy, eggs, or fortified shakes.",
}


def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]+", " ", value.lower())


def item_text(item: FoodItem) -> str:
    return " ".join(
        part for part in [item.name, item.station, item.ingredients] if part
    ).lower()


def serving_factor(item: FoodItem) -> float:
    calories = item.calories or 0
    if calories >= 650:
        return 1.25
    if calories >= 350:
        return 1.0
    if calories >= 180:
        return 0.7
    if calories >= 80:
        return 0.45
    return 0.25


def matched_profiles(item: FoodItem) -> list[NutrientProfile]:
    text = _clean_text(item_text(item))
    matches: list[NutrientProfile] = []
    for profile in PROFILES:
        if any(re.search(rf"\b{re.escape(pattern)}\b", text) for pattern in profile.patterns):
            matches.append(profile)
    return matches


def estimate_item(item: FoodItem) -> tuple[dict[str, float], float, list[str]]:
    estimates = dict.fromkeys(NUTRIENT_KEYS, 0.0)
    profiles = matched_profiles(item)
    factor = serving_factor(item)
    reasons: list[str] = []
    confidence_weights = []

    for profile in profiles:
        reasons.append(profile.reason)
        confidence_weights.append(profile.confidence)
        for nutrient, amount in profile.nutrients.items():
            if nutrient in estimates:
                estimates[nutrient] += amount * factor

    if item.omega3_mg and item.omega3_mg > 0:
        reasons.append("packaged omega-3 label")
        confidence_weights.append(0.8)

    if not profiles:
        return estimates, 0.15, ["no meaningful ingredient match"]

    confidence = sum(confidence_weights) / len(confidence_weights)
    if item.source == "onsite-packaged":
        confidence = min(0.85, confidence + 0.1)
    elif item.ingredients:
        confidence = min(0.75, confidence + 0.05)
    return {key: round(value, 2) for key, value in estimates.items()}, round(confidence, 2), reasons


def confidence_label(value: float) -> str:
    if value >= 0.65:
        return "medium-high"
    if value >= 0.45:
        return "medium"
    if value >= 0.25:
        return "low-medium"
    return "low"


def estimate_day(items: list[FoodItem], micronutrient_config: dict[str, Any]) -> dict[str, Any]:
    totals = dict.fromkeys(NUTRIENT_KEYS, 0.0)
    confidence_numerators = dict.fromkeys(NUTRIENT_KEYS, 0.0)
    confidence_denominators = dict.fromkeys(NUTRIENT_KEYS, 0.0)
    item_notes = []

    for item in items:
        estimate, confidence, reasons = estimate_item(item)
        item_notes.append(
            {
                "item": item.name,
                "confidence": confidence,
                "reasons": reasons[:4],
            }
        )
        for nutrient, amount in estimate.items():
            totals[nutrient] += amount
            if amount > 0:
                confidence_numerators[nutrient] += amount * confidence
                confidence_denominators[nutrient] += amount

    targets = micronutrient_config["targets"]
    rows = []
    for nutrient, meta in targets.items():
        amount = round(totals.get(nutrient, 0.0), 1)
        target = float(meta["target"])
        percent = round((amount / target) * 100, 1) if target else 0.0
        confidence = (
            confidence_numerators[nutrient] / confidence_denominators[nutrient]
            if confidence_denominators[nutrient]
            else 0.15
        )
        rows.append(
            {
                "key": nutrient,
                "label": meta["label"],
                "amount": amount,
                "target": target,
                "unit": meta["unit"],
                "percent": percent,
                "confidence": confidence_label(confidence),
                "fix": GAP_FIXES.get(nutrient, "Add more varied whole foods."),
            }
        )

    low_threshold = float(micronutrient_config.get("low_threshold_percent", 70))
    strong_threshold = float(micronutrient_config.get("strong_threshold_percent", 110))
    rows.sort(key=lambda row: row["percent"])
    gaps = [row for row in rows if row["percent"] < low_threshold]
    strong = [row for row in rows if row["percent"] >= strong_threshold]

    return {
        "rows": rows,
        "gaps": gaps,
        "strong": strong,
        "item_notes": item_notes,
    }
