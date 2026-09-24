"""Meal selections written by the nutritionist routine.

A selection file at data/selections/YYYY-MM-DD.json replaces the algorithmic
menu pick for that day. It names items only; every macro still comes from the
scraped menu data, so a selection can't invent numbers. Items that can't be
found on the day's menu, or that break a hard exclusion (no pork), are dropped
with a warning. If nothing usable is left, the planner falls back to its own
selection.

Format:

    {
      "summary": "One or two sentences on today's approach.",
      "meals": [
        {
          "name": "Uber Breakfast",
          "note": "Why these items.",
          "items": [
            {"name": "Berry Cottage Cheese Protein Smoothie", "station": "@Wellness", "servings": 1}
          ]
        }
      ]
    }

`station` is optional and only needed when two stations serve an item with the
same name. `servings` defaults to 1.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from .menu import FoodItem, normalize_name
from .nutrition import Meal, is_excluded, totals


@dataclass
class Selection:
    summary: str
    meals: list[Meal]
    warnings: list[str]


def selection_path(data_dir: Path, day: date) -> Path:
    return data_dir / "selections" / f"{day.isoformat()}.json"


def _find_item(pool: list[FoodItem], name: str, station: str | None) -> FoodItem | None:
    wanted = normalize_name(name)
    matches = [item for item in pool if normalize_name(item.name) == wanted]
    if station and len(matches) > 1:
        by_station = [item for item in matches if normalize_name(item.station or "") == normalize_name(station)]
        matches = by_station or matches
    return matches[0] if matches else None


def load_selection(path: Path, menu: list[FoodItem], nutrition_config: dict[str, Any]) -> Selection | None:
    if not path.exists():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    # Everything on the menu with macros, plus the packaged Evolve fallbacks.
    pool = [item for item in menu if item.has_macros()] + [
        FoodItem(**item, source="onsite-packaged") for item in nutrition_config.get("onsite_packaged", [])
    ]

    warnings: list[str] = []
    meals: list[Meal] = []
    for meal in raw.get("meals", []):
        items: list[FoodItem] = []
        for entry in meal.get("items", []):
            item = _find_item(pool, entry.get("name", ""), entry.get("station"))
            if item is None:
                warnings.append(f"not on today's menu: {entry.get('name')}")
                continue
            if is_excluded(item, nutrition_config):
                warnings.append(f"excluded food, dropped: {item.name}")
                continue
            servings = float(entry.get("servings", 1))
            items.append(item if servings == 1 else item.scaled(servings))
        if items:
            meals.append(Meal(meal.get("name", "Meal"), items, meal.get("note", "")))

    for warning in warnings:
        print(f"selection warning: {warning}", file=sys.stderr)
    if not meals:
        print("selection warning: no usable items, using the planner's own selection", file=sys.stderr)
        return None
    return Selection(raw.get("summary", ""), meals, warnings)


def selection_totals(selection: Selection) -> dict[str, float]:
    return totals([item for meal in selection.meals for item in meal.items])
