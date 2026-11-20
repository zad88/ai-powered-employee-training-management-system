"""Read-only analysis of the local ESCO reference datasets."""

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import unicodedata
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

import backend.app.db.models as _registered_models
from backend.app.db.esco_occupation import ESCOOccupation
from backend.app.db.esco_occupation_skill import ESCOOccupationSkill
from backend.app.db.esco_skill_hierarchy_node import ESCOSkillHierarchyNode
from backend.app.db.skill import Skill
from backend.app.services.esco_csv_parser import (
    DATASET_FILES,
    ESCOCSVError,
    ESCOCSVReader,
    ESCOCSVRowIssue,
    ESCO_DATA_DIR,
)


_ = _registered_models
MAX_EXAMPLES = 5
HIERARCHY_LEVELS = range(4)


def _bucket() -> dict:
    return {"count": 0, "examples": []}


def _add_example(bucket: dict, example: dict) -> None:
    bucket["count"] += 1
    if len(bucket["examples"]) < MAX_EXAMPLES:
        bucket["examples"].append(example)


def _dataset_report(dataset: str, data_dir: Path) -> dict:
    return {
        "source_file": str(data_dir / DATASET_FILES[dataset]),
        "encoding": None,
        "delimiter": None,
        "headers": [],
        "source_rows": 0,
        "valid_rows": 0,
        "failed_records": 0,
        "_failed_source_rows": set(),
        "unique_records": 0,
        "existing_matches": 0,
        "proposed_additions": 0,
        "duplicate_records": 0,
        "duplicate_uri_groups": 0,
        "inconsistent_duplicate_groups": _bucket(),
        "representation_only_duplicate_groups": _bucket(),
        "conflicting_records": _bucket(),
        "preferred_label_conflicts": _bucket(),
        "ambiguous_alternative_labels": _bucket(),
        "held_for_manual_review": _bucket(),
        "validation_errors": _bucket(),
        "normalization_warnings": _bucket(),
        "invalid_source_references": _bucket(),
        "unresolved_relationships": _bucket(),
        "existing_match_examples": [],
        "source_complete": True,
    }


def _add_validation_error(report: dict, example: dict) -> None:
    _mark_failed_source_row(report, example.get("row"))
    _add_example(report["validation_errors"], example)


def _mark_failed_source_row(report: dict, row_number: int | None) -> None:
    if row_number is not None:
        report["_failed_source_rows"].add(row_number)


def _finalize_failed_source_rows(report: dict) -> None:
    report["failed_records"] = len(report.pop("_failed_source_rows"))


def _uri_is_valid(value: str) -> bool:
    if not value or value != value.strip():
        return False
    parsed = urlsplit(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _normalized_label(value: str) -> str:
    return " ".join(
        unicodedata.normalize("NFKC", value).casefold().split()
    )


def _normalized_duplicate_value(field: str, value: str | None) -> object:
    if not value:
        return ""
    if field == "modifiedDate":
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return " ".join(value.split())
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc)
        return parsed.isoformat()
    if field in {"altLabels", "hiddenLabels", "inScheme"}:
        return tuple(
            sorted(
                " ".join(item.split())
                for item in value.splitlines()
                if item.strip()
            )
        )
    return " ".join(value.split())


def _label_values(value: str | None) -> list[str]:
    if not value:
        return []
    return [label for label in value.splitlines() if label.strip()]


def _read_concepts(
    dataset: str,
    data_dir: Path,
) -> tuple[dict, dict[str, dict], set[str]]:
    report = _dataset_report(dataset, data_dir)
    reader = ESCOCSVReader(data_dir / DATASET_FILES[dataset], dataset)
    concepts: dict[str, dict] = {}
    observed_uris: set[str] = set()
    duplicate_groups: set[str] = set()

    max_lengths = {
        "skills": {
            "conceptUri": 500,
            "preferredLabel": 150,
            "skillType": 40,
            "reuseLevel": 50,
            "status": 30,
        },
        "occupations": {
            "conceptUri": 500,
            "iscoGroup": 20,
            "code": 50,
            "status": 30,
        },
    }[dataset]

    try:
        for item in reader:
            report["source_rows"] += 1
            if isinstance(item, ESCOCSVRowIssue):
                report["source_complete"] = False
                _add_validation_error(
                    report,
                    {
                        "row": item.row_number,
                        "physical_line": item.physical_line_end,
                        "code": item.code,
                        "message": item.message,
                        "actual_width": item.actual_width,
                    },
                )
                continue

            if item.padded_columns:
                _add_example(
                    report["normalization_warnings"],
                    {
                        "row": item.row_number,
                        "code": "trailing_optional_columns_padded",
                        "columns": list(item.padded_columns),
                    },
                )

            values = item.values
            row_errors = []
            uri = values.get("conceptUri", "")
            preferred_label = values.get("preferredLabel", "")
            valid_uri = _uri_is_valid(uri)
            if valid_uri:
                observed_uris.add(uri)
            else:
                row_errors.append(
                    ("invalid_uri", "conceptUri", "Invalid or empty URI.")
                )
            if not preferred_label.strip():
                row_errors.append(
                    (
                        "missing_preferred_label",
                        "preferredLabel",
                        "Preferred label is required.",
                    )
                )
            for field, max_length in max_lengths.items():
                value = values.get(field, "")
                if value and len(value) > max_length:
                    row_errors.append(
                        (
                            "field_too_long",
                            field,
                            f"Value exceeds the {max_length}-character limit.",
                        )
                    )

            if values.get("modifiedDate"):
                try:
                    datetime.fromisoformat(
                        values["modifiedDate"].replace("Z", "+00:00")
                    )
                except ValueError:
                    row_errors.append(
                        (
                            "invalid_modified_date",
                            "modifiedDate",
                            "Expected an ISO-8601 date or timestamp.",
                        )
                    )

            if row_errors:
                for code, field, message in row_errors:
                    _add_validation_error(
                        report,
                        {
                            "row": item.row_number,
                            "code": code,
                            "field": field,
                            "message": message,
                        },
                    )
                continue

            report["valid_rows"] += 1
            if uri not in concepts:
                concepts[uri] = {
                    "values": values,
                    "row": item.row_number,
                    "rows": [(item.row_number, values)],
                    "inconsistent_duplicate": False,
                }
                continue

            concepts[uri]["rows"].append((item.row_number, values))
            report["duplicate_records"] += 1
            if uri not in duplicate_groups:
                duplicate_groups.add(uri)
                report["duplicate_uri_groups"] += 1
    except ESCOCSVError as exc:
        report["source_complete"] = False
        _add_validation_error(
            report,
            {
                "code": exc.code,
                "row": exc.row_number,
                "physical_line": exc.physical_line,
                "message": str(exc),
            },
        )

    for uri, record in concepts.items():
        duplicate_rows = record["rows"]
        if len(duplicate_rows) < 2:
            continue
        fields = reader.headers
        raw_differing_fields = sorted(
            field
            for field in fields
            if len({values.get(field, "") for _, values in duplicate_rows}) > 1
        )
        differing_fields = [
            field
            for field in raw_differing_fields
            if len(
                {
                    _normalized_duplicate_value(
                        field,
                        values.get(field),
                    )
                    for _, values in duplicate_rows
                }
            )
            > 1
        ]
        if differing_fields:
            record["inconsistent_duplicate"] = True
            example = {
                "uri": uri,
                "rows": [row_number for row_number, _ in duplicate_rows],
                "differing_fields": differing_fields,
                "field_values": {
                    field: [
                        {"row": row_number, "value": values.get(field, "")}
                        for row_number, values in duplicate_rows
                    ]
                    for field in differing_fields
                },
            }
            _add_example(
                report["inconsistent_duplicate_groups"],
                example,
            )
            _add_example(report["conflicting_records"], example)
        elif raw_differing_fields:
            _add_example(
                report["representation_only_duplicate_groups"],
                {
                    "uri": uri,
                    "rows": [row_number for row_number, _ in duplicate_rows],
                    "differing_fields": raw_differing_fields,
                },
            )

    report["encoding"] = reader.encoding
    report["delimiter"] = reader.delimiter
    report["headers"] = list(reader.headers)
    report["source_rows"] = max(report["source_rows"], reader.source_rows)
    report["unique_records"] = len(concepts)

    preferred_labels: dict[str, set[str]] = defaultdict(set)
    for uri, record in concepts.items():
        label = record["values"].get("preferredLabel", "")
        preferred_labels[_normalized_label(label)].add(uri)
    for normalized, uris in preferred_labels.items():
        if normalized and len(uris) > 1:
            _add_example(
                report["preferred_label_conflicts"],
                {
                    "normalized_label": normalized,
                    "uris": sorted(uris),
                },
            )

    _finalize_failed_source_rows(report)
    return report, concepts, observed_uris


def _load_existing_catalogue(db: Session) -> dict:
    skills = [
        {
            "id": row.skill_id,
            "name": row.skill_name,
            "uri": row.esco_concept_uri,
            "alternative_labels": row.alternative_labels,
            "metadata": {
                "preferredLabel": row.skill_name or "",
                "altLabels": row.alternative_labels or "",
                "description": row.description or "",
                "skillType": row.esco_skill_type or "",
                "reuseLevel": row.esco_reuse_level or "",
                "status": row.esco_status or "",
                "modifiedDate": row.esco_modified_date,
            },
        }
        for row in db.query(
            Skill.skill_id,
            Skill.skill_name,
            Skill.esco_concept_uri,
            Skill.alternative_labels,
            Skill.description,
            Skill.esco_skill_type,
            Skill.esco_reuse_level,
            Skill.esco_status,
            Skill.esco_modified_date,
        ).yield_per(500)
    ]
    occupations = [
        {
            "id": row.id,
            "uri": row.esco_concept_uri,
            "label": row.preferred_label,
            "metadata": {
                "preferredLabel": row.preferred_label or "",
                "altLabels": row.alternative_labels or "",
                "description": row.description or "",
                "iscoGroup": row.isco_group or "",
                "code": row.code or "",
                "naceCode": row.nace_code or "",
                "regulatedProfessionNote": (
                    row.regulated_profession_note or ""
                ),
                "scopeNote": row.scope_note or "",
                "definition": row.definition or "",
                "inScheme": row.in_scheme or "",
                "status": row.status or "",
                "modifiedDate": row.modified_date,
            },
        }
        for row in db.query(
            ESCOOccupation.id,
            ESCOOccupation.esco_concept_uri,
            ESCOOccupation.preferred_label,
            ESCOOccupation.alternative_labels,
            ESCOOccupation.description,
            ESCOOccupation.isco_group,
            ESCOOccupation.code,
            ESCOOccupation.nace_code,
            ESCOOccupation.regulated_profession_note,
            ESCOOccupation.scope_note,
            ESCOOccupation.definition,
            ESCOOccupation.in_scheme,
            ESCOOccupation.status,
            ESCOOccupation.modified_date,
        ).yield_per(500)
    ]
    hierarchy_rows = list(
        db.query(
            ESCOSkillHierarchyNode.id,
            ESCOSkillHierarchyNode.esco_concept_uri,
            ESCOSkillHierarchyNode.label,
            ESCOSkillHierarchyNode.hierarchy_level,
            ESCOSkillHierarchyNode.code,
            ESCOSkillHierarchyNode.description,
            ESCOSkillHierarchyNode.scope_note,
            ESCOSkillHierarchyNode.parent_id,
        ).yield_per(500)
    )
    hierarchy_uri_by_id = {row.id: row.esco_concept_uri for row in hierarchy_rows}
    hierarchy = {
        row.esco_concept_uri: {
            "id": row.id,
            "uri": row.esco_concept_uri,
            "label": row.label,
            "level": row.hierarchy_level,
            "code": row.code or "",
            "description": row.description or "",
            "scope_note": row.scope_note or "",
            "parent_uri": hierarchy_uri_by_id.get(row.parent_id),
        }
        for row in hierarchy_rows
    }
    relations = {
        (
            row.occupation_uri,
            row.skill_uri,
            row.relation_type,
        )
        for row in db.query(
            ESCOOccupation.esco_concept_uri.label("occupation_uri"),
            Skill.esco_concept_uri.label("skill_uri"),
            ESCOOccupationSkill.relation_type,
        )
        .join(
            ESCOOccupation,
            ESCOOccupation.id == ESCOOccupationSkill.occupation_id,
        )
        .join(Skill, Skill.skill_id == ESCOOccupationSkill.skill_id)
        .yield_per(1000)
        if row.occupation_uri and row.skill_uri
    }
    return {
        "skills": skills,
        "occupations": occupations,
        "hierarchy": hierarchy,
        "relations": relations,
    }


def _normalized_datetime(value: datetime | str | None) -> datetime | None:
    if not value:
        return None
    parsed = (
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        if isinstance(value, str)
        else value
    )
    if parsed.tzinfo is not None:
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _metadata_differences(
    source: dict[str, str],
    existing: dict[str, object],
) -> list[str]:
    differences = []
    for field, source_value in source.items():
        if field == "conceptUri":
            continue
        existing_value = existing.get(field)
        if field == "modifiedDate":
            matches = _normalized_datetime(source_value) == _normalized_datetime(
                existing_value
            )
        else:
            matches = (source_value or "") == (existing_value or "")
        if not matches:
            differences.append(field)
    return differences


def _match_skills(
    report: dict,
    concepts: dict[str, dict],
    existing_skills: list[dict],
) -> set[str]:
    existing_uri_to_id = {
        row["uri"]: row["id"] for row in existing_skills if row["uri"]
    }
    report["existing_matches"] = sum(
        uri in existing_uri_to_id for uri in concepts
    )
    report["existing_match_examples"] = [
        {"uri": uri, "skill_id": existing_uri_to_id[uri]}
        for uri in concepts
        if uri in existing_uri_to_id
    ][:MAX_EXAMPLES]

    alias_to_uris: dict[str, set[str]] = defaultdict(set)
    all_label_to_uris: dict[str, set[str]] = defaultdict(set)
    preferred_label_to_uris: dict[str, set[str]] = defaultdict(set)
    for uri, record in concepts.items():
        values = record["values"]
        preferred = values.get("preferredLabel", "")
        preferred_key = _normalized_label(preferred)
        if preferred_key:
            all_label_to_uris[preferred_key].add(uri)
            preferred_label_to_uris[preferred_key].add(uri)
        aliases = {
            alias for alias in _label_values(values.get("altLabels"))
            if _normalized_label(alias)
        }
        for alias in aliases:
            key = _normalized_label(alias)
            alias_to_uris[key].add(uri)
            all_label_to_uris[key].add(uri)

    ambiguous_label_uris: set[str] = set()
    alternative_to_alternative_keys: set[str] = set()
    alternative_to_preferred_keys: set[str] = set()
    for key, uris in alias_to_uris.items():
        matching_uris = all_label_to_uris[key]
        if len(matching_uris) > 1:
            ambiguous_label_uris.update(matching_uris)
            if len(uris) > 1:
                alternative_to_alternative_keys.add(key)
            if any(
                alias_uri != preferred_uri
                for alias_uri in uris
                for preferred_uri in preferred_label_to_uris.get(key, set())
            ):
                alternative_to_preferred_keys.add(key)
            _add_example(
                report["ambiguous_alternative_labels"],
                {"label": key, "uris": sorted(matching_uris)},
            )

    holds: dict[str, set[str]] = defaultdict(set)
    for uri, record in concepts.items():
        if record["inconsistent_duplicate"]:
            holds[uri].add("inconsistent_duplicate_uri_metadata")
        existing = next(
            (row for row in existing_skills if row["uri"] == uri),
            None,
        )
        if existing:
            differences = _metadata_differences(
                record["values"],
                existing["metadata"],
            )
            if differences:
                holds[uri].add("existing_uri_metadata_differs")
                _add_example(
                    report["conflicting_records"],
                    {
                        "uri": uri,
                        "differing_fields": differences,
                        "reason": "existing_uri_metadata_differs",
                    },
                )

    preferred_labels: dict[str, set[str]] = defaultdict(set)
    for uri, record in concepts.items():
        label = record["values"].get("preferredLabel", "")
        key = _normalized_label(label)
        if key:
            preferred_labels[key].add(uri)
    for key, uris in preferred_labels.items():
        if len(uris) > 1:
            for uri in uris:
                holds[uri].add("source_preferred_label_conflict")

    db_labels: dict[str, list[dict]] = defaultdict(list)
    for row in existing_skills:
        labels = [row["name"], *_label_values(row["alternative_labels"])]
        for label in labels:
            key = _normalized_label(label)
            if key:
                db_labels[key].append(row)

    db_conflict_examples: set[tuple[str, int, str]] = set()
    python_candidate_examples: set[tuple[str, int]] = set()
    for uri, record in concepts.items():
        values = record["values"]
        labels = [
            ("preferred_label", values.get("preferredLabel", "")),
            *(
                ("alternative_label", value)
                for value in _label_values(values.get("altLabels"))
            ),
        ]
        for source_field, label in labels:
            for db_row in db_labels.get(_normalized_label(label), []):
                if db_row["uri"] == uri:
                    continue
                example_key = (uri, db_row["id"], source_field)
                if example_key in db_conflict_examples:
                    continue
                db_conflict_examples.add(example_key)
                holds[uri].add("matches_existing_skill_label")
                example = {
                    "source_uri": uri,
                    "source_preferred_label": values.get(
                        "preferredLabel", ""
                    ),
                    "database_skill_id": db_row["id"],
                    "database_skill_name": db_row["name"],
                    "matched_source_field": source_field,
                    "identity_match": False,
                }
                _add_example(
                    report["conflicting_records"],
                    example,
                )
                if (
                    source_field == "alternative_label"
                    and _normalized_label(db_row["name"]) == _normalized_label(label)
                ):
                    python_candidate_examples.add((uri, db_row["id"]))

    for uri, db_skill_id in sorted(python_candidate_examples):
        holds[uri].add("python_alias_review")
        source = concepts[uri]["values"]
        db_row = next(row for row in existing_skills if row["id"] == db_skill_id)
        _add_example(
            report["held_for_manual_review"],
            {
                "reason": "alternative_label_matches_existing_skill",
                "source_uri": uri,
                "source_preferred_label": source.get("preferredLabel", ""),
                "database_skill_id": db_skill_id,
                "database_skill_name": db_row["name"],
                "automatic_link": False,
            },
        )

    python_candidate_uris = {
        uri for uri, _ in python_candidate_examples
    }
    for uri in sorted(holds):
        if uri in python_candidate_uris:
            continue
        _add_example(
            report["held_for_manual_review"],
            {
                "source_uri": uri,
                "source_preferred_label": concepts[uri]["values"].get(
                    "preferredLabel", ""
                ),
                "reasons": sorted(holds[uri]),
                "automatic_link": False,
            },
        )

    held_uris = set(holds)
    duplicate_conflicts = {
        uri
        for uri, reasons in holds.items()
        if "inconsistent_duplicate_uri_metadata" in reasons
    }
    preferred_conflicts = {
        uri
        for uri, reasons in holds.items()
        if "source_preferred_label_conflict" in reasons
    }
    python_reviews = {
        uri
        for uri, reasons in holds.items()
        if "python_alias_review" in reasons
    }
    database_conflicts = {
        uri
        for uri, reasons in holds.items()
        if "matches_existing_skill_label" in reasons
        or "existing_uri_metadata_differs" in reasons
    } - python_reviews
    prioritized = duplicate_conflicts | preferred_conflicts | python_reviews | database_conflicts
    report["ambiguous_alternative_labels"]["concept_count"] = len(
        ambiguous_label_uris
    )
    report["ambiguous_alternative_labels"]["collision_types"] = {
        "alternative_to_alternative": len(alternative_to_alternative_keys),
        "alternative_to_preferred": len(alternative_to_preferred_keys),
        "both": len(
            alternative_to_alternative_keys & alternative_to_preferred_keys
        ),
    }
    report["proposed_additions"] = (
        sum(
            uri not in existing_uri_to_id and uri not in held_uris
            for uri in concepts
        )
        if report["source_complete"]
        else 0
    )
    report["held_for_manual_review"]["count"] = len(held_uris)
    report["held_for_manual_review"]["reason_counts"] = {
        "duplicate_uri_conflict": len(duplicate_conflicts),
        "preferred_label_conflict": len(
            preferred_conflicts - duplicate_conflicts
        ),
        "existing_database_identity_conflict": len(
            database_conflicts
            - duplicate_conflicts
            - preferred_conflicts
        ),
        "python_alias_review": len(
            python_reviews - duplicate_conflicts - preferred_conflicts
        ),
        "other_reason": len(held_uris - prioritized),
    }
    return held_uris


def _match_occupations(
    report: dict,
    concepts: dict[str, dict],
    existing_occupations: list[dict],
) -> set[str]:
    existing_uri_to_id = {
        row["uri"]: row["id"] for row in existing_occupations
    }
    report["existing_matches"] = sum(
        uri in existing_uri_to_id for uri in concepts
    )
    report["existing_match_examples"] = [
        {"uri": uri, "occupation_id": existing_uri_to_id[uri]}
        for uri in concepts
        if uri in existing_uri_to_id
    ][:MAX_EXAMPLES]

    holds: dict[str, set[str]] = defaultdict(set)
    for uri, record in concepts.items():
        if record["inconsistent_duplicate"]:
            holds[uri].add("inconsistent_duplicate_uri_metadata")
        existing = next(
            (row for row in existing_occupations if row["uri"] == uri),
            None,
        )
        if existing:
            differences = _metadata_differences(
                record["values"],
                existing["metadata"],
            )
            if differences:
                holds[uri].add("existing_uri_metadata_differs")
                _add_example(
                    report["conflicting_records"],
                    {
                        "uri": uri,
                        "differing_fields": differences,
                        "reason": "existing_uri_metadata_differs",
                    },
                )

    labels: dict[str, set[str]] = defaultdict(set)
    for uri, record in concepts.items():
        label = record["values"].get("preferredLabel", "")
        key = _normalized_label(label)
        if key:
            labels[key].add(uri)
    for key, uris in labels.items():
        if len(uris) > 1:
            for uri in uris:
                holds[uri].add("source_preferred_label_conflict")

    report["held_for_manual_review"]["count"] = len(holds)
    report["held_for_manual_review"]["examples"] = [
        {
            "source_uri": uri,
            "source_preferred_label": concepts[uri]["values"].get(
                "preferredLabel", ""
            ),
            "reasons": sorted(reasons),
        }
        for uri, reasons in sorted(holds.items())
    ][:MAX_EXAMPLES]
    report["proposed_additions"] = (
        sum(
            uri not in existing_uri_to_id and uri not in holds
            for uri in concepts
        )
        if report["source_complete"]
        else 0
    )
    return set(holds)


def _hierarchy_value(
    values: dict[str, str],
    level: int,
    field: str,
) -> str:
    return values.get(f"Level {level} {field}", "")


def _read_hierarchy(
    data_dir: Path,
    existing_nodes: dict[str, dict] | None = None,
) -> tuple[dict, dict[str, dict], set[tuple[str, str]], set[str]]:
    report = _dataset_report("hierarchy", data_dir)
    reader = ESCOCSVReader(
        data_dir / DATASET_FILES["hierarchy"],
        "hierarchy",
    )
    nodes: dict[str, dict] = {}
    node_occurrences: dict[str, int] = defaultdict(int)
    edges: set[tuple[str, str]] = set()
    edge_occurrences: dict[tuple[str, str], int] = defaultdict(int)
    conflicted_nodes: set[str] = set()

    try:
        for item in reader:
            report["source_rows"] += 1
            if isinstance(item, ESCOCSVRowIssue):
                report["source_complete"] = False
                _add_validation_error(
                    report,
                    {
                        "row": item.row_number,
                        "physical_line": item.physical_line_end,
                        "code": item.code,
                        "message": item.message,
                        "actual_width": item.actual_width,
                    },
                )
                continue

            if item.padded_columns:
                _add_example(
                    report["normalization_warnings"],
                    {
                        "row": item.row_number,
                        "code": "trailing_optional_columns_padded",
                        "columns": list(item.padded_columns),
                    },
                )

            path = []
            row_errors = []
            gap_seen = False
            for level in HIERARCHY_LEVELS:
                uri = _hierarchy_value(item.values, level, "URI")
                label = _hierarchy_value(
                    item.values,
                    level,
                    "preferred term",
                )
                if not uri and not label:
                    gap_seen = True
                    continue
                if gap_seen:
                    row_errors.append(
                        (
                            "hierarchy_level_gap",
                            f"Level {level}",
                            "A hierarchy level is populated after a missing "
                            "parent level.",
                        )
                    )
                if not _uri_is_valid(uri):
                    row_errors.append(
                        (
                            "invalid_hierarchy_uri",
                            f"Level {level} URI",
                            "Hierarchy node URI is invalid or empty.",
                        )
                    )
                if not label.strip():
                    row_errors.append(
                        (
                            "missing_hierarchy_label",
                            f"Level {level} preferred term",
                            "A node URI requires a preferred term.",
                        )
                    )
                code = _hierarchy_value(item.values, level, "code")
                if len(code) > 50:
                    row_errors.append(
                        (
                            "field_too_long",
                            f"Level {level} code",
                            "Value exceeds the 50-character limit.",
                        )
                    )
                path.append(
                    {
                        "uri": uri,
                        "label": label,
                        "level": level,
                        "code": code,
                    }
                )

            if row_errors:
                for code, field, message in row_errors:
                    _add_validation_error(
                        report,
                        {
                            "row": item.row_number,
                            "code": code,
                            "field": field,
                            "message": message,
                        },
                    )
                continue

            if not path or path[0]["level"] != 0:
                _add_validation_error(
                    report,
                    {
                        "row": item.row_number,
                        "code": "missing_hierarchy_root",
                        "message": "Every hierarchy path must start at level 0.",
                    },
                )
                continue

            report["valid_rows"] += 1
            deepest_uri = path[-1]["uri"]
            description = item.values.get("Description", "")
            scope_note = item.values.get("Scope note", "")
            for index, path_node in enumerate(path):
                uri = path_node["uri"]
                parent_uri = path[index - 1]["uri"] if index else None
                candidate = {
                    **path_node,
                    "parent_uri": parent_uri,
                    "description": (
                        description if uri == deepest_uri else ""
                    ),
                    "scope_note": scope_note if uri == deepest_uri else "",
                    "row": item.row_number,
                }
                node_occurrences[uri] += 1
                if uri not in nodes:
                    nodes[uri] = candidate
                else:
                    original = nodes[uri]
                    differing_fields = []
                    for field in ("label", "level", "code", "parent_uri"):
                        if original[field] != candidate[field]:
                            differing_fields.append(field)
                    for field in ("description", "scope_note"):
                        if (
                            original[field]
                            and candidate[field]
                            and original[field] != candidate[field]
                        ):
                            differing_fields.append(field)
                        elif candidate[field] and not original[field]:
                            original[field] = candidate[field]
                    if differing_fields and uri not in conflicted_nodes:
                        conflicted_nodes.add(uri)
                        _add_example(
                            report["conflicting_records"],
                            {
                                "uri": uri,
                                "rows": [original["row"], item.row_number],
                                "differing_fields": sorted(
                                    set(differing_fields)
                                ),
                            },
                        )
                if parent_uri:
                    edge = (parent_uri, uri)
                    edges.add(edge)
                    edge_occurrences[edge] += 1

    except ESCOCSVError as exc:
        report["source_complete"] = False
        _add_validation_error(
            report,
            {
                "code": exc.code,
                "row": exc.row_number,
                "physical_line": exc.physical_line,
                "message": str(exc),
            },
        )

    report["encoding"] = reader.encoding
    report["delimiter"] = reader.delimiter
    report["headers"] = list(reader.headers)
    report["source_rows"] = max(report["source_rows"], reader.source_rows)
    report["valid_rows"] = min(report["valid_rows"], report["source_rows"])
    report["unique_records"] = len(nodes)
    report["node_occurrences"] = sum(node_occurrences.values())
    report["repeated_node_appearances"] = sum(
        max(count - 1, 0) for count in node_occurrences.values()
    )
    report["unique_parent_child_relationships"] = len(edges)
    report["repeated_edge_appearances"] = sum(
        max(count - 1, 0) for count in edge_occurrences.values()
    )
    report["nodes_by_level"] = {
        str(level): sum(node["level"] == level for node in nodes.values())
        for level in HIERARCHY_LEVELS
    }
    report["root_count"] = sum(
        node["level"] == 0 for node in nodes.values()
    )
    report["unresolved_parent_links"] = _bucket()

    held = set(conflicted_nodes)
    for uri, node in nodes.items():
        if node["level"] == 0:
            if node["parent_uri"] is not None:
                held.add(uri)
                _add_validation_error(
                    report,
                    {
                        "row": node["row"],
                        "uri": uri,
                        "code": "root_has_parent",
                        "message": "Level 0 nodes must not have a parent.",
                    },
                )
            continue
        parent = nodes.get(node["parent_uri"])
        if parent is None:
            held.add(uri)
            _mark_failed_source_row(report, node["row"])
            _add_example(
                report["unresolved_parent_links"],
                {
                    "uri": uri,
                    "parent_uri": node["parent_uri"],
                    "reason": "parent_not_in_source_hierarchy",
                },
            )
        elif parent["level"] != node["level"] - 1:
            held.add(uri)
            _add_validation_error(
                report,
                {
                    "row": node["row"],
                    "uri": uri,
                    "parent_uri": node["parent_uri"],
                    "code": "parent_level_mismatch",
                    "child_level": node["level"],
                    "parent_level": parent["level"],
                },
            )
        if node["parent_uri"] is None:
            held.add(uri)
            _mark_failed_source_row(report, node["row"])
            _add_example(
                report["unresolved_parent_links"],
                {
                    "uri": uri,
                    "parent_uri": None,
                    "reason": "non_root_node_missing_parent",
                },
            )

    existing_nodes = existing_nodes or {}
    report["existing_matches"] = sum(
        uri in existing_nodes for uri in nodes
    )
    existing_conflicts = set()
    for uri in set(nodes).intersection(existing_nodes):
        source = nodes[uri]
        existing = existing_nodes[uri]
        differences = [
            field
            for field in (
                "label",
                "level",
                "code",
                "description",
                "scope_note",
                "parent_uri",
            )
            if (source.get(field) or "") != (existing.get(field) or "")
        ]
        if differences:
            existing_conflicts.add(uri)
            held.add(uri)
            _add_example(
                report["conflicting_records"],
                {
                    "uri": uri,
                    "differing_fields": differences,
                    "reason": "existing_uri_metadata_differs",
                },
            )

    report["held_for_manual_review"]["count"] = len(held)
    report["held_for_manual_review"]["examples"] = [
        {
            "uri": uri,
            "label": nodes[uri]["label"],
            "reason": (
                "existing_uri_metadata_differs"
                if uri in existing_conflicts
                else "hierarchy_validation_conflict"
            ),
        }
        for uri in sorted(held)
    ][:MAX_EXAMPLES]
    report["existing_match_examples"] = [
        {"uri": uri, "node_id": existing_nodes[uri]["id"]}
        for uri in nodes
        if uri in existing_nodes
    ][:MAX_EXAMPLES]
    report["proposed_additions"] = (
        sum(uri not in existing_nodes and uri not in held for uri in nodes)
        if report["source_complete"]
        else 0
    )
    report["proposed_parent_child_relationships"] = sum(
        child not in held
        and parent not in held
        and (
            child not in existing_nodes
            or existing_nodes[child]["parent_uri"] != parent
        )
        for parent, child in edges
    )
    _finalize_failed_source_rows(report)
    return report, nodes, edges, held


def _analyze_relations(
    data_dir: Path,
    skill_report: dict,
    skills: dict[str, dict],
    observed_skill_uris: set[str],
    held_skills: set[str],
    occupation_report: dict,
    occupations: dict[str, dict],
    observed_occupation_uris: set[str],
    held_occupations: set[str],
    existing_relations: set[tuple[str, str, str]],
) -> tuple[
    dict,
    dict[tuple[str, str, str], dict],
    set[tuple[str, str, str]],
    set[tuple[str, str, str]],
    set[tuple[str, str, str]],
    set[tuple[str, str, str]],
]:
    report = _dataset_report("occupation_skill_relations", data_dir)
    reader = ESCOCSVReader(
        data_dir / DATASET_FILES["occupation_skill_relations"],
        "occupation_skill_relations",
    )
    relations: dict[tuple[str, str, str], dict] = {}
    relation_rows: dict[tuple[str, str, str], set[int]] = defaultdict(set)
    duplicate_groups: set[tuple[str, str, str]] = set()
    invalid_reference_examples = set()
    incomplete_reference_examples = set()
    unresolved_keys: set[tuple[str, str, str]] = set()
    held_relation_keys: set[tuple[str, str, str]] = set()
    invalid_reference_keys: set[tuple[str, str, str]] = set()
    invalid_concept_keys: set[tuple[str, str, str]] = set()
    inconsistent_relations: set[tuple[str, str, str]] = set()
    held_relation_examples = []

    try:
        for item in reader:
            report["source_rows"] += 1
            if isinstance(item, ESCOCSVRowIssue):
                report["source_complete"] = False
                _add_validation_error(
                    report,
                    {
                        "row": item.row_number,
                        "physical_line": item.physical_line_end,
                        "code": item.code,
                        "message": item.message,
                        "actual_width": item.actual_width,
                    },
                )
                continue

            values = item.values
            occupation_uri = values.get("occupationUri", "")
            skill_uri = values.get("skillUri", "")
            relation_type = values.get("relationType", "")
            skill_type = values.get("skillType", "")
            row_errors = []
            if not _uri_is_valid(occupation_uri):
                row_errors.append(
                    ("invalid_occupation_uri", "occupationUri")
                )
            if not _uri_is_valid(skill_uri):
                row_errors.append(("invalid_skill_uri", "skillUri"))
            relation_key = relation_type.casefold()
            if relation_key not in {"essential", "optional"}:
                row_errors.append(("invalid_relation_type", "relationType"))
            if len(skill_type) > 40:
                row_errors.append(("field_too_long", "skillType"))
            if row_errors:
                for code, field in row_errors:
                    _add_validation_error(
                        report,
                        {
                            "row": item.row_number,
                            "code": code,
                            "field": field,
                        },
                    )
                continue

            report["valid_rows"] += 1
            key = (occupation_uri, skill_uri, relation_key)
            relation_rows[key].add(item.row_number)
            if key in relations:
                report["duplicate_records"] += 1
                if key not in duplicate_groups:
                    duplicate_groups.add(key)
                    report["duplicate_uri_groups"] += 1
                previous = relations[key]
                if previous["skill_type"] != skill_type:
                    inconsistent_relations.add(key)
                    _add_example(
                        report["conflicting_records"],
                        {
                            "key": key,
                            "rows": [previous["row"], item.row_number],
                            "differing_fields": ["skillType"],
                        },
                    )
                continue

            relations[key] = {
                "row": item.row_number,
                "skill_type": skill_type,
                "occupation_label": values.get("occupationLabel", ""),
                "skill_label": values.get("skillLabel", ""),
            }
    except ESCOCSVError as exc:
        report["source_complete"] = False
        _add_validation_error(
            report,
            {
                "code": exc.code,
                "row": exc.row_number,
                "physical_line": exc.physical_line,
                "message": str(exc),
            },
        )

    report["encoding"] = reader.encoding
    report["delimiter"] = reader.delimiter
    report["headers"] = list(reader.headers)
    report["source_rows"] = max(report["source_rows"], reader.source_rows)
    report["unique_records"] = len(relations)

    proposed = 0
    existing_matches = 0
    for key in relations:
        occupation_uri, skill_uri, relation_type = key
        invalid_sources = []
        invalid_concepts = []
        incomplete_sources = []
        for kind, uri, concept_report, concepts, observed_uris in (
            (
                "occupation",
                occupation_uri,
                occupation_report,
                occupations,
                observed_occupation_uris,
            ),
            ("skill", skill_uri, skill_report, skills, observed_skill_uris),
        ):
            if uri in concepts:
                continue
            if not concept_report["source_complete"]:
                incomplete_sources.append(kind)
            elif uri not in observed_uris:
                invalid_sources.append(kind)
            else:
                invalid_concepts.append(kind)

        if invalid_sources:
            invalid_reference_keys.add(key)
            for row_number in relation_rows[key]:
                _mark_failed_source_row(report, row_number)
            example_key = (key, tuple(invalid_sources))
            if example_key not in invalid_reference_examples:
                invalid_reference_examples.add(example_key)
                _add_example(
                    report["unresolved_relationships"],
                    {
                        "occupation_uri": occupation_uri,
                        "skill_uri": skill_uri,
                        "relation_type": relation_type,
                        "reason": "invalid_source_reference",
                    },
                )
                unresolved_keys.add(key)
            continue

        if invalid_concepts:
            invalid_concept_keys.add(key)
            unresolved_keys.add(key)
            for row_number in relation_rows[key]:
                _mark_failed_source_row(report, row_number)
            _add_example(
                report["unresolved_relationships"],
                {
                    "occupation_uri": occupation_uri,
                    "skill_uri": skill_uri,
                    "relation_type": relation_type,
                    "reason": "invalid_source_concept",
                    "sources": invalid_concepts,
                },
            )
            continue

        if incomplete_sources:
            incomplete_reference_examples.add(key)
            unresolved_keys.add(key)
            for row_number in relation_rows[key]:
                _mark_failed_source_row(report, row_number)
            _add_example(
                report["unresolved_relationships"],
                {
                    "occupation_uri": occupation_uri,
                    "skill_uri": skill_uri,
                    "relation_type": relation_type,
                    "reason": {
                        "type": "concept_source_incomplete",
                        "sources": incomplete_sources,
                    },
                },
            )
            continue

        if key in existing_relations:
            existing_matches += 1
            if len(report["existing_match_examples"]) < MAX_EXAMPLES:
                report["existing_match_examples"].append(
                    {
                        "occupation_uri": occupation_uri,
                        "skill_uri": skill_uri,
                        "relation_type": relation_type,
                    }
                )
            continue

        hold_reasons = []
        if key in inconsistent_relations:
            hold_reasons.append("inconsistent_duplicate_relation")
        if skill_uri in held_skills:
            hold_reasons.append("skill_held_for_manual_review")
        if occupation_uri in held_occupations:
            hold_reasons.append("occupation_held_for_manual_review")
        if hold_reasons:
            held_relation_keys.add(key)
            unresolved_keys.add(key)
            example = {
                "occupation_uri": occupation_uri,
                "skill_uri": skill_uri,
                "relation_type": relation_type,
                "reason": hold_reasons,
            }
            _add_example(report["unresolved_relationships"], example)
            if len(held_relation_examples) < MAX_EXAMPLES:
                held_relation_examples.append(example)
            continue
        proposed += 1

    report["existing_matches"] = existing_matches
    report["proposed_additions"] = (
        proposed
        if report["source_complete"]
        and skill_report["source_complete"]
        and occupation_report["source_complete"]
        else 0
    )
    report["invalid_source_references"] = _bucket()
    for key, missing in sorted(invalid_reference_examples, key=str):
        _add_example(
            report["invalid_source_references"],
            {
                "occupation_uri": key[0],
                "skill_uri": key[1],
                "missing_sources": list(missing),
            },
        )
    report["unresolved_relationship_count"] = len(unresolved_keys)
    report["held_for_manual_review"]["count"] = len(held_relation_keys)
    report["held_for_manual_review"]["examples"] = held_relation_examples
    _finalize_failed_source_rows(report)
    return (
        report,
        relations,
        held_relation_keys,
        unresolved_keys,
        invalid_reference_keys,
        invalid_concept_keys,
    )


def _start_read_only_transaction(db: Session):
    if db.in_transaction():
        raise RuntimeError(
            "ESCO dry-run requires a fresh SQLAlchemy session."
        )
    if db.new or db.dirty or db.deleted:
        raise RuntimeError(
            "ESCO dry-run cannot run with pending ORM changes."
        )

    previous_autoflush = db.autoflush
    db.autoflush = False
    try:
        connection = db.connection()
        if connection.dialect.name == "postgresql":
            connection.exec_driver_sql("SET TRANSACTION READ ONLY")
            return connection, previous_autoflush, False
        if connection.dialect.name == "sqlite":
            connection.exec_driver_sql("PRAGMA query_only = ON")
            return connection, previous_autoflush, True
        raise RuntimeError(
            "ESCO dry-run supports PostgreSQL and SQLite read-only sessions."
        )
    except Exception:
        db.autoflush = previous_autoflush
        raise


def _analyze_esco_catalogue(
    db: Session,
    data_dir: Path,
) -> tuple[dict, dict]:
    existing = _load_existing_catalogue(db)
    skills_report, skills, observed_skill_uris = _read_concepts(
        "skills",
        data_dir,
    )
    occupations_report, occupations, observed_occupation_uris = _read_concepts(
        "occupations",
        data_dir,
    )
    hierarchy_report, hierarchy_nodes, hierarchy_edges, held_hierarchy = (
        _read_hierarchy(data_dir, existing["hierarchy"])
    )

    held_skills = _match_skills(
        skills_report,
        skills,
        existing["skills"],
    )
    held_occupations = _match_occupations(
        occupations_report,
        occupations,
        existing["occupations"],
    )
    (
        relations_report,
        relations,
        held_relations,
        unresolved_relations,
        invalid_reference_relations,
        invalid_concept_relations,
    ) = _analyze_relations(
        data_dir,
        skills_report,
        skills,
        observed_skill_uris,
        held_skills,
        occupations_report,
        occupations,
        observed_occupation_uris,
        held_occupations,
        existing["relations"],
    )
    datasets = {
        "skills": skills_report,
        "occupations": occupations_report,
        "hierarchy": hierarchy_report,
        "occupation_skill_relations": relations_report,
    }
    report = {
        "dry_run": True,
        "write_performed": False,
        "datasets": datasets,
        "summary": {
            "source_rows": sum(
                item["source_rows"] for item in datasets.values()
            ),
            "unique_records": sum(
                item["unique_records"] for item in datasets.values()
            ),
            "existing_matches": sum(
                item["existing_matches"] for item in datasets.values()
            ),
            "proposed_additions": sum(
                item["proposed_additions"] for item in datasets.values()
            ),
            "validation_errors": sum(
                item["validation_errors"]["count"]
                for item in datasets.values()
            ),
            "records_held_for_manual_review": (
                skills_report["held_for_manual_review"]["count"]
                + occupations_report["held_for_manual_review"]["count"]
                + hierarchy_report["held_for_manual_review"]["count"]
                + relations_report["held_for_manual_review"]["count"]
            ),
            "unresolved_relationships": (
                relations_report["unresolved_relationship_count"]
                + hierarchy_report["unresolved_parent_links"]["count"]
            ),
        },
    }
    context = {
        "existing": existing,
        "skills": skills,
        "occupations": occupations,
        "hierarchy_nodes": hierarchy_nodes,
        "hierarchy_edges": hierarchy_edges,
        "relations": relations,
        "held_skills": held_skills,
        "held_occupations": held_occupations,
        "held_hierarchy": held_hierarchy,
        "held_relations": held_relations,
        "unresolved_relations": unresolved_relations,
        "invalid_reference_relations": invalid_reference_relations,
        "invalid_concept_relations": invalid_concept_relations,
        "observed_skill_uris": observed_skill_uris,
        "observed_occupation_uris": observed_occupation_uris,
    }
    return report, context


def run_esco_dry_run(
    db: Session,
    data_dir: Path = ESCO_DATA_DIR,
) -> dict:
    """Analyze the four local ESCO datasets without writing to the database."""
    connection, previous_autoflush, sqlite_query_only = (
        _start_read_only_transaction(db)
    )
    try:
        report, _ = _analyze_esco_catalogue(db, data_dir)
        return report
    finally:
        try:
            if sqlite_query_only:
                connection.exec_driver_sql("PRAGMA query_only = OFF")
        finally:
            db.autoflush = previous_autoflush
