"""What actually happened on a day, logged by the coach routine.

The coach writes data/logs/YYYY-MM-DD.json as the client reports in during
the day ("had breakfast", "skipped lunch", "row felt easy at 130"). Like a
selection file, menu items are named, not measured: macros come from the
scraped menu, so the log can't invent numbers for them. Food that isn't on the
menu (home food, a snack from outside) is logged with estimated macros and
flagged as an estimate.

Format:

    {
      "date": "2026-09-28",
      "meals": {
        "Uber Breakfast": {"status": "as_planned", "time": "08:20"},
        "Uber HQ Lunch": {"status": "custom", "time": "12:40", "note": "Swapped pasta for rice"},
        "Uber Pre-workout": {"status": "skipped", "note": "Meeting ran long"}
      },
      "eaten": [
        {"meal": "Uber HQ Lunch", "name": "Lemon Oregano Roasted Chicken", "servings": 1},
        {"meal": "Uber HQ Lunch", "name": "Steamed Jasmine Rice", "servings": 1.5},
        {"meal": "Snack", "name": "Protein bar", "calories": 210, "protein_g": 20,
         "carbs_g": 23, "fat_g": 7, "fiber_g": 3, "estimate": true}
      ],
      "lifts": [
        {"exercise": "Cable row, neutral grip", "load": "130 lb", "reps": [10, 10], "rir": 2,
         "note": "easy, go up next time"}
      ],
      "cardio": {"done": true, "minutes": 25, "note": "incline walk"},
      "steps": 11200,
      "water_oz": 96,
      "bodyweight_lb": 184.6,
      "notes": ["Knee fine on leg press"]
    }

Meal statuses:
- `as_planned`: every item in today's plan for that meal counts.
- `custom`: only the `eaten` entries tagged with that meal count.
- `skipped`: nothing counts.
A planned meal missing from `meals` is still pending.

Every `eaten` entry always counts, so extras on top of an `as_planned` meal go
there too. An entry with `calories` set is taken as given; anything else is
looked up on the day's menu (plus packaged and emergency staples) by name.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from .menu import FoodItem
from .nutrition import Meal, totals
from .selection import _find_item

STATUSES = {"as_planned", "custom", "skipped"}
MACRO_KEYS = ["calories", "protein_g", "carbs_g", "fat_g", "fiber_g", "sodium_mg"]


@dataclass
class DayStatus:
    day: date
    meals: list[dict[str, Any]]
    extras: list[FoodItem]
    eaten_totals: dict[str, float]
    projected_totals: dict[str, float]
    remaining: dict[str, float]
    log: dict[str, Any]
    warnings: list[str] = field(default_factory=list)


def log_path(data_dir: Path, day: date) -> Path:
    return data_dir / "logs" / f"{day.isoformat()}.json"


def load_log(path: Path, day: date) -> dict[str, Any]:
    if not path.exists():
        return {"date": day.isoformat(), "meals": {}, "eaten": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _logged_item(entry: dict[str, Any], pool: list[FoodItem]) -> FoodItem | None:
    servings = float(entry.get("servings", 1))
    if entry.get("calories") is not None:
        item = FoodItem(
            name=entry.get("name", "Logged food"),
            **{key: entry.get(key) for key in MACRO_KEYS},
            station=entry.get("meal"),
            source="logged-estimate" if entry.get("estimate", True) else "logged",
        )
    else:
        item = _find_item(pool, entry.get("name", ""), entry.get("station"))
        if item is None:
            return None
    return item if servings == 1 else item.scaled(servings)


def day_status(
    day: date,
    log: dict[str, Any],
    planned_meals: list[Meal],
    menu: list[FoodItem],
    nutrition_config: dict[str, Any],
) -> DayStatus:
    pool = (
        [item for item in menu if item.has_macros()]
        + [FoodItem(**item, source="onsite-packaged") for item in nutrition_config.get("onsite_packaged", [])]
        + [FoodItem(**item, source="emergency-staple") for item in nutrition_config.get("emergency_staples", [])]
    )
    warnings: list[str] = []
    logged_meals: dict[str, Any] = log.get("meals", {})
    planned_names = {meal.name for meal in planned_meals}

    for name, entry in logged_meals.items():
        if entry.get("status") not in STATUSES:
            warnings.append(f"meal '{name}' has unknown status {entry.get('status')!r}")
        if entry.get("status") == "as_planned" and name not in planned_names:
            warnings.append(f"meal '{name}' marked as_planned but is not in today's plan")

    logged_by_meal: dict[str, list[FoodItem]] = {}
    for entry in log.get("eaten", []):
        item = _logged_item(entry, pool)
        if item is None:
            warnings.append(
                f"not on today's menu: {entry.get('name')} (log it with estimated calories/protein_g/carbs_g/fat_g)"
            )
            continue
        logged_by_meal.setdefault(entry.get("meal") or "Extra", []).append(item)

    eaten: list[FoodItem] = []
    pending: list[FoodItem] = []
    meal_rows: list[dict[str, Any]] = []
    for meal in planned_meals:
        entry = logged_meals.get(meal.name, {})
        status = entry.get("status", "pending")
        logged = logged_by_meal.pop(meal.name, [])
        counted = (meal.items if status == "as_planned" else []) + logged
        eaten += counted
        if status == "pending":
            pending += meal.items
        meal_rows.append({
            "name": meal.name,
            "status": status,
            "time": entry.get("time"),
            "note": entry.get("note"),
            "planned": meal.items,
            "counted": counted,
        })

    extras = [item for items in logged_by_meal.values() for item in items]
    eaten += extras
    eaten_totals = totals(eaten)
    projected_totals = totals(eaten + pending)
    targets = nutrition_config["daily_targets"]
    remaining = {
        "calories": round(targets["calories"] - eaten_totals["calories"], 1),
        "protein_g": round(targets["protein_g"] - eaten_totals["protein_g"], 1),
        "carbs_g": round(targets["carbs_g"] - eaten_totals["carbs_g"], 1),
        "fat_g": round(targets["fat_g"] - eaten_totals["fat_g"], 1),
        "fiber_g_to_min": round(targets["fiber_g_min"] - eaten_totals["fiber_g"], 1),
    }
    return DayStatus(day, meal_rows, extras, eaten_totals, projected_totals, remaining, log, warnings)


def _fmt(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:g}"


def _item_list(items: list[FoodItem]) -> str:
    return "; ".join(item.name for item in items) or "-"


def render_status(status: DayStatus, training_plan: Any, nutrition_config: dict[str, Any]) -> str:
    targets = nutrition_config["daily_targets"]
    log = status.log
    lines = [
        f"# Day status - {status.day.isoformat()}",
        f"Training: {training_plan.session_name} (week {training_plan.week}, day {training_plan.day_number})",
        "",
        "## Meals",
        "",
        "| Meal | Status | Time | Planned items | Counted items | Note |",
        "|---|---|---|---|---|---|",
    ]
    for row in status.meals:
        lines.append(
            f"| {row['name']} | {row['status']} | {row['time'] or ''} | {_item_list(row['planned'])} | "
            f"{_item_list(row['counted'])} | {row['note'] or ''} |"
        )
    if status.extras:
        lines += ["", "Extras: " + "; ".join(
            f"{item.name} ({_fmt(item.calories)} cal, {_fmt(item.protein_g)}P"
            + (", estimate" if item.source == "logged-estimate" else "") + ")"
            for item in status.extras
        )]

    eaten, projected, remaining = status.eaten_totals, status.projected_totals, status.remaining
    lines += [
        "",
        "## Nutrition",
        "",
        "| | Cal | P | C | F | Fiber | Sodium |",
        "|---|---:|---:|---:|---:|---:|---:|",
        f"| Target | {targets['calories']} | {targets['protein_g']} | {targets['carbs_g']} | {targets['fat_g']} | "
        f"{targets['fiber_g_min']}-{targets['fiber_g_max']} | <{targets['sodium_mg_soft_max']} |",
        f"| Eaten so far | {_fmt(eaten['calories'])} | {_fmt(eaten['protein_g'])} | {_fmt(eaten['carbs_g'])} | "
        f"{_fmt(eaten['fat_g'])} | {_fmt(eaten['fiber_g'])} | {_fmt(eaten['sodium_mg'])} |",
        f"| Remaining | {_fmt(remaining['calories'])} | {_fmt(remaining['protein_g'])} | {_fmt(remaining['carbs_g'])} | "
        f"{_fmt(remaining['fat_g'])} | {_fmt(max(remaining['fiber_g_to_min'], 0))} to min | |",
        f"| Projected if pending meals eaten as planned | {_fmt(projected['calories'])} | {_fmt(projected['protein_g'])} | "
        f"{_fmt(projected['carbs_g'])} | {_fmt(projected['fat_g'])} | {_fmt(projected['fiber_g'])} | "
        f"{_fmt(projected['sodium_mg'])} |",
    ]

    logged_lifts = {lift.get("exercise", "").lower(): lift for lift in log.get("lifts", [])}
    lines += [
        "",
        "## Training",
        "",
        "| Exercise | Prescribed | Logged |",
        "|---|---|---|",
    ]
    matched: set[str] = set()
    for ex in training_plan.exercises:
        # "Leg press" should match "Leg press, high narrow foot".
        key = next((name for name in logged_lifts if name and ex.name.lower().startswith(name)), None)
        lift = logged_lifts.get(key) if key else None
        if key:
            matched.add(key)
        logged = "-"
        if lift:
            reps = "/".join(str(r) for r in lift.get("reps", []))
            logged = f"{lift.get('load', '')} x {reps}".strip() + (
                f", RIR {lift['rir']}" if lift.get("rir") is not None else ""
            ) + (f" ({lift['note']})" if lift.get("note") else "")
        lines.append(
            f"| {ex.name} | {ex.sets} x {ex.rep_target} ({ex.rep_range}) @ {ex.load_label}, RIR {ex.rir} | {logged} |"
        )
    for name, lift in logged_lifts.items():
        if name not in matched:
            lines.append(f"| {lift.get('exercise')} (not in plan) | - | {lift.get('load', '')} x "
                         f"{'/'.join(str(r) for r in lift.get('reps', []))} |")

    cardio = log.get("cardio") or {}
    cardio_plan = training_plan.cardio
    lines += [
        "",
        "## Cardio, steps, water",
        "",
        f"- Cardio: {'done' if cardio.get('done') else 'not logged'}"
        + (f", {cardio['minutes']} min" if cardio.get("minutes") else "")
        + (f" ({cardio['note']})" if cardio.get("note") else "")
        + f". Plan: {cardio_plan.modality}, {cardio_plan.duration}"
        + ("" if cardio_plan.required else " (optional)"),
        f"- Steps: {log.get('steps', 'not logged')} (target {cardio_plan.steps_target})",
        f"- Water: {log.get('water_oz', 'not logged')} oz (target {targets['water_oz']} oz)",
    ]
    if log.get("bodyweight_lb"):
        lines.append(f"- Bodyweight: {log['bodyweight_lb']} lb")
    if log.get("notes"):
        lines += ["", "## Notes", ""] + [f"- {note}" for note in log["notes"]]
    if status.warnings:
        lines += ["", "## Warnings", ""] + [f"- log warning: {warning}" for warning in status.warnings]
    return "\n".join(lines)
