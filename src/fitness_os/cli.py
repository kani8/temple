from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import date, timedelta
from pathlib import Path

from .config import DATA_DIR, ensure_data_dirs, load_micronutrients, load_nutrition, load_profile, load_training
from .checkin import calorie_adjustment, load_bodyweights
from .digest import build_html, build_text, fetch_prepu
from .emailer import preview_html, send_email
from .menu import FoodItem, fetch_menu_html, load_menu_file, parse_menu, parse_wellness_items, save_menu_file
from .micronutrients import estimate_day
from .nutrition import build_meal_plan, is_drink, is_excluded, meal_candidates
from .render import render_plan, short_text, write_plan
from .selection import load_selection, selection_path, selection_totals
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
        cached_menu = load_menu_file(saved_path)
        if cached_menu:
            return cached_menu

    html = fetch_menu_html(menu_date, nutrition["cafeteria"]["url_template"])
    menu = parse_menu(html)
    if menu:
        save_menu_file(saved_path, menu)
    return menu


def load_or_fetch_wellness(menu_date: date, nutrition: dict) -> list[FoodItem]:
    """Wellness-bar items (protein smoothies) live on a separate cafe page."""
    cafeteria = nutrition["cafeteria"]
    url_template = cafeteria.get("wellness_url_template")
    if not url_template:
        return []

    saved_path = DATA_DIR / "menus" / "wellness" / f"{menu_date.isoformat()}.json"
    if saved_path.exists():
        cached = load_menu_file(saved_path)
        if cached:
            return cached

    html = fetch_menu_html(menu_date, url_template)
    items = parse_wellness_items(html, cafeteria.get("wellness_station", "Wellness"))
    if items:
        saved_path.parent.mkdir(parents=True, exist_ok=True)
        save_menu_file(saved_path, items)
    return items


def cmd_digest_debug(today: date) -> int:
    """Explain precisely why the Prep-U section is or isn't available."""
    import os
    import sys as _sys
    from .digest import DEFAULT_PREPU_DIRS, PrepUError, _python, fetch_prepu_strict, find_prepu_repo

    print("Prep-U digest diagnostics")
    print(f"  date            : {today.isoformat()}")
    print(f"  PREPU_REPO env  : {os.getenv('PREPU_REPO') or '(unset)'}")
    for path in DEFAULT_PREPU_DIRS:
        marker = path / "platform" / "scripts" / "daily_brief.py"
        print(f"  fallback path   : {path}  [{'found' if marker.exists() else 'missing'}]")
    repo = find_prepu_repo()
    print(f"  resolved repo   : {repo or '(none)'}")
    print(f"  this python     : {_sys.executable}")
    print(f"  subprocess uses : {_python() or '(none)'}")
    print()

    try:
        data = fetch_prepu_strict(today)
    except PrepUError as exc:
        print(f"FAILED: {exc}")
        print()
        print("Most common causes:")
        print("  - PREPU_REPO not set, or pointing somewhere without platform/scripts/daily_brief.py")
        print("  - the repo lives outside ~/projects/ (pass PREPU_REPO explicitly)")
        print("  - daily_brief.py raising - run it directly to see the traceback")
        return 1

    print("OK")
    print(f"  week      : {data.get('week')}  phase {data.get('phase')}")
    print(f"  topics    : {', '.join(data.get('topics') or []) or '(none)'}")
    print(f"  rest day  : {data.get('rest_day')}")
    print(f"  questions : {len(data.get('questions') or [])}")
    print(f"  streak    : {data.get('streak')} days, {data.get('solved')} solved")
    print(f"  html      : {len(data.get('html') or '')} bytes")
    return 0


def load_day_menu(today: date, nutrition: dict, menu_file: Path | None = None, no_fetch: bool = False) -> list[FoodItem]:
    """Cafeteria menu plus the wellness bar, fetched once and cached in data/menus."""
    try:
        menu = load_or_fetch_menu(today, nutrition, menu_file, no_fetch)
    except RuntimeError as exc:
        print(f"menu warning: {exc}", file=sys.stderr)
        menu = []

    if not menu_file and not no_fetch:
        try:
            menu += load_or_fetch_wellness(today, nutrition)
        except RuntimeError as exc:
            print(f"wellness menu warning: {exc}", file=sys.stderr)
    return menu


def cmd_daily(args: argparse.Namespace) -> int:
    ensure_data_dirs()
    today = parse_date(args.date)

    if getattr(args, "digest_debug", False):
        return cmd_digest_debug(today)
    profile = load_profile()
    nutrition = load_nutrition()
    training = load_training()
    micronutrients = load_micronutrients()

    menu = load_day_menu(today, nutrition, args.menu_file, args.no_fetch_menu)

    training_plan = build_training_plan(training, profile, today)
    selection = None if args.no_selection else load_selection(selection_path(DATA_DIR, today), menu, nutrition)
    if selection:
        meals, daily_totals = selection.meals, selection_totals(selection)
    else:
        meals, daily_totals = build_meal_plan(nutrition, menu)
    planned_items = [item for meal in meals for item in meal.items]
    micronutrient_report = estimate_day(planned_items, micronutrients)
    markdown = render_plan(
        today,
        profile,
        nutrition,
        training,
        training_plan,
        meals,
        daily_totals,
        menu,
        micronutrient_report,
        nutritionist_note=selection.summary if selection else None,
    )
    path = write_plan(markdown, DATA_DIR / "plans", today)

    if args.json:
        payload = {
            "date": today.isoformat(),
            "plan_path": str(path),
            "training": asdict(training_plan),
            "nutrition_totals": daily_totals,
            "micronutrients": micronutrient_report,
            "menu_items": [asdict(item) for item in menu],
        }
        print(json.dumps(payload, indent=2))
    else:
        print(path)

    if args.preview:
        out = preview_html(
            f"Fitness OS Plan - {today.isoformat()} - {training_plan.session_name}",
            markdown,
            Path(args.preview),
        )
        print(f"preview written to {out}")

    if args.email or args.digest:
        prepu = fetch_prepu(today) if args.digest else None
        if args.digest:
            subject = f"[Temple] Morning brief - {today.isoformat()} - {training_plan.session_name}"
            html_body = build_html(today, markdown, prepu, training_plan.session_name)
            text_body = build_text(today, markdown, prepu)
            if prepu is None:
                print("digest warning: Prep-U section unavailable, sending fitness only", file=sys.stderr)
        else:
            subject = f"[Temple] Fitness OS Plan - {today.isoformat()} - {training_plan.session_name}"
            html_body = None
            text_body = markdown

        # The digest already contains the whole plan in its body, so attaching
        # the source Markdown adds nothing and only invites clients to render it
        # inline. Keep the attachment for the plain --email path, where it is a
        # useful copy, and allow --attach to force it back on.
        attach = path if (args.email and not args.digest) or args.attach else None

        send_email(subject, text_body, attach, html_body=html_body)
        print(f"sent email to configured EMAIL_TO for {today.isoformat()}")

    return 0


def cmd_candidates(args: argparse.Namespace) -> int:
    """Print the day's usable menu for the nutritionist: no pork, no coffee drinks."""
    ensure_data_dirs()
    today = parse_date(args.date)
    nutrition = load_nutrition()
    training_plan = build_training_plan(load_training(), load_profile(), today)
    menu = load_day_menu(today, nutrition)
    usable = [
        item for item in menu
        if item.has_macros() and not is_drink(item) and not is_excluded(item, nutrition)
    ]
    packaged = [FoodItem(**item, source="onsite-packaged") for item in nutrition.get("onsite_packaged", [])]

    targets = nutrition["daily_targets"]
    print(f"# Menu candidates - {today.isoformat()}")
    print(f"Training: {training_plan.session_name} (week {training_plan.week}, day {training_plan.day_number})")
    print(
        f"Daily targets: {targets['calories']} cal, {targets['protein_g']}P, {targets['carbs_g']}C, "
        f"{targets['fat_g']}F, {targets['fiber_g_min']}-{targets['fiber_g_max']}g fiber, "
        f"sodium soft max {targets['sodium_mg_soft_max']}mg"
    )
    for name, meal in nutrition["meal_targets"].items():
        print(f"  {name}: " + ", ".join(f"{k} {v}" for k, v in meal.items()))
    excluded = [item for item in menu if item.has_macros() and is_excluded(item, nutrition)]
    print(f"Excluded as pork: {len(excluded)} items")
    print()
    print("| Item | Station | Cal | P | C | F | Fiber | Sodium | Serving | Ingredients |")
    print("|---|---|---:|---:|---:|---:|---:|---:|---|---|")
    for item in sorted(usable, key=lambda i: (i.station or "", i.name)) + packaged:
        print(
            f"| {item.name} | {item.station or item.source} | {item.calories:g} | {item.protein_g:g} | "
            f"{item.carbs_g:g} | {item.fat_g:g} | {item.fiber_g or 0:g} | {item.sodium_mg or 0:g} | "
            f"{item.serving or ''} | {short_text(item.ingredients, 120)} |"
        )
    if not usable:
        print()
        print("No cafeteria menu for this date (weekend, holiday, or fetch failed).")
    return 0


def cmd_prefetch(args: argparse.Namespace) -> int:
    """Cache upcoming weekday menus so the nutritionist can plan before the morning run."""
    ensure_data_dirs()
    nutrition = load_nutrition()
    start = parse_date(args.date)
    for offset in range(args.days + 1):
        day = start + timedelta(days=offset)
        if day.weekday() >= 5:
            continue
        menu = load_day_menu(day, nutrition)
        print(f"{day.isoformat()}: {len(menu)} items")
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
    daily.add_argument("--digest", action="store_true",
                       help="Email one combined brief: Prep-U study plan + fitness plan. Implies --email.")
    daily.add_argument("--digest-debug", action="store_true",
                       help="Diagnose the Prep-U half of the digest and exit. Sends nothing.")
    daily.add_argument("--preview", metavar="PATH",
                       help="Write the rendered HTML email to PATH instead of sending. No SMTP needed.")
    daily.add_argument("--attach", action="store_true",
                       help="Attach the plan's source Markdown. Off by default for --digest.")
    daily.add_argument("--json", action="store_true", help="Print machine-readable output.")
    daily.add_argument("--no-selection", action="store_true",
                       help="Ignore data/selections/<date>.json and use the planner's own menu pick.")
    daily.set_defaults(func=cmd_daily)

    candidates = sub.add_parser("candidates", help="Print the day's usable menu items and targets.")
    candidates.add_argument("--date", help="Date in YYYY-MM-DD. Defaults to today.")
    candidates.set_defaults(func=cmd_candidates)

    prefetch = sub.add_parser("prefetch", help="Cache weekday menus for today and the next N days.")
    prefetch.add_argument("--date", help="Start date in YYYY-MM-DD. Defaults to today.")
    prefetch.add_argument("--days", type=int, default=3)
    prefetch.set_defaults(func=cmd_prefetch)

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
