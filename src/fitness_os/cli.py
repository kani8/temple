from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

from .config import DATA_DIR, ensure_data_dirs, load_micronutrients, load_nutrition, load_profile, load_training
from .checkin import calorie_adjustment, load_bodyweights
from .digest import build_html, build_text, fetch_prepu
from .emailer import preview_html, send_email
from .menu import FoodItem, fetch_menu_html, load_menu_file, parse_menu, save_menu_file
from .micronutrients import estimate_day
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
        cached_menu = load_menu_file(saved_path)
        if cached_menu:
            return cached_menu

    html = fetch_menu_html(menu_date, nutrition["cafeteria"]["url_template"])
    menu = parse_menu(html)
    if menu:
        save_menu_file(saved_path, menu)
    return menu


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


def cmd_daily(args: argparse.Namespace) -> int:
    ensure_data_dirs()
    today = parse_date(args.date)

    if getattr(args, "digest_debug", False):
        return cmd_digest_debug(today)
    profile = load_profile()
    nutrition = load_nutrition()
    training = load_training()
    micronutrients = load_micronutrients()

    try:
        menu = load_or_fetch_menu(today, nutrition, args.menu_file, args.no_fetch_menu)
    except RuntimeError as exc:
        print(f"menu warning: {exc}", file=sys.stderr)
        menu = []

    training_plan = build_training_plan(training, profile, today)
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
            subject = f"Morning brief - {today.isoformat()} - {training_plan.session_name}"
            html_body = build_html(today, markdown, prepu, training_plan.session_name)
            text_body = build_text(today, markdown, prepu)
            if prepu is None:
                print("digest warning: Prep-U section unavailable, sending fitness only", file=sys.stderr)
        else:
            subject = f"Fitness OS Plan - {today.isoformat()} - {training_plan.session_name}"
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
