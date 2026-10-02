"""Data-quality check execution and the quality gate that runs before audit controls.

Order of work for every control run: the source's active quality checks run
first on the same records; a failed *critical* check blocks the control, a
failed *warning* check lets it run but flags the result. Failing rows are never
silently removed from the audit population.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable

from models import DataSource, QualityCheck, QualityCheckRun, db, utcnow
from services.locale_values import parse_datetime, parse_number


CHECK_TYPES = {"not_null", "unique", "numeric_range", "accepted_values", "type_conformance"}
CHECK_SEVERITIES = {"critical", "warning"}


def _stable_value(value: Any) -> str:
    return f"{type(value).__name__}:{value!r}"


def _empty(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _conforms(value: Any, expected: str) -> bool:
    try:
        if expected == "date":
            parse_datetime(value)
        else:
            parse_number(value)
        return True
    except (TypeError, ValueError):
        return False


def execute_quality_check(check: QualityCheck) -> QualityCheckRun:
    records = list((check.data_source.config or {}).get("records", []))
    started = utcnow()
    failures: list[dict[str, Any]] = []
    field = check.field_name
    parameters = check.parameters or {}
    counts = Counter(_stable_value(record.get(field)) for record in records
                     if record.get(field) not in (None, "")) if check.check_type == "unique" else Counter()
    accepted = {_stable_value(item) for item in parameters.get("values", [])}

    for index, record in enumerate(records):
        value = record.get(field)
        failed = False
        if check.check_type == "not_null":
            failed = _empty(value)
        elif check.check_type == "unique":
            failed = value not in (None, "") and counts[_stable_value(value)] > 1
        elif check.check_type == "numeric_range":
            try:
                number = parse_number(value)
                failed = ((parameters.get("min") is not None and number < float(parameters["min"])) or
                          (parameters.get("max") is not None and number > float(parameters["max"])))
            except (TypeError, ValueError):
                failed = True
        elif check.check_type == "accepted_values":
            failed = _stable_value(value) not in accepted
        elif check.check_type == "type_conformance":
            # Blank cells are completeness, not format, problems; not_null covers them.
            failed = not _empty(value) and not _conforms(value, parameters.get("type", "number"))
        if failed:
            failures.append({"row_index": index, "value": value})

    scanned = len(records)
    failed_count = len(failures)
    failure_rate = failed_count / scanned * 100 if scanned else 0.0
    tolerance = float(parameters.get("tolerance_percent") or 0)
    run = QualityCheckRun(quality_check=check, status="failed" if failure_rate > tolerance else "passed",
                          scanned_records=scanned, failed_records=failed_count,
                          pass_rate=round(100 - failure_rate, 2),
                          failure_sample=failures[:100], started_at=started, finished_at=utcnow())
    check.last_run_at = run.finished_at
    db.session.add(run)
    db.session.commit()
    return run


def run_quality_gate(sources: Iterable[DataSource]) -> dict[str, Any]:
    """Run every active check on the given sources and decide whether controls may run."""
    results = []
    for source in {item.id: item for item in sources if item is not None}.values():
        for check in sorted(source.quality_checks, key=lambda item: item.id):
            if not check.is_active:
                continue
            run = execute_quality_check(check)
            results.append({"check_id": check.id, "run_id": run.id, "data_source_id": source.id,
                            "data_source_name": source.name, "name": check.name,
                            "check_type": check.check_type, "field_name": check.field_name,
                            "severity": check.severity, "status": run.status,
                            "scanned_records": run.scanned_records,
                            "failed_records": run.failed_records, "pass_rate": run.pass_rate})
    failed = [item for item in results if item["status"] == "failed"]
    if not results:
        status = "not_configured"
    elif any(item["severity"] == "critical" for item in failed):
        status = "blocked"
    elif failed:
        status = "warning"
    else:
        status = "passed"
    return {"status": status, "checks": results, "check_count": len(results),
            "failed_count": len(failed),
            "blocking": [item["name"] for item in failed if item["severity"] == "critical"],
            "warnings": [item["name"] for item in failed if item["severity"] != "critical"]}
