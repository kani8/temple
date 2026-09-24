from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import combinations
from typing import Any

from .menu import FoodItem


@dataclass
class Meal:
    name: str
    items: list[FoodItem]
    note: str = ""


def totals(items: list[FoodItem]) -> dict[str, float]:
    keys = ["calories", "protein_g", "carbs_g", "fat_g", "fiber_g", "sodium_mg", "omega3_mg"]
    result = dict.fromkeys(keys, 0.0)
    for item in items:
        for key in keys:
            value = getattr(item, key)
            if value is not None:
                result[key] += float(value)
    return {key: round(value, 1) for key, value in result.items()}


def item_by_name(staples: list[FoodItem], name: str) -> FoodItem:
    for item in staples:
        if item.name == name:
            return item
    raise KeyError(f"Missing staple: {name}")


# Flavourings that mention meat or fish but don't make a dish a meat dish.
MEAT_FLAVOURINGS = re.compile(r"(vegan )?fish sauce|(chicken|beef|fish) (stock|broth|base|bouillon)")


def is_vegetarian_protein(item: FoodItem, meat_keywords: list[str]) -> bool:
    """A protein-heavy dish with no meat or fish in its name or ingredients."""
    if not meat_keywords or (item.protein_g or 0) < 12 or item.source != "cafeteria-json":
        return False
    text = MEAT_FLAVOURINGS.sub(" ", f"{item.name} {item.ingredients or ''}".lower())
    return not any(keyword.lower() in text for keyword in meat_keywords)


def score_cafeteria_item(
    item: FoodItem,
    preferred: list[str],
    avoid: list[str],
    weights: dict[str, float] | None = None,
    meat_keywords: list[str] | None = None,
    vegetarian_penalty: float = 0,
) -> float:
    name = item.name.lower()
    score = 0.0
    for keyword in preferred:
        if keyword.lower() in name:
            score += 5
    for keyword in avoid:
        if keyword.lower() in name:
            score -= 8
    for keyword, weight in (weights or {}).items():
        if keyword.lower() in name:
            score += float(weight)
    if vegetarian_penalty and is_vegetarian_protein(item, meat_keywords or []):
        score -= float(vegetarian_penalty)
    if item.has_macros():
        score += (item.protein_g or 0) * 1.6
        score += min(item.carbs_g or 0, 80) * 0.15
        score -= max((item.fat_g or 0) - 25, 0) * 0.6
        score -= max((item.sodium_mg or 0) - 700, 0) / 120
    return score


def is_drink(item: FoodItem) -> bool:
    text = f"{item.station or ''} {item.name}".lower()
    return any(word in text for word in ["coffee", "tea", "latte", "mocha", "espresso", "cappuccino", "chai"])


def is_evolve(item: FoodItem) -> bool:
    return "evolve protein shake" in item.name.lower()


def is_protein_smoothie(item: FoodItem) -> bool:
    return (
        item.source == "wellness-bar"
        and "protein" in item.name.lower()
        and (item.protein_g or 0) >= 15
    )


def is_protein_drink(item: FoodItem) -> bool:
    """Wellness-bar protein smoothies and packaged Evolve shakes fill the same slot."""
    return is_protein_smoothie(item) or is_evolve(item)


def is_excluded(item: FoodItem, nutrition_config: dict[str, Any]) -> bool:
    """Hard food exclusions (e.g. no pork), checked against name and ingredients.

    Exception phrases such as "chicken sausage" or "plant-based chorizo" are
    removed first so they don't trip the broader exclude patterns, and items
    named as plant-based/vegan are exempt outright.
    """
    cafeteria = nutrition_config["cafeteria"]
    patterns = cafeteria.get("exclude_patterns", [])
    if not patterns:
        return False
    name = item.name.lower()
    if any(word.lower() in name for word in cafeteria.get("exclude_exempt_names", [])):
        return False
    text = f"{name} {item.ingredients or ''}".lower()
    for phrase in cafeteria.get("exclude_exceptions", []):
        text = text.replace(phrase.lower(), " ")
    return any(re.search(pattern, text) for pattern in patterns)


def is_breakfast_item(item: FoodItem) -> bool:
    text = f"{item.station or ''} {item.name}".lower()
    return any(
        word in text
        for word in [
            "breakfast",
            "continental",
            "bagel",
            "bialy",
            "bread",
            "muffin",
            "yogurt",
            "oat",
            "cereal",
            "chia",
            "salmon cheese spread",
        ]
    )


def meal_candidates(menu: list[FoodItem], nutrition_config: dict[str, Any]) -> list[FoodItem]:
    cafe_items = [
        item for item in menu
        if item.has_macros()
        and (item.calories or 0) >= 80
        and (not is_drink(item))
        and (item.source != "wellness-bar" or is_protein_smoothie(item))
        and not is_excluded(item, nutrition_config)
    ]
    # Wellness-bar protein smoothies replace Evolve shakes whenever they're on.
    if any(is_protein_smoothie(item) for item in cafe_items):
        return cafe_items
    packaged = [
        FoodItem(**item, source="onsite-packaged")
        for item in nutrition_config.get("onsite_packaged", [])
    ]
    return cafe_items + packaged


def candidate_rank(item: FoodItem, nutrition_config: dict[str, Any]) -> float:
    # Protein smoothies from the wellness bar are preferred over Evolve shakes.
    if is_protein_smoothie(item):
        return 70
    if is_evolve(item):
        return 65
    return score_cafeteria_item(
        item,
        nutrition_config["cafeteria"]["preferred_keywords"],
        nutrition_config["cafeteria"]["avoid_keywords"],
        nutrition_config["cafeteria"].get("keyword_weights"),
        nutrition_config["cafeteria"].get("meat_keywords"),
        nutrition_config["cafeteria"].get("vegetarian_protein_penalty", 0),
    )


def choose_meal_items(
    candidates: list[FoodItem],
    nutrition_config: dict[str, Any],
    target: dict[str, float],
    *,
    breakfast: bool = False,
    pre_workout: bool = False,
    allow_evolve: bool = True,
    exclude_names: set[str] | None = None,
) -> list[FoodItem]:
    excluded = exclude_names or set()
    pool = [
        item for item in candidates
        if item.name not in excluded or is_protein_drink(item)
    ]
    if breakfast:
        pool = [item for item in pool if is_breakfast_item(item) or is_protein_drink(item)]
    elif pre_workout:
        pool = [
            item for item in pool
            if is_protein_drink(item)
            or "bagel" in item.name.lower()
            or "bread" in item.name.lower()
            or "rice" in item.name.lower()
            or "pasta" in item.name.lower()
            or "potato" in item.name.lower()
        ]
    else:
        pool = [item for item in pool if not is_breakfast_item(item) or (item.protein_g or 0) >= 15]
    if not allow_evolve:
        pool = [item for item in pool if not is_protein_drink(item)]

    ranked = sorted(pool, key=lambda item: candidate_rank(item, nutrition_config), reverse=True)[:26]
    meat_keywords = nutrition_config["cafeteria"].get("meat_keywords", [])
    veggie_penalty = float(nutrition_config["cafeteria"].get("vegetarian_meal_penalty", 0))
    if not ranked:
        return []

    combos: list[tuple[FoodItem, ...]] = []
    combos.extend((item,) for item in ranked)
    combos.extend(combinations(ranked[:18], 2))
    combos.extend(combinations(ranked[:14], 3))
    if not pre_workout:
        combos.extend(combinations(ranked[:10], 4))

    def combo_score(items: tuple[FoodItem, ...]) -> float:
        total = totals(list(items))
        penalty = 0.0
        penalty += abs(total["calories"] - target["calories"]) / 85
        penalty += abs(total["protein_g"] - target["protein_g"]) / 10
        penalty += abs(total["carbs_g"] - target["carbs_g"]) / 22
        penalty += abs(total["fat_g"] - target["fat_g"]) / 7
        penalty += max(target["fiber_g"] - total["fiber_g"], 0) / 4
        penalty += max(total["fiber_g"] - target["fiber_g"] - 5, 0) / 3
        penalty += max(total["sodium_mg"] - target["sodium_mg"], 0) / 110
        penalty += max(total["calories"] - target["calories"] - 180, 0) / 60
        if pre_workout and total["fat_g"] > 12:
            penalty += 5
        if sum(1 for item in items if is_protein_drink(item)) > 1:
            penalty += 12
        if breakfast and not any(is_protein_drink(item) or (item.protein_g or 0) >= 10 for item in items):
            penalty += 8
        # Prefer chicken/meat over veggie proteins even at some cost to macro fit.
        penalty += veggie_penalty * sum(1 for item in items if is_vegetarian_protein(item, meat_keywords))
        quality_bonus = sum(candidate_rank(item, nutrition_config) for item in items) / 45
        return penalty - quality_bonus

    return list(min(combos, key=combo_score))


def choose_cafeteria_items(menu: list[FoodItem], nutrition_config: dict[str, Any]) -> list[FoodItem]:
    macro_items = [item for item in menu if item.has_macros()]
    if not macro_items:
        return menu[:3]

    meal_items = [
        item for item in macro_items
        if (item.calories or 0) >= 150
        and "coffee" not in (item.station or "").lower()
        and "coffee" not in item.name.lower()
        and "tea" not in item.name.lower()
        and "latte" not in item.name.lower()
    ]
    ranked = sorted(
        meal_items,
        key=lambda item: score_cafeteria_item(
            item,
            nutrition_config["cafeteria"]["preferred_keywords"],
            nutrition_config["cafeteria"]["avoid_keywords"],
        ),
        reverse=True,
    )[:30]

    target = {"calories": 850, "protein_g": 55, "carbs_g": 110, "fat_g": 22, "fiber_g": 8, "sodium_mg": 1200}

    def combo_score(items: tuple[FoodItem, ...]) -> float:
        total = totals(list(items))
        penalty = 0.0
        penalty += abs(total["calories"] - target["calories"]) / 90
        penalty += abs(total["protein_g"] - target["protein_g"]) / 12
        penalty += abs(total["carbs_g"] - target["carbs_g"]) / 25
        penalty += abs(total["fat_g"] - target["fat_g"]) / 8
        penalty += max(target["fiber_g"] - total["fiber_g"], 0) / 4
        penalty += max(total["sodium_mg"] - target["sodium_mg"], 0) / 250
        if len(items) == 2 and (total["calories"] > 950 or total["fat_g"] > 35):
            penalty += 8
        quality_bonus = sum(
            score_cafeteria_item(
                item,
                nutrition_config["cafeteria"]["preferred_keywords"],
                nutrition_config["cafeteria"]["avoid_keywords"],
            )
            for item in items
        ) / 40
        return penalty - quality_bonus

    combos: list[tuple[FoodItem, ...]] = [(item,) for item in ranked]
    combos.extend(combinations(ranked[:15], 2))
    best = min(combos, key=combo_score) if combos else tuple()
    return list(best)


def fill_remaining_with_staples(
    current_items: list[FoodItem],
    staples: list[FoodItem],
    targets: dict[str, float],
) -> list[FoodItem]:
    planned = list(current_items)

    def current() -> dict[str, float]:
        return totals(planned)

    # Protein first, then fiber-aware carbs, then fats. This keeps the plan
    # interpretable while preventing low-fiber rice-only filler meals.
    while current()["protein_g"] < targets["protein_g"] - 20:
        planned.append(item_by_name(staples, "Whey isolate, 1 scoop"))
        if len(planned) > 40:
            break

    while current()["carbs_g"] < targets["carbs_g"] - 35:
        if current()["fiber_g"] < targets["fiber_g_min"] and current()["carbs_g"] < targets["carbs_g"] - 70:
            planned.append(item_by_name(staples, "Cooked potato, 300g"))
        else:
            planned.append(item_by_name(staples, "Cooked white rice, 1 cup"))
        if len(planned) > 50:
            break

    while current()["fiber_g"] < targets["fiber_g_min"]:
        if current()["fiber_g"] < targets["fiber_g_min"] - 3:
            planned.append(item_by_name(staples, "Mixed vegetables, 2 cups"))
        else:
            planned.append(item_by_name(staples, "Leafy greens, 2 cups"))
        if len(planned) > 55:
            break

    if current()["carbs_g"] < targets["carbs_g"] - 15:
        planned.append(item_by_name(staples, "Cooked white rice, 1 cup").scaled(0.5))

    while current()["fat_g"] < targets["fat_g"] - 8:
        planned.append(item_by_name(staples, "Olive oil, 1 tbsp").scaled(0.5))
        if len(planned) > 60:
            break

    if current()["calories"] < targets["calories"] - 120 and current()["carbs_g"] < targets["carbs_g"] + 20:
        planned.append(item_by_name(staples, "Cooked white rice, 1 cup").scaled(0.5))

    return planned


def emergency_meal_plan(staples: list[FoodItem], nutrition_config: dict[str, Any]) -> tuple[list[Meal], dict[str, float]]:
    targets = nutrition_config["daily_targets"]
    breakfast = [
        item_by_name(staples, name)
        for name in nutrition_config["fixed_meals"]["breakfast"]
    ]
    pre_workout = [
        item_by_name(staples, name)
        for name in nutrition_config["fixed_meals"]["pre_workout"]
    ]
    lunch_items = [
        item_by_name(staples, "Chicken breast, cooked, 8 oz"),
        item_by_name(staples, "Cooked white rice, 1 cup").scaled(1.5),
        item_by_name(staples, "Mixed vegetables, 2 cups"),
    ]
    base = breakfast + lunch_items + pre_workout
    filled = fill_remaining_with_staples(base, staples, targets)
    dinner_items = filled[len(base):]
    note = "Emergency fallback because no visible cafeteria menu was parsed. Replace with Uber cafeteria equivalents when the menu is available."
    meals = [
        Meal("Emergency Breakfast", breakfast, note),
        Meal("Emergency Lunch", lunch_items, note),
        Meal("Emergency Pre-workout", pre_workout, note),
        Meal("Emergency Dinner", dinner_items, note),
    ]
    return meals, totals([item for meal in meals for item in meal.items])


def build_meal_plan(nutrition_config: dict[str, Any], menu: list[FoodItem]) -> tuple[list[Meal], dict[str, float]]:
    staples = [FoodItem(**item, source="emergency-staple") for item in nutrition_config["emergency_staples"]]
    targets = nutrition_config["daily_targets"]
    meal_targets = nutrition_config["meal_targets"]
    candidates = meal_candidates(menu, nutrition_config)
    cafeteria_available = any(
        item.has_macros()
        and (item.calories or 0) >= 80
        and not is_drink(item)
        for item in menu
    )
    if not cafeteria_available:
        return emergency_meal_plan(staples, nutrition_config)

    used: set[str] = set()
    breakfast = choose_meal_items(candidates, nutrition_config, meal_targets["breakfast"], breakfast=True)
    used.update(item.name for item in breakfast if not is_protein_drink(item))
    lunch_items = choose_meal_items(
        candidates,
        nutrition_config,
        meal_targets["uber_hq_lunch"],
        allow_evolve=False,
        exclude_names=used,
    )
    used.update(item.name for item in lunch_items if not is_protein_drink(item))
    pre_workout = choose_meal_items(candidates, nutrition_config, meal_targets["pre_workout"], pre_workout=True)
    used.update(item.name for item in pre_workout if not is_protein_drink(item))
    dinner_items = choose_meal_items(
        candidates,
        nutrition_config,
        meal_targets["post_workout_dinner"],
        allow_evolve=False,
        exclude_names=used,
    )

    base = breakfast + lunch_items + pre_workout + dinner_items
    if not base:
        return emergency_meal_plan(staples, nutrition_config)

    day_total = totals(base)
    # Top up protein with wellness-bar protein smoothies first, Evolve shakes after.
    smoothies = sorted(
        [item for item in candidates if is_protein_smoothie(item)],
        key=lambda item: item.protein_g or 0,
        reverse=True,
    )
    onsite_packaged = [FoodItem(**item, source="onsite-packaged") for item in nutrition_config.get("onsite_packaged", [])]
    protein_drinks = smoothies or onsite_packaged
    shake_idx = 0
    existing_shakes = sum(1 for item in base if is_protein_drink(item))
    planning = nutrition_config.get("planning", {})
    max_shakes = int(planning.get("max_protein_drinks_per_day", planning.get("max_evolve_shakes_per_day", 2)))
    while day_total["protein_g"] < targets["protein_g"] - 8 and protein_drinks and existing_shakes + shake_idx < max_shakes:
        dinner_items.append(protein_drinks[shake_idx % len(protein_drinks)])
        shake_idx += 1
        day_total = totals(breakfast + lunch_items + pre_workout + dinner_items)
        if shake_idx > 3:
            break

    day_total = totals(breakfast + lunch_items + pre_workout + dinner_items)
    carb_candidates = sorted(
        [
            item for item in candidates
            if not is_protein_drink(item)
            and (item.carbs_g or 0) >= 25
            and (item.fat_g or 0) <= 8
            and item.name not in {existing.name for existing in dinner_items}
        ],
        key=lambda item: abs((targets["calories"] - day_total["calories"]) - (item.calories or 0)),
    )
    if day_total["calories"] < targets["calories"] - 180 and carb_candidates:
        dinner_items.append(carb_candidates[0])

    if day_total["calories"] < targets["calories"] - 180 and nutrition_config.get("planning", {}).get("home_fallback_allowed", False):
        filled = fill_remaining_with_staples(breakfast + lunch_items + pre_workout + dinner_items, staples, targets)
        dinner_items.extend(filled[len(breakfast + lunch_items + pre_workout + dinner_items):])

    meals = [
        Meal("Uber Breakfast", breakfast, "Chosen from cafeteria breakfast/continental options plus a protein smoothie or Evolve if useful."),
        Meal("Uber HQ Lunch", lunch_items, "Chosen from live Bon Appetit nutrition data."),
        Meal("Uber Pre-workout", pre_workout, "Uber grab-and-go friendly; eat 60-90 min before lifting."),
        Meal("Uber Post-workout / Dinner", dinner_items, "Cafeteria items, wellness-bar protein smoothies, and packaged shakes selected to close the daily gaps."),
    ]
    return meals, totals([item for meal in meals for item in meal.items])


def macro_delta(actual: dict[str, float], targets: dict[str, float]) -> dict[str, float]:
    return {
        "calories": round(actual["calories"] - targets["calories"], 1),
        "protein_g": round(actual["protein_g"] - targets["protein_g"], 1),
        "carbs_g": round(actual["carbs_g"] - targets["carbs_g"], 1),
        "fat_g": round(actual["fat_g"] - targets["fat_g"], 1),
        "fiber_g_vs_min": round(actual["fiber_g"] - targets["fiber_g_min"], 1),
    }
