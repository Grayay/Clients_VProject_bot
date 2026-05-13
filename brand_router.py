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

    return _current_rule(
        [
            rule
            for rule in rules
            if rule.get("is_active") and normalize_brand(rule.get("brand_pattern")) == normalized_brand
        ]
    )


def find_exact_brand_rules(brand_name: str, rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized_brand = normalize_brand(brand_name)
    if not normalized_brand:
        return []

    return [
        rule
        for rule in rules
        if rule.get("is_active") and normalize_brand(rule.get("brand_pattern")) == normalized_brand
    ]


def _rule_sort_key(rule: dict[str, Any]) -> tuple[str, str, int]:
    return (
        str(rule.get("updated_at") or ""),
        str(rule.get("created_at") or ""),
        int(rule.get("id") or 0),
    )


def _current_rule(rules: list[dict[str, Any]]) -> dict[str, Any] | None:
    return max(rules, key=_rule_sort_key) if rules else None


def _single_current_rule(rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rule = _current_rule(rules)
    return [rule] if rule else []


def current_active_brand_rules(rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    current_by_brand: dict[str, dict[str, Any]] = {}
    for rule in rules:
        if not rule.get("is_active"):
            continue
        normalized_brand = normalize_brand(rule.get("brand_pattern"))
        if not normalized_brand:
            continue

        current = current_by_brand.get(normalized_brand)
        if current is None or _rule_sort_key(rule) > _rule_sort_key(current):
            current_by_brand[normalized_brand] = rule

    return sorted(
        current_by_brand.values(),
        key=lambda rule: (normalize_brand(rule.get("brand_pattern")), int(rule.get("id") or 0)),
    )


def deactivate_duplicate_active_brand_rules(database: Database) -> int:
    rules = database.list_active_brand_rules()
    keep_rule_ids = {int(rule["id"]) for rule in current_active_brand_rules(rules)}
    deactivate_rule_ids = [
        int(rule["id"])
        for rule in rules
        if normalize_brand(rule.get("brand_pattern")) and int(rule["id"]) not in keep_rule_ids
    ]
    return database.deactivate_brand_rules(deactivate_rule_ids)


def _find_bookers_in_rules(brand_name: str, rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized_brand = normalize_brand(brand_name)
    if not normalized_brand:
        return []

    normalized_rules = [
        (rule, normalize_brand(rule.get("brand_pattern")))
        for rule in rules
        if rule.get("is_active")
    ]
    normalized_rules = [(rule, pattern) for rule, pattern in normalized_rules if pattern]

    exact_matches = [
        rule
        for rule, pattern in normalized_rules
        if normalized_brand == pattern
    ]
    if exact_matches:
        return _single_current_rule(exact_matches)

    partial_matches = [
        rule
        for rule, pattern in normalized_rules
        if normalized_brand in pattern or pattern in normalized_brand
    ]
    return _single_current_rule(partial_matches)


def _find_booker_in_rules(brand_name: str, rules: list[dict[str, Any]]) -> dict[str, Any] | None:
    bookers = _find_bookers_in_rules(brand_name, rules)
    return bookers[0] if bookers else None


def find_bookers_in_rules(brand_name: str, rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _find_bookers_in_rules(brand_name, rules)


def find_booker_for_brand(brand_name: str) -> dict[str, Any] | None:
    config = load_config()
    database = Database(config.database_path)
    database.init()
    return _find_booker_in_rules(brand_name, database.list_active_brand_rules())


def find_bookers_for_brand(brand_name: str) -> list[dict[str, Any]]:
    config = load_config()
    database = Database(config.database_path)
    database.init()
    return _find_bookers_in_rules(brand_name, database.list_active_brand_rules())
