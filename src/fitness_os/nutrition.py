from __future__ import annotations

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


def score_cafeteria_item(item: FoodItem, preferred: list[str], avoid: list[str]) -> float:
    name = item.name.lower()
    score = 0.0
    for keyword in preferred:
        if keyword.lower() in name:
            score += 5
    for keyword in avoid:
        if keyword.lower() in name:
            score -= 8
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
    ]
    packaged = [
        FoodItem(**item, source="onsite-packaged")
        for item in nutrition_config.get("onsite_packaged", [])
    ]
    return cafe_items + packaged


def candidate_rank(item: FoodItem, nutrition_config: dict[str, Any]) -> float:
    if is_evolve(item):
        return 65
    return score_cafeteria_item(
        item,
        nutrition_config["cafeteria"]["preferred_keywords"],
        nutrition_config["cafeteria"]["avoid_keywords"],
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
        if item.name not in excluded or is_evolve(item)
    ]
    if breakfast:
        pool = [item for item in pool if is_breakfast_item(item) or is_evolve(item)]
    elif pre_workout:
        pool = [
            item for item in pool
            if is_evolve(item)
            or "bagel" in item.name.lower()
            or "bread" in item.name.lower()
            or "rice" in item.name.lower()
            or "pasta" in item.name.lower()
            or "potato" in item.name.lower()
        ]
    else:
        pool = [item for item in pool if not is_breakfast_item(item) or (item.protein_g or 0) >= 15]
    if not allow_evolve:
        pool = [item for item in pool if not is_evolve(item)]

    ranked = sorted(pool, key=lambda item: candidate_rank(item, nutrition_config), reverse=True)[:26]
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
        if sum(1 for item in items if is_evolve(item)) > 1:
            penalty += 12
        if breakfast and not any(is_evolve(item) or (item.protein_g or 0) >= 10 for item in items):
            penalty += 8
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


def build_meal_plan(nutrition_config: dict[str, Any], menu: list[FoodItem]) -> tuple[list[Meal], dict[str, float]]:
    staples = [FoodItem(**item, source="emergency-staple") for item in nutrition_config["emergency_staples"]]
    targets = nutrition_config["daily_targets"]
    meal_targets = nutrition_config["meal_targets"]
    candidates = meal_candidates(menu, nutrition_config)

    used: set[str] = set()
    breakfast = choose_meal_items(candidates, nutrition_config, meal_targets["breakfast"], breakfast=True)
    used.update(item.name for item in breakfast if not is_evolve(item))
    lunch_items = choose_meal_items(
        candidates,
        nutrition_config,
        meal_targets["uber_hq_lunch"],
        allow_evolve=False,
        exclude_names=used,
    )
    used.update(item.name for item in lunch_items if not is_evolve(item))
    pre_workout = choose_meal_items(candidates, nutrition_config, meal_targets["pre_workout"], pre_workout=True)
    used.update(item.name for item in pre_workout if not is_evolve(item))
    dinner_items = choose_meal_items(
        candidates,
        nutrition_config,
        meal_targets["post_workout_dinner"],
        allow_evolve=False,
        exclude_names=used,
    )

    base = breakfast + lunch_items + pre_workout + dinner_items
    if not base:
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

    day_total = totals(base)
    onsite_packaged = [FoodItem(**item, source="onsite-packaged") for item in nutrition_config.get("onsite_packaged", [])]
    shake_idx = 0
    existing_shakes = sum(1 for item in base if is_evolve(item))
    max_shakes = int(nutrition_config.get("planning", {}).get("max_evolve_shakes_per_day", 2))
    while day_total["protein_g"] < targets["protein_g"] - 8 and onsite_packaged and existing_shakes + shake_idx < max_shakes:
        dinner_items.append(onsite_packaged[shake_idx % len(onsite_packaged)])
        shake_idx += 1
        day_total = totals(breakfast + lunch_items + pre_workout + dinner_items)
        if shake_idx > 3:
            break

    day_total = totals(breakfast + lunch_items + pre_workout + dinner_items)
    carb_candidates = sorted(
        [
            item for item in candidates
            if not is_evolve(item)
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
        Meal("Uber Breakfast", breakfast, "Chosen from cafeteria breakfast/continental options plus Evolve if useful."),
        Meal("Uber HQ Lunch", lunch_items, "Chosen from live Bon Appetit nutrition data."),
        Meal("Uber Pre-workout", pre_workout, "Uber grab-and-go friendly; eat 60-90 min before lifting."),
        Meal("Uber Post-workout / Dinner", dinner_items, "Cafeteria and packaged items selected to close the daily gaps."),
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
