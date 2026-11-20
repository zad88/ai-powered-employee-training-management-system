"""Transactional ESCO catalogue ingestion; dry-run is the safe default."""

from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from backend.app.db.esco_occupation import ESCOOccupation
from backend.app.db.esco_occupation_skill import ESCOOccupationSkill
from backend.app.db.esco_skill_hierarchy_node import ESCOSkillHierarchyNode
from backend.app.db.skill import Skill
from backend.app.services.esco_csv_parser import (
    ESCO_DATA_DIR,
    ESCO_EXPECTED_SOURCE_ROWS,
)
from backend.app.services.esco_dry_run import (
    _analyze_esco_catalogue,
    _start_read_only_transaction,
)


_DATASET_KEYS = (
    "skills",
    "occupations",
    "hierarchy",
    "occupation_skill_relations",
)
EXPECTED_SOURCE_ROWS = ESCO_EXPECTED_SOURCE_ROWS


def _valid_relation_records(
    report: dict,
    context: dict,
) -> set[tuple[str, str, str]]:
    source_complete = all(
        report["datasets"][name]["source_complete"]
        for name in ("skills", "occupations", "occupation_skill_relations")
    )
    if not source_complete:
        return set()
    return set(context["relations"]) - context["unresolved_relations"]


def _dataset_result(
    source_report: dict,
    *,
    unique_count: int,
    existing_count: int,
    proposed_count: int,
    held_count: int,
    invalid_reference_count: int = 0,
) -> dict:
    return {
        "source_complete": source_report["source_complete"],
        "source_rows": source_report["source_rows"],
        "expected_source_rows": source_report["expected_source_rows"],
        "source_row_count_matches_expected": source_report[
            "source_row_count_matches_expected"
        ],
        "completeness_errors": source_report["completeness_errors"],
        "unique_concepts": unique_count,
        "eligible_records": existing_count + proposed_count,
        "proposed_records": proposed_count,
        "inserted_records": 0,
        "already_existing_records": existing_count,
        "held_records": held_count,
        "invalid_references": invalid_reference_count,
        "failed_records": source_report["failed_records"],
        "validation_errors": source_report["validation_errors"]["count"],
        "duplicate_records": source_report["duplicate_records"],
    }


def _validate_source_completeness(
    source_report: dict,
    context: dict,
) -> None:
    datasets = source_report["datasets"]
    for name in _DATASET_KEYS:
        report = datasets[name]
        expected_rows = EXPECTED_SOURCE_ROWS[name]
        actual_rows = report["source_rows"]
        errors = []
        report["expected_source_rows"] = expected_rows
        report["source_row_count_matches_expected"] = (
            actual_rows == expected_rows
        )

        if actual_rows != expected_rows:
            errors.append(
                {
                    "code": "source_row_count_mismatch",
                    "expected": expected_rows,
                    "actual": actual_rows,
                }
            )
        if not report["source_complete"]:
            errors.append({"code": "csv_parse_incomplete"})
        if report["failed_records"]:
            errors.append(
                {
                    "code": "invalid_source_rows",
                    "failed_records": report["failed_records"],
                }
            )
        if (
            name == "hierarchy"
            and report["unresolved_parent_links"]["count"]
        ):
            errors.append(
                {
                    "code": "unresolved_hierarchy_parents",
                    "count": report["unresolved_parent_links"]["count"],
                }
            )
        if name == "occupation_skill_relations":
            invalid_references = (
                context["invalid_reference_relations"]
                | context["invalid_concept_relations"]
            )
            if invalid_references:
                errors.append(
                    {
                        "code": "unresolved_relationship_endpoints",
                        "count": len(invalid_references),
                    }
                )

        report["completeness_errors"] = errors
        if errors:
            report["source_complete"] = False


def _build_report(source_report: dict, context: dict) -> tuple[dict, dict]:
    datasets = source_report["datasets"]
    existing = context["existing"]

    skill_existing = {
        row["uri"]: row["id"]
        for row in existing["skills"]
        if row["uri"]
    }
    occupation_existing = {
        row["uri"]: row["id"]
        for row in existing["occupations"]
    }
    hierarchy_existing = {
        uri: row["id"] for uri, row in existing["hierarchy"].items()
    }
    eligible_skills = (
        set(context["skills"]) - context["held_skills"]
        if datasets["skills"]["source_complete"]
        else set()
    )
    eligible_occupations = (
        set(context["occupations"]) - context["held_occupations"]
        if datasets["occupations"]["source_complete"]
        else set()
    )
    eligible_hierarchy = (
        set(context["hierarchy_nodes"]) - context["held_hierarchy"]
        if datasets["hierarchy"]["source_complete"]
        else set()
    )
    eligible_relations = _valid_relation_records(source_report, context)

    skill_existing_eligible = eligible_skills & skill_existing.keys()
    occupation_existing_eligible = (
        eligible_occupations & occupation_existing.keys()
    )
    hierarchy_existing_eligible = (
        eligible_hierarchy & hierarchy_existing.keys()
    )
    existing_relations = existing["relations"]
    relation_existing_eligible = eligible_relations & existing_relations

    skill_proposed = eligible_skills - skill_existing.keys()
    occupation_proposed = eligible_occupations - occupation_existing.keys()
    hierarchy_proposed = eligible_hierarchy - hierarchy_existing.keys()
    relation_proposed = eligible_relations - existing_relations

    invalid_hierarchy_refs = datasets["hierarchy"][
        "unresolved_parent_links"
    ]["count"]
    relation_invalid_refs = len(
        context["invalid_reference_relations"]
        | context["invalid_concept_relations"]
    )
    per_dataset = {
        "skills": _dataset_result(
            datasets["skills"],
            unique_count=datasets["skills"]["unique_records"],
            existing_count=len(skill_existing_eligible),
            proposed_count=len(skill_proposed),
            held_count=len(context["held_skills"]),
        ),
        "occupations": _dataset_result(
            datasets["occupations"],
            unique_count=datasets["occupations"]["unique_records"],
            existing_count=len(occupation_existing_eligible),
            proposed_count=len(occupation_proposed),
            held_count=len(context["held_occupations"]),
        ),
        "hierarchy": _dataset_result(
            datasets["hierarchy"],
            unique_count=datasets["hierarchy"]["unique_records"],
            existing_count=len(hierarchy_existing_eligible),
            proposed_count=len(hierarchy_proposed),
            held_count=len(context["held_hierarchy"]),
            invalid_reference_count=invalid_hierarchy_refs,
        ),
        "occupation_skill_relations": _dataset_result(
            datasets["occupation_skill_relations"],
            unique_count=datasets["occupation_skill_relations"][
                "unique_records"
            ],
            existing_count=len(relation_existing_eligible),
            proposed_count=len(relation_proposed),
            held_count=len(context["held_relations"]),
            invalid_reference_count=relation_invalid_refs,
        ),
    }
    plan = {
        "skills": skill_proposed,
        "occupations": occupation_proposed,
        "hierarchy": hierarchy_proposed,
        "occupation_skill_relations": relation_proposed,
    }
    totals = {
        key: sum(dataset[key] for dataset in per_dataset.values())
        for key in (
            "source_rows",
            "unique_concepts",
            "eligible_records",
            "proposed_records",
            "inserted_records",
            "already_existing_records",
            "held_records",
            "invalid_references",
            "failed_records",
            "duplicate_records",
        )
    }
    report = {
        "dry_run": True,
        "write_performed": False,
        "aborted": False,
        "datasets": per_dataset,
        "summary": totals,
    }
    return report, plan


def _parse_modified_date(value: str) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _optional(value: str) -> str | None:
    return value if value else None


def _insert_eligible_records(
    db: Session,
    context: dict,
    report: dict,
    plan: dict,
) -> None:
    existing = context["existing"]
    skill_ids = {
        row["uri"]: row["id"]
        for row in existing["skills"]
        if row["uri"]
    }
    occupation_ids = {
        row["uri"]: row["id"]
        for row in existing["occupations"]
    }
    hierarchy_ids = {
        uri: row["id"] for uri, row in existing["hierarchy"].items()
    }

    skill_rows = []
    for uri in sorted(plan["skills"]):
        source = context["skills"][uri]["values"]
        skill_rows.append(
            Skill(
                skill_name=source["preferredLabel"],
                description=_optional(source.get("description", "")),
                esco_concept_uri=uri,
                alternative_labels=_optional(source.get("altLabels", "")),
                esco_skill_type=_optional(source.get("skillType", "")),
                esco_reuse_level=_optional(source.get("reuseLevel", "")),
                esco_status=_optional(source.get("status", "")),
                esco_modified_date=_parse_modified_date(
                    source.get("modifiedDate", "")
                ),
            )
        )
    db.add_all(skill_rows)
    if skill_rows:
        db.flush()
        for row in skill_rows:
            skill_ids[row.esco_concept_uri] = row.skill_id
    report["datasets"]["skills"]["inserted_records"] = len(skill_rows)

    occupation_rows = []
    for uri in sorted(plan["occupations"]):
        source = context["occupations"][uri]["values"]
        occupation_rows.append(
            ESCOOccupation(
                esco_concept_uri=uri,
                preferred_label=source["preferredLabel"],
                alternative_labels=_optional(source.get("altLabels", "")),
                description=_optional(source.get("description", "")),
                isco_group=_optional(source.get("iscoGroup", "")),
                code=_optional(source.get("code", "")),
                nace_code=_optional(source.get("naceCode", "")),
                regulated_profession_note=_optional(
                    source.get("regulatedProfessionNote", "")
                ),
                scope_note=_optional(source.get("scopeNote", "")),
                definition=_optional(source.get("definition", "")),
                in_scheme=_optional(source.get("inScheme", "")),
                status=_optional(source.get("status", "")),
                modified_date=_parse_modified_date(
                    source.get("modifiedDate", "")
                ),
            )
        )
    db.add_all(occupation_rows)
    if occupation_rows:
        db.flush()
        for row in occupation_rows:
            occupation_ids[row.esco_concept_uri] = row.id
    report["datasets"]["occupations"]["inserted_records"] = len(
        occupation_rows
    )

    hierarchy_rows = [
        context["hierarchy_nodes"][uri]
        for uri in plan["hierarchy"]
    ]
    inserted_hierarchy = 0
    for level in range(4):
        level_rows = sorted(
            (node for node in hierarchy_rows if node["level"] == level),
            key=lambda node: node["uri"],
        )
        pending_nodes = []
        pending_rows = []
        for node in level_rows:
            parent_id = None
            if node["parent_uri"]:
                parent_id = hierarchy_ids.get(node["parent_uri"])
                if parent_id is None:
                    raise RuntimeError(
                        "ESCO hierarchy parent is unavailable for eligible "
                        f"node {node['uri']}."
                    )
            pending_nodes.append(node)
            pending_rows.append(
                ESCOSkillHierarchyNode(
                    esco_concept_uri=node["uri"],
                    label=node["label"],
                    hierarchy_level=node["level"],
                    code=_optional(node["code"]),
                    description=_optional(node["description"]),
                    scope_note=_optional(node["scope_note"]),
                    parent_id=parent_id,
                )
            )
        db.add_all(pending_rows)
        if pending_rows:
            db.flush()
            for node, row in zip(pending_nodes, pending_rows):
                hierarchy_ids[node["uri"]] = row.id
        inserted_hierarchy += len(pending_rows)
    report["datasets"]["hierarchy"]["inserted_records"] = inserted_hierarchy

    relation_rows = []
    for occupation_uri, skill_uri, relation_type in sorted(
        plan["occupation_skill_relations"]
    ):
        occupation_id = occupation_ids.get(occupation_uri)
        skill_id = skill_ids.get(skill_uri)
        if occupation_id is None or skill_id is None:
            raise RuntimeError(
                "ESCO relationship has an unresolved eligible endpoint: "
                f"{occupation_uri} -> {skill_uri}."
            )
        relation = context["relations"][
            (occupation_uri, skill_uri, relation_type)
        ]
        relation_rows.append(
            ESCOOccupationSkill(
                occupation_id=occupation_id,
                skill_id=skill_id,
                relation_type=relation_type,
                skill_type=_optional(relation["skill_type"]),
            )
        )
    db.add_all(relation_rows)
    if relation_rows:
        db.flush()
    report["datasets"]["occupation_skill_relations"][
        "inserted_records"
    ] = len(relation_rows)

    report["summary"]["inserted_records"] = sum(
        dataset["inserted_records"]
        for dataset in report["datasets"].values()
    )


def run_esco_ingestion(
    db: Session,
    data_dir: Path = ESCO_DATA_DIR,
    *,
    dry_run: bool = True,
) -> dict:
    """Analyze or ingest eligible ESCO records in one atomic transaction."""
    if dry_run:
        connection, previous_autoflush, sqlite_query_only = (
            _start_read_only_transaction(db)
        )
        try:
            source_report, context = _analyze_esco_catalogue(db, data_dir)
            _validate_source_completeness(source_report, context)
            report, _ = _build_report(source_report, context)
            return report
        finally:
            try:
                if sqlite_query_only:
                    connection.exec_driver_sql("PRAGMA query_only = OFF")
            finally:
                db.autoflush = previous_autoflush

    if db.in_transaction():
        raise RuntimeError(
            "ESCO ingestion requires a fresh SQLAlchemy session."
        )
    if db.new or db.dirty or db.deleted:
        raise RuntimeError(
            "ESCO ingestion cannot run with pending ORM changes."
        )

    with db.begin():
        source_report, context = _analyze_esco_catalogue(db, data_dir)
        _validate_source_completeness(source_report, context)
        report, plan = _build_report(source_report, context)
        if not all(
            source_report["datasets"][name]["source_complete"]
            for name in _DATASET_KEYS
        ):
            report["aborted"] = True
            report["dry_run"] = False
            return report

        _insert_eligible_records(db, context, report, plan)
        report["dry_run"] = False
        report["write_performed"] = report["summary"]["inserted_records"] > 0
        return report
