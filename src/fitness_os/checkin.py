from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from statistics import mean
from typing import Any


@dataclass
class WeightEntry:
    day: date
    weight_lb: float


def load_bodyweights(path: Path) -> list[WeightEntry]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        entries = [
            WeightEntry(date.fromisoformat(row["date"]), float(row["weight_lb"]))
            for row in reader
            if row.get("date") and row.get("weight_lb")
        ]
    return sorted(entries, key=lambda entry: entry.day)


def rolling_average(entries: list[WeightEntry], days: int = 7) -> float | None:
    if len(entries) < days:
        return None
    return round(mean(entry.weight_lb for entry in entries[-days:]), 2)


def prior_rolling_average(entries: list[WeightEntry], days: int = 7) -> float | None:
    if len(entries) < days * 2:
        return None
    return round(mean(entry.weight_lb for entry in entries[-days * 2:-days]), 2)


def calorie_adjustment(entries: list[WeightEntry], nutrition_config: dict[str, Any]) -> dict[str, Any]:
    current_avg = rolling_average(entries)
    prior_avg = prior_rolling_average(entries)
    titration = nutrition_config["titration"]
    current_target = nutrition_config["daily_targets"]["calories"]

    if current_avg is None:
        return {
            "status": "need_more_data",
            "message": "Need at least 7 bodyweight entries before reading the trend.",
            "current_target": current_target,
            "recommended_target": current_target,
        }
    if prior_avg is None:
        return {
            "status": "baseline",
            "message": "Need 14 entries for week-over-week comparison. Keep calories unchanged.",
            "current_7_day_avg": current_avg,
            "current_target": current_target,
            "recommended_target": current_target,
        }

    weekly_gain = round(current_avg - prior_avg, 2)
    adjustment = 0
    if weekly_gain < titration["low_gain_lb_per_week"]:
        adjustment = titration["calorie_step"]
    elif weekly_gain > titration["high_gain_lb_per_week"]:
        adjustment = -titration["calorie_step"]

    recommended = current_target + adjustment
    return {
        "status": "adjust" if adjustment else "hold",
        "prior_7_day_avg": prior_avg,
        "current_7_day_avg": current_avg,
        "weekly_gain_lb": weekly_gain,
        "calorie_adjustment": adjustment,
        "current_target": current_target,
        "recommended_target": recommended,
    }

