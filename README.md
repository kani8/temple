# Fitness OS

Daily training and nutrition planner. Current phase (from 2026-09-23): recomp from 185 lb @ ~30% BF toward 175-180 lb @ 20-22% BF, rebuilding strength from re-baselined loads.

The system generates:

- A daily seven-day PPL training plan with exact target loads, reps, RIR, and week-32 strength milestones.
- An Uber-first macro plan targeting 2,500 calories, 190g protein, 280g carbs, 68g fat, and 35-45g fiber.
- A Bon Appetit cafeteria menu ingest for Uber HQ, plus on-site packaged Evolve protein shakes.
- Ingredient-based micronutrient estimates, priority gap fixes, and confidence signals.
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

It compares the latest 7-day average against the previous 7-day average and recommends `+150`, `0`, or `-150` calories using the titration rules in `config/nutrition.json`. For the recomp, losing faster than 1 lb/week adds 150 calories and losing less than 0.25 lb/week removes 150.

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

`.github/workflows/daily-plan.yml` sends the email at 6:00am Pacific, in both daylight and standard time. GitHub often starts scheduled runs hours late, so the workflow is triggered early (09:17, 10:47 and 12:17 UTC) and waits until 6:00am Pacific before sending. The first run to start sends the email and writes `data/sent/YYYY-MM-DD`; the backup runs see that file and skip. Manual runs send straight away.

The workflow:

1. Checks out the repo.
2. Installs the package.
3. Generates the daily plan and commits `data/menus` and `data/plans`.
4. Waits until 6:00am Pacific (scheduled runs only).
5. Emails it using SMTP secrets and records the send in `data/sent`.

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

## Food Preferences

Set in `config/nutrition.json` under `cafeteria`:

- `exclude_patterns`: hard excludes checked against item names and ingredients (currently: no pork, including ham, bacon, salami, chorizo, sausage, etc.). `exclude_exceptions` whitelists phrases like "chicken sausage", and `exclude_exempt_names` exempts items named plant-based or vegan.
- `keyword_weights`, `vegetarian_protein_penalty` and `vegetarian_meal_penalty`: prefer chicken (and other meat or fish) over veggie proteins. A dish counts as a veggie protein when it has 12g+ protein and none of `meat_keywords` appear in its name or ingredients.

## Wellness Bar Protein Smoothies

Protein smoothies come from the Wellness station on the Mission Bay 3 cafe page (`wellness_url_template`), cached in `data/menus/wellness/YYYY-MM-DD.json`. When a wellness-bar protein smoothie is on the menu, it replaces the Evolve shakes; Evolve is only used on days the smoothie isn't available. `planning.max_protein_drinks_per_day` caps how many the protein top-up adds.

## Micronutrients

`config/micronutrients.json` defines daily targets for calcium, iron, magnesium, potassium, zinc, selenium, folate, choline, vitamins A/C/D/E/K, and B vitamins.

Bon Appetit does not expose full micronutrient labels in the parsed menu fields, so `src/fitness_os/micronutrients.py` estimates likely coverage from visible item names, ingredients, and packaged-food assumptions. The daily plan marks each nutrient with a confidence label and lists the ingredient signals that drove the estimate. Treat this as a gap detector, not lab-grade nutrition tracking.
