from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from .menu import FoodItem
from .nutrition import Meal, macro_delta, totals
from .training import TrainingPlan, strength_milestones


def fmt_num(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:.1f}"


def short_text(value: str | None, limit: int = 180) -> str:
    if not value:
        return ""
    cleaned = " ".join(value.split()).replace("|", "/")
    return cleaned if len(cleaned) <= limit else cleaned[: limit - 3] + "..."


def nutrition_table(items: list[FoodItem]) -> str:
    rows = ["| Item | Station | Cal | P | C | F | Fiber | Sodium | Omega-3 |", "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for item in items:
        rows.append(
            "| "
            + " | ".join(
                [
                    item.name,
                    item.station or item.source,
                    fmt_num(item.calories or 0),
                    fmt_num(item.protein_g or 0),
                    fmt_num(item.carbs_g or 0),
                    fmt_num(item.fat_g or 0),
                    fmt_num(item.fiber_g or 0),
                    fmt_num(item.sodium_mg or 0),
                    fmt_num(item.omega3_mg or 0),
                ]
            )
            + " |"
        )
    subtotal = totals(items)
    rows.append(
        f"| **Subtotal** |  | **{fmt_num(subtotal['calories'])}** | **{fmt_num(subtotal['protein_g'])}** | **{fmt_num(subtotal['carbs_g'])}** | **{fmt_num(subtotal['fat_g'])}** | **{fmt_num(subtotal['fiber_g'])}** | **{fmt_num(subtotal['sodium_mg'])}** | **{fmt_num(subtotal['omega3_mg'])}** |"
    )
    return "\n".join(rows)


def label_table(items: list[FoodItem]) -> str:
    rows = [
        "| Item | Serving | Sat Fat | Trans Fat | Chol. | Sugars | Ingredients |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for item in items:
        rows.append(
            "| "
            + " | ".join(
                [
                    item.name,
                    item.serving or "",
                    f"{fmt_num(item.saturated_fat_g or 0)}g",
                    f"{fmt_num(item.trans_fat_g or 0)}g",
                    f"{fmt_num(item.cholesterol_mg or 0)}mg",
                    f"{fmt_num(item.sugar_g or 0)}g",
                    short_text(item.ingredients),
                ]
            )
            + " |"
        )
    return "\n".join(rows)


def micronutrient_table(report: dict[str, Any]) -> str:
    rows = [
        "| Nutrient | Estimate | Target | Coverage | Confidence |",
        "|---|---:|---:|---:|---|",
    ]
    for row in report["rows"]:
        rows.append(
            f"| {row['label']} | {fmt_num(row['amount'])}{row['unit']} | {fmt_num(row['target'])}{row['unit']} | {fmt_num(row['percent'])}% | {row['confidence']} |"
        )
    return "\n".join(rows)


def micronutrient_gap_table(report: dict[str, Any]) -> str:
    gaps = report.get("gaps", [])[:8]
    if not gaps:
        return "No estimated micronutrient gaps below the configured threshold."
    rows = ["| Priority Gap | Coverage | Uber-first fix |", "|---|---:|---|"]
    for row in gaps:
        rows.append(f"| {row['label']} | {fmt_num(row['percent'])}% | {row['fix']} |")
    return "\n".join(rows)


def micronutrient_evidence_table(report: dict[str, Any]) -> str:
    notes = [
        note for note in report.get("item_notes", [])
        if note.get("reasons") and note["reasons"][0] != "no meaningful ingredient match"
    ][:10]
    if not notes:
        return "No ingredient matches were strong enough to explain micronutrient estimates."
    rows = ["| Planned Item | Confidence | Ingredient signals |", "|---|---:|---|"]
    for note in notes:
        rows.append(
            f"| {note['item']} | {fmt_num(float(note['confidence']) * 100)}% | {short_text(', '.join(note['reasons']), 140)} |"
        )
    return "\n".join(rows)


def render_plan(
    today: date,
    profile: dict[str, Any],
    nutrition_config: dict[str, Any],
    training_config: dict[str, Any],
    training_plan: TrainingPlan,
    meals: list[Meal],
    daily_totals: dict[str, float],
    menu: list[FoodItem],
    micronutrient_report: dict[str, Any] | None = None,
) -> str:
    targets = nutrition_config["daily_targets"]
    delta = macro_delta(daily_totals, targets)
    menu_status = (
        f"{len([item for item in menu if item.has_macros()])} cafeteria items with macros parsed"
        if menu
        else "no cafeteria menu parsed"
    )

    lines = [
        f"# Fitness OS Daily Plan - {today.isoformat()}",
        "",
        f"Program day: **{training_plan.day_number}** | Week: **{training_plan.week}** | Bodyweight goal: **{profile['goal_bodyweight_lb_min']}-{profile['goal_bodyweight_lb_max']} lb @ {profile['goal_body_fat_percent_min']}-{profile['goal_body_fat_percent_max']}% BF**",
        "",
        "## Today's Non-Negotiables",
        "",
        "- Hit protein within 10g.",
        "- Log every working set with load, reps, and RIR.",
        "- Stop knee-aggravating movements above 3/10 pain.",
        f"- Drink at least {targets['water_oz']} oz water.",
        "",
        "## Training",
        "",
        f"Session: **{training_plan.session_name}**",
        "",
        f"Warm-up: {training_plan.warmup}",
        "",
        "| Exercise | Prescription | Load | RIR | Week 32 Target | Notes |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for ex in training_plan.exercises:
        lines.append(
            f"| {ex.name} | {ex.sets} x {ex.rep_target} target ({ex.rep_range} range) | {ex.load_label} | {ex.rir} | {ex.week_32_goal} | {ex.notes} |"
        )

    lines.extend(
        [
            "",
            f"Cardio: {training_plan.cardio}",
            "",
            "### Session Strength Milestones",
            "",
            "| Exercise | W1 | W4 | W8 | W16 | W24 | W32 |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in strength_milestones(training_config, training_plan.session_key):
        lines.append(
            f"| {row['exercise']} | {row['week_1']} | {row['week_4']} | {row['week_8']} | {row['week_16']} | {row['week_24']} | {row['week_32']} |"
        )

    lines.extend(
        [
            "",
            "## Nutrition",
            "",
            f"Menu ingest: {menu_status}.",
            "",
            f"Targets: **{targets['calories']} cal**, **{targets['protein_g']}P**, **{targets['carbs_g']}C**, **{targets['fat_g']}F**, **{targets['fiber_g_min']}-{targets['fiber_g_max']}g fiber**.",
            "",
        ]
    )
    for meal in meals:
        lines.extend(
            [
                f"### {meal.name}",
                "",
                meal.note,
                "",
                nutrition_table(meal.items),
                "",
                label_table(meal.items),
                "",
            ]
        )

    lines.extend(
        [
            "### Daily Macro Check",
            "",
            "| Metric | Actual | Target | Delta |",
            "|---|---:|---:|---:|",
            f"| Calories | {fmt_num(daily_totals['calories'])} | {targets['calories']} | {fmt_num(delta['calories'])} |",
            f"| Protein | {fmt_num(daily_totals['protein_g'])}g | {targets['protein_g']}g | {fmt_num(delta['protein_g'])}g |",
            f"| Carbs | {fmt_num(daily_totals['carbs_g'])}g | {targets['carbs_g']}g | {fmt_num(delta['carbs_g'])}g |",
            f"| Fat | {fmt_num(daily_totals['fat_g'])}g | {targets['fat_g']}g | {fmt_num(delta['fat_g'])}g |",
            f"| Fiber | {fmt_num(daily_totals['fiber_g'])}g | {targets['fiber_g_min']}-{targets['fiber_g_max']}g | {fmt_num(daily_totals['fiber_g'] - targets['fiber_g_max'])}g vs max |",
            f"| Sodium | {fmt_num(daily_totals['sodium_mg'])}mg | {targets['sodium_mg_soft_max']}mg soft max | {fmt_num(daily_totals['sodium_mg'] - targets['sodium_mg_soft_max'])}mg |",
            f"| Omega-3 | {fmt_num(daily_totals['omega3_mg'])}mg | track only |  |",
            "",
        ]
    )

    if micronutrient_report:
        lines.extend(
            [
                "### Micronutrient Estimate",
                "",
                "Ingredient-based estimates from visible Uber menu items and packaged-food assumptions. Use this to catch likely gaps; macros, sodium, fiber, and ingredients are stronger signals than these micronutrient estimates.",
                "",
                micronutrient_gap_table(micronutrient_report),
                "",
                micronutrient_table(micronutrient_report),
                "",
                "### Micronutrient Evidence",
                "",
                micronutrient_evidence_table(micronutrient_report),
                "",
            ]
        )

    lines.extend(
        [
            "## Evening Log",
            "",
            "- Morning bodyweight:",
            "- Workout completed? Y/N:",
            "- Knee pain 0-10:",
            "- Sleep last night:",
            "- Energy/mood 1-10:",
            "- Macro adherence notes:",
        ]
    )
    return "\n".join(lines) + "\n"


def write_plan(markdown: str, output_dir: Path, today: date) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{today.isoformat()}.md"
    path.write_text(markdown, encoding="utf-8")
    return path
