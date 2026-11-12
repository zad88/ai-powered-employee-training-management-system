"""Automatic source-column detection for employee imports."""

import re
from difflib import SequenceMatcher
from typing import Any


# Internal employee fields and their accepted source-column names.
EMPLOYEE_FIELD_ALIASES = {
    "employee_id": [
        "employee_id", "employee id", "empid", "emp id",
        "staff id", "staff number", "employee number",
        "personnel number",
    ],
    "full_name": [
        "full_name", "full name", "employee name",
        "staff name", "name",
    ],
    "first_name": [
        "first_name", "first name", "firstname", "given name",
    ],
    "last_name": [
        "last_name", "last name", "lastname", "surname",
        "family name",
    ],
    "email": [
        "email", "email address", "work email",
        "business email", "ad email", "ademail",
    ],
    "job_title": [
        "job_title", "job title", "title", "position",
        "role", "designation",
    ],
    "department": [
        "department", "department name",
        "dept", "departmenttype", "department type",
    ],
    "manager_id": [
        "manager_id", "manager id", "supervisor id",
        "reporting manager id",
    ],
    "manager_name": [
        "manager", "manager name", "supervisor",
        "supervisor name", "reporting manager",
    ],
    "employment_status": [
        "employment_status", "employment status",
        "employee status", "employeestatus", "status",
    ],
    "employment_type": [
        "employment_type", "employment type",
        "employee type", "employeetype", "contract type",
    ],
    "hire_date": [
        "hire_date", "hire date", "start date", "startdate",
        "joining date", "date of joining",
    ],
    "job_level": [
        "job_level", "job level", "career level",
        "seniority level", "grade",
    ],
    "working_hours_per_week": [
        "working hours per week", "weekly working hours",
        "working_hours_per_week",
    ],
    "learning_hours_per_week": [
        "learning hours per week", "weekly learning hours",
        "learning_hours_per_week",
    ],
    "years_of_experience": [
        "years of experience", "experience years",
        "years_of_experience",
    ],
}


def normalize_column_name(value: str) -> str:
    """Normalize a column name for comparison."""
    value = str(value).strip().lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def _similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, left, right).ratio()


def detect_employee_columns(columns: list[str]) -> dict[str, Any]:
    """
    Suggest mappings from uploaded employee columns to internal fields.

    Suggestions are not automatically approved.
    Multiple source columns may be combined for full_name.
    """
    normalized_aliases = {
        field: {
            normalize_column_name(alias)
            for alias in aliases
        }
        for field, aliases in EMPLOYEE_FIELD_ALIASES.items()
    }

    suggestions = {}
    unmatched_columns = []
    used_fields = set()

    for original_column in columns:
        normalized_column = normalize_column_name(original_column)

        exact_matches = [
            field
            for field, aliases in normalized_aliases.items()
            if normalized_column in aliases
        ]

        if len(exact_matches) == 1:
            field = exact_matches[0]

            # First and last name are combined later.
            if field in {"first_name", "last_name"}:
                suggestions[original_column] = {
                    "field": field,
                    "confidence": 1.0,
                    "match_type": "exact",
                    "requires_review": False,
                }
                continue

            if field not in used_fields:
                suggestions[original_column] = {
                    "field": field,
                    "confidence": 1.0,
                    "match_type": "exact",
                    "requires_review": False,
                }
                used_fields.add(field)
            else:
                suggestions[original_column] = {
                    "field": field,
                    "confidence": 1.0,
                    "match_type": "duplicate_candidate",
                    "requires_review": True,
                }
            continue

        if len(exact_matches) > 1:
            suggestions[original_column] = {
                "field": None,
                "confidence": 0.0,
                "match_type": "ambiguous",
                "requires_review": True,
                "candidates": exact_matches,
            }
            continue

        # Fuzzy matching only creates a suggestion for manual review.
        scores = []

        for field, aliases in normalized_aliases.items():
            best_score = max(
                (_similarity(normalized_column, alias) for alias in aliases),
                default=0.0,
            )
            scores.append((field, best_score))

        scores.sort(key=lambda item: item[1], reverse=True)

        best_field, best_score = scores[0]
        second_score = scores[1][1] if len(scores) > 1 else 0.0

        if best_score >= 0.80 and best_score - second_score >= 0.08 and best_field != "department":
            suggestions[original_column] = {
                "field": best_field,
                "confidence": round(best_score, 2),
                "match_type": "fuzzy",
                "requires_review": True,
            }
        else:
            unmatched_columns.append(original_column)
            suggestions[original_column] = {
                "field": None,
                "confidence": round(best_score, 2),
                "match_type": "unmatched",
                "requires_review": False,
            }

    # Build the combined full-name suggestion.
    first_name_columns = [
        column for column, result in suggestions.items()
        if result.get("field") == "first_name"
    ]
    last_name_columns = [
        column for column, result in suggestions.items()
        if result.get("field") == "last_name"
    ]

    combined_name = None

    if first_name_columns and last_name_columns:
        combined_name = {
            "field": "full_name",
            "source_columns": [
                first_name_columns[0],
                last_name_columns[0],
            ],
            "transformation": "combine_names",
            "requires_review": False,
        }
    elif "full_name" in used_fields:
        full_name_column = next(
            column for column, result in suggestions.items()
            if result.get("field") == "full_name"
            and result.get("match_type") == "exact"
        )
        combined_name = {
            "field": "full_name",
            "source_columns": [full_name_column],
            "transformation": "direct",
            "requires_review": False,
        }

    return {
        "entity_type": "employee",
        "suggestions": suggestions,
        "combined_fields": [
            combined_name
        ] if combined_name else [],
        "unmatched_columns": unmatched_columns,
        "requires_manual_review": any(
            result.get("requires_review", True)
            for result in suggestions.values()
        ),
    }




