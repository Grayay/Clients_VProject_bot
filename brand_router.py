import re
from typing import Any

from config import load_config
from database import Database


LEGAL_SUFFIXES = {"ооо", "ип", "зао", "ао", "llc", "ltd", "inc"}


def normalize_brand(value: str | None) -> str:
    text = str(value or "").lower().replace("ё", "е").strip()
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    text = text.replace("_", " ")
    tokens = [token for token in text.split() if token not in LEGAL_SUFFIXES]
    return " ".join(tokens)


def find_exact_brand_rule(brand_name: str, rules: list[dict[str, Any]]) -> dict[str, Any] | None:
    normalized_brand = normalize_brand(brand_name)
    if not normalized_brand:
        return None

    for rule in rules:
        if rule.get("is_active") and normalize_brand(rule.get("brand_pattern")) == normalized_brand:
            return rule

    return None


def _find_booker_in_rules(brand_name: str, rules: list[dict[str, Any]]) -> dict[str, Any] | None:
    normalized_brand = normalize_brand(brand_name)
    if not normalized_brand:
        return None

    normalized_rules = [
        (rule, normalize_brand(rule.get("brand_pattern")))
        for rule in rules
        if rule.get("is_active")
    ]
    normalized_rules = [(rule, pattern) for rule, pattern in normalized_rules if pattern]

    for rule, pattern in normalized_rules:
        if normalized_brand == pattern:
            return rule

    for rule, pattern in normalized_rules:
        if normalized_brand in pattern or pattern in normalized_brand:
            return rule

    return None


def find_booker_for_brand(brand_name: str) -> dict[str, Any] | None:
    config = load_config()
    database = Database(config.database_path)
    database.init()
    return _find_booker_in_rules(brand_name, database.list_active_brand_rules())
