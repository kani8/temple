# Fitness OS

Daily training and nutrition planner for a lean bulk from 167 lb to 195-200 lb.

The system generates:

- A daily seven-day PPL training plan with exact target loads, reps, RIR, and week-32 strength milestones.
- An Uber-first macro plan targeting 2,900 calories, 190g protein, 385g carbs, 67g fat, and 35-45g fiber.
- A Bon Appetit cafeteria menu ingest for Uber HQ, plus on-site packaged Evolve protein shakes.
- A 6am email workflow through GitHub Actions.

## Local Setup

```bash
cd /Users/kvatsa/fitness-os
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
fitness-os daily --date 2026-06-10 --no-fetch-menu
```

Generated plans are written to `data/plans/YYYY-MM-DD.md`.

## Weekly Check-In

Create `data/logs/bodyweight.csv`:

```csv
date,weight_lb
2026-06-10,167.0
2026-06-11,167.4
```

Then run:

```bash
fitness-os weekly
```

It compares the latest 7-day average against the previous 7-day average and recommends `+150`, `0`, or `-150` calories using the titration rules in `config/nutrition.json`.

## Email Setup

The mailer uses SMTP so it can work with Gmail app passwords, Fastmail, SendGrid SMTP, Resend SMTP, or another provider.

Set these environment variables locally or as GitHub Actions repository secrets:

```bash
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=...
SMTP_PASSWORD=...
EMAIL_FROM=you@example.com
EMAIL_TO=you@example.com
```

Then run:

```bash
fitness-os daily --email
```

## GitHub Actions

`.github/workflows/daily-plan.yml` runs at `13:00 UTC`, which is 6:00am Pacific during daylight saving time. In standard time, change it to `14:00 UTC` if you want exactly 6:00am.

The workflow:

1. Checks out the repo.
2. Installs the package.
3. Generates the daily plan.
4. Emails it using SMTP secrets.
5. Commits `data/menus` and `data/plans` back to the repo.

## Calibration

The starting weights in `config/training.json` are conservative seed values. Replace each `baseline_lb` after your first real session on that machine.

Use this rule:

- If you beat the target reps with RIR 1-2, increase the baseline.
- If you miss the lower bound or form degrades, lower the baseline.
- Machine stacks differ, so the logbook beats the estimate.

## Cafeteria Scraping

The scraper uses a two-tier pipeline:

1. Tier 1: extract only visibly listed menu items from the rendered Bon Appetit daypart markup.
2. Tier 2: enrich those visible item IDs/names with embedded nutrition and ingredient JSON.

Hidden nutrition records are excluded from meal planning. This prevents reusable or stale nutrition components from appearing in a plan when they are not visible on the actual menu.

By default `config/nutrition.json` sets `planning.home_fallback_allowed` to `false`, so normal plans use Uber cafeteria items and on-site packaged options only. Turn it on only if you want emergency home foods like whey, rice, eggs, or potatoes to fill gaps when the cafeteria data is unavailable.
