import json
import shutil
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
)
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from backend.app.api.dependencies import AuthContext, get_auth_context, get_db
from backend.app.db.company import Company
from backend.app.db.employee import Employee
from backend.app.db.import_batch import ImportBatch
from backend.app.db.import_row_issue import ImportRowIssue
from backend.app.db.import_issue_correction import ImportIssueCorrection
from backend.app.services.file_reader import (
    SUPPORTED_EXTENSIONS,
    WorksheetSelectionRequired,
    read_tabular_file,
)
from backend.app.services.column_mapper import detect_employee_columns
from backend.app.services.data_correction import correct_email, classify_duplicate_email
from backend.app.services.employee_import_pipeline import (
    APPROVED_DEFAULTS,
    AVAILABLE_MAPPING_FIELDS,
    EMPLOYEE_FIELDS,
    build_employee_import_preview,
    employee_model_values,
    suggested_column_mapping,
)
from backend.app.services.odoo_client import (
    OdooAuthenticationError,
    OdooConfigurationError,
    OdooError,
    OdooFetchError,
    OdooPermissionError,
    OdooUnavailableError,
    OdooClient,
    OdooConfig,
    detect_odoo_version,
    normalize_odoo_employees,
)


router = APIRouter(
    prefix="/employee-imports",
    tags=["Employee Imports"],
)

MAX_FILE_SIZE = 20 * 1024 * 1024
IMPORT_STORAGE_ROOT = (
    Path(__file__).resolve().parents[2] / "data" / "imports"
)


def json_safe(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()

    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}

    if isinstance(value, list):
        return [json_safe(item) for item in value]

    return value


def build_issue_counts(issues: list[dict]) -> dict:
    return dict(Counter(issue["type"] for issue in issues))


def save_batch_files(
    company_id: int,
    batch_id: int,
    filename: str,
    file_content: bytes,
    metadata: dict,
) -> list[Path]:
    """Save the source file and its processing metadata."""
    batch_directory = IMPORT_STORAGE_ROOT / str(company_id) / str(batch_id)
    batch_directory.mkdir(parents=True, exist_ok=False)

    extension = Path(filename).suffix.lower()
    source_path = batch_directory / f"source{extension}"
    metadata_path = batch_directory / "metadata.json"

    try:
        source_path.write_bytes(file_content)
        metadata_path.write_text(
            json.dumps(json_safe(metadata), indent=2),
            encoding="utf-8",
        )
    except Exception:
        shutil.rmtree(batch_directory, ignore_errors=True)
        raise

    return [source_path, metadata_path]


async def read_upload_limited(file: UploadFile) -> bytes:
    content = bytearray()
    while True:
        remaining = MAX_FILE_SIZE + 1 - len(content)
        chunk = await file.read(min(1024 * 1024, remaining))
        if not chunk:
            break
        content.extend(chunk)
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail="The uploaded file exceeds the 20 MB limit.",
            )
    return bytes(content)


def _safe_upload_filename(uploaded_name: str | None) -> str:
    filename = (uploaded_name or "").replace("\\", "/").rsplit("/", 1)[-1]
    filename = filename.strip()
    if (
        not filename
        or filename in {".", ".."}
        or len(filename) > 255
        or any(ord(character) < 32 for character in filename)
    ):
        raise HTTPException(
            status_code=400,
            detail="A valid filename is required.",
        )
    return filename


def _batch_directory(company_id: int, batch_id: int) -> Path:
    return IMPORT_STORAGE_ROOT / str(company_id) / str(batch_id)


def _read_batch_metadata(
    batch: ImportBatch,
    company_id: int,
) -> tuple[dict[str, Any], dict[str, Any], Path]:
    batch_directory = _batch_directory(company_id, batch.id)
    metadata_path = batch_directory / "metadata.json"
    extension = Path(batch.file_name or "").suffix.lower()
    source_path = batch_directory / f"source{extension}"

    if not metadata_path.is_file() or not source_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Original source file or metadata not found.",
        )

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if (
        metadata.get("company_id") != company_id
        or metadata.get("batch_id") != batch.id
    ):
        raise HTTPException(
            status_code=409,
            detail="Stored metadata does not match this batch.",
        )
    file_data = read_tabular_file(
        source_path.read_bytes(),
        batch.file_name or "",
        sheet_name=metadata.get("worksheet"),
    )
    return metadata, file_data, metadata_path


def _structured_mapping(
    column_mapping: dict[str, str | None],
) -> dict[str, dict[str, Any]]:
    return {
        column: {
            "field": field,
            "confidence": 1.0 if field else 0.0,
            "match_type": "manual" if field else "unmapped",
            "requires_review": False,
        }
        for column, field in column_mapping.items()
    }


def _combined_name_fields(
    column_mapping: dict[str, str | None],
) -> list[dict[str, Any]]:
    first_name = next(
        (column for column, field in column_mapping.items()
         if field == "first_name"),
        None,
    )
    last_name = next(
        (column for column, field in column_mapping.items()
         if field == "last_name"),
        None,
    )
    if first_name is None or last_name is None:
        return []
    return [{
        "field": "full_name",
        "source_columns": [first_name, last_name],
        "transformation": "combine_names",
        "requires_review": False,
    }]


def _write_batch_metadata(
    metadata_path: Path,
    metadata: dict[str, Any],
) -> None:
    temporary_path = metadata_path.with_suffix(".tmp")
    temporary_path.write_text(
        json.dumps(json_safe(metadata), indent=2),
        encoding="utf-8",
    )
    temporary_path.replace(metadata_path)


def persist_issues(
    db: Session,
    batch_id: int,
    issues: list[dict],
) -> None:
    records = []

    for issue in issues:
        row_number = issue.get("row_number")

        # File-level mapping issues are returned in the API response.
        if row_number is None:
            continue

        raw_value = issue.get("raw_value")

        records.append(
            ImportRowIssue(
                batch_id=batch_id,
                row_number=row_number,
                field_name=issue.get("field"),
                issue_type=issue["type"][:30],
                message=issue["message"],
                raw_value=(
                    str(raw_value)
                    if raw_value is not None
                    else None
                ),
                status=(
                    "Resolved"
                    if issue["type"].startswith("warning_")
                    else "Open"
                ),
                resolved_at=(
                    datetime.utcnow()
                    if issue["type"].startswith("warning_")
                    else None
                ),
                resolution_note=(
                    "Informational validation warning recorded during import."
                    if issue["type"].startswith("warning_")
                    else None
                ),
            )
        )

    if records:
        db.add_all(records)


def replace_import_issues(
    db: Session,
    batch_id: int,
    issues: list[dict],
) -> None:
    db.query(ImportRowIssue).filter(
        ImportRowIssue.batch_id == batch_id
    ).delete(synchronize_session=False)
    persist_issues(db, batch_id, issues)


def link_manager_references(db: Session, company_id: int) -> None:
    employees = db.query(Employee).filter(
        Employee.company_id == company_id,
    ).all()
    employee_by_code = {
        employee.employee_id.strip().casefold(): employee
        for employee in employees
    }
    employee_by_id = {employee.id: employee for employee in employees}

    for employee in employees:
        if employee.manager_internal_id is not None:
            linked_manager = employee_by_id.get(employee.manager_internal_id)
            if linked_manager is None or not linked_manager.is_active:
                employee.manager_internal_id = None

        manager_code = (employee.manager_id or "").strip().casefold()
        if manager_code:
            manager = employee_by_code.get(manager_code)
            employee.manager_internal_id = (
                manager.id
                if manager and manager.id != employee.id and manager.is_active
                else None
            )


class OdooFetchPreviewRequest(BaseModel):
    include_archived: bool = False
    odoo_company_id: int | None = None
    employee_ids: list[int] | None = None
    column_mapping: dict[str, str | None] | None = None


class ImportRowReview(BaseModel):
    row_number: int
    values: dict[str, Any] = Field(default_factory=dict)
    source_decision: Literal["update", "keep"] | None = None


class ImportRowReviewRequest(BaseModel):
    rows: list[ImportRowReview]


def _row_overrides(metadata: dict[str, Any]) -> dict[int, dict[str, Any]]:
    stored = metadata.get("row_edits", {})
    if not isinstance(stored, dict):
        return {}
    overrides = {}
    for row_number, values in stored.items():
        if not isinstance(values, dict):
            continue
        try:
            parsed_row_number = int(row_number)
        except (TypeError, ValueError):
            continue
        overrides[parsed_row_number] = values
    return overrides


def _odoo_source_decisions(metadata: dict[str, Any]) -> dict[str, str]:
    decisions = metadata.get("source_decisions", {})
    if not isinstance(decisions, dict):
        return {}
    return {
        reference: decision
        for reference, decision in decisions.items()
        if isinstance(reference, str) and decision in {"update", "keep"}
    }


def _odoo_update_employee_ids(
    db: Session,
    company_id: int,
    source_rows: list[dict[str, Any]],
    decisions: dict[str, str],
) -> set[int]:
    if not decisions:
        return set()
    imported_sources, _ = _odoo_source_history(db, company_id)
    employee_ids = set()
    for row in source_rows:
        reference = row.get("_odoo_source_reference")
        if not isinstance(reference, str) or decisions.get(reference) != "update":
            continue
        imported = imported_sources.get(reference)
        employee = imported.get("employee") if imported else None
        if employee is not None:
            employee_ids.add(employee.id)
    return employee_ids


def _require_training_manager(context: AuthContext) -> None:
    if context.role != "Training Manager":
        raise HTTPException(
            status_code=403,
            detail="Only Training Managers may manage employee imports.",
        )


def _assert_odoo_source_is_current(
    config: OdooConfig,
    metadata: dict[str, Any],
    staged_rows: list[dict[str, Any]],
) -> None:
    staged_snapshots = metadata.get("odoo_source_snapshots")
    if not isinstance(staged_snapshots, dict):
        raise HTTPException(
            status_code=409,
            detail="This Odoo batch has no source version. Fetch it again before confirming.",
        )
    staged_references = {
        row.get("_odoo_source_reference")
        for row in staged_rows
        if isinstance(row.get("_odoo_source_reference"), str)
    }
    if staged_references != set(staged_snapshots):
        raise HTTPException(
            status_code=409,
            detail="The staged Odoo source data is incomplete. Fetch it again before confirming.",
        )
    options = metadata.get("odoo_fetch_options", {})
    if not isinstance(options, dict):
        options = {}
    fetched = OdooClient(config).fetch_employees(
        include_archived=bool(options.get("include_archived", False)),
        odoo_company_id=options.get("odoo_company_id"),
        employee_ids=options.get("employee_ids"),
    )
    _, latest_rows, _ = normalize_odoo_employees(
        fetched["records"],
        odoo_database=config.database,
    )
    latest_snapshots = _odoo_snapshots_by_reference(latest_rows)
    if latest_snapshots != staged_snapshots:
        raise HTTPException(
            status_code=409,
            detail="Odoo records changed after preview. Fetch and review the latest version before confirming.",
        )


def _safe_odoo_http_error(exc: OdooError) -> HTTPException:
    if isinstance(exc, OdooConfigurationError):
        status_code = 400
    elif isinstance(exc, (OdooAuthenticationError, OdooPermissionError)):
        status_code = 403
    elif isinstance(exc, (OdooUnavailableError, OdooFetchError)):
        status_code = 502
    else:
        status_code = 500
    return HTTPException(status_code=status_code, detail=str(exc))


ODOO_METADATA_COLUMNS = {
    "_odoo_source_reference",
    "_odoo_employee_id_generated",
    "odoo_create_date",
    "odoo_write_date",
}


def _odoo_source_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    snapshot_fields = (
        "employee_id",
        "full_name",
        "email",
        "department",
        "job_title",
        "manager_name",
        "employment_status",
        "hire_date",
        "contract_start_date",
        "employment_type",
        "job_level",
        "odoo_write_date",
    )
    return {
        field: json_safe(row.get(field))
        for field in snapshot_fields
        if field in row
    }


def _odoo_snapshots_by_reference(
    rows: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    return {
        reference: _odoo_source_snapshot(row)
        for row in rows
        if isinstance(
            reference := row.get("_odoo_source_reference"),
            str,
        )
    }


def _odoo_mapping(
    mapping: dict[str, str | None],
    columns: list[str],
    *,
    reject_metadata_mapping: bool = True,
) -> dict[str, str | None]:
    unknown_columns = set(mapping) - set(columns)
    if unknown_columns:
        raise ValueError("The mapping contains Odoo columns not in the fetched data.")
    normalized = {column: mapping.get(column) for column in columns}
    for column in ODOO_METADATA_COLUMNS.intersection(normalized):
        if reject_metadata_mapping and normalized[column] is not None:
            raise ValueError("Odoo metadata columns cannot be mapped to employee fields.")
        normalized[column] = None
    return normalized


def _odoo_source_history(
    db: Session,
    company_id: int,
    *,
    exclude_batch_id: int | None = None,
) -> tuple[dict[str, dict[str, Any]], set[str]]:
    imported_sources: dict[str, dict[str, Any]] = {}
    pending_references: set[str] = set()
    company_employees = db.query(Employee).filter(
        Employee.company_id == company_id,
    ).all()
    employees_by_id = {employee.id: employee for employee in company_employees}
    employees_by_code = {
        employee.employee_id.strip().casefold(): employee
        for employee in company_employees
    }
    batches = db.query(ImportBatch).filter(
        ImportBatch.company_id == company_id,
        ImportBatch.entity_type == "employee",
        ImportBatch.source_type == "ODOO",
    ).order_by(ImportBatch.created_at.desc(), ImportBatch.id.desc()).all()
    for batch in batches:
        if exclude_batch_id is not None and batch.id == exclude_batch_id:
            continue
        metadata_path = _batch_directory(company_id, batch.id) / "metadata.json"
        if not metadata_path.is_file():
            continue
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        snapshots = metadata.get("odoo_source_snapshots", {})
        if not isinstance(snapshots, dict):
            snapshots = {}
        imported = metadata.get("odoo_imported_sources", {})
        if not isinstance(imported, dict):
            imported = {}

        decisions = metadata.get("source_decisions", {})
        acknowledged_references = {
            reference
            for reference, decision in decisions.items()
            if isinstance(reference, str)
            and decision == "keep"
            and reference in imported
        } if isinstance(decisions, dict) else set()
        if (
            batch.status in {"Completed", "Completed with errors"}
            and (batch.successful_rows > 0 or acknowledged_references)
        ):
            if imported:
                imported_items = imported.items()
            else:
                source_map = metadata.get("odoo_employee_source_map", {})
                if not isinstance(source_map, dict):
                    source_map = {}
                imported_items = (
                    (reference, {"employee_id": employee_code})
                    for employee_code, reference in source_map.items()
                    if isinstance(reference, str)
                )
            for reference, item in imported_items:
                if not isinstance(reference, str) or reference in imported_sources:
                    continue
                if not isinstance(item, dict):
                    item = {}
                employee = None
                employee_pk = item.get("employee_pk")
                if isinstance(employee_pk, int):
                    employee = employees_by_id.get(employee_pk)
                employee_code = item.get("employee_id")
                if employee is None and isinstance(employee_code, str):
                    employee = employees_by_code.get(employee_code.strip().casefold())
                snapshot = item.get("source_snapshot")
                if not isinstance(snapshot, dict):
                    snapshot = snapshots.get(reference)
                imported_sources[reference] = {
                    "employee": employee,
                    "source_snapshot": (
                        snapshot if isinstance(snapshot, dict) else None
                    ),
                }
            continue

        if batch.successful_rows == 0 and batch.status in {
            "Awaiting preview",
            "Awaiting confirmation",
            "Needs review",
        }:
            references = metadata.get("odoo_source_references", [])
            if not isinstance(references, list):
                references = []
            pending_references.update(
                reference
                for reference in references
                if isinstance(reference, str)
            )
    return imported_sources, pending_references


def _apply_odoo_source_conflicts(
    db: Session,
    company_id: int,
    batch: ImportBatch,
    preview: dict[str, Any],
    source_rows: list[dict[str, Any]],
    source_snapshots: dict[str, dict[str, Any]],
    source_decisions: dict[str, str] | None = None,
) -> dict[str, Any]:
    imported_sources, pending_references = _odoo_source_history(
        db,
        company_id,
        exclude_batch_id=batch.id,
    )
    source_decisions = source_decisions or {}
    skipped_rows = 0

    for row in preview["rows"]:
        data = row["data"]
        source_index = row["row_number"] - 2
        source_row = (
            source_rows[source_index]
            if 0 <= source_index < len(source_rows)
            else {}
        )
        reference = source_row.get("_odoo_source_reference")
        reference = reference if isinstance(reference, str) else None
        row["source_reference"] = reference
        row["source_status"] = "new"
        row["source_changes"] = []
        row["existing_employee"] = None

        imported = imported_sources.get(reference) if reference else None
        decision = source_decisions.get(reference) if reference else None
        if imported is not None:
            employee = imported["employee"]
            baseline = imported["source_snapshot"]
            current_snapshot = source_snapshots.get(reference or "")
            changes = []
            if isinstance(baseline, dict) and isinstance(current_snapshot, dict):
                for field in sorted(set(baseline) | set(current_snapshot)):
                    if baseline.get(field) != current_snapshot.get(field):
                        changes.append({
                            "field": field,
                            "previous_value": baseline.get(field),
                            "current_value": current_snapshot.get(field),
                        })
            if employee is not None:
                row["existing_employee"] = {
                    field: getattr(employee, field)
                    for field in EMPLOYEE_FIELDS
                    if hasattr(employee, field)
                }
            if changes:
                row["source_status"] = "changed"
                row["source_changes"] = changes
                if decision == "keep":
                    row["importable"] = False
                    skipped_rows += 1
                    row["warnings"].append({
                        "row_number": row["row_number"],
                        "field": "_odoo_source_reference",
                        "type": "odoo_source_change_ignored",
                        "message": "The existing application employee was left unchanged.",
                    })
                elif decision != "update" or employee is None:
                    error = {
                        "row_number": row["row_number"],
                        "field": "_odoo_source_reference",
                        "type": "odoo_source_change_requires_review",
                        "message": (
                            "Odoo has newer employee data. Choose whether to "
                            "update the existing application employee or leave it unchanged."
                        ),
                        "raw_value": reference,
                    }
                    row["errors"].append(error)
                    preview["errors"].append(error)
                    row["importable"] = False
            else:
                row["source_status"] = "previously_imported"
                row["importable"] = False
                skipped_rows += 1
                row["warnings"].append({
                    "row_number": row["row_number"],
                    "field": "_odoo_source_reference",
                    "type": "odoo_source_already_imported",
                    "message": (
                        "This Odoo employee was already imported and has no "
                        "new source changes."
                    ),
                })
        elif reference and reference in pending_references:
            row["source_status"] = "duplicate"
            error = {
                "row_number": row["row_number"],
                "field": "_odoo_source_reference",
                "type": "odoo_source_already_staged",
                "message": (
                    "This Odoo employee already has an unresolved import batch "
                    "in this company."
                ),
                "raw_value": reference,
            }
            row["errors"].append(error)
            preview["errors"].append(error)
            row["importable"] = False
            skipped_rows += 1
        elif any(
            error.get("type") in {"duplicate_in_file", "duplicate_in_database"}
            for error in row["errors"]
        ):
            row["source_status"] = "duplicate"

        if source_row.get("_odoo_employee_id_generated") is True:
            warning = {
                "row_number": row["row_number"],
                "field": "employee_id",
                "type": "odoo_generated_employee_id",
                "message": (
                    "Odoo did not provide identification_id or barcode; "
                    "a visible stable ODOO-{record_id} employee ID was used."
                ),
            }
            row["warnings"].append(warning)
            preview["warnings"].append(warning)

    preview["valid_rows"] = [
        {"row_number": row["row_number"], "data": row["data"]}
        for row in preview["rows"]
        if not row["errors"] and row["importable"]
    ]
    preview["summary"]["importable_rows"] = len(preview["valid_rows"])
    preview["summary"]["skipped_rows"] = skipped_rows
    preview["summary"]["invalid_rows"] = max(
        0,
        len(preview["rows"]) - len(preview["valid_rows"]) - skipped_rows,
    )
    preview["summary"]["total_errors"] = len(preview["errors"])
    preview["summary"]["total_warnings"] = len(preview["warnings"])
    preview["summary"]["ready_for_confirmation"] = (
        not preview["missing_mappings"]
        and not any(
            error.get("row_number") is None
            for error in preview["errors"]
        )
    )
    preview["source_status_counts"] = {
        status: sum(
            row["source_status"] == status
            for row in preview["rows"]
        )
        for status in ("new", "previously_imported", "changed", "duplicate")
    }
    return preview


@router.get("/odoo/status")
def odoo_status(
    context: AuthContext = Depends(get_auth_context),
):
    if context.role != "Training Manager":
        raise HTTPException(
            status_code=403,
            detail="Only Training Managers may configure Odoo imports.",
        )
    try:
        config = OdooConfig.from_env()
    except OdooConfigurationError as exc:
        return {
            "configured": False,
            "missing_configuration": str(exc),
            "api_key_configured": False,
        }
    status = config.safe_status()
    return status


@router.post("/odoo/test-connection")
def test_odoo_connection(
    context: AuthContext = Depends(get_auth_context),
):
    if context.role != "Training Manager":
        raise HTTPException(
            status_code=403,
            detail="Only Training Managers may test Odoo imports.",
        )
    try:
        result = OdooClient().test_connection()
    except OdooError as exc:
        raise _safe_odoo_http_error(exc) from exc
    return {
        "success": result["success"],
        "server_version": result["server_version"],
        "server_serie": result["server_serie"],
        "database": result["database"],
        "selected_adapter": result["selected_adapter"],
        "employee_model_access": result["employee_model_access"],
        "employee_count": result["employee_count"],
        "available_employee_fields": result["available_employee_fields"],
    }


@router.get("/odoo/companies")
def list_odoo_companies(
    context: AuthContext = Depends(get_auth_context),
):
    if context.role != "Training Manager":
        raise HTTPException(
            status_code=403,
            detail="Only Training Managers may view Odoo companies.",
        )
    try:
        companies = OdooClient().get_companies()
    except OdooError as exc:
        raise _safe_odoo_http_error(exc) from exc
    return {"companies": companies}


@router.post("/odoo/fetch-preview")
def fetch_odoo_preview(
    request: OdooFetchPreviewRequest,
    company_id: int | None = Query(default=None, gt=0),
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    effective_company_id = context.company_id
    if context.role != "Training Manager":
        raise HTTPException(
            status_code=403,
            detail="Only Training Managers may fetch Odoo employees.",
        )
    if company_id is not None and company_id != effective_company_id:
        raise HTTPException(
            status_code=403,
            detail="The selected company is not an active membership.",
        )

    try:
        config = OdooConfig.from_env()
        client = OdooClient(config)
        fetched = client.fetch_employees(
            include_archived=request.include_archived,
            odoo_company_id=request.odoo_company_id,
            employee_ids=request.employee_ids,
        )
        columns, rows, suggested_mapping = normalize_odoo_employees(
            fetched["records"],
            odoo_database=config.database,
        )
        if request.column_mapping is not None:
            unknown_columns = set(request.column_mapping) - set(columns)
            if unknown_columns:
                raise ValueError(
                    "The mapping contains Odoo columns not in the fetched data."
                )
            mapping = _odoo_mapping(
                request.column_mapping,
                columns,
            )
        else:
            mapping = _odoo_mapping(
                suggested_mapping,
                columns,
                reject_metadata_mapping=False,
            )

        preview = build_employee_import_preview(
            db,
            effective_company_id,
            columns,
            rows,
            mapping,
        )
    except OdooError as exc:
        raise _safe_odoo_http_error(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    batch = ImportBatch(
        company_id=effective_company_id,
        created_by_user_id=context.user.user_id,
        source_type="ODOO",
        entity_type="employee",
        file_name=(
            f"odoo-{config.database}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.json"
        ),
        status="Awaiting preview",
        total_rows=len(rows),
        successful_rows=0,
        failed_rows=0,
    )
    db.add(batch)
    db.flush()

    retrieved_at = datetime.now(timezone.utc).isoformat()
    source_snapshots = _odoo_snapshots_by_reference(rows)
    metadata = {
        "company_id": effective_company_id,
        "batch_id": batch.id,
        "original_filename": batch.file_name,
        "source_type": "ODOO",
        "odoo_database": config.database,
        "odoo_base_url": config.base_url,
        "odoo_company_id": request.odoo_company_id,
        "odoo_version": None,
        "retrieved_at": retrieved_at,
        "odoo_fetch_options": {
            "include_archived": request.include_archived,
            "odoo_company_id": request.odoo_company_id,
            "employee_ids": request.employee_ids,
        },
        "column_mapping_fields": mapping,
        "column_mapping": _structured_mapping(mapping),
        "combined_fields": _combined_name_fields(mapping),
        "approved_defaults": APPROVED_DEFAULTS,
        "odoo_source_references": [
            row["_odoo_source_reference"] for row in rows
        ],
        "odoo_source_snapshots": source_snapshots,
        "odoo_imported_sources": {},
        "source_decisions": {},
        "odoo_employee_source_map": {
            str(row["employee_id"]).strip(): row["_odoo_source_reference"]
            for row in rows
            if row.get("employee_id")
        },
        "previewed": False,
    }
    try:
        detected = detect_odoo_version(config)
        metadata["odoo_version"] = detected["server_version"]
    except OdooError:
        pass

    batch_directory = _batch_directory(effective_company_id, batch.id)
    try:
        save_batch_files(
            company_id=effective_company_id,
            batch_id=batch.id,
            filename=batch.file_name,
            file_content=json.dumps(
                rows,
                ensure_ascii=False,
                indent=2,
            ).encode("utf-8"),
            metadata=metadata,
        )
    except (OSError, SQLAlchemyError) as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Could not stage the Odoo employee import.",
        ) from exc

    preview = _apply_odoo_source_conflicts(
        db,
        effective_company_id,
        batch,
        preview,
        rows,
        source_snapshots,
    )
    metadata["column_mapping_fields"] = preview["column_mapping"]
    metadata["column_mapping"] = _structured_mapping(
        preview["column_mapping"]
    )
    metadata["combined_fields"] = _combined_name_fields(
        preview["column_mapping"]
    )
    metadata["previewed"] = True
    _write_batch_metadata(
        batch_directory / "metadata.json",
        metadata,
    )

    persisted_issues = list(preview["errors"])
    persisted_issues.extend(
        {
            **warning,
            "type": f"warning_{warning['type']}",
        }
        for warning in preview["warnings"]
    )
    replace_import_issues(db, batch.id, persisted_issues)
    batch.status = (
        "Awaiting confirmation"
        if preview["summary"]["ready_for_confirmation"]
        else "Needs review"
    )
    batch.total_rows = len(rows)
    db.commit()
    db.refresh(batch)

    return json_safe({
        "batch_id": batch.id,
        "company_id": effective_company_id,
        "filename": batch.file_name,
        "status": batch.status,
        "source_type": "ODOO",
        "odoo_database": config.database,
        "odoo_company_id": request.odoo_company_id,
        "odoo_version": metadata["odoo_version"],
        "odoo_company_count": None,
        "total_fetched": fetched["total"],
        "source_status_counts": preview.get("source_status_counts", {}),
        "retrieved_at": retrieved_at,
        "columns": columns,
        "column_mapping": mapping,
        "available_fields": AVAILABLE_MAPPING_FIELDS,
        "available_sheets": [],
        "worksheet": None,
        **preview,
    })


@router.post("/upload")
async def upload_employee_file(
    company_id: int | None = Query(default=None, gt=0),
    file: UploadFile = File(...),
    sheet_name: str | None = Form(default=None),
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    effective_company_id = context.company_id
    if company_id is not None and company_id != effective_company_id:
        raise HTTPException(
            status_code=403,
            detail="The selected company is not an active membership.",
        )

    company = db.query(Company).filter(
        Company.company_id == effective_company_id
    ).first()

    if company is None:
        raise HTTPException(
            status_code=404,
            detail="Company not found.",
        )

    filename = _safe_upload_filename(file.filename)
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Only CSV, XLSX, XLS, and JSON files are supported.",
        )
    if sheet_name and extension not in {".xlsx", ".xls"}:
        raise HTTPException(
            status_code=422,
            detail="Worksheet selection is only valid for Excel files.",
        )

    batch_directory = None
    storage_created = False
    committed = False
    try:
        file_content = await read_upload_limited(file)
        if not file_content:
            raise HTTPException(
                status_code=400,
                detail="The uploaded file is empty.",
            )

        file_data = read_tabular_file(
            file_content,
            filename,
            sheet_name=sheet_name,
            require_sheet_selection=True,
        )
        detection = detect_employee_columns(file_data["columns"])
        mapping_fields = suggested_column_mapping(file_data["columns"])
        batch = ImportBatch(
            company_id=effective_company_id,
            created_by_user_id=context.user.user_id,
            source_type=extension.lstrip(".").upper(),
            entity_type="employee",
            file_name=filename,
            status="Awaiting preview",
            total_rows=file_data["total_rows"],
            successful_rows=0,
            failed_rows=0,
        )
        db.add(batch)
        db.flush()

        metadata = {
            "company_id": effective_company_id,
            "batch_id": batch.id,
            "original_filename": filename,
            "source_type": file_data["file_type"],
            "column_mapping": detection["suggestions"],
            "column_mapping_fields": mapping_fields,
            "combined_fields": _combined_name_fields(mapping_fields),
            "approved_defaults": APPROVED_DEFAULTS,
            "worksheet": file_data["worksheet"],
            "previewed": False,
        }
        batch_directory = _batch_directory(effective_company_id, batch.id)
        save_batch_files(
            company_id=effective_company_id,
            batch_id=batch.id,
            filename=filename,
            file_content=file_content,
            metadata=metadata,
        )
        storage_created = True
        db.commit()
        committed = True
        db.refresh(batch)

        return json_safe({
            "message": "File uploaded. Review the field mapping and preview before confirming.",
            "batch_id": batch.id,
            "company_id": effective_company_id,
            "filename": filename,
            "status": batch.status,
            "source_type": file_data["file_type"],
            "total_rows": batch.total_rows,
            "columns": file_data["columns"],
            "column_mapping": mapping_fields,
            "available_fields": AVAILABLE_MAPPING_FIELDS,
            "unmatched_columns": detection["unmatched_columns"],
            "available_sheets": file_data["available_sheets"],
            "worksheet": file_data["worksheet"],
        })

    except WorksheetSelectionRequired as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "worksheet_selection_required",
                "message": str(exc),
                "available_sheets": exc.sheet_names,
            },
        ) from exc
    except HTTPException:
        db.rollback()
        if storage_created and batch_directory is not None:
            shutil.rmtree(batch_directory, ignore_errors=True)
        raise

    except ValueError as exc:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except (OSError, SQLAlchemyError) as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Could not stage the employee import.",
        ) from exc

    finally:
        if not committed:
            db.rollback()
            if storage_created and batch_directory is not None:
                shutil.rmtree(batch_directory, ignore_errors=True)
        await file.close()


class ImportPreviewRequest(BaseModel):
    column_mapping: dict[str, str | None] | None = None


class ImportConfirmationRequest(BaseModel):
    confirmed: bool


def _get_company_batch(
    db: Session,
    batch_id: int,
    company_id: int,
    *,
    lock: bool = False,
) -> ImportBatch:
    query = db.query(ImportBatch).filter(
        ImportBatch.id == batch_id,
        ImportBatch.company_id == company_id,
        ImportBatch.entity_type == "employee",
    )
    if lock:
        query = query.with_for_update()
    batch = query.first()
    if batch is None:
        raise HTTPException(
            status_code=404,
            detail="Employee import batch not found.",
        )
    return batch


@router.get("/history")
def list_employee_import_history(
    company_id: int | None = Query(default=None, gt=0),
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    effective_company_id = context.company_id
    if company_id is not None and company_id != effective_company_id:
        raise HTTPException(
            status_code=403,
            detail="The selected company is not an active membership.",
        )

    batches = db.query(ImportBatch).filter(
        ImportBatch.company_id == effective_company_id,
        ImportBatch.entity_type == "employee",
    ).order_by(
        ImportBatch.created_at.desc(),
        ImportBatch.id.desc(),
    ).limit(50).all()

    return {
        "company_id": effective_company_id,
        "batches": [
            {
                "batch_id": batch.id,
                "file_name": batch.file_name,
                "source_type": batch.source_type,
                "uploaded_by_user_id": batch.created_by_user_id,
                "uploaded_at": (
                    batch.created_at.isoformat()
                    if batch.created_at else None
                ),
                "status": batch.status,
                "total_rows": batch.total_rows,
                "successful_rows": batch.successful_rows,
                "failed_rows": batch.failed_rows,
                "completed_at": (
                    batch.completed_at.isoformat()
                    if batch.completed_at else None
                ),
            }
            for batch in batches
        ],
    }


@router.post("/{batch_id}/preview")
def preview_employee_import(
    batch_id: int,
    request: ImportPreviewRequest,
    company_id: int | None = Query(default=None, gt=0),
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    _require_training_manager(context)
    effective_company_id = context.company_id
    if company_id is not None and company_id != effective_company_id:
        raise HTTPException(
            status_code=403,
            detail="The selected company is not an active membership.",
        )

    batch = _get_company_batch(db, batch_id, effective_company_id)
    if batch.status not in {
        "Awaiting preview",
        "Awaiting confirmation",
        "Needs review",
    }:
        raise HTTPException(
            status_code=409,
            detail="This batch is no longer available for preview.",
        )

    try:
        metadata, file_data, metadata_path = _read_batch_metadata(
            batch,
            effective_company_id,
        )
        mapping = request.column_mapping or metadata.get("column_mapping_fields")
        if batch.source_type == "ODOO" and mapping is not None:
            mapping = _odoo_mapping(
                mapping,
                file_data["columns"],
                reject_metadata_mapping=request.column_mapping is not None,
            )
        decisions = _odoo_source_decisions(metadata)
        overrides = _row_overrides(metadata)
        preview = build_employee_import_preview(
            db,
            effective_company_id,
            file_data["columns"],
            file_data["rows"],
            mapping,
            row_overrides=overrides,
            exclude_employee_ids=(
                _odoo_update_employee_ids(
                    db,
                    effective_company_id,
                    file_data["rows"],
                    decisions,
                )
                if batch.source_type == "ODOO"
                else None
            ),
        )
        if batch.source_type == "ODOO":
            preview = _apply_odoo_source_conflicts(
                db,
                effective_company_id,
                batch,
                preview,
                file_data["rows"],
                metadata.get("odoo_source_snapshots", {}),
                decisions,
            )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    metadata["column_mapping_fields"] = preview["column_mapping"]
    metadata["column_mapping"] = _structured_mapping(
        preview["column_mapping"]
    )
    metadata["combined_fields"] = _combined_name_fields(
        preview["column_mapping"]
    )
    metadata["previewed"] = True
    _write_batch_metadata(metadata_path, metadata)

    persisted_issues = list(preview["errors"])
    persisted_issues.extend(
        {
            **warning,
            "type": f"warning_{warning['type']}",
        }
        for warning in preview["warnings"]
    )
    replace_import_issues(db, batch.id, persisted_issues)
    batch.status = (
        "Awaiting confirmation"
        if preview["summary"]["ready_for_confirmation"]
        else "Needs review"
    )
    db.commit()

    return json_safe({
        "batch_id": batch.id,
        "company_id": effective_company_id,
        "file_name": batch.file_name,
        "source_type": batch.source_type,
        "worksheet": file_data["worksheet"],
        "retrieved_at": metadata.get("retrieved_at"),
        "row_edits": metadata.get("row_edits", {}),
        "source_decisions": _odoo_source_decisions(metadata),
        **preview,
    })


@router.patch("/{batch_id}/rows")
def review_odoo_import_rows(
    batch_id: int,
    request: ImportRowReviewRequest,
    company_id: int | None = Query(default=None, gt=0),
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    _require_training_manager(context)
    effective_company_id = context.company_id
    if company_id is not None and company_id != effective_company_id:
        raise HTTPException(
            status_code=403,
            detail="The selected company is not an active membership.",
        )
    batch = _get_company_batch(db, batch_id, effective_company_id)
    if batch.source_type != "ODOO" or batch.status not in {
        "Awaiting preview",
        "Awaiting confirmation",
        "Needs review",
    }:
        raise HTTPException(
            status_code=409,
            detail="Only an unresolved Odoo employee batch can be edited.",
        )
    if not request.rows:
        raise HTTPException(status_code=422, detail="At least one row is required.")

    try:
        metadata, file_data, metadata_path = _read_batch_metadata(
            batch,
            effective_company_id,
        )
        mapping = _odoo_mapping(
            metadata.get("column_mapping_fields", {}),
            file_data["columns"],
            reject_metadata_mapping=False,
        )
        existing_overrides = _row_overrides(metadata)
        original_preview = build_employee_import_preview(
            db,
            effective_company_id,
            file_data["columns"],
            file_data["rows"],
            mapping,
        )
        staged_preview = build_employee_import_preview(
            db,
            effective_company_id,
            file_data["columns"],
            file_data["rows"],
            mapping,
            row_overrides=existing_overrides,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    allowed_fields = EMPLOYEE_FIELDS | {"first_name", "last_name", "manager_name"}
    original_by_row = {
        row["row_number"]: row["data"] for row in original_preview["rows"]
    }
    staged_by_row = {
        row["row_number"]: row["data"] for row in staged_preview["rows"]
    }
    stored_edits = metadata.setdefault("row_edits", {})
    decisions = metadata.setdefault("source_decisions", {})
    if not isinstance(stored_edits, dict):
        stored_edits = metadata["row_edits"] = {}
    if not isinstance(decisions, dict):
        decisions = metadata["source_decisions"] = {}
    edit_history = metadata.setdefault("edit_history", [])
    if not isinstance(edit_history, list):
        edit_history = metadata["edit_history"] = []

    imported_sources, _ = _odoo_source_history(
        db,
        effective_company_id,
        exclude_batch_id=batch.id,
    )
    source_snapshots = metadata.get("odoo_source_snapshots", {})
    if not isinstance(source_snapshots, dict):
        source_snapshots = {}
    source_rows_by_number = {
        index + 2: row for index, row in enumerate(file_data["rows"])
    }
    seen_rows: set[int] = set()
    now = datetime.now(timezone.utc).isoformat()

    for reviewed_row in request.rows:
        row_number = reviewed_row.row_number
        if (
            row_number in seen_rows
            or row_number not in source_rows_by_number
        ):
            raise HTTPException(
                status_code=422,
                detail=f"Invalid or repeated Odoo row number: {row_number}.",
            )
        seen_rows.add(row_number)
        if not reviewed_row.values and reviewed_row.source_decision is None:
            raise HTTPException(
                status_code=422,
                detail=f"Row {row_number} contains no edits or source decision.",
            )
        unsupported_fields = set(reviewed_row.values) - allowed_fields
        if unsupported_fields:
            raise HTTPException(
                status_code=422,
                detail="Only supported employee fields may be edited.",
            )

        source_row = source_rows_by_number[row_number]
        reference = source_row.get("_odoo_source_reference")
        if reviewed_row.source_decision is not None:
            imported = (
                imported_sources.get(reference)
                if isinstance(reference, str)
                else None
            )
            current_snapshot = (
                source_snapshots.get(reference)
                if isinstance(reference, str)
                else None
            )
            if (
                imported is None
                or imported.get("employee") is None
                or not isinstance(imported.get("source_snapshot"), dict)
                or not isinstance(current_snapshot, dict)
                or imported["source_snapshot"] == current_snapshot
            ):
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "A source decision is available only for an employee "
                        "with a previously imported, changed Odoo record."
                    ),
                )
            decisions[reference] = reviewed_row.source_decision

        overrides = stored_edits.setdefault(str(row_number), {})
        if not isinstance(overrides, dict):
            overrides = stored_edits[str(row_number)] = {}
        previous_data = staged_by_row.get(row_number, {})
        original_data = original_by_row.get(row_number, {})
        for field, value in reviewed_row.values.items():
            edit_history.append({
                "row_number": row_number,
                "field": field,
                "original_source_value": original_data.get(field),
                "previous_staged_value": previous_data.get(field),
                "new_value": value,
                "edited_by_user_id": context.user.user_id,
                "edited_at": now,
            })
            overrides[field] = value

    _write_batch_metadata(metadata_path, metadata)
    batch.status = "Needs review"
    db.commit()
    return json_safe({
        "batch_id": batch.id,
        "status": batch.status,
        "edited_rows": sorted(seen_rows),
        "row_edits": metadata["row_edits"],
        "source_decisions": _odoo_source_decisions(metadata),
    })


@router.post("/{batch_id}/confirm")
def confirm_employee_import(
    batch_id: int,
    request: ImportConfirmationRequest,
    company_id: int | None = Query(default=None, gt=0),
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    _require_training_manager(context)
    effective_company_id = context.company_id
    if company_id is not None and company_id != effective_company_id:
        raise HTTPException(
            status_code=403,
            detail="The selected company is not an active membership.",
        )
    if not request.confirmed:
        raise HTTPException(
            status_code=400,
            detail="Explicit confirmation is required before importing.",
        )

    batch = _get_company_batch(
        db,
        batch_id,
        effective_company_id,
        lock=True,
    )
    if batch.status != "Awaiting confirmation":
        raise HTTPException(
            status_code=409,
            detail="Preview and resolve mapping errors before confirming.",
        )

    try:
        metadata, file_data, _ = _read_batch_metadata(
            batch,
            effective_company_id,
        )
        if not metadata.get("previewed"):
            raise HTTPException(
                status_code=409,
                detail="Generate a preview before confirming this import.",
            )

        decisions = _odoo_source_decisions(metadata)
        overrides = _row_overrides(metadata)
        mapping = metadata.get("column_mapping_fields")
        if batch.source_type == "ODOO":
            config = OdooConfig.from_env()
            _assert_odoo_source_is_current(
                config,
                metadata,
                file_data["rows"],
            )
            mapping = _odoo_mapping(
                mapping or {},
                file_data["columns"],
                reject_metadata_mapping=False,
            )
        excluded_employee_ids = (
            _odoo_update_employee_ids(
                db,
                effective_company_id,
                file_data["rows"],
                decisions,
            )
            if batch.source_type == "ODOO"
            else None
        )
        preview = build_employee_import_preview(
            db,
            effective_company_id,
            file_data["columns"],
            file_data["rows"],
            mapping,
            row_overrides=overrides,
            exclude_employee_ids=excluded_employee_ids,
        )
        if batch.source_type == "ODOO":
            preview = _apply_odoo_source_conflicts(
                db,
                effective_company_id,
                batch,
                preview,
                file_data["rows"],
                metadata.get("odoo_source_snapshots", {}),
                decisions,
            )
        if not preview["summary"]["ready_for_confirmation"]:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Resolve required mappings before confirming.",
                    "missing_mappings": preview["missing_mappings"],
                    "errors": [
                        error for error in preview["errors"]
                        if error.get("row_number") is None
                    ],
                },
            )

        imported_sources, _ = _odoo_source_history(
            db,
            effective_company_id,
            exclude_batch_id=batch.id,
        ) if batch.source_type == "ODOO" else ({}, set())
        source_rows_by_number = {
            index + 2: row for index, row in enumerate(file_data["rows"])
        }
        employees_to_insert = []
        employees_to_update: list[tuple[Employee, dict[str, Any]]] = []
        for row in preview["valid_rows"]:
            source_row = source_rows_by_number.get(row["row_number"], {})
            reference = source_row.get("_odoo_source_reference")
            if (
                batch.source_type == "ODOO"
                and isinstance(reference, str)
                and decisions.get(reference) == "update"
            ):
                imported = imported_sources.get(reference)
                employee = imported.get("employee") if imported else None
                if employee is None:
                    raise HTTPException(
                        status_code=409,
                        detail="The previously imported employee is no longer available.",
                    )
                employees_to_update.append((employee, row["data"]))
            else:
                employees_to_insert.append(
                    Employee(
                        **employee_model_values(row["data"]),
                        company_id=effective_company_id,
                    )
                )
        db.add_all(employees_to_insert)
        for employee, data in employees_to_update:
            for field, value in employee_model_values(data).items():
                setattr(employee, field, value)
        db.flush()

        company_employees = db.query(Employee).filter(
            Employee.company_id == effective_company_id,
            Employee.is_active.is_(True),
        ).all()
        employees_by_code = {
            employee.employee_id.strip().casefold(): employee
            for employee in company_employees
        }
        for employee in employees_to_insert:
            manager_code = (employee.manager_id or "").strip().casefold()
            if not manager_code:
                continue
            manager = employees_by_code.get(manager_code)
            if manager is None or manager.id == employee.id:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "A manager relationship changed after preview; "
                        "preview the batch again."
                    ),
                )
            employee.manager_internal_id = manager.id
        for employee, _ in employees_to_update:
            manager_code = (employee.manager_id or "").strip().casefold()
            if not manager_code:
                employee.manager_internal_id = None
                continue
            manager = employees_by_code.get(manager_code)
            if manager is None or manager.id == employee.id:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "A manager relationship changed after preview; "
                        "preview the batch again."
                    ),
                )
            employee.manager_internal_id = manager.id

        if batch.source_type == "ODOO":
            imported_metadata = metadata.setdefault("odoo_imported_sources", {})
            if not isinstance(imported_metadata, dict):
                imported_metadata = metadata["odoo_imported_sources"] = {}
            for row in preview["valid_rows"]:
                source_row = source_rows_by_number.get(row["row_number"], {})
                reference = source_row.get("_odoo_source_reference")
                if not isinstance(reference, str):
                    continue
                employee = next(
                    (
                        updated_employee
                        for updated_employee, _ in employees_to_update
                        if updated_employee is imported_sources.get(reference, {}).get("employee")
                    ),
                    None,
                )
                if employee is None:
                    employee = next(
                        (
                            inserted_employee
                            for inserted_employee in employees_to_insert
                            if inserted_employee.employee_id
                            == employee_model_values(row["data"]).get("employee_id")
                        ),
                        None,
                    )
                if employee is None:
                    raise HTTPException(
                        status_code=409,
                        detail="The employee import could not be linked to its Odoo source.",
                    )
                imported_metadata[reference] = {
                    "employee_pk": employee.id,
                    "employee_id": employee.employee_id,
                    "source_snapshot": metadata.get(
                        "odoo_source_snapshots", {}
                    ).get(reference),
                }
            for reference, decision in decisions.items():
                if decision != "keep":
                    continue
                imported = imported_sources.get(reference)
                employee = imported.get("employee") if imported else None
                if employee is None:
                    continue
                imported_metadata[reference] = {
                    "employee_pk": employee.id,
                    "employee_id": employee.employee_id,
                    "source_snapshot": metadata.get(
                        "odoo_source_snapshots", {}
                    ).get(reference),
                }

        persisted_issues = list(preview["errors"])
        persisted_issues.extend(
            {
                **warning,
                "type": f"warning_{warning['type']}",
            }
            for warning in preview["warnings"]
        )
        replace_import_issues(db, batch.id, persisted_issues)

        batch.successful_rows = (
            len(employees_to_insert) + len(employees_to_update)
        )
        batch.failed_rows = (
            len({
                error.get("row_number")
                for error in preview["errors"]
                if error.get("row_number") is not None
            })
            if batch.source_type == "ODOO"
            else batch.total_rows - batch.successful_rows
        )
        batch.status = (
            "Completed with errors"
            if batch.failed_rows
            else "Completed"
        )
        batch.completed_at = datetime.utcnow()
        if batch.source_type == "ODOO":
            _, _, metadata_path = _read_batch_metadata(
                batch,
                effective_company_id,
            )
            _write_batch_metadata(metadata_path, metadata)
        db.commit()
        db.refresh(batch)

        return json_safe({
            "message": "Employee import confirmed.",
            "batch_id": batch.id,
            "company_id": effective_company_id,
            "status": batch.status,
            "summary": {
                "total_rows": batch.total_rows,
                "successful_rows": batch.successful_rows,
                "failed_rows": batch.failed_rows,
                "updated_rows": len(employees_to_update),
                "skipped_rows": preview["summary"].get("skipped_rows", 0),
                "total_errors": len(preview["errors"]),
                "total_warnings": len(preview["warnings"]),
            },
            "errors": preview["errors"],
            "warnings": preview["warnings"],
        })
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=(
                "Employee data changed after preview. Review the batch again "
                "before retrying."
            ),
        ) from exc
    except OdooError as exc:
        db.rollback()
        raise _safe_odoo_http_error(exc) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="The employee import could not be committed.",
        ) from exc


class ImportIssueCorrectionRequest(BaseModel):
    corrected_value: str
    resolution_note: str | None = None


@router.get("/{batch_id}/issues")
def list_import_issues(
    batch_id: int,
    company_id: int = Query(..., gt=0),
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    batch = db.query(ImportBatch).filter(
        ImportBatch.id == batch_id,
        ImportBatch.company_id == company_id,
    ).first()

    if batch is None:
        raise HTTPException(status_code=404, detail="Import batch not found.")

    query = db.query(ImportRowIssue).filter(
        ImportRowIssue.batch_id == batch_id
    )

    if status:
        query = query.filter(ImportRowIssue.status == status)

    issues = query.order_by(
        ImportRowIssue.row_number,
        ImportRowIssue.id,
    ).all()

    return {
        "batch_id": batch_id,
        "company_id": company_id,
        "batch_status": batch.status,
        "total_issues": len(issues),
        "issues": [
            {
                "id": issue.id,
                "row_number": issue.row_number,
                "field_name": issue.field_name,
                "issue_type": issue.issue_type,
                "message": issue.message,
                "raw_value": issue.raw_value,
                "corrected_value": issue.corrected_value,
                "status": issue.status,
                "resolved_at": (
                    issue.resolved_at.isoformat()
                    if issue.resolved_at else None
                ),
                "resolution_note": issue.resolution_note,
            }
            for issue in issues
        ],
    }


@router.patch("/{batch_id}/issues/{issue_id}")
def correct_import_issue(
    batch_id: int,
    issue_id: int,
    correction: ImportIssueCorrectionRequest,
    company_id: int = Query(..., gt=0),
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    batch = db.query(ImportBatch).filter(
        ImportBatch.id == batch_id,
        ImportBatch.company_id == company_id,
    ).first()

    if batch is None:
        raise HTTPException(status_code=404, detail="Import batch not found.")

    issue = db.query(ImportRowIssue).filter(
        ImportRowIssue.id == issue_id,
        ImportRowIssue.batch_id == batch_id,
    ).first()

    if issue is None:
        raise HTTPException(status_code=404, detail="Import issue not found.")

    if issue.field_name != "email":
        raise HTTPException(
            status_code=400,
            detail="This endpoint currently supports email corrections only.",
        )

    if issue.status == "Resolved":
        raise HTTPException(
            status_code=409,
            detail="This issue has already been resolved.",
        )

    corrected_value = correction.corrected_value.strip()

    if not corrected_value:
        raise HTTPException(
            status_code=400,
            detail="Corrected email cannot be empty.",
        )

    # Validate that the manually supplied address is a complete email.
    # No guessed address is accepted by this endpoint.
    from backend.app.services.data_correction import correct_email

    validation = correct_email(corrected_value)
    if validation["action"] == "human_review":
        raise HTTPException(
            status_code=400,
            detail="The corrected email is not a valid normalized email address.",
        )

    corrected_value = validation["corrected_value"]

    # Preserve the proposed value on the issue until reprocessing succeeds.
    issue.corrected_value = corrected_value
    issue.resolution_note = correction.resolution_note
    issue.resolved_at = None
    issue.status = "Open"

    # Keep an immutable audit entry for this human decision.
    audit_record = ImportIssueCorrection(
        issue_id=issue.id,
        original_value=issue.raw_value,
        proposed_value=corrected_value,
        applied_value=None,
        action="human_approved",
        method="manual_review",
        confidence=1.0,
        status="Approved",
        resolution_note=correction.resolution_note,
        reviewed_at=datetime.utcnow(),
        reviewed_by_user_id=context.user.user_id,
    )
    db.add(audit_record)

    db.commit()
    db.refresh(issue)

    return {
        "message": "Correction saved. Reprocess the batch to validate it.",
        "batch_id": batch_id,
        "issue_id": issue.id,
        "row_number": issue.row_number,
        "original_value": issue.raw_value,
        "corrected_value": issue.corrected_value,
        "status": issue.status,
    }


@router.post("/{batch_id}/reprocess")
def reprocess_employee_import(
    batch_id: int,
    company_id: int = Query(..., gt=0),
    db: Session = Depends(get_db),
):
    batch = db.query(ImportBatch).filter(
        ImportBatch.id == batch_id,
        ImportBatch.company_id == company_id,
    ).first()

    if batch is None:
        raise HTTPException(status_code=404, detail="Import batch not found.")

    if batch.entity_type != "employee":
        raise HTTPException(
            status_code=400,
            detail="This endpoint only supports employee imports.",
        )

    try:
        open_issues = db.query(ImportRowIssue).filter(
            ImportRowIssue.batch_id == batch_id,
            ImportRowIssue.status == "Open",
        ).order_by(ImportRowIssue.id).all()

        if not open_issues:
            return {
                "message": "There are no open issues to reprocess.",
                "batch_id": batch_id,
                "status": batch.status,
                "newly_imported_rows": 0,
                "remaining_failed_rows": 0,
            }

        unsupported_issues = [
            issue for issue in open_issues
            if issue.field_name != "email"
        ]

        if unsupported_issues:
            raise HTTPException(
                status_code=409,
                detail="This version can reprocess email issues only.",
            )

        affected_rows = {
            issue.row_number for issue in open_issues
        }

        batch_directory = _batch_directory(company_id, batch_id)
        metadata_path = batch_directory / "metadata.json"

        extension = Path(batch.file_name or "").suffix.lower()
        source_path = batch_directory / f"source{extension}"

        if not metadata_path.is_file() or not source_path.is_file():
            raise HTTPException(
                status_code=404,
                detail="Original source file or metadata not found.",
            )

        metadata = json.loads(
            metadata_path.read_text(encoding="utf-8")
        )

        if (
            metadata.get("company_id") != company_id
            or metadata.get("batch_id") != batch_id
        ):
            raise HTTPException(
                status_code=409,
                detail="Stored metadata does not match this batch.",
            )

        file_data = read_tabular_file(
            source_path.read_bytes(),
            batch.file_name,
            sheet_name=metadata.get("worksheet"),
        )

        suggestions = metadata.get("column_mapping", {})
        combined_fields = metadata.get("combined_fields", [])
        approved_defaults = metadata.get("approved_defaults", {})

        email_columns = [
            column
            for column, suggestion in suggestions.items()
            if suggestion.get("field") == "email"
        ]

        if len(email_columns) != 1:
            raise HTTPException(
                status_code=409,
                detail="Could not identify exactly one mapped email column.",
            )

        email_column = email_columns[0]
        source_rows = file_data["rows"]

        # Apply the latest saved correction to each affected source row.
        corrections_by_row = {}

        for issue in open_issues:
            if issue.corrected_value is not None:
                corrections_by_row[issue.row_number] = (
                    issue.corrected_value
                )

        for row_number, corrected_email in corrections_by_row.items():
            row_index = row_number - 2

            if row_index < 0 or row_index >= len(source_rows):
                raise HTTPException(
                    status_code=409,
                    detail=f"Source row {row_number} does not exist.",
                )

            source_rows[row_index][email_column] = corrected_email

        # Validate the source, but only process rows with open issues.
        validation_result = validate_employee_rows(
            rows=source_rows,
            suggestions=suggestions,
            combined_fields=combined_fields,
            approved_defaults=approved_defaults,
        )

        if validation_result["missing_mappings"]:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Required mappings are missing.",
                    "missing_mappings": validation_result["missing_mappings"],
                },
            )

        errors_by_row = {}

        for error in validation_result["errors"]:
            row_number = error.get("row_number")
            if row_number in affected_rows:
                errors_by_row.setdefault(row_number, []).append(error)

        valid_affected_rows = [
            item for item in validation_result["valid_rows"]
            if item["row_number"] in affected_rows
        ]

        # Check database conflicts only for affected rows.
        candidate_ids = {
            str(item["data"]["employee_id"])
            for item in valid_affected_rows
        }
        candidate_emails = {
            str(item["data"]["email"]).lower()
            for item in valid_affected_rows
        }

        existing_ids = set()
        existing_emails = set()

        if candidate_ids:
            existing_ids = {
                value
                for (value,) in db.query(Employee.employee_id).filter(
                    Employee.company_id == company_id,
                    Employee.employee_id.in_(candidate_ids),
                ).all()
            }

        if candidate_emails:
            existing_emails = {
                value.lower()
                for (value,) in db.query(
                    func.lower(Employee.email)
                ).filter(
                    Employee.company_id == company_id,
                    func.lower(Employee.email).in_(candidate_emails),
                ).all()
            }

        database_errors_by_row = {}
        employees_to_insert = []
        inserted_rows = set()

        for item in valid_affected_rows:
            data = item["data"]
            row_number = item["row_number"]
            employee_id = str(data["employee_id"])
            email = str(data["email"]).lower()

            conflict = None

            if employee_id in existing_ids:
                conflict = {
                    "row_number": row_number,
                    "field": "employee_id",
                    "type": "duplicate_in_database",
                    "message": (
                        f"Employee ID '{employee_id}' already exists "
                        "in this company."
                    ),
                }
            elif email in existing_emails:
                conflict = {
                    "row_number": row_number,
                    "field": "email",
                    "type": "duplicate_in_database",
                    "message": (
                        f"Email '{email}' already exists in this company."
                    ),
                }

            if conflict:
                database_errors_by_row.setdefault(
                    row_number, []
                ).append(conflict)
                continue

            employee_data = {
                key: value
                for key, value in data.items()
                if key in EMPLOYEE_FIELDS
            }

            employees_to_insert.append(
                Employee(
                    **employee_data,
                    company_id=company_id,
                )
            )

            existing_ids.add(employee_id)
            existing_emails.add(email)
            inserted_rows.add(row_number)

        if employees_to_insert:
            db.add_all(employees_to_insert)
            db.flush()
            link_manager_references(db, company_id)

        # Create newly discovered issues without duplicating existing ones.
        all_batch_issues = db.query(ImportRowIssue).filter(
            ImportRowIssue.batch_id == batch_id
        ).all()

        existing_issue_keys = {
            (issue.row_number, issue.field_name, issue.issue_type)
            for issue in all_batch_issues
        }

        for row_number, errors in errors_by_row.items():
            for error in errors:
                issue_type = error.get("type", "validation_error")[:30]
                field_name = error.get("field")
                key = (row_number, field_name, issue_type)

                if key not in existing_issue_keys:
                    db.add(
                        ImportRowIssue(
                            batch_id=batch_id,
                            row_number=row_number,
                            field_name=field_name,
                            issue_type=issue_type,
                            message=error.get(
                                "message", "Validation failed."
                            ),
                            raw_value=(
                                str(error["raw_value"])
                                if error.get("raw_value") is not None
                                else None
                            ),
                        )
                    )
                    existing_issue_keys.add(key)

        for row_number, errors in database_errors_by_row.items():
            for error in errors:
                issue_type = error["type"][:30]
                field_name = error["field"]
                key = (row_number, field_name, issue_type)

                if key not in existing_issue_keys:
                    db.add(
                        ImportRowIssue(
                            batch_id=batch_id,
                            row_number=row_number,
                            field_name=field_name,
                            issue_type=issue_type,
                            message=error["message"],
                        )
                    )
                    existing_issue_keys.add(key)

        # Resolve all issues for rows successfully inserted.
        for issue in all_batch_issues:
            if issue.row_number in inserted_rows:
                issue.status = "Resolved"
                issue.resolved_at = datetime.utcnow()
                if not issue.resolution_note:
                    issue.resolution_note = (
                        "Resolved after successful batch reprocessing."
                    )

        # Mark the corresponding audit entries as applied.
        # The original CSV remains unchanged; applied_value records
        # the value used for the inserted database employee.
        if inserted_rows:
            applied_issue_ids = [
                issue.id
                for issue in all_batch_issues
                if issue.row_number in inserted_rows
                and issue.field_name == "email"
            ]

            if applied_issue_ids:
                audit_entries = db.query(ImportIssueCorrection).filter(
                    ImportIssueCorrection.issue_id.in_(applied_issue_ids),
                    ImportIssueCorrection.status == "Approved",
                ).all()

                for audit in audit_entries:
                    audit.applied_value = audit.proposed_value
                    audit.status = "Applied"
                    audit.reviewed_at = audit.reviewed_at or datetime.utcnow()
                    if not audit.resolution_note:
                        audit.resolution_note = (
                            "Human-approved email correction applied "
                            "after successful row reprocessing."
                        )

        db.flush()

        remaining_open_rows = {
            issue.row_number
            for issue in db.query(ImportRowIssue).filter(
                ImportRowIssue.batch_id == batch_id,
                ImportRowIssue.status == "Open",
            ).all()
        }

        remaining_open_count = db.query(ImportRowIssue).filter(
            ImportRowIssue.batch_id == batch_id,
            ImportRowIssue.status == "Open",
        ).count()

        resolved_count = db.query(ImportRowIssue).filter(
            ImportRowIssue.batch_id == batch_id,
            ImportRowIssue.status == "Resolved",
        ).count()

        batch.successful_rows = (
            (batch.successful_rows or 0) + len(inserted_rows)
        )
        batch.failed_rows = len(remaining_open_rows)
        batch.status = (
            "Completed with errors"
            if remaining_open_rows
            else "Completed"
        )
        batch.completed_at = datetime.utcnow()

        db.commit()
        db.refresh(batch)

        return {
            "message": "Batch reprocessing completed.",
            "batch_id": batch_id,
            "company_id": company_id,
            "status": batch.status,
            "summary": {
                "affected_rows": len(affected_rows),
                "newly_imported_rows": len(inserted_rows),
                "total_imported_rows": batch.successful_rows,
                "remaining_failed_rows": batch.failed_rows,
                "remaining_open_issues": remaining_open_count,
                "resolved_issues": resolved_count,
            },
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=(
                "Batch reprocessing failed. "
                "No reprocessing database changes were committed."
            ),
        ) from exc


@router.get("/{batch_id}/preview-corrections")
def preview_import_corrections(
    batch_id: int,
    company_id: int = Query(..., gt=0),
    db: Session = Depends(get_db),
):
    """
    Read-only preview of proposed email corrections.
    Does not modify source files, issues, employees, or audit records.
    """

    batch = db.query(ImportBatch).filter(
        ImportBatch.id == batch_id,
        ImportBatch.company_id == company_id,
        ImportBatch.entity_type == "employee",
    ).first()

    if batch is None:
        raise HTTPException(
            status_code=404,
            detail="Employee import batch not found.",
        )

    batch_directory = _batch_directory(company_id, batch_id)
    metadata_path = batch_directory / "metadata.json"

    extension = Path(batch.file_name or "").suffix.lower()
    source_path = batch_directory / f"source{extension}"

    if not metadata_path.is_file() or not source_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Original source file or metadata not found.",
        )

    metadata = json.loads(
        metadata_path.read_text(encoding="utf-8")
    )

    if (
        metadata.get("company_id") != company_id
        or metadata.get("batch_id") != batch_id
    ):
        raise HTTPException(
            status_code=409,
            detail="Stored metadata does not match this batch.",
        )

    file_data = read_tabular_file(
        source_path.read_bytes(),
        batch.file_name,
        sheet_name=metadata.get("worksheet"),
    )

    email_columns = [
        column
        for column, suggestion in metadata.get(
            "column_mapping", {}
        ).items()
        if suggestion.get("field") == "email"
    ]

    if len(email_columns) != 1:
        raise HTTPException(
            status_code=409,
            detail="Could not identify exactly one mapped email column.",
        )

    email_column = email_columns[0]
    source_rows = file_data["rows"]

    open_issues = db.query(ImportRowIssue).filter(
        ImportRowIssue.batch_id == batch_id,
        ImportRowIssue.status == "Open",
        ImportRowIssue.field_name == "email",
    ).order_by(
        ImportRowIssue.row_number,
        ImportRowIssue.id,
    ).all()

    duplicate_rows = {
        issue.row_number
        for issue in open_issues
        if "duplicate" in issue.issue_type.lower()
    }

    preview = []

    for issue in open_issues:
        row_index = issue.row_number - 2

        if row_index < 0 or row_index >= len(source_rows):
            preview.append({
                "issue_id": issue.id,
                "row_number": issue.row_number,
                "original_value": issue.raw_value,
                "action": "human_review",
                "proposed_value": None,
                "reason": "Source row could not be located.",
            })
            continue

        original_value = source_rows[row_index].get(email_column)

        if issue.row_number in duplicate_rows:
            result = classify_duplicate_email(
                str(original_value or "")
            )
        else:
            result = correct_email(original_value)

        preview.append({
            "issue_id": issue.id,
            "row_number": issue.row_number,
            "original_value": result["original_value"],
            "proposed_value": result["corrected_value"],
            "action": result["action"],
            "confidence": result["confidence"],
            "method": result["method"],
            "reason": result["message"],
            "existing_human_correction": issue.corrected_value,
        })

    return {
        "batch_id": batch_id,
        "company_id": company_id,
        "mode": "READ_ONLY_PREVIEW",
        "source_modified": False,
        "database_modified": False,
        "total_open_email_issues": len(preview),
        "automatic_corrections": sum(
            item["action"] == "auto_correct"
            for item in preview
        ),
        "human_review_required": sum(
            item["action"] == "human_review"
            for item in preview
        ),
        "items": preview,
    }