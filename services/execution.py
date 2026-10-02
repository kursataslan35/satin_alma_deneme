"""Persistence boundary for rule execution, alarms, and evidence."""

from __future__ import annotations

from datetime import timedelta, timezone
from uuid import uuid4

from flask import current_app
from sqlalchemy import or_

from models import Alarm, AuditRule, RuleExecution, db, utcnow
from services.rule_engine import evaluate_records
from services.detectors import get_detector
from services.mapping import mapped_records_for_rule
from services.federated_records import load_federated_records
from services.compound_rule_engine import evaluate_compound_rule
from services.quality_gate import run_quality_gate
from notification_policies import enqueue_alarm_notifications


class RuleLocked(RuntimeError):
    """Raised when another manual or scheduled run currently owns the rule."""


def _naive_utc(value):
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def claim_rule(rule: AuditRule, *, now=None, require_schedule: bool = False) -> str | None:
    """Atomically take the per-rule execution lock shared by manual and scheduled runs."""
    now = _naive_utc(now or utcnow())
    token = str(uuid4())
    lock_until = now + timedelta(seconds=max(1, rule.execution_timeout_seconds))
    query = AuditRule.query.filter(
        AuditRule.id == rule.id,
        or_(AuditRule.execution_lock_until.is_(None), AuditRule.execution_lock_until <= now),
    )
    if require_schedule:
        query = query.filter(AuditRule.schedule_enabled.is_(True))
    updated = query.update({AuditRule.execution_lock_token: token,
                            AuditRule.execution_lock_until: lock_until}, synchronize_session=False)
    db.session.commit()
    return token if updated == 1 else None


def release_rule(rule_id: int, token: str) -> None:
    AuditRule.query.filter(AuditRule.id == rule_id, AuditRule.execution_lock_token == token).update(
        {AuditRule.execution_lock_token: None, AuditRule.execution_lock_until: None},
        synchronize_session=False)
    db.session.commit()


def _evaluate(rule: AuditRule):
    records = (load_federated_records(
        rule, max_source_records=current_app.config.get("FEDERATED_SOURCE_LIMIT", 10_000),
        max_output_records=current_app.config.get("FEDERATED_OUTPUT_LIMIT", 10_000)).records
        if rule.source_links else mapped_records_for_rule(rule))
    params = dict(rule.parameters or {})
    evidence_limit = int(current_app.config.get("EVIDENCE_SAMPLE_LIMIT", 1_000))
    if rule.rule_type == "numeric" and "value" not in params:
        params.update(operator=rule.operator, value=rule.threshold_value)
    if rule.rule_type == "compound":
        result = evaluate_compound_rule(records, params, max_evidence=min(evidence_limit, 10_000))
        matches = list(result.evidence) if result.alarm_triggered else []
        return (result.scanned_records, result.selected_records, matches, "compound", 0, None)
    if rule.rule_type == "anomaly":
        detector = get_detector(str(params.get("detector", "statistical_zscore")))
        result = detector.detect(
            records,
            fields=params.get("fields") or [rule.field_name],
            sensitivity=params.get("sensitivity", 0.5),
            confidence_threshold=params.get("confidence_threshold", 0.8),
            max_evidence=min(int(params.get("max_evidence", evidence_limit)), evidence_limit),
        )
        return (result.scanned_records, result.anomaly_count,
                [item.to_dict() for item in result.evidence], result.detector,
                result.invalid_records, None)
    result = evaluate_records(records, rule_type=rule.rule_type, field=rule.field_name,
                              parameters=params, max_matches=evidence_limit)
    return (result.scanned_records, result.matched_records, result.matches, rule.rule_type,
            result.skipped_records, list(result.skipped_examples))


def _finish(execution_id: int, values: dict) -> bool:
    """Close a run only if no timeout sweep or other worker has closed it first."""
    return RuleExecution.query.filter_by(id=execution_id, status="running").update(
        values, synchronize_session=False) == 1


def run_rule(rule: AuditRule, *, trigger: str = "manual", attempt: int = 1) -> RuleExecution:
    if not rule.is_active:
        raise ValueError("rule is inactive")
    timeout = timedelta(seconds=max(1, rule.execution_timeout_seconds))
    started_at = utcnow()
    execution = RuleExecution(rule=rule, status="running", trigger=trigger, attempt=attempt,
                              started_at=started_at)
    db.session.add(execution)
    # Commit the running row so other workers can see the run and expire it on timeout.
    db.session.commit()
    execution_id = execution.id
    try:
        # Data quality runs first, on the same records the control is about to read.
        gate = run_quality_gate([rule.data_source, *(link.data_source for link in rule.source_links)])
        quality = {"quality_status": gate["status"], "quality_summary": gate}
        if gate["status"] == "blocked":
            _finish(execution_id, {**quality, "status": "blocked", "finished_at": utcnow(),
                                   "error_message": "critical data-quality checks failed: "
                                                    + ", ".join(gate["blocking"])})
            db.session.commit()
            db.session.refresh(execution)
            return execution
        scanned, matched, matches, label, skipped, skipped_examples = _evaluate(rule)
        finished_at = utcnow()
        if _naive_utc(finished_at) - _naive_utc(started_at) > timeout:
            db.session.rollback()
            _finish(execution_id, {"status": "timed_out", "finished_at": finished_at,
                                   "error_message": "execution exceeded configured timeout; "
                                                    "results were discarded"})
            db.session.commit()
            db.session.refresh(execution)
            return execution
        if not _finish(execution_id, {"status": "completed", "scanned_records": scanned,
                                      "matched_records": matched, "skipped_records": skipped,
                                      "skipped_examples": skipped_examples or None,
                                      "finished_at": finished_at, **quality}):
            # Another worker already marked this run timed out; its evidence is not trusted.
            db.session.rollback()
            db.session.refresh(execution)
            return execution
        rule.last_run_at = finished_at
        if matches:
            message = (f"{matched} record(s) matched {label} control; "
                       f"{len(matches)} retained as evidence")
            if skipped:
                message += f"; {skipped} record(s) could not be parsed and were not evaluated"
            if gate["status"] == "warning":
                message += "; data-quality warnings: " + ", ".join(gate["warnings"])
            alarm = Alarm(title=rule.name, message=message, severity=rule.severity,
                          affected_records=matches, rule=rule, audit_area=rule.audit_area,
                          data_source=rule.data_source)
            rule.trigger_count += 1
            db.session.add(alarm)
            db.session.flush()
            enqueue_alarm_notifications(alarm)
        db.session.commit()
    except Exception as exc:
        # The failure may have come from the database itself, so discard the broken
        # transaction before recording the failure.
        db.session.rollback()
        _finish(execution_id, {"status": "failed", "error_message": str(exc)[:2000],
                               "finished_at": utcnow()})
        db.session.commit()
    db.session.refresh(execution)
    return execution
