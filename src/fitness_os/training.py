from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from math import floor
from typing import Any


@dataclass
class ExercisePlan:
    key: str
    name: str
    sets: int
    rep_target: int
    rep_range: str
    load_label: str
    rir: str
    failure: bool
    week_32_goal: str
    notes: str


@dataclass
class CardioPlan:
    required: bool
    modality: str
    duration: str
    intensity: str
    heart_rate_target: str
    timing: str
    steps_target: str
    notes: str


@dataclass
class TrainingPlan:
    session_key: str
    session_name: str
    week: int
    day_number: int
    exercises: list[ExercisePlan]
    warmup: str
    cardio: CardioPlan


def program_day(program_start: date, today: date) -> int:
    return max(0, (today - program_start).days)


def planned_load(exercise: dict[str, Any], week: int) -> float:
    baseline = float(exercise["baseline_lb"])
    goal = float(exercise["goal_week_32_lb"])
    increment = float(exercise["increment_lb"])
    progress = min(max(week - 1, 0), 31) / 31
    raw = baseline + ((goal - baseline) * progress)
    step = abs(increment) if increment else 5
    rounded = round(raw / step) * step
    if increment >= 0:
        return min(max(rounded, baseline), goal)
    return max(min(rounded, baseline), goal)


def rep_target(exercise: dict[str, Any], week: int) -> int:
    rep_min = int(exercise["rep_min"])
    rep_max = int(exercise["rep_max"])
    span = rep_max - rep_min + 1
    return min(rep_max, rep_min + ((week - 1) % span))


def load_label(exercise: dict[str, Any], load: float) -> str:
    suffix = " assistance" if exercise.get("assistance") else ""
    per_hand = " each hand" if exercise.get("per_hand") else ""
    if load == 0:
        base = "bodyweight"
    elif float(load).is_integer():
        base = f"{int(load)} lb"
    else:
        base = f"{load:g} lb"
    return f"{base}{per_hand}{suffix}"


def session_display_name(session_key: str) -> str:
    return session_key.replace("_", " ").title()


def cardio_for_session(session_key: str, day_number: int) -> CardioPlan:
    if session_key.startswith("push") or session_key.startswith("pull"):
        return CardioPlan(
            required=True,
            modality="Incline treadmill walk",
            duration="20-25 min",
            intensity="Zone 2; 10-12% grade at 3.0-3.5 mph",
            heart_rate_target="125-140 bpm",
            timing="Immediately post-lift or later same day",
            steps_target="8,000-10,000 total daily steps",
            notes="Nasal-breathing pace. Add speed only if HR stays below target.",
        )
    if day_number % 7 == 5:
        return CardioPlan(
            required=True,
            modality="Bike or rower intervals",
            duration="10 rounds: 30s hard / 90s easy",
            intensity="Hard rounds at RPE 8-9; easy rounds at RPE 2-3",
            heart_rate_target="Recover below 140 bpm before the next hard round when possible",
            timing="Post-lower or separate session 6+ hours from lifting",
            steps_target="8,000-10,000 total daily steps",
            notes="Skip intervals if knee pain is above 3/10, sleep was poor, or leg performance is dropping.",
        )
    return CardioPlan(
        required=False,
        modality="Easy bike cooldown",
        duration="10-15 min",
        intensity="Zone 1-2; easy flush pace",
        heart_rate_target="110-130 bpm",
        timing="Post-lower",
        steps_target="8,000-10,000 total daily steps",
        notes="Keep this easy. The step target is the required cardio anchor today.",
    )


def build_training_plan(training: dict[str, Any], profile: dict[str, Any], today: date) -> TrainingPlan:
    start = date.fromisoformat(profile["program_start_date"])
    day = program_day(start, today)
    week = floor(day / 7) + 1
    rotation = training["rotation"]
    session_key = rotation[day % len(rotation)]
    exercise_keys = training["sessions"][session_key]
    exercises: list[ExercisePlan] = []

    for idx, key in enumerate(exercise_keys):
        ex = training["exercise_targets"][key]
        load = planned_load(ex, week)
        target = rep_target(ex, week)
        failure = idx in {len(exercise_keys) - 1}
        notes = "last set can reach RIR 0 today" if failure else "stop with clean reps in reserve"
        exercises.append(
            ExercisePlan(
                key=key,
                name=ex["name"],
                sets=int(ex["sets"]),
                rep_target=target,
                rep_range=f'{ex["rep_min"]}-{ex["rep_max"]}',
                load_label=load_label(ex, load),
                rir="0 on final set" if failure else training["global_rules"]["default_rir"],
                failure=failure,
                week_32_goal=load_label(ex, float(ex["goal_week_32_lb"])),
                notes=notes,
            )
        )

    warmup = "5 min easy machine warm-up, then 1-2 ramp sets for first compound."
    if session_key.startswith("legs"):
        warmup = training["global_rules"]["lower_warmup"]

    return TrainingPlan(
        session_key=session_key,
        session_name=session_display_name(session_key),
        week=week,
        day_number=day + 1,
        exercises=exercises,
        warmup=warmup,
        cardio=cardio_for_session(session_key, day),
    )


def strength_milestones(training: dict[str, Any], session_key: str) -> list[dict[str, str]]:
    milestones = []
    for key in training["sessions"][session_key]:
        ex = training["exercise_targets"][key]
        row = {"exercise": ex["name"]}
        for week in [1, 4, 8, 16, 24, 32]:
            row[f"week_{week}"] = load_label(ex, planned_load(ex, week))
        milestones.append(row)
    return milestones
