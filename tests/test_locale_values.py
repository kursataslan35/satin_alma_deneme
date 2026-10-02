from datetime import date, datetime

import pytest

from data_sources import parse_csv
from services.locale_values import parse_date, parse_datetime, parse_number
from services.rule_engine import evaluate_records


@pytest.mark.parametrize(("raw", "expected"), [
    ("1.250.000,00", 1_250_000.0),
    ("1.250,5", 1250.5),
    ("75.000", 75_000.0),
    ("1250,50", 1250.5),
    ("0,5", 0.5),
    ("12.5", 12.5),
    ("1450.50", 1450.5),
    ("0.500", 0.5),
    ("₺ 1.250,00", 1250.0),
    ("1.250,00 TL", 1250.0),
    ("1 250 000,00", 1_250_000.0),
    ("-1.250,00", -1250.0),
    ("1.250,00-", -1250.0),
    ("(1.250,00)", -1250.0),
    ("1,250,000.00", 1_250_000.0),
    ("1e3", 1000.0),
    (42, 42.0),
    (3.5, 3.5),
])
def test_parse_number_turkish_default(raw, expected):
    assert parse_number(raw) == expected


def test_parse_number_english_locale_resolves_ambiguous_groups():
    assert parse_number("1,250", "en") == 1250.0
    assert parse_number("75.000", "en") == 75.0
    assert parse_number("1,250", "tr") == 1.25


@pytest.mark.parametrize("raw", ["", "abc", "1.25.0", "1,2,3", "nan", "inf", True, "1.250,00,00"])
def test_parse_number_rejects_invalid_values(raw):
    with pytest.raises((TypeError, ValueError)):
        parse_number(raw)


def test_parse_dates_accept_iso_and_day_first_formats():
    assert parse_date("2024-03-15") == date(2024, 3, 15)
    assert parse_date("15.03.2024") == date(2024, 3, 15)
    assert parse_date("15/03/2024") == date(2024, 3, 15)
    assert parse_date("03/15/2024", "en") == date(2024, 3, 15)
    assert parse_datetime("15.03.2024 14:30") == datetime(2024, 3, 15, 14, 30)
    with pytest.raises(ValueError):
        parse_date("31.02.2024")


def test_numeric_rule_flags_turkish_amounts_and_reports_unparsable_values():
    records = [{"id": 1, "amount": "1.250.000,00"}, {"id": 2, "amount": "75.000"},
               {"id": 3, "amount": "12.000"}, {"id": 4, "amount": "bilinmiyor"},
               {"id": 5, "amount": None}]
    result = evaluate_records(records, rule_type="numeric", field="amount",
                              parameters={"operator": ">", "value": 25000})
    assert [item["id"] for item in result.matches] == [1, 2]
    assert result.skipped_records == 1
    assert result.skipped_examples == ({"row_index": 3, "id": 4, "field": "amount",
                                        "value": "bilinmiyor"},)


def test_date_rule_reads_turkish_dates():
    result = evaluate_records([{"id": 1, "tarih": "15.03.2024"}], rule_type="date", field="tarih",
                              parameters={"operator": "older_than_days", "days": 30},
                              today=date(2024, 6, 1))
    assert result.matched_records == 1
    assert result.skipped_records == 0


def test_rule_locale_can_be_overridden():
    result = evaluate_records([{"id": 1, "amount": "75.000"}], rule_type="numeric", field="amount",
                              parameters={"operator": ">", "value": 1000, "number_locale": "en"})
    assert result.matched_records == 0


def test_semicolon_csv_from_turkish_excel_is_split_into_columns():
    content = "fatura_no;tedarikci;tutar\nF-1;Atlas;1.250,00\n".encode("utf-8-sig")
    records, columns = parse_csv(content, 100, 10)
    assert [column["name"] for column in columns] == ["fatura_no", "tedarikci", "tutar"]
    assert records == [{"fatura_no": "F-1", "tedarikci": "Atlas", "tutar": "1.250,00"}]
