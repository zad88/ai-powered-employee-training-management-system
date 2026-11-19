from collections import defaultdict
from typing import Any

from sqlalchemy.orm import Session

from backend.app.db.employee import Employee
from backend.app.services.column_mapper import (
    EMPLOYEE_FIELD_ALIASES,
    detect_employee_columns,
)
from backend.app.services.employee_validator import validate_employee_rows


APPROVED_DEFAULTS = {"job_level": "Not specified"}
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
AVAILABLE_MAPPING_FIELDS = sorted(
    set(EMPLOYEE_FIELD_ALIASES)
    | {
        "first_name",
        "last_name",
        "manager_name",
        "_odoo_source_reference",
        "_odoo_employee_id_generated",
    }
)
STRING_FIELD_LIMITS = {
    "employee_id": 100,
    "full_name": 150,
    "email": 255,
    "job_title": 150,
    "department": 100,
    "manager_id": 100,
    "manager_name": 150,
    "employment_status": 30,
    "job_level": 50,
    "employment_type": 50,
    "preferred_learning_mode": 30,
}


def _casefold(value: Any) -> str:
    return str(value).strip().casefold()


def _normalized_name(value: Any) -> str:
    return " ".join(str(value).strip().casefold().split())


def suggested_column_mapping(columns: list[str]) -> dict[str, str | None]:
    detection = detect_employee_columns(columns)
    return {
        column: suggestion.get("field")
        for column, suggestion in detection["suggestions"].items()
    }


def _validation_mapping(
    columns: list[str],
    column_mapping: dict[str, str | None] | None,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]], dict[str, str | None]]:
    mapping = (
        suggested_column_mapping(columns)
        if column_mapping is None
        else column_mapping
    )
    unknown_columns = set(mapping) - set(columns)
    if unknown_columns:
        raise ValueError(
            "The mapping contains source columns not present in the uploaded file."
        )

    normalized_mapping = {
        column: mapping.get(column)
        for column in columns
    }
    allowed_fields = set(AVAILABLE_MAPPING_FIELDS)
    if any(
        field is not None and field not in allowed_fields
        for field in normalized_mapping.values()
    ):
        raise ValueError("The mapping contains an unsupported employee field.")

    mapped_fields: dict[str, list[str]] = defaultdict(list)
    for column, field in normalized_mapping.items():
        if field:
            mapped_fields[field].append(column)

    mapping_errors = []
    for field, source_columns in mapped_fields.items():
        if len(source_columns) > 1:
            mapping_errors.append({
                "row_number": None,
                "field": field,
                "type": "mapping_conflict",
                "message": (
                    f"Map only one source column to '{field}'; "
                    f"currently mapped: {', '.join(source_columns)}."
                ),
            })

    if "full_name" in mapped_fields and (
        "first_name" in mapped_fields or "last_name" in mapped_fields
    ):
        mapping_errors.append({
            "row_number": None,
            "field": "full_name",
            "type": "mapping_conflict",
            "message": (
                "Map either a full-name column or both first- and last-name "
                "columns, not both."
            ),
        })

    first_names = mapped_fields.get("first_name", [])
    last_names = mapped_fields.get("last_name", [])
    combined_fields = []
    if first_names and last_names:
        combined_fields.append({
            "field": "full_name",
            "source_columns": [first_names[0], last_names[0]],
            "transformation": "combine_names",
            "requires_review": False,
        })

    suggestions = {
        column: {
            "field": field,
            "confidence": 1.0 if field else 0.0,
            "match_type": "manual" if field else "unmapped",
            "requires_review": False,
        }
        for column, field in normalized_mapping.items()
    }
    return suggestions, combined_fields, normalized_mapping


def _add_row_error(
    row: dict[str, Any],
    errors: list[dict[str, Any]],
    *,
    field: str,
    error_type: str,
    message: str,
    raw_value: Any = None,
) -> None:
    error = {
        "row_number": row["row_number"],
        "field": field,
        "type": error_type,
        "message": message,
    }
    if raw_value is not None:
        error["raw_value"] = raw_value
    row["errors"].append(error)
    errors.append(error)


def _normalize_row_values(
    rows: list[dict[str, Any]],
    errors: list[dict[str, Any]],
) -> None:
    for row in rows:
        data = row["data"]
        employee_id = data.get("employee_id")
        if isinstance(employee_id, bool):
            _add_row_error(
                row,
                errors,
                field="employee_id",
                error_type="invalid_value",
                message="Employee ID must be text or a number, not a boolean.",
                raw_value=employee_id,
            )
        elif isinstance(employee_id, float) and employee_id.is_integer():
            data["employee_id"] = str(int(employee_id))
        elif employee_id is not None:
            data["employee_id"] = str(employee_id).strip()

        for field, maximum_length in STRING_FIELD_LIMITS.items():
            value = data.get(field)
            if value is None:
                continue
            if field == "employee_id" or field == "manager_id":
                if isinstance(value, bool):
                    _add_row_error(
                        row,
                        errors,
                        field=field,
                        error_type="invalid_value",
                        message=f"'{field}' must be text or a number.",
                        raw_value=value,
                    )
                    continue
                value = str(value).strip()
                data[field] = value or None
            elif not isinstance(value, str):
                _add_row_error(
                    row,
                    errors,
                    field=field,
                    error_type="invalid_value",
                    message=f"'{field}' must be text.",
                    raw_value=value,
                )
                continue
            else:
                value = value.strip()
                data[field] = value or None

            if value and len(value) > maximum_length:
                _add_row_error(
                    row,
                    errors,
                    field=field,
                    error_type="value_too_long",
                    message=(
                        f"'{field}' exceeds the {maximum_length}-character "
                        "limit."
                    ),
                    raw_value=value,
                )


def _append_case_insensitive_duplicate_errors(
    rows: list[dict[str, Any]],
    errors: list[dict[str, Any]],
) -> None:
    for field in ("employee_id", "email"):
        rows_by_value: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            value = row["data"].get(field)
            if value:
                rows_by_value[_casefold(value)].append(row)

        for value, duplicates in rows_by_value.items():
            if len(duplicates) < 2:
                continue
            row_numbers = [row["row_number"] for row in duplicates]
            for row in duplicates:
                if any(
                    error.get("field") == field
                    and error.get("type") == "duplicate_in_file"
                    for error in row["errors"]
                ):
                    continue
                _add_row_error(
                    row,
                    errors,
                    field=field,
                    error_type="duplicate_in_file",
                    message=(
                        f"Duplicate {field} '{value}' appears on rows "
                        f"{row_numbers}."
                    ),
                    raw_value=row["data"].get(field),
                )


def _manager_indexes(
    employees: list[Employee],
    candidate_rows: list[dict[str, Any]],
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    codes: dict[str, list[str]] = defaultdict(list)
    names: dict[str, list[str]] = defaultdict(list)

    for employee in employees:
        code = employee.employee_id.strip()
        codes[_casefold(code)].append(code)
        names[_normalized_name(employee.full_name)].append(code)

    for row in candidate_rows:
        data = row["data"]
        code = str(data["employee_id"]).strip()
        codes[_casefold(code)].append(code)
        names[_normalized_name(data["full_name"])].append(code)
    return codes, names


def _validate_manager_references(
    rows: list[dict[str, Any]],
    employees: list[Employee],
    errors: list[dict[str, Any]],
) -> None:
    candidates = [
        row
        for row in rows
        if not row["errors"]
        and row["data"].get("employee_id")
        and row["data"].get("full_name")
    ]
    codes, names = _manager_indexes(employees, candidates)

    manager_codes: dict[int, str] = {}
    for row in candidates:
        data = row["data"]
        id_value = data.get("manager_id")
        name_value = data.pop("manager_name", None)
        id_code = None
        name_code = None

        if id_value:
            matches = codes.get(_casefold(id_value), [])
            if len(matches) == 1:
                id_code = matches[0]
            else:
                _add_row_error(
                    row,
                    errors,
                    field="manager_id",
                    error_type=(
                        "ambiguous_manager_reference"
                        if matches else "invalid_manager_reference"
                    ),
                    message=(
                        "Manager ID does not identify one employee in this "
                        "company or the valid import rows."
                    ),
                    raw_value=id_value,
                )

        if name_value:
            matches = names.get(_normalized_name(name_value), [])
            if len(matches) == 1:
                name_code = matches[0]
            else:
                _add_row_error(
                    row,
                    errors,
                    field="manager_name",
                    error_type=(
                        "ambiguous_manager_reference"
                        if matches else "invalid_manager_reference"
                    ),
                    message=(
                        "Manager name does not identify one employee in this "
                        "company or the valid import rows."
                    ),
                    raw_value=name_value,
                )

        if id_code and name_code and _casefold(id_code) != _casefold(name_code):
            _add_row_error(
                row,
                errors,
                field="manager_id",
                error_type="inconsistent_manager_reference",
                message="Manager ID and manager name identify different employees.",
            )
            continue

        manager_code = id_code or name_code
        if manager_code is None:
            data["manager_id"] = None
            continue

        employee_code = str(data["employee_id"]).strip()
        if _casefold(manager_code) == _casefold(employee_code):
            _add_row_error(
                row,
                errors,
                field="manager_id",
                error_type="invalid_manager_reference",
                message="An employee cannot be their own manager.",
                raw_value=manager_code,
            )
            continue
        data["manager_id"] = manager_code
        manager_codes[row["row_number"]] = manager_code

    graph: dict[str, str] = {}
    employees_by_id = {employee.id: employee for employee in employees}
    for employee in employees:
        manager = employees_by_id.get(employee.manager_internal_id)
        manager_code = (
            manager.employee_id
            if manager is not None
            else employee.manager_id
        )
        if manager_code:
            graph[_casefold(employee.employee_id)] = _casefold(manager_code)

    for row in candidates:
        data = row["data"]
        manager_code = manager_codes.get(row["row_number"])
        if manager_code:
            graph[_casefold(data["employee_id"])] = _casefold(manager_code)

    for row in candidates:
        if row["errors"]:
            continue
        current = _casefold(row["data"]["employee_id"])
        seen = set()
        while current in graph:
            if current in seen:
                _add_row_error(
                    row,
                    errors,
                    field="manager_id",
                    error_type="manager_cycle",
                    message="This manager reference would create a reporting cycle.",
                )
                break
            seen.add(current)
            current = graph[current]

    import_candidates: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in candidates:
        import_candidates[
            _casefold(row["data"]["employee_id"])
        ].append(row)

    changed = True
    while changed:
        changed = False
        for row in candidates:
            if row["errors"]:
                continue
            manager_code = row["data"].get("manager_id")
            targets = import_candidates.get(_casefold(manager_code), [])
            if targets and any(target["errors"] for target in targets):
                _add_row_error(
                    row,
                    errors,
                    field="manager_id",
                    error_type="invalid_manager_reference",
                    message=(
                        "The referenced manager row cannot be imported until "
                        "its own validation errors are corrected."
                    ),
                    raw_value=manager_code,
                )
                changed = True


def build_employee_import_preview(
    db: Session,
    company_id: int,
    columns: list[str],
    rows: list[dict[str, Any]],
    column_mapping: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    suggestions, combined_fields, normalized_mapping = _validation_mapping(
        columns,
        column_mapping,
    )
    validation = validate_employee_rows(
        rows=rows,
        suggestions=suggestions,
        combined_fields=combined_fields,
        approved_defaults=APPROVED_DEFAULTS,
    )

    row_items = validation["rows"]
    errors = list(validation["errors"])
    warnings = list(validation["warnings"])
    _normalize_row_values(row_items, errors)
    _append_case_insensitive_duplicate_errors(row_items, errors)

    existing_employees = db.query(Employee).filter(
        Employee.company_id == company_id,
    ).all()
    existing_ids = {
        _casefold(employee.employee_id)
        for employee in existing_employees
    }
    existing_emails = {
        _casefold(employee.email)
        for employee in existing_employees
    }
    for row in row_items:
        data = row["data"]
        employee_id = data.get("employee_id")
        email = data.get("email")
        if employee_id and _casefold(employee_id) in existing_ids:
            _add_row_error(
                row,
                errors,
                field="employee_id",
                error_type="duplicate_in_database",
                message="This employee ID already exists in this company.",
                raw_value=employee_id,
            )
        if (
            isinstance(email, str)
            and "@" in email
            and _casefold(email) in existing_emails
        ):
            _add_row_error(
                row,
                errors,
                field="email",
                error_type="duplicate_in_database",
                message="This email already exists in this company.",
                raw_value=email,
            )

    _validate_manager_references(
        row_items,
        [employee for employee in existing_employees if employee.is_active],
        errors,
    )

    file_errors = [error for error in errors if error.get("row_number") is None]
    missing_mappings = validation["missing_mappings"]
    importable_rows = [
        {"row_number": row["row_number"], "data": row["data"]}
        for row in row_items
        if not row["errors"]
    ]
    invalid_rows = len(row_items) - len(importable_rows)

    return {
        "columns": columns,
        "column_mapping": normalized_mapping,
        "available_fields": AVAILABLE_MAPPING_FIELDS,
        "rows": [
            {
                "row_number": row["row_number"],
                "data": row["data"],
                "errors": row["errors"],
                "warnings": row["warnings"],
                "importable": not row["errors"],
            }
            for row in row_items
        ],
        "valid_rows": importable_rows,
        "errors": errors,
        "warnings": warnings,
        "missing_mappings": missing_mappings,
        "summary": {
            "total_rows": len(row_items),
            "importable_rows": len(importable_rows),
            "invalid_rows": invalid_rows,
            "total_errors": len(errors),
            "total_warnings": len(warnings),
            "ready_for_confirmation": (
                not missing_mappings
                and not file_errors
            ),
        },
    }


def employee_model_values(data: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in data.items()
        if key in EMPLOYEE_FIELDS
    }
