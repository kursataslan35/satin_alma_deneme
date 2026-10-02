"""Deterministic, side-effect-free audit rule evaluation."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timezone
import operator
from typing import Any, Iterable, Mapping

from services.locale_values import parse_date, parse_number


COMPARATORS = {
    ">": operator.gt, ">=": operator.ge, "<": operator.lt,
    "<=": operator.le, "==": operator.eq, "!=": operator.ne,
}
RULE_TYPES = {"numeric", "text", "date", "null", "duplicate", "comparison"}
MAX_SKIPPED_EXAMPLES = 20
TEXT_OPERATORS = {"equals", "not_equals", "contains", "not_contains", "starts_with", "ends_with"}


class InvalidRule(ValueError):
    """Raised when a rule definition cannot be evaluated safely."""


@dataclass(frozen=True)
class EvaluationResult:
    scanned_records: int
    matches: list[dict[str, Any]]
    total_matches: int | None = None
    skipped_records: int = 0
    skipped_examples: tuple[dict[str, Any], ...] = ()

    @property
    def matched_records(self) -> int:
        return self.total_matches if self.total_matches is not None else len(self.matches)


def _number(value: Any, locale: str | None = None) -> float:
    return parse_number(value, locale)


def _date(value: Any, locale: str | None = None) -> date:
    return parse_date(value, locale)


def _compare(left: Any, operation: str, right: Any) -> bool:
    try:
        comparator = COMPARATORS[operation]
    except KeyError as exc:
        raise InvalidRule(f"unsupported comparison operator: {operation}") from exc
    return comparator(left, right)


def _match_record(record: Mapping[str, Any], rule_type: str, field: str, params: Mapping[str, Any], *, today: date) -> bool:
    value = record.get(field)
    operation = str(params.get("operator", "=="))
    locale = params.get("number_locale")

    if rule_type == "null":
        if operation not in {"is_null", "not_null"}:
            raise InvalidRule("null operator must be is_null or not_null")
        empty = value is None or (isinstance(value, str) and not value.strip())
        return empty if operation == "is_null" else not empty

    if value is None:
        return False
    if rule_type == "numeric":
        return _compare(_number(value, locale), operation, _number(params["value"], locale))
    if rule_type == "text":
        left, right = str(value), str(params.get("value", ""))
        if not params.get("case_sensitive", False):
            left, right = left.casefold(), right.casefold()
        operations = {
            "equals": lambda: left == right, "not_equals": lambda: left != right,
            "contains": lambda: right in left, "not_contains": lambda: right not in left,
            "starts_with": lambda: left.startswith(right), "ends_with": lambda: left.endswith(right),
        }
        if operation not in operations:
            raise InvalidRule(f"unsupported text operator: {operation}")
        return operations[operation]()
    if rule_type == "date":
        left = _date(value, locale)
        if operation in {"older_than_days", "newer_than_days"}:
            age = (today - left).days
            days = int(params["days"])
            return age > days if operation == "older_than_days" else age < days
        return _compare(left, operation, _date(params["value"], locale))
    if rule_type == "comparison":
        right_field = str(params.get("right_field", "")).strip()
        if not right_field:
            raise InvalidRule("comparison requires right_field")
        right = record.get(right_field)
        if right is None:
            return False
        if params.get("value_type", "numeric") == "numeric":
            value, right = _number(value, locale), _number(right, locale)
        return _compare(value, operation, right)
    raise InvalidRule(f"unsupported rule type: {rule_type}")


def _validate(rule_type: str, field: str, params: Mapping[str, Any]) -> None:
    if rule_type not in RULE_TYPES:
        raise InvalidRule(f"unsupported rule type: {rule_type}")
    if params.get("number_locale") not in (None, "tr", "en"):
        raise InvalidRule("number_locale must be tr or en")
    if rule_type == "duplicate":
        return
    if not field:
        raise InvalidRule("field is required")
    operation = str(params.get("operator", "=="))
    if rule_type in {"numeric", "comparison"} and operation not in COMPARATORS:
        raise InvalidRule(f"unsupported comparison operator: {operation}")
    if rule_type == "numeric":
        if "value" not in params:
            raise InvalidRule("numeric rule requires value")
        try:
            _number(params["value"], params.get("number_locale"))
        except (TypeError, ValueError) as exc:
            raise InvalidRule("numeric rule value must be numeric") from exc
    if rule_type == "text" and operation not in TEXT_OPERATORS:
        raise InvalidRule(f"unsupported text operator: {operation}")
    if rule_type == "null" and operation not in {"is_null", "not_null"}:
        raise InvalidRule("null operator must be is_null or not_null")
    if rule_type == "date":
        if operation in {"older_than_days", "newer_than_days"}:
            try:
                if int(params["days"]) < 0:
                    raise ValueError
            except (KeyError, TypeError, ValueError) as exc:
                raise InvalidRule("date age rule requires non-negative days") from exc
        elif operation in COMPARATORS:
            try:
                _date(params["value"], params.get("number_locale"))
            except (KeyError, TypeError, ValueError) as exc:
                raise InvalidRule("date comparison requires an ISO date value") from exc
        else:
            raise InvalidRule(f"unsupported date operator: {operation}")
    if rule_type == "comparison" and not str(params.get("right_field", "")).strip():
        raise InvalidRule("comparison requires right_field")


def evaluate_records(records: Iterable[Mapping[str, Any]], *, rule_type: str, field: str = "",
                     parameters: Mapping[str, Any] | None = None, today: date | None = None,
                     max_matches: int = 1_000) -> EvaluationResult:
    """Evaluate records without executing user-provided code or SQL."""
    if max_matches < 1:
        raise InvalidRule("max_matches must be positive")
    params = dict(parameters or {})
    _validate(rule_type, field, params)
    materialized = [dict(record) for record in records]
    if rule_type == "duplicate":
        fields = params.get("fields") or ([field] if field else [])
        if not fields or not all(isinstance(item, str) and item for item in fields):
            raise InvalidRule("duplicate rule requires fields")
        def normalize(value):
            if isinstance(value, str):
                value = value.strip()
                if params.get("normalize_numeric"):
                    try:
                        return _number(value, params.get("number_locale"))
                    except ValueError:
                        pass
                if not params.get("case_sensitive", False):
                    return value.casefold()
            return value

        keys = [tuple(normalize(record.get(name)) for name in fields) for record in materialized]
        counts = Counter(keys)
        all_matches = [record for record, key in zip(materialized, keys)
                       if counts[key] > 1 and not all(value is None for value in key)]
        return EvaluationResult(len(materialized), all_matches[:max_matches], len(all_matches))

    if not field:
        raise InvalidRule("field is required")
    current_date = today or datetime.now(timezone.utc).date()
    matches = []
    total_matches = 0
    skipped_examples = []
    skipped = 0
    for index, record in enumerate(materialized):
        try:
            if _match_record(record, rule_type, field, params, today=current_date):
                total_matches += 1
                if len(matches) < max_matches:
                    matches.append(record)
        except (TypeError, ValueError, KeyError):
            # Invalid source values do not abort a full audit population, but they
            # are counted so the population is never silently reported as complete.
            skipped += 1
            if len(skipped_examples) < MAX_SKIPPED_EXAMPLES:
                skipped_examples.append({"row_index": index, "id": record.get("id"),
                                         "field": field, "value": _example(record.get(field))})
    return EvaluationResult(len(materialized), matches, total_matches,
                            skipped, tuple(skipped_examples))


def _example(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    text = str(value)
    return text if len(text) <= 100 else text[:97] + "..."
