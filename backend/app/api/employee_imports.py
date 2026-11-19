import json
import shutil
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any

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
from pydantic import BaseModel

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


def _odoo_existing_source_references(
    db: Session,
    company_id: int,
    *,
    exclude_batch_id: int | None = None,
) -> set[str]:
    employee_ids: set[str] = set()
    batches = db.query(ImportBatch).filter(
        ImportBatch.company_id == company_id,
        ImportBatch.entity_type == "employee",
        ImportBatch.source_type == "ODOO",
    ).all()
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
        source_map = metadata.get("odoo_employee_source_map", {})
        if isinstance(source_map, dict):
            for employee_id in source_map:
                if isinstance(employee_id, str):
                    employee_ids.add(employee_id.strip().casefold())
        for reference in metadata.get("odoo_source_references", []):
            if isinstance(reference, str):
                suffix = reference.rsplit(":", 1)[-1]
                employee_ids.add(f"odoo-{suffix}".casefold())
    return employee_ids


def _apply_odoo_source_conflicts(
    db: Session,
    company_id: int,
    batch: ImportBatch,
    preview: dict[str, Any],
) -> dict[str, Any]:
    existing = _odoo_existing_source_references(
        db,
        company_id,
        exclude_batch_id=batch.id,
    )
    fallback_warnings: list[dict[str, Any]] = []

    for row in preview["rows"]:
        data = row["data"]
        employee_id = data.get("employee_id")
        source_key = (
            str(employee_id).strip().casefold()
            if employee_id is not None
            else ""
        )
        if source_key and source_key in existing:
            error = {
                "row_number": row["row_number"],
                "field": "_odoo_source_reference",
                "type": "duplicate_odoo_source_reference",
                "message": (
                    "This Odoo employee source reference was already used "
                    "by a previous import batch."
                ),
                "raw_value": employee_id,
            }
            row["errors"].append(error)
            preview["errors"].append(error)
            row["importable"] = False

        if data.get("_odoo_employee_id_generated") is True:
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
            fallback_warnings.append(warning)

    preview["warnings"].extend(fallback_warnings)
    preview["valid_rows"] = [
        {"row_number": row["row_number"], "data": row["data"]}
        for row in preview["rows"]
        if not row["errors"]
    ]
    preview["summary"]["importable_rows"] = len(preview["valid_rows"])
    preview["summary"]["invalid_rows"] = (
        len(preview["rows"]) - len(preview["valid_rows"])
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
    status["api_key_configured"] = bool(config.api_key)
    status["api_key"] = None
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
            mapping = request.column_mapping
        else:
            mapping = suggested_mapping

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

    metadata = {
        "company_id": effective_company_id,
        "batch_id": batch.id,
        "original_filename": batch.file_name,
        "source_type": "ODOO",
        "odoo_database": config.database,
        "odoo_base_url": config.base_url,
        "odoo_company_id": request.odoo_company_id,
        "odoo_version": None,
        "column_mapping_fields": mapping,
        "column_mapping": _structured_mapping(mapping),
        "combined_fields": _combined_name_fields(mapping),
        "approved_defaults": APPROVED_DEFAULTS,
        "odoo_source_references": [
            row["_odoo_source_reference"] for row in rows
        ],
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
        preview = build_employee_import_preview(
            db,
            effective_company_id,
            file_data["columns"],
            file_data["rows"],
            request.column_mapping,
        )
        if batch.source_type == "ODOO":
            preview = _apply_odoo_source_conflicts(
                db,
                effective_company_id,
                batch,
                preview,
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
        **preview,
    })


@router.post("/{batch_id}/confirm")
def confirm_employee_import(
    batch_id: int,
    request: ImportConfirmationRequest,
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

        preview = build_employee_import_preview(
            db,
            effective_company_id,
            file_data["columns"],
            file_data["rows"],
            metadata.get("column_mapping_fields"),
        )
        if batch.source_type == "ODOO":
            preview = _apply_odoo_source_conflicts(
                db,
                effective_company_id,
                batch,
                preview,
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

        employees_to_insert = [
            Employee(
                **employee_model_values(row["data"]),
                company_id=effective_company_id,
            )
            for row in preview["valid_rows"]
        ]
        db.add_all(employees_to_insert)
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

        persisted_issues = list(preview["errors"])
        persisted_issues.extend(
            {
                **warning,
                "type": f"warning_{warning['type']}",
            }
            for warning in preview["warnings"]
        )
        replace_import_issues(db, batch.id, persisted_issues)

        batch.successful_rows = len(employees_to_insert)
        batch.failed_rows = batch.total_rows - batch.successful_rows
        batch.status = (
            "Completed with errors"
            if batch.failed_rows
            else "Completed"
        )
        batch.completed_at = datetime.utcnow()
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