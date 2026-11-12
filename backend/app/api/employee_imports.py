import json
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session
from pydantic import BaseModel

from backend.app.api.dependencies import get_db
from backend.app.db.company import Company
from backend.app.db.employee import Employee
from backend.app.db.import_batch import ImportBatch
from backend.app.db.import_row_issue import ImportRowIssue
from backend.app.db.import_issue_correction import ImportIssueCorrection
from backend.app.services.file_reader import read_tabular_file
from backend.app.services.column_mapper import detect_employee_columns
from backend.app.services.employee_validator import validate_employee_rows
from backend.app.services.data_correction import correct_email, classify_duplicate_email


router = APIRouter(
    prefix="/employee-imports",
    tags=["Employee Imports"],
)

MAX_FILE_SIZE = 20 * 1024 * 1024

# This default was explicitly approved for the current employee dataset.
APPROVED_DEFAULTS = {
    "job_level": "Not specified",
}

# Only these standardized fields may be inserted into Employee.
EMPLOYEE_FIELDS = {
    "employee_id",
    "full_name",
    "email",
    "job_title",
    "department",
    "manager_id",
    "employment_status",
    "working_hours_per_week",
    "learning_hours_per_week",
    "years_of_experience",
    "hire_date",
    "job_level",
    "employment_type",
    "preferred_learning_mode",
}


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
    storage_root = Path(__file__).resolve().parents[2] / "data" / "imports"

    batch_directory = storage_root / str(company_id) / str(batch_id)
    batch_directory.mkdir(parents=True, exist_ok=False)

    extension = Path(filename).suffix.lower()
    source_path = batch_directory / f"source{extension}"
    metadata_path = batch_directory / "metadata.json"

    source_path.write_bytes(file_content)

    metadata_path.write_text(
        json.dumps(json_safe(metadata), indent=2),
        encoding="utf-8",
    )

    return [source_path, metadata_path]


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
            )
        )

    if records:
        db.add_all(records)


@router.post("/upload")
async def upload_employee_file(
    company_id: int = Query(..., gt=0),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    company = db.query(Company).filter(
        Company.company_id == company_id
    ).first()

    if company is None:
        raise HTTPException(
            status_code=404,
            detail="Company not found.",
        )

    filename = Path(file.filename or "").name

    if not filename:
        raise HTTPException(
            status_code=400,
            detail="A filename is required.",
        )

    extension = Path(filename).suffix.lower()

    if extension not in {".csv", ".xlsx"}:
        raise HTTPException(
            status_code=400,
            detail="Only CSV and XLSX files are supported.",
        )

    stored_paths: list[Path] = []

    try:
        file_content = await file.read()

        if not file_content:
            raise HTTPException(
                status_code=400,
                detail="The uploaded file is empty.",
            )

        if len(file_content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail="The uploaded file exceeds the 20 MB limit.",
            )

        file_data = read_tabular_file(file_content, filename)

        mapping_result = detect_employee_columns(
            file_data["columns"]
        )

        validation_result = validate_employee_rows(
            rows=file_data["rows"],
            suggestions=mapping_result["suggestions"],
            combined_fields=mapping_result["combined_fields"],
            approved_defaults=APPROVED_DEFAULTS,
        )

        batch = ImportBatch(
            company_id=company_id,
            source_type="CSV" if extension == ".csv" else "Excel",
            entity_type="employee",
            file_name=filename,
            status="Processing",
            total_rows=validation_result["summary"]["total_rows"],
            successful_rows=0,
            failed_rows=0,
        )

        db.add(batch)
        db.flush()

        metadata = {
            "company_id": company_id,
            "batch_id": batch.id,
            "original_filename": filename,
            "source_type": file_data["file_type"],
            "column_mapping": mapping_result["suggestions"],
            "combined_fields": mapping_result["combined_fields"],
            "approved_defaults": APPROVED_DEFAULTS,
        }

        stored_paths = save_batch_files(
            company_id=company_id,
            batch_id=batch.id,
            filename=filename,
            file_content=file_content,
            metadata=metadata,
        )

        validation_errors = list(validation_result["errors"])
        database_errors = []
        imported_count = 0

        # Do not import anything if mappings are uncertain or
        # required fields have not been mapped.
        requires_review = (
            mapping_result["requires_manual_review"]
            or bool(validation_result["missing_mappings"])
        )

        if not requires_review:
            valid_rows = validation_result["valid_rows"]

            employee_ids = {
                str(item["data"]["employee_id"])
                for item in valid_rows
            }

            emails = {
                str(item["data"]["email"]).lower()
                for item in valid_rows
            }

            existing_ids = set()
            existing_emails = set()

            if employee_ids:
                existing_ids = {
                    value
                    for (value,) in db.query(Employee.employee_id).filter(
                        Employee.company_id == company_id,
                        Employee.employee_id.in_(employee_ids),
                    ).all()
                }

            if emails:
                existing_emails = {
                    value.lower()
                    for (value,) in db.query(
                        func.lower(Employee.email)
                    ).filter(
                        Employee.company_id == company_id,
                        func.lower(Employee.email).in_(emails),
                    ).all()
                }

            employees_to_insert = []

            for item in valid_rows:
                data = item["data"]
                row_number = item["row_number"]

                employee_id = str(data["employee_id"])
                email = str(data["email"]).lower()

                if employee_id in existing_ids:
                    database_errors.append({
                        "row_number": row_number,
                        "field": "employee_id",
                        "type": "duplicate_in_database",
                        "message": (
                            f"Employee ID '{employee_id}' "
                            "already exists in this company."
                        ),
                    })
                    continue

                if email in existing_emails:
                    database_errors.append({
                        "row_number": row_number,
                        "field": "email",
                        "type": "duplicate_in_database",
                        "message": (
                            f"Email '{email}' already exists "
                            "in this company."
                        ),
                    })
                    continue

                # Whitelist model fields. In particular, manager_name,
                # first_name, last_name and email_original are excluded.
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

            if employees_to_insert:
                db.add_all(employees_to_insert)
                db.flush()
                imported_count = len(employees_to_insert)

        all_errors = validation_errors + database_errors

        # Persist errors only. Approved-default warnings are returned
        # in the response but are not stored as thousands of issue rows.
        persist_issues(db, batch.id, all_errors)

        batch.successful_rows = imported_count
        batch.failed_rows = (
            validation_result["summary"]["invalid_rows"]
            + len(database_errors)
        )

        if requires_review:
            batch.status = "Needs review"
        elif batch.failed_rows:
            batch.status = "Completed with errors"
        else:
            batch.status = "Completed"

        batch.completed_at = datetime.utcnow()

        db.commit()
        db.refresh(batch)

        return json_safe({
            "message": (
                "Import held for mapping review."
                if requires_review
                else "Employee import completed."
            ),
            "batch_id": batch.id,
            "company_id": company_id,
            "filename": filename,
            "status": batch.status,
            "storage": "Original file and metadata saved.",
            "approved_defaults": APPROVED_DEFAULTS,
            "summary": {
                "total_rows": batch.total_rows,
                "imported_rows": batch.successful_rows,
                "failed_rows": batch.failed_rows,
                "validation_errors": len(validation_errors),
                "database_duplicates": len(database_errors),
                "total_errors": len(all_errors),
                "mapping_review_required": requires_review,
            },
            "column_mapping": mapping_result["suggestions"],
            "combined_fields": mapping_result["combined_fields"],
            "unmatched_columns": mapping_result["unmatched_columns"],
            "missing_mappings": validation_result["missing_mappings"],
            "error_counts": build_issue_counts(all_errors),
            "errors": all_errors,
            "warning_counts": build_issue_counts(
                validation_result["warnings"]
            ),
        })

    except HTTPException:
        db.rollback()
        for path in stored_paths:
            path.unlink(missing_ok=True)
        raise

    except ValueError as exc:
        db.rollback()
        for path in stored_paths:
            path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        db.rollback()
        for path in stored_paths:
            path.unlink(missing_ok=True)

        raise HTTPException(
            status_code=500,
            detail=(
                "The employee import failed. "
                "No database changes were committed."
            ),
        ) from exc

    finally:
        await file.close()


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

        storage_root = (
            Path(__file__).resolve().parents[2]
            / "data" / "imports"
        )
        batch_directory = storage_root / str(company_id) / str(batch_id)
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

    storage_root = (
        Path(__file__).resolve().parents[2]
        / "data" / "imports"
    )
    batch_directory = storage_root / str(company_id) / str(batch_id)
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