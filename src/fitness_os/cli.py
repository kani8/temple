from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

from .config import DATA_DIR, ensure_data_dirs, load_nutrition, load_profile, load_training
from .checkin import calorie_adjustment, load_bodyweights
from .emailer import send_email
from .menu import FoodItem, fetch_menu_html, load_menu_file, parse_menu, save_menu_file
from .nutrition import build_meal_plan
from .render import render_plan, write_plan
from .training import build_training_plan


def parse_date(value: str | None) -> date:
    return date.today() if value is None else date.fromisoformat(value)


def load_or_fetch_menu(menu_date: date, nutrition: dict, menu_file: Path | None, no_fetch: bool) -> list[FoodItem]:
    if menu_file:
        return load_menu_file(menu_file)

    if no_fetch:
        return []

    saved_path = DATA_DIR / "menus" / f"{menu_date.isoformat()}.json"
    if saved_path.exists():
        return load_menu_file(saved_path)

    html = fetch_menu_html(menu_date, nutrition["cafeteria"]["url_template"])
    menu = parse_menu(html)
    save_menu_file(saved_path, menu)
    return menu


def cmd_daily(args: argparse.Namespace) -> int:
    ensure_data_dirs()
    today = parse_date(args.date)
    profile = load_profile()
    nutrition = load_nutrition()
    training = load_training()

    try:
        menu = load_or_fetch_menu(today, nutrition, args.menu_file, args.no_fetch_menu)
    except RuntimeError as exc:
        print(f"menu warning: {exc}", file=sys.stderr)
        menu = []

    training_plan = build_training_plan(training, profile, today)
    meals, daily_totals = build_meal_plan(nutrition, menu)
    markdown = render_plan(today, profile, nutrition, training, training_plan, meals, daily_totals, menu)
    path = write_plan(markdown, DATA_DIR / "plans", today)

    if args.json:
        payload = {
            "date": today.isoformat(),
            "plan_path": str(path),
            "training": asdict(training_plan),
            "nutrition_totals": daily_totals,
            "menu_items": [asdict(item) for item in menu],
        }
        print(json.dumps(payload, indent=2))
    else:
        print(path)

    if args.email:
        subject = f"Fitness OS Plan - {today.isoformat()} - {training_plan.session_name}"
        send_email(subject, markdown, path)
        print(f"sent email to configured EMAIL_TO for {today.isoformat()}")

    return 0


def cmd_weekly(args: argparse.Namespace) -> int:
    ensure_data_dirs()
    nutrition = load_nutrition()
    log_path = args.bodyweight_log or DATA_DIR / "logs" / "bodyweight.csv"
    entries = load_bodyweights(log_path)
    result = calorie_adjustment(entries, nutrition)
    print(json.dumps(result, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fitness-os")
    sub = parser.add_subparsers(dest="command", required=True)

    daily = sub.add_parser("daily", help="Generate the daily training and nutrition plan.")
    daily.add_argument("--date", help="Date in YYYY-MM-DD. Defaults to today.")
    daily.add_argument("--menu-file", type=Path, help="Use a saved menu JSON file instead of fetching.")
    daily.add_argument("--no-fetch-menu", action="store_true", help="Skip cafeteria fetch and use staple defaults.")
    daily.add_argument("--email", action="store_true", help="Email the generated plan using SMTP env vars.")
    daily.add_argument("--json", action="store_true", help="Print machine-readable output.")
    daily.set_defaults(func=cmd_daily)

    weekly = sub.add_parser("weekly", help="Run the weekly bodyweight calorie titration check.")
    weekly.add_argument("--bodyweight-log", type=Path, help="CSV with columns: date,weight_lb.")
    weekly.set_defaults(func=cmd_weekly)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
