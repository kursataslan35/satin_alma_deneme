from datetime import datetime, timedelta, timezone

import pytest

import services.execution as execution_module
from app import create_app
from models import Alarm, AuditArea, AuditRule, DataSource, RuleExecution, db
from services.execution import claim_rule, release_rule, run_rule
from services.scheduler import run_due_rules


@pytest.fixture()
def app(tmp_path):
    application = create_app({"TESTING": True, "AUTH_REQUIRED": False,
                              "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'safety.db'}"})
    with application.app_context():
        area = AuditArea(name="Satın alma")
        source = DataSource(name="Faturalar", audit_area=area, config={"records": [
            {"id": 1, "tutar": "1.250.000,00"}, {"id": 2, "tutar": "500,00"}, {"id": 3, "tutar": "?"},
        ]})
        rule = AuditRule(name="Yüksek tutar", field_name="tutar", operator=">", threshold_value=25000,
                         rule_type="numeric", parameters={"operator": ">", "value": 25000},
                         severity="high", schedule_interval_minutes=60,
                         next_run_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
                         audit_area=area, data_source=source)
        db.session.add_all([area, source, rule])
        db.session.commit()
    return application


def test_execution_records_skipped_values_and_mentions_them_in_alarm(app):
    with app.app_context():
        execution = run_rule(AuditRule.query.one())
        assert execution.status == "completed"
        assert (execution.scanned_records, execution.matched_records, execution.skipped_records) == (3, 1, 1)
        assert execution.skipped_examples[0]["value"] == "?"
        assert "1 record(s) could not be parsed" in Alarm.query.one().message


def test_manual_run_api_reports_skipped_records(app):
    response = app.test_client().post("/api/rules/1/run")
    assert response.status_code == 200
    assert response.json["skipped_records"] == 1
    assert response.json["status"] == "completed"


def test_manual_run_is_rejected_while_rule_is_locked(app):
    with app.app_context():
        token = claim_rule(AuditRule.query.one())
        assert token
    client = app.test_client()
    response = client.post("/api/rules/1/run")
    assert response.status_code == 409
    with app.app_context():
        assert RuleExecution.query.count() == 0
        release_rule(1, token)
    assert client.post("/api/rules/1/run").status_code == 200


def test_scheduler_skips_rule_held_by_manual_run(app):
    now = datetime(2025, 1, 2, tzinfo=timezone.utc)
    with app.app_context():
        rule = AuditRule.query.one()
        token = claim_rule(rule, now=now)
        assert run_due_rules(now=now) == []
        release_rule(rule.id, token)
        assert len(run_due_rules(now=now)) == 1


def test_running_row_is_visible_to_other_sessions_during_evaluation(app, monkeypatch):
    seen = {}

    def observe(rule):
        with db.engine.connect() as connection:
            seen["status"] = connection.execute(
                db.text("SELECT status FROM rule_executions")).scalar()
        return 3, 0, [], "numeric", 0, None

    monkeypatch.setattr(execution_module, "_evaluate", observe)
    with app.app_context():
        assert run_rule(AuditRule.query.one()).status == "completed"
    assert seen["status"] == "running"


def test_database_error_during_run_is_recorded_as_failure(app, monkeypatch):
    def broken(rule):
        db.session.execute(db.text("SELECT * FROM missing_table"))

    monkeypatch.setattr(execution_module, "_evaluate", broken)
    with app.app_context():
        execution = run_rule(AuditRule.query.one())
        assert execution.status == "failed"
        assert "missing_table" in execution.error_message
        assert RuleExecution.query.one().status == "failed"


def test_run_exceeding_timeout_discards_results(app, monkeypatch):
    def slow(rule):
        start = execution_module.utcnow()
        monkeypatch.setattr(execution_module, "utcnow", lambda: start + timedelta(seconds=301))
        return 3, 1, [{"id": 1}], "numeric", 0, None

    monkeypatch.setattr(execution_module, "_evaluate", slow)
    with app.app_context():
        execution = run_rule(AuditRule.query.one())
        assert execution.status == "timed_out"
        assert Alarm.query.count() == 0


def test_results_are_discarded_when_another_worker_expired_the_run(app, monkeypatch):
    def expired_elsewhere(rule):
        with db.engine.begin() as connection:
            connection.execute(db.text("UPDATE rule_executions SET status = 'timed_out'"))
        return 3, 1, [{"id": 1}], "numeric", 0, None

    monkeypatch.setattr(execution_module, "_evaluate", expired_elsewhere)
    with app.app_context():
        execution = run_rule(AuditRule.query.one())
        assert execution.status == "timed_out"
        assert Alarm.query.count() == 0
