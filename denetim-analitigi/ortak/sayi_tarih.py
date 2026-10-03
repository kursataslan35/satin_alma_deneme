"""Locale-aware parsing of numbers and dates found in uploaded audit data.

Source files exported from Turkish systems use "1.250.000,00" for numbers and
"15.03.2024" for dates. Python's float()/fromisoformat() reject or silently
misread those values ("75.000" becomes 75.0), which makes controls miss
exceptions. Every control path parses through this module instead.
"""

from __future__ import annotations

import math
import os
import re
from datetime import date, datetime
from typing import Any


SUPPORTED_LOCALES = {"tr", "en"}
THOUSANDS_SEPARATOR = {"tr": ".", "en": ","}
_CURRENCY = re.compile(r"^(?:₺|TL|TRY|\$|USD|€|EUR|£|GBP)\s*|\s*(?:₺|TL|TRY|\$|USD|€|EUR|£|GBP)$",
                       re.IGNORECASE)
_SPACES = re.compile(r"[\s  ']")
_DIGITS = re.compile(r"^[0-9.,]+$")
_LOCAL_DATE = re.compile(
    r"^(\d{1,2})([./-])(\d{1,2})\2(\d{4})(?:[ T](\d{1,2}):(\d{2})(?::(\d{2}))?)?$")


def default_locale() -> str:
    locale = os.environ.get("AUDITAI_LOCALE", "tr").strip().lower()
    return locale if locale in SUPPORTED_LOCALES else "tr"


def _resolve(locale: str | None) -> str:
    if locale is None:
        return default_locale()
    if locale not in SUPPORTED_LOCALES:
        raise ValueError(f"unsupported locale: {locale}")
    return locale


def _check_groups(text: str, separator: str) -> str:
    parts = text.split(separator)
    if not 1 <= len(parts[0]) <= 3 or any(len(part) != 3 for part in parts[1:]):
        raise ValueError("invalid digit grouping")
    return "".join(parts)


def _normalize_digits(body: str, locale: str) -> str:
    has_dot, has_comma = "." in body, "," in body
    if has_dot and has_comma:
        decimal = "." if body.rfind(".") > body.rfind(",") else ","
        thousands = "," if decimal == "." else "."
        if body.count(decimal) > 1:
            raise ValueError("multiple decimal separators")
        whole, fraction = body.split(decimal)
        return _check_groups(whole, thousands) + "." + fraction
    if not has_dot and not has_comma:
        return body
    separator = "." if has_dot else ","
    if body.count(separator) > 1:
        return _check_groups(body, separator)
    whole, fraction = body.split(separator)
    # "75.000" / "1,250" are ambiguous: a single group of exactly three digits is
    # a thousands separator only in the locale that uses that character for it.
    ambiguous = len(fraction) == 3 and 1 <= len(whole) <= 3 and not whole.startswith("0")
    if ambiguous and separator == THOUSANDS_SEPARATOR[locale]:
        return whole + fraction
    return (whole or "0") + "." + fraction


def parse_number(value: Any, locale: str | None = None) -> float:
    """Return a finite float or raise ValueError/TypeError."""
    if isinstance(value, bool):
        raise ValueError("booleans are not numbers")
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        if value is None:
            raise TypeError("value is missing")
        text = _CURRENCY.sub("", str(value).strip())
        text = _SPACES.sub("", text)
        negative = False
        if text.startswith("(") and text.endswith(")"):
            negative, text = True, text[1:-1]
        if text.endswith("-"):
            negative, text = True, text[:-1]
        elif text[:1] in {"-", "+"}:
            negative, text = text[0] == "-", text[1:]
        if text and _DIGITS.fullmatch(text):
            number = float(_normalize_digits(text, _resolve(locale)))
        else:
            number = float(text)
        number = -number if negative else number
    if not math.isfinite(number):
        raise ValueError("number must be finite")
    return number


def parse_datetime(value: Any, locale: str | None = None) -> datetime:
    """Parse ISO 8601 or local day-first dates ("15.03.2024", "15/03/2024 14:30")."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    if value is None:
        raise TypeError("value is missing")
    text = str(value).strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        pass
    match = _LOCAL_DATE.fullmatch(text)
    if not match:
        raise ValueError(f"unrecognized date: {text[:40]}")
    first, separator, second, year = int(match[1]), match[2], int(match[3]), int(match[4])
    month_first = separator in {"/", "-"} and _resolve(locale) == "en"
    month, day = (first, second) if month_first else (second, first)
    hour, minute, second_value = (int(match[5] or 0), int(match[6] or 0), int(match[7] or 0))
    return datetime(year, month, day, hour, minute, second_value)


def parse_date(value: Any, locale: str | None = None) -> date:
    return parse_datetime(value, locale).date()
