"""Column profiling of persisted source records and data-quality check suggestions.

Profiling answers "what is actually in this file?" before any control runs:
the real type of each column (CSV cells all arrive as text), how complete and
unique it is, value ranges, formats and anomalies an auditor should know about.
"""

from __future__ import annotations

import re
import statistics
from collections import Counter
from datetime import date, datetime, timezone
from typing import Any, Iterable, Mapping

from services.locale_values import parse_datetime, parse_number


TYPE_THRESHOLD = 0.95
MAX_EXAMPLES = 5
MAX_ACCEPTED_VALUES = 12
KEY_LIKE_UNIQUE_PCT = 95
RARE_VALUE_MIN_ROWS = 50
BOOLEAN_VALUES = {"true", "false", "evet", "hayır", "hayir", "yes", "no", "e", "h", "y", "n"}
_HAS_DATE_SEPARATOR = re.compile(r"\d[-./]\d")


def _is_empty(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _classify(value: Any) -> tuple[str, Any]:
    """Return the semantic kind of one non-empty cell and its parsed value."""
    if isinstance(value, bool):
        return "boolean", value
    if isinstance(value, (int, float)):
        return "number", float(value)
    if isinstance(value, datetime):
        return "date", value
    if isinstance(value, date):
        return "date", datetime(value.year, value.month, value.day)
    text = str(value).strip()
    if text.casefold() in BOOLEAN_VALUES:
        return "boolean", text
    try:
        return "number", parse_number(text)
    except (TypeError, ValueError):
        pass
    if _HAS_DATE_SEPARATOR.search(text):
        try:
            return "date", parse_datetime(text)
        except (TypeError, ValueError):
            pass
    return "text", text


def _pattern(text: str) -> str:
    shape = re.sub(r"[A-Za-zÇĞİÖŞÜçğıöşü]", "A", re.sub(r"\d", "9", text))
    return shape if len(shape) <= 30 else shape[:27] + "..."


def _round(value: float) -> float:
    return round(value, 4)


def _numeric_stats(numbers: list[float]) -> dict[str, Any]:
    ordered = sorted(numbers)
    stats = {"min": _round(ordered[0]), "max": _round(ordered[-1]),
             "mean": _round(statistics.fmean(ordered)), "median": _round(statistics.median(ordered)),
             "sum": _round(sum(ordered)),
             "negative_count": sum(1 for item in ordered if item < 0),
             "zero_count": sum(1 for item in ordered if item == 0),
             "integer_only": all(item.is_integer() for item in ordered), "outlier_count": 0}
    if len(ordered) >= 8:
        q1, _, q3 = statistics.quantiles(ordered, n=4)
        spread = q3 - q1
        low, high = q1 - 1.5 * spread, q3 + 1.5 * spread
        stats.update(outlier_count=sum(1 for item in ordered if item < low or item > high),
                     outlier_bounds=[_round(low), _round(high)])
    return stats


def _date_stats(dates: list[datetime], today: date) -> dict[str, Any]:
    days = sorted(item.date() for item in dates)
    return {"min": days[0].isoformat(), "max": days[-1].isoformat(),
            "future_count": sum(1 for item in days if item > today),
            "weekend_count": sum(1 for item in days if item.weekday() >= 5)}


def _text_stats(raw_values: list[str]) -> dict[str, Any]:
    lengths = [len(item) for item in raw_values]
    variants: dict[str, set[str]] = {}
    for item in raw_values:
        variants.setdefault(item.strip().casefold(), set()).add(item)
    groups = [sorted(values) for values in variants.values() if len(values) > 1]
    return {"min_length": min(lengths), "max_length": max(lengths),
            "whitespace_issue_count": sum(1 for item in raw_values if item != item.strip()),
            "variant_group_count": len(groups), "variant_examples": groups[:MAX_EXAMPLES],
            "top_patterns": [{"pattern": pattern, "count": count} for pattern, count in
                             Counter(_pattern(item.strip()) for item in raw_values).most_common(5)]}


def profile_column(name: str, values: list[Any], *, today: date) -> dict[str, Any]:
    total = len(values)
    present = [value for value in values if not _is_empty(value)]
    classified = [_classify(value) for value in present]
    kinds = Counter(kind for kind, _ in classified)
    filled = len(present)
    distinct = len({str(value).strip() for value in present})
    inferred = "empty"
    if filled:
        kind, count = kinds.most_common(1)[0]
        inferred = kind if count / filled >= TYPE_THRESHOLD else "mixed"
        if inferred == "number" and all(parsed.is_integer() for item_kind, parsed in classified
                                        if item_kind == "number"):
            inferred = "integer"
    identifier_type = inferred in {"text", "integer"}
    profile: dict[str, Any] = {
        "name": name, "inferred_type": inferred, "type_breakdown": dict(kinds),
        "row_count": total, "filled_count": filled, "empty_count": total - filled,
        "filled_pct": round(filled / total * 100, 2) if total else 0.0,
        "distinct_count": distinct,
        "unique_pct": round(distinct / filled * 100, 2) if filled else 0.0,
        "is_key_candidate": identifier_type and filled == total and total > 1 and distinct == filled,
        "is_key_like": identifier_type and total > 1 and filled / total * 100 >= TYPE_THRESHOLD * 100
        and distinct / filled * 100 >= KEY_LIKE_UNIQUE_PCT,
        "repeated_value_count": filled - distinct,
        "top_values": [{"value": value, "count": count} for value, count in
                       Counter(str(value).strip() for value in present).most_common(5)],
    }
    if distinct <= MAX_ACCEPTED_VALUES:
        value_counts = Counter(str(value).strip() for value in present)
        profile["distinct_values"] = sorted(value_counts)
        profile["rare_values"] = sorted(value for value, count in value_counts.items()
                                        if count == 1 and filled >= RARE_VALUE_MIN_ROWS)
    base_kind = "number" if inferred in {"number", "integer"} else inferred
    if base_kind in {"number", "date"}:
        nonconforming = [value for value, (kind, _) in zip(present, classified) if kind != base_kind]
        profile["nonconforming_count"] = len(nonconforming)
        profile["nonconforming_examples"] = [str(item)[:60] for item in nonconforming[:MAX_EXAMPLES]]
    numbers = [parsed for kind, parsed in classified if kind == "number"]
    dates = [parsed for kind, parsed in classified if kind == "date"]
    texts = [str(value) for value, (kind, _) in zip(present, classified) if kind == "text"]
    if base_kind == "number" and numbers:
        profile["numeric"] = _numeric_stats(numbers)
    if base_kind == "date" and dates:
        profile["dates"] = _date_stats(dates, today)
    if texts and base_kind in {"text", "mixed"}:
        profile["text"] = _text_stats(texts)
    profile["issues"] = _issues(profile)
    return profile


def _issues(profile: Mapping[str, Any]) -> list[dict[str, str]]:
    issues = []

    def add(level: str, message: str) -> None:
        issues.append({"level": level, "message": message})

    if profile["inferred_type"] == "empty":
        add("high", "Sütun tamamen boş")
        return issues
    if profile["empty_count"]:
        add("medium" if profile["filled_pct"] >= 95 else "high",
            f"{profile['empty_count']} boş değer (doluluk %{profile['filled_pct']})")
    if profile["is_key_like"] and profile["repeated_value_count"]:
        add("high", f"Anahtar benzeri sütunda {profile['repeated_value_count']} tekrar eden değer")
    if profile.get("rare_values"):
        add("medium", "Tek sefer geçen değer(ler): " + ", ".join(profile["rare_values"][:MAX_EXAMPLES]))
    if profile["inferred_type"] == "mixed":
        add("high", "Karışık veri tipi: " + ", ".join(
            f"{kind} {count}" for kind, count in profile["type_breakdown"].items()))
    if profile.get("nonconforming_count"):
        label = "tarih" if profile["inferred_type"] == "date" else "sayı"
        add("high", f"{profile['nonconforming_count']} değer {label} olarak okunamıyor")
    numeric = profile.get("numeric", {})
    if numeric.get("negative_count"):
        add("medium", f"{numeric['negative_count']} negatif değer")
    if numeric.get("outlier_count"):
        add("low", f"{numeric['outlier_count']} aykırı değer (IQR)")
    dates = profile.get("dates", {})
    if dates.get("future_count"):
        add("medium", f"{dates['future_count']} ileri tarihli kayıt")
    text = profile.get("text", {})
    if text.get("whitespace_issue_count"):
        add("medium", f"{text['whitespace_issue_count']} değerde baş/son boşluk")
    if text.get("variant_group_count"):
        add("medium", f"{text['variant_group_count']} değer farklı yazımlarla tekrarlanıyor "
                      "(büyük/küçük harf veya boşluk)")
    return issues


def profile_records(records: Iterable[Mapping[str, Any]], column_names: Iterable[str] = (),
                    *, today: date | None = None) -> dict[str, Any]:
    rows = [dict(record) for record in records]
    names = list(dict.fromkeys(column_names))
    for row in rows:
        names.extend(key for key in row if key not in names)
    today = today or datetime.now(timezone.utc).date()
    row_keys = Counter(tuple((name, str(row.get(name))) for name in names) for row in rows)
    columns = [profile_column(name, [row.get(name) for row in rows], today=today) for name in names]
    return {"row_count": len(rows), "column_count": len(names),
            "duplicate_row_count": sum(count - 1 for count in row_keys.values() if count > 1),
            "key_candidates": [column["name"] for column in columns if column["is_key_candidate"]],
            "issue_count": sum(len(column["issues"]) for column in columns),
            "columns": columns}


def suggest_quality_checks(profile: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Propose quality checks from what the data already looks like; a person approves them."""
    suggestions = []

    def suggest(column, check_type, severity, reason, parameters=None):
        suggestions.append({"name": f"{column['name']} · {check_type}", "field_name": column["name"],
                            "check_type": check_type, "severity": severity,
                            "parameters": parameters or {}, "reason": reason})

    for column in profile["columns"]:
        inferred = column["inferred_type"]
        if inferred == "empty":
            continue
        if column["is_key_like"]:
            suggest(column, "not_null", "critical", "Anahtar benzeri sütun: her satırda dolu olmalı")
            suggest(column, "unique", "warning",
                    f"{column['repeated_value_count']} tekrar eden değer var; tekrarlar denetim "
                    "kuralıyla incelenir, bu yüzden kapıyı durdurmaz" if column["repeated_value_count"]
                    else "Şu an tekil; yeni yüklemelerde tekrar eden anahtar uyarı versin")
        elif column["filled_pct"] >= 95:
            suggest(column, "not_null", "warning",
                    f"{column['empty_count']} boş değer var; bunlar istisna olarak listelenir"
                    if column["empty_count"] else "Sütun tamamen dolu; boş değer gelirse uyarı versin")
        if inferred in {"number", "integer", "date"}:
            kind = "date" if inferred == "date" else "number"
            suggest(column, "type_conformance", "critical",
                    f"Sütun {'tarih' if kind == 'date' else 'sayı'}; okunamayan değerler "
                    "kontrolleri yanıltır", {"type": kind})
        numeric = column.get("numeric")
        if numeric and numeric["min"] >= 0 and not column["is_key_candidate"]:
            suggest(column, "numeric_range", "warning", "Tüm değerler sıfır veya pozitif",
                    {"min": 0})
        text = column.get("text", {})
        if (inferred == "text" and 1 < column["distinct_count"] <= MAX_ACCEPTED_VALUES
                and column["filled_count"] >= 3 * column["distinct_count"]
                and not text.get("variant_group_count") and not text.get("whitespace_issue_count")):
            # Values seen only once in a large file are more likely typos than valid codes.
            values = [item for item in column["distinct_values"] if item not in column["rare_values"]]
            reason = f"Yalnızca {column['distinct_count']} farklı değer var"
            if column["rare_values"]:
                reason += "; tek sefer geçen " + ", ".join(column["rare_values"]) + " listeye alınmadı"
            suggest(column, "accepted_values", "warning", reason, {"values": values})
    return suggestions
