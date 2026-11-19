from datetime import date, datetime
import math
from typing import Any
import re


REQUIRED_FIELDS = [
    "employee_id",
    "full_name",
    "email",
    "job_title",
    "department",
    "employment_status",
    "hire_date",
    "job_level",
    "employment_type",
]

NUMERIC_FIELDS = [
    "working_hours_per_week",
    "learning_hours_per_week",
    "years_of_experience",
]

DATE_FORMATS = [
    "%Y-%m-%d",
    "%d-%b-%y",
    "%d-%b-%Y",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%d-%m-%Y",
    "%Y/%m/%d",
]

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def clean_value(value: Any) -> Any:
    if value is None:
        return None

    if isinstance(value, str):
        value = value.strip()
        return value if value else None

    return value


def parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    if not isinstance(value, str):
        return None

    for date_format in DATE_FORMATS:
        try:
            return datetime.strptime(
                value.strip(), date_format
            ).date()
        except ValueError:
            continue

    return None


def build_field_mapping(suggestions: dict) -> tuple[dict, list]:
    mapping = {}
    issues = []
    used_fields = {}

    for source_column, suggestion in suggestions.items():
        field = suggestion.get("field")

        if not field:
            continue

        if field in used_fields:
            issues.append({
                "type": "mapping_conflict",
                "field": field,
                "message": (
                    f"Both '{used_fields[field]}' and "
                    f"'{source_column}' suggest the same field."
                ),
            })
            continue

        mapping[field] = source_column
        used_fields[field] = source_column

    return mapping, issues


def validate_employee_rows(
    rows: list[dict],
    suggestions: dict,
    combined_fields: list | None = None,
    approved_defaults: dict | None = None,
) -> dict:
    """
    Validate and standardize employee rows without database writes.

    approved_defaults contains only explicitly approved fallback values.
    Example: {"job_level": "Not specified"}
    """
    combined_fields = combined_fields or []
    approved_defaults = approved_defaults or {}

    field_mapping, mapping_issues = build_field_mapping(suggestions)

    combined_field_names = {
        item.get("field") for item in combined_fields
    }

    missing_mappings = [
        field for field in REQUIRED_FIELDS
        if field not in field_mapping
        and field not in combined_field_names
        and field not in approved_defaults
    ]

    errors = []
    warnings = []
    valid_rows = []

    employees = []
    employee_id_rows = {}
    email_rows = {}

    # File-level mapping issues.
    for issue in mapping_issues:
        errors.append({
            "row_number": None,
            **issue,
        })

    for field in missing_mappings:
        errors.append({
            "row_number": None,
            "type": "missing_mapping",
            "field": field,
            "message": (
                f"Required field '{field}' has no mapped source column."
            ),
        })

    for index, raw_row in enumerate(rows):
        row_number = index + 2
        employee = {}
        row_errors = []
        row_warnings = []

        # Apply detected source-column mappings.
        for internal_field, source_column in field_mapping.items():
            employee[internal_field] = clean_value(
                raw_row.get(source_column)
            )

        # Combine first and last names.
        for combination in combined_fields:
            if combination.get("field") != "full_name":
                continue

            parts = [
                clean_value(raw_row.get(column))
                for column in combination.get("source_columns", [])
            ]

            parts = [
                str(part) for part in parts if part is not None
            ]

            if parts:
                employee["full_name"] = " ".join(parts)

        # Apply explicitly approved defaults.
        for field, default_value in approved_defaults.items():
            if employee.get(field) is None:
                employee[field] = default_value
                row_warnings.append({
                    "row_number": row_number,
                    "field": field,
                    "type": "approved_default_applied",
                    "message": (
                        f"Approved default '{default_value}' "
                        f"was applied to '{field}'."
                    ),
                })

        # Standardize surrounding whitespace.
        for field, value in list(employee.items()):
            if isinstance(value, str):
                employee[field] = value.strip()

        # Required-field checks.
        for field in REQUIRED_FIELDS:
            if field in missing_mappings:
                continue

            value = employee.get(field)

            if value is None or value == "":
                row_errors.append({
                    "row_number": row_number,
                    "field": field,
                    "type": "missing_value",
                    "message": f"Required value '{field}' is missing.",
                })

        # Email validation. Preserve the original value.
        original_email = employee.get("email")

        if original_email is not None and original_email != "":
            if not isinstance(original_email, str):
                row_errors.append({
                    "row_number": row_number,
                    "field": "email",
                    "type": "invalid_email",
                    "message": (
                        "Email address must be text."
                    ),
                    "raw_value": original_email,
                })
            else:
                normalized_email = original_email.lower()
                employee["email"] = normalized_email
                employee["email_original"] = original_email

                if not EMAIL_PATTERN.fullmatch(normalized_email):
                    row_errors.append({
                        "row_number": row_number,
                        "field": "email",
                        "type": "invalid_email",
                        "message": (
                            f"Invalid email address: {original_email}"
                        ),
                        "raw_value": original_email,
                    })

        # Hire date validation.
        hire_date = employee.get("hire_date")

        if hire_date is not None:
            parsed_date = parse_date(hire_date)

            if parsed_date is None:
                row_errors.append({
                    "row_number": row_number,
                    "field": "hire_date",
                    "type": "invalid_date",
                    "message": f"Could not parse hire date: {hire_date}",
                    "raw_value": hire_date,
                })
            else:
                employee["hire_date"] = parsed_date

        # Optional numeric-field validation.
        for field in NUMERIC_FIELDS:
            value = employee.get(field)

            if value is None:
                continue

            try:
                number = float(value)

                if not math.isfinite(number) or number < 0:
                    raise ValueError

                employee[field] = number

            except (TypeError, ValueError):
                row_errors.append({
                    "row_number": row_number,
                    "field": field,
                    "type": "invalid_number",
                    "message": (
                        f"'{field}' must be a non-negative number."
                    ),
                })

        # Collect employee IDs for duplicate detection.
        employee_id = employee.get("employee_id")

        if employee_id:
            employee_id = str(employee_id).strip()
            employee["employee_id"] = employee_id

            employee_id_rows.setdefault(employee_id, []).append(
                row_number
            )

        # Collect valid-format emails for duplicate detection.
        email = employee.get("email")

        if isinstance(email, str) and email and EMAIL_PATTERN.fullmatch(email):
            email_rows.setdefault(email, []).append(row_number)

        employees.append({
            "row_number": row_number,
            "data": employee,
            "errors": row_errors,
            "warnings": row_warnings,
        })

    # Flag every row involved in a duplicate employee ID.
    for employee_id, row_numbers in employee_id_rows.items():
        if len(row_numbers) > 1:
            for item in employees:
                if item["row_number"] in row_numbers:
                    item["errors"].append({
                        "row_number": item["row_number"],
                        "field": "employee_id",
                        "type": "duplicate_in_file",
                        "message": (
                            f"Employee ID '{employee_id}' appears "
                            f"on rows {row_numbers}."
                        ),
                    })

    # Flag every row involved in a duplicate email.
    for email, row_numbers in email_rows.items():
        if len(row_numbers) > 1:
            for item in employees:
                if item["row_number"] in row_numbers:
                    item["errors"].append({
                        "row_number": item["row_number"],
                        "field": "email",
                        "type": "duplicate_in_file",
                        "message": (
                            f"Email '{email}' appears "
                            f"on rows {row_numbers}."
                        ),
                    })

    # Finalize row results.
    for item in employees:
        errors.extend(item["errors"])
        warnings.extend(item["warnings"])

        if not item["errors"]:
            valid_rows.append({
                "row_number": item["row_number"],
                "data": item["data"],
            })

    invalid_rows = len(rows) - len(valid_rows)

    return {
        "valid_rows": valid_rows,
        "rows": employees,
        "errors": errors,
        "warnings": warnings,
        "mapping": field_mapping,
        "missing_mappings": missing_mappings,
        "summary": {
            "total_rows": len(rows),
            "valid_rows": len(valid_rows),
            "invalid_rows": invalid_rows,
            "total_errors": len(errors),
            "total_warnings": len(warnings),
            "ready_for_import": (
                len(rows) > 0
                and invalid_rows == 0
                and len(errors) == 0
                and not missing_mappings
            ),
        },
    }
