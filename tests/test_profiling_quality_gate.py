from datetime import date
from pathlib import Path

import pytest

from app import create_app
from data_sources import parse_csv
from models import Alarm, AuditArea, QualityCheck, QualityCheckRun, RuleExecution, db
from services.profiling import profile_records, suggest_quality_checks


SAMPLE = Path(__file__).resolve().parents[1] / "docs" / "ornek_veri" / "satin_alma_faturalar.csv"


@pytest.fixture()
def app(tmp_path):
    application = create_app({"TESTING": True, "AUTH_REQUIRED": False,
                              "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'gate.db'}"})
    with application.app_context():
        db.session.add(AuditArea(name="Satın alma"))
        db.session.commit()
    return application


@pytest.fixture()
def client(app):
    return app.test_client()


def _sample_profile():
    records, columns = parse_csv(SAMPLE.read_bytes(), 10_000, 100)
    return profile_records(records, [item["name"] for item in columns], today=date(2026, 10, 2))


def _column(profile, name):
    return next(item for item in profile["columns"] if item["name"] == name)


def _upload(client, content=None, name="satin_alma_faturalar.csv"):
    response = client.post("/api/data-sources/upload", data={
        "audit_area_id": "1", "name": "Faturalar",
        "file": (SAMPLE.open("rb") if content is None else __import__("io").BytesIO(content), name),
    }, content_type="multipart/form-data")
    assert response.status_code == 201, response.get_json()
    return response.get_json()["source_id"]


def test_profile_detects_real_types_and_planted_problems():
    profile = _sample_profile()
    assert (profile["row_count"], profile["column_count"]) == (200, 9)
    assert _column(profile, "tutar")["inferred_type"] == "number"
    assert _column(profile, "fatura_tarihi")["inferred_type"] == "date"
    assert _column(profile, "fatura_no")["inferred_type"] == "text"

    tutar = _column(profile, "tutar")
    assert tutar["nonconforming_examples"] == ["bilinmiyor"]
    assert tutar["numeric"]["negative_count"] == 1
    assert not tutar["is_key_candidate"]

    tarih = _column(profile, "fatura_tarihi")
    assert tarih["nonconforming_examples"] == ["31.02.2024"]
    assert tarih["dates"]["future_count"] == 1

    fatura_no = _column(profile, "fatura_no")
    assert fatura_no["is_key_like"] and fatura_no["repeated_value_count"] == 1
    assert _column(profile, "tedarikci_adi")["text"]["variant_group_count"] == 1
    assert _column(profile, "para_birimi")["rare_values"] == ["TL"]
    assert _column(profile, "siparis_no")["empty_count"] == 3


def test_suggestions_do_not_bake_bad_values_into_accepted_lists():
    suggestions = {(item["field_name"], item["check_type"]): item
                   for item in suggest_quality_checks(_sample_profile())}
    assert suggestions[("para_birimi", "accepted_values")]["parameters"]["values"] == ["EUR", "TRY", "USD"]
    assert ("tedarikci_adi", "accepted_values") not in suggestions
    assert suggestions[("tutar", "type_conformance")]["severity"] == "critical"
    assert suggestions[("fatura_no", "not_null")]["severity"] == "critical"
    assert suggestions[("fatura_no", "unique")]["severity"] == "warning"
    assert ("tutar", "numeric_range") not in suggestions


def test_identifier_digits_are_not_profiled_as_dates():
    profile = profile_records([{"kod": "20240315"}, {"kod": "20240316"}])
    assert profile["columns"][0]["inferred_type"] == "integer"


def test_profile_suggest_save_and_gate_block_then_warn(app, client):
    source_id = _upload(client)
    body = client.get(f"/api/data-sources/{source_id}/profile").get_json()
    assert body["profile"]["row_count"] == 200
    suggestions = [item for item in body["suggestions"] if not item["already_exists"]]
    created = client.post(f"/api/data-sources/{source_id}/quality-checks/bulk", json={"checks": [
        {key: item[key] for key in ("name", "check_type", "field_name", "severity", "parameters")}
        for item in suggestions]})
    assert created.status_code == 201
    again = client.get(f"/api/data-sources/{source_id}/profile").get_json()["suggestions"]
    assert all(item["already_exists"] for item in again)

    gate = client.post(f"/api/data-sources/{source_id}/quality-checks/run").get_json()
    assert gate["status"] == "blocked"
    assert set(gate["blocking"]) == {"tutar · type_conformance", "fatura_tarihi · type_conformance"}

    rule = client.post("/api/rules", json={"name": "Yüksek tutarlı fatura", "field_name": "tutar",
                                           "operator": ">", "threshold_value": 100000,
                                           "severity": "high", "audit_area_id": 1,
                                           "data_source_id": source_id}).get_json()
    blocked = client.post(f"/api/rules/{rule['id']}/run").get_json()
    assert blocked["status"] == "blocked"
    assert blocked["quality_status"] == "blocked"
    assert "tutar · type_conformance" in blocked["error_message"]
    with app.app_context():
        assert Alarm.query.count() == 0

    # The auditor accepts the format problems as warnings; the control now runs and is flagged.
    with app.app_context():
        for check in QualityCheck.query.filter_by(check_type="type_conformance").all():
            assert client.patch(f"/api/quality-checks/{check.id}",
                                json={"severity": "warning"}).status_code == 200
    result = client.post(f"/api/rules/{rule['id']}/run").get_json()
    assert result["status"] == "completed"
    assert result["quality_status"] == "warning"
    assert result["skipped_records"] == 1
    with app.app_context():
        alarm = Alarm.query.one()
        assert "data-quality warnings" in alarm.message
        execution = db.session.get(RuleExecution, result["execution_id"])
        assert execution.quality_summary["failed_count"] >= 2
        assert QualityCheckRun.query.count() > 0


def test_rule_runs_without_configured_checks(client):
    source_id = _upload(client, b"id;tutar\n1;150.000,00\n2;10,00\n", "kucuk.csv")
    rule = client.post("/api/rules", json={"name": "Limit", "field_name": "tutar", "operator": ">",
                                           "threshold_value": 1000, "severity": "high",
                                           "audit_area_id": 1, "data_source_id": source_id}).get_json()
    result = client.post(f"/api/rules/{rule['id']}/run").get_json()
    assert (result["status"], result["quality_status"], result["matched_records"]) == (
        "completed", "not_configured", 1)


def test_type_conformance_ignores_blanks_and_honours_tolerance(client):
    source_id = _upload(client, b"id;tutar\n1;10,00\n2;\n3;abc\n4;5,00\n", "tolerans.csv")
    created = client.post(f"/api/data-sources/{source_id}/quality-checks", json={
        "name": "tutar sayı", "check_type": "type_conformance", "field_name": "tutar",
        "severity": "critical", "parameters": {"type": "number", "tolerance_percent": 30}}).get_json()
    run = client.post(f"/api/quality-checks/{created['id']}/run").get_json()
    assert (run["status"], run["failed_records"]) == ("passed", 1)
    client.patch(f"/api/quality-checks/{created['id']}",
                 json={"parameters": {"type": "number", "tolerance_percent": 10}})
    assert client.post(f"/api/quality-checks/{created['id']}/run").get_json()["status"] == "failed"


@pytest.mark.parametrize("payload, message", [
    ({"checks": []}, "checks must be"),
    ({"checks": [{"name": "a", "check_type": "not_null", "field_name": "tutar", "severity": "high"}]},
     "severity"),
    ({"checks": [{"name": "a", "check_type": "type_conformance", "field_name": "tutar",
                  "parameters": {"type": "text"}}]}, "type_conformance"),
    ({"checks": [{"name": "a", "check_type": "not_null", "field_name": "tutar"},
                 {"name": "a", "check_type": "unique", "field_name": "tutar"}]}, "already exists"),
])
def test_bulk_create_rejects_invalid_input_atomically(app, client, payload, message):
    source_id = _upload(client, b"id;tutar\n1;10,00\n", "bulk.csv")
    response = client.post(f"/api/data-sources/{source_id}/quality-checks/bulk", json=payload)
    assert response.status_code == 400
    assert message in response.get_json()["error"]
    with app.app_context():
        assert QualityCheck.query.count() == 0
