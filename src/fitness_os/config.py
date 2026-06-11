from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_profile() -> dict[str, Any]:
    return load_json(CONFIG_DIR / "profile.json")


def load_nutrition() -> dict[str, Any]:
    return load_json(CONFIG_DIR / "nutrition.json")


def load_training() -> dict[str, Any]:
    return load_json(CONFIG_DIR / "training.json")


def ensure_data_dirs() -> None:
    for path in [DATA_DIR / "menus", DATA_DIR / "logs", DATA_DIR / "plans"]:
        path.mkdir(parents=True, exist_ok=True)

