from __future__ import annotations

import html
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, asdict
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


@dataclass
class FoodItem:
    name: str
    item_id: str | None = None
    calories: float | None = None
    protein_g: float | None = None
    carbs_g: float | None = None
    fat_g: float | None = None
    saturated_fat_g: float | None = None
    trans_fat_g: float | None = None
    cholesterol_mg: float | None = None
    fiber_g: float | None = None
    sugar_g: float | None = None
    sodium_mg: float | None = None
    omega3_mg: float | None = None
    ingredients: str | None = None
    serving: str | None = None
    station: str | None = None
    visible: bool = False
    source: str = "unknown"

    def has_macros(self) -> bool:
        return all(
            value is not None
            for value in [self.calories, self.protein_g, self.carbs_g, self.fat_g]
        )

    def scaled(self, factor: float) -> "FoodItem":
        data = asdict(self)
        data["name"] = f"{self.name} x{factor:g}"
        for key in [
            "calories",
            "protein_g",
            "carbs_g",
            "fat_g",
            "saturated_fat_g",
            "trans_fat_g",
            "cholesterol_mg",
            "fiber_g",
            "sugar_g",
            "sodium_mg",
            "omega3_mg",
        ]:
            if data[key] is not None:
                data[key] = round(data[key] * factor, 1)
        return FoodItem(**data)


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_script = False
        self.scripts: list[str] = []
        self._script_parts: list[str] = []
        self.text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "script":
            self.in_script = True
            self._script_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self.in_script = False
            self.scripts.append("".join(self._script_parts))
            self._script_parts = []

    def handle_data(self, data: str) -> None:
        if self.in_script:
            self._script_parts.append(data)
        else:
            cleaned = " ".join(data.split())
            if cleaned:
                self.text_parts.append(cleaned)


def fetch_menu_html(menu_date: date, url_template: str) -> str:
    url = url_template.format(date=menu_date.isoformat())
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "fitness-os/0.1 (+https://github.com/kvatsa/fitness-os)",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not fetch cafeteria menu: {exc}") from exc


def extract_json_objects(script: str) -> list[Any]:
    objects: list[Any] = []
    decoder = json.JSONDecoder()
    for idx, char in enumerate(script):
        if char not in "[{":
            continue
        try:
            parsed, _ = decoder.raw_decode(script[idx:])
        except json.JSONDecodeError:
            continue
        objects.append(parsed)
    return objects


def walk_json(value: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        lower_keys = {str(k).lower() for k in value.keys()}
        if (
            "id" in lower_keys and "label" in lower_keys
            or
            {"name", "calories"} <= lower_keys
            or {"label", "calories"} <= lower_keys
            or {"label", "nutrition_details"} <= lower_keys
        ):
            found.append(value)
        for child in value.values():
            found.extend(walk_json(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(walk_json(child))
    return found


def number_from(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"-?\d+(\.\d+)?", str(value).replace(",", ""))
    return float(match.group(0)) if match else None


def normalize_name(value: str) -> str:
    value = html.unescape(value).lower()
    value = strip_tags(value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def item_from_mapping(data: dict[str, Any]) -> FoodItem | None:
    lowered = {str(k).lower(): v for k, v in data.items()}
    name = lowered.get("name") or lowered.get("label") or lowered.get("title")
    details = lowered.get("nutrition_details") if isinstance(lowered.get("nutrition_details"), dict) else {}

    def detail_value(key: str) -> Any:
        raw = details.get(key) if isinstance(details, dict) else None
        return raw.get("value") if isinstance(raw, dict) else raw

    def detail_unit(key: str) -> str:
        raw = details.get(key) if isinstance(details, dict) else None
        return str(raw.get("unit") or "") if isinstance(raw, dict) else ""

    nutrition = lowered.get("nutrition") if isinstance(lowered.get("nutrition"), dict) else {}
    calories = lowered.get("calories") or lowered.get("kcal") or detail_value("calories") or nutrition.get("kcal")
    if not name or calories is None:
        return None

    serving_value = lowered.get("serving") or lowered.get("serving_size") or detail_value("servingSize")
    serving = None
    if serving_value:
        serving = f"{serving_value}{detail_unit('servingSize')}".strip()

    return FoodItem(
        name=html.unescape(str(name)).strip(),
        item_id=str(lowered.get("id") or "").strip() or None,
        calories=number_from(calories),
        protein_g=number_from(lowered.get("protein") or lowered.get("protein_g") or detail_value("proteinContent")),
        carbs_g=number_from(
            lowered.get("carbohydrates")
            or lowered.get("carbs")
            or lowered.get("total_carbohydrate")
            or lowered.get("carbs_g")
            or detail_value("carbohydrateContent")
        ),
        fat_g=number_from(lowered.get("fat") or lowered.get("total_fat") or lowered.get("fat_g") or detail_value("fatContent")),
        saturated_fat_g=number_from(lowered.get("saturated_fat") or lowered.get("saturated_fat_g") or detail_value("saturatedFatContent")),
        trans_fat_g=number_from(lowered.get("trans_fat") or lowered.get("trans_fat_g") or detail_value("transFatContent")),
        cholesterol_mg=number_from(lowered.get("cholesterol") or lowered.get("cholesterol_mg") or detail_value("cholesterolContent")),
        fiber_g=number_from(lowered.get("fiber") or lowered.get("dietary_fiber") or lowered.get("fiber_g") or detail_value("fiberContent")),
        sugar_g=number_from(lowered.get("sugars") or lowered.get("sugar") or lowered.get("sugar_g") or detail_value("sugarContent")),
        sodium_mg=number_from(lowered.get("sodium") or lowered.get("sodium_mg") or detail_value("sodiumContent")),
        ingredients=strip_tags(str(lowered.get("ingredients") or "")).strip() or None,
        serving=serving,
        station=strip_tags(str(lowered.get("station") or lowered.get("category") or "")).strip() or None,
        visible=False,
        source="cafeteria-json",
    )


def strip_tags(value: str) -> str:
    return re.sub(r"<[^>]+>", "", html.unescape(value))


class VisibleMenuParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.current_station: str | None = None
        self.in_station_title = False
        self.station_parts: list[str] = []
        self.current_item_id: str | None = None
        self.in_item_title = False
        self.item_parts: list[str] = []
        self.visible_items: list[tuple[str, str | None, str | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        classes = set((attr.get("class") or "").split())
        if tag == "h3" and "site-panel__daypart-station-title" in classes:
            self.in_station_title = True
            self.station_parts = []
        if tag == "div" and attr.get("data-js") == "site-panel__daypart-item":
            self.current_item_id = attr.get("data-id")
        if tag == "button" and attr.get("data-js") == "site-panel__daypart-item-title":
            self.in_item_title = True
            self.item_parts = []
            self.current_item_id = attr.get("data-id") or self.current_item_id

    def handle_endtag(self, tag: str) -> None:
        if tag == "h3" and self.in_station_title:
            self.current_station = " ".join(" ".join(self.station_parts).split())
            self.in_station_title = False
        if tag == "button" and self.in_item_title:
            title = " ".join(" ".join(self.item_parts).split())
            if title:
                self.visible_items.append((title, self.current_station, self.current_item_id))
            self.in_item_title = False
            self.item_parts = []
        if tag == "div" and self.current_item_id and not self.in_item_title:
            # The next visible item block will set a new id.
            pass

    def handle_data(self, data: str) -> None:
        if self.in_station_title:
            self.station_parts.append(data)
        elif self.in_item_title:
            self.item_parts.append(data)


def extract_visible_menu_items(html_text: str) -> list[FoodItem]:
    parser = VisibleMenuParser()
    parser.feed(html_text)
    visible: list[FoodItem] = []
    seen: set[tuple[str, str | None, str | None]] = set()
    for title, station, item_id in parser.visible_items:
        if re.search(r"^(nutrition|collapse|expand|today|this week|subscript)", title, re.I):
            continue
        key = (normalize_name(title), station, item_id)
        if key in seen:
            continue
        seen.add(key)
        visible.append(
            FoodItem(
                name=html.unescape(title).strip(),
                item_id=item_id,
                station=f"@{station}" if station and not station.startswith("@") else station,
                visible=True,
                source="visible-menu",
            )
        )
    return visible


def parse_menu(html_text: str) -> list[FoodItem]:
    parser = TextExtractor()
    parser.feed(html_text)

    visible_items = extract_visible_menu_items(html_text)
    visible_ids = {item.item_id for item in visible_items if item.item_id}
    visible_by_name = {normalize_name(item.name): item for item in visible_items}

    items: list[FoodItem] = []
    seen: set[str] = set()
    for script in parser.scripts:
        if "calories" not in script.lower():
            continue
        for obj in extract_json_objects(script):
            for candidate in walk_json(obj):
                item = item_from_mapping(candidate)
                if not item:
                    continue
                visible_match = None
                if item.item_id and item.item_id in visible_ids:
                    visible_match = next((vis for vis in visible_items if vis.item_id == item.item_id), None)
                if visible_match is None:
                    visible_match = visible_by_name.get(normalize_name(item.name))
                if visible_match is None:
                    continue
                item.visible = True
                item.name = visible_match.name
                item.station = visible_match.station or item.station
                key = item.item_id or f"{normalize_name(item.name)}|{item.station or ''}"
                if key not in seen:
                    seen.add(key)
                    items.append(item)

    if items:
        return items

    return visible_items


def load_menu_file(path: Path) -> list[FoodItem]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [FoodItem(**entry) for entry in raw]


def save_menu_file(path: Path, items: list[FoodItem]) -> None:
    path.write_text(
        json.dumps([asdict(item) for item in items], indent=2, sort_keys=True),
        encoding="utf-8",
    )
