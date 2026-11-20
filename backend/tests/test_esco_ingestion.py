import csv

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

import backend.app.db.models as _registered_models
import backend.app.services.esco_ingestion as esco_ingestion
from backend.app.db.base import Base
from backend.app.db.company import Company
from backend.app.db.employee import Employee
from backend.app.db.esco_occupation import ESCOOccupation
from backend.app.db.esco_occupation_skill import ESCOOccupationSkill
from backend.app.db.esco_skill_hierarchy_node import ESCOSkillHierarchyNode
from backend.app.db.job_skill import JobSkill
from backend.app.db.skill import Skill
from backend.app.db.auth_models import User
from backend.app.services.esco_csv_parser import DATASET_COLUMNS, DATASET_FILES
from backend.app.services.esco_ingestion import run_esco_ingestion


_ = (_registered_models, Employee, User)
_INGESTION_TABLES = (
    "companies",
    "employees",
    "users",
    "skills",
    "job_skills",
    "esco_occupations",
    "esco_skill_hierarchy_nodes",
    "esco_occupation_skills",
)


@pytest.fixture
def ingestion_engine():
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        _ = _record
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(
        engine,
        tables=[Base.metadata.tables[name] for name in _INGESTION_TABLES],
    )
    try:
        yield engine
    finally:
        engine.dispose()


def _write_dataset(directory, dataset, rows):
    path = directory / DATASET_FILES[dataset]
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(DATASET_COLUMNS[dataset])
        writer.writerows(rows)


def _set_expected_rows(
    monkeypatch,
    *,
    skills,
    occupations=1,
    hierarchy=1,
    relations,
):
    monkeypatch.setattr(
        esco_ingestion,
        "EXPECTED_SOURCE_ROWS",
        {
            "skills": skills,
            "occupations": occupations,
            "hierarchy": hierarchy,
            "occupation_skill_relations": relations,
        },
    )


def _row(dataset, **values):
    return [values.get(column, "") for column in DATASET_COLUMNS[dataset]]


def _skill(uri, label, **extra):
    values = {
        "conceptUri": uri,
        "preferredLabel": label,
        "description": f"{label} description",
        "skillType": "skill/competence",
        "reuseLevel": "cross-sector",
        "status": "released",
        "modifiedDate": "2024-01-02T03:04:05Z",
    }
    values.update(extra)
    return _row("skills", **values)


def _occupation(uri="https://example.test/occupation/1"):
    return _row(
        "occupations",
        conceptUri=uri,
        preferredLabel="Test occupation",
        altLabels="Test job",
        description="Occupation description",
        iscoGroup="1234",
        code="1234.5",
        status="released",
        modifiedDate="2024-01-02T03:04:05Z",
    )


def _hierarchy(*nodes):
    values = {}
    for level, (uri, label) in enumerate(nodes):
        values[f"Level {level} URI"] = uri
        values[f"Level {level} preferred term"] = label
        values[f"Level {level} code"] = str(level)
    return _row("hierarchy", **values)


def _relation(skill_uri, relation_type="essential"):
    return _row(
        "occupation_skill_relations",
        occupationUri="https://example.test/occupation/1",
        occupationLabel="Test occupation",
        relationType=relation_type,
        skillType="skill/competence",
        skillUri=skill_uri,
        skillLabel="Source skill",
    )


def _write_valid_datasets(directory, *, include_python=True):
    skill_uri = "https://example.test/skill/1"
    python_uri = "https://example.test/skill/python"
    skill_rows = [
        _skill(skill_uri, "Data analysis", altLabels="Data analytics"),
        _skill(skill_uri, "Data analysis", altLabels="Data analytics"),
    ]
    relations = [
        _relation(skill_uri, "essential"),
        _relation(skill_uri, "optional"),
    ]
    if include_python:
        skill_rows.append(
            _skill(
                python_uri,
                "Programming in Python",
                altLabels="Python",
            )
        )
        relations.append(_relation(python_uri))
    _write_dataset(directory, "skills", skill_rows)
    _write_dataset(directory, "occupations", [_occupation()])
    _write_dataset(
        directory,
        "hierarchy",
        [
            _hierarchy(
                ("https://example.test/hierarchy/root", "Root"),
                ("https://example.test/hierarchy/child", "Child"),
            )
        ],
    )
    _write_dataset(directory, "occupation_skill_relations", relations)
    return skill_uri, python_uri


def test_ingestion_inserts_all_datasets_and_skips_python_alias(
    tmp_path,
    ingestion_engine,
    monkeypatch,
):
    skill_uri, _ = _write_valid_datasets(tmp_path)
    _set_expected_rows(monkeypatch, skills=3, relations=3)
    with Session(ingestion_engine) as db:
        curated_python = Skill(
            skill_name="Python",
            description="Manually curated Python skill",
            alternative_labels="Python language",
        )
        db.add(curated_python)
        db.commit()
        python_id = curated_python.skill_id

    with Session(ingestion_engine) as db:
        report = run_esco_ingestion(db, tmp_path, dry_run=False)

    assert report["dry_run"] is False
    assert report["write_performed"] is True
    assert report["aborted"] is False
    assert report["datasets"]["skills"]["inserted_records"] == 1
    assert report["datasets"]["skills"]["held_records"] == 1
    assert report["datasets"]["skills"]["duplicate_records"] == 1
    assert report["datasets"]["occupations"]["inserted_records"] == 1
    assert report["datasets"]["hierarchy"]["inserted_records"] == 2
    assert (
        report["datasets"]["occupation_skill_relations"]["inserted_records"]
        == 2
    )
    assert (
        report["datasets"]["occupation_skill_relations"]["held_records"]
        == 1
    )
    with Session(ingestion_engine) as db:
        skills = db.query(Skill).order_by(Skill.skill_id).all()
        assert len(skills) == 2
        python = db.get(Skill, python_id)
        assert python.skill_name == "Python"
        assert python.description == "Manually curated Python skill"
        assert python.alternative_labels == "Python language"
        imported = db.query(Skill).filter_by(esco_concept_uri=skill_uri).one()
        assert imported.skill_name == "Data analysis"
        assert imported.alternative_labels == "Data analytics"
        assert imported.esco_skill_type == "skill/competence"
        assert imported.esco_modified_date is not None
        assert db.query(ESCOOccupation).count() == 1
        assert db.query(ESCOSkillHierarchyNode).count() == 2
        child = db.query(ESCOSkillHierarchyNode).filter_by(
            esco_concept_uri="https://example.test/hierarchy/child"
        ).one()
        assert child.parent.label == "Root"
        relations = db.query(ESCOOccupationSkill).all()
        assert {relation.relation_type for relation in relations} == {
            "essential",
            "optional",
        }
        assert all(
            relation.skill.esco_concept_uri == skill_uri
            for relation in relations
        )
        assert db.query(JobSkill).count() == 0


def test_ingestion_is_idempotent_and_reports_existing_records(
    tmp_path,
    ingestion_engine,
    monkeypatch,
):
    _write_valid_datasets(tmp_path, include_python=False)
    _set_expected_rows(monkeypatch, skills=2, relations=2)
    with Session(ingestion_engine) as db:
        first = run_esco_ingestion(db, tmp_path, dry_run=False)
    with Session(ingestion_engine) as db:
        second = run_esco_ingestion(db, tmp_path, dry_run=False)

    assert first["summary"]["inserted_records"] == 6
    assert second["summary"]["inserted_records"] == 0
    assert second["write_performed"] is False
    assert second["datasets"]["skills"]["already_existing_records"] == 1
    assert second["datasets"]["occupations"]["already_existing_records"] == 1
    assert second["datasets"]["hierarchy"]["already_existing_records"] == 2
    assert (
        second["datasets"]["occupation_skill_relations"][
            "already_existing_records"
        ]
        == 2
    )


def test_duplicate_modified_date_conflict_remains_review_held(
    tmp_path,
    ingestion_engine,
    monkeypatch,
):
    skill_uri, _ = _write_valid_datasets(tmp_path, include_python=False)
    _write_dataset(
        tmp_path,
        "skills",
        [
            _skill(
                skill_uri,
                "Data analysis",
                altLabels="Data analytics",
                modifiedDate="2025-01-01T00:00:00Z",
            ),
            _skill(
                skill_uri,
                "Data analysis",
                altLabels="Data analytics",
                modifiedDate="2025-02-01T00:00:00Z",
            ),
        ],
    )
    _set_expected_rows(monkeypatch, skills=2, relations=2)

    with Session(ingestion_engine) as db:
        report = run_esco_ingestion(db, tmp_path, dry_run=False)

    assert report["aborted"] is False
    assert report["datasets"]["skills"]["held_records"] == 1
    assert report["datasets"]["skills"]["inserted_records"] == 0
    assert report["datasets"]["occupation_skill_relations"][
        "held_records"
    ] == 2
    assert report["datasets"]["occupation_skill_relations"][
        "inserted_records"
    ] == 0
    with Session(ingestion_engine) as db:
        assert db.query(Skill).filter_by(esco_concept_uri=skill_uri).count() == 0
        assert db.query(ESCOOccupation).count() == 1


def test_dry_run_is_read_only_and_missing_endpoints_are_reported(
    tmp_path,
    ingestion_engine,
    monkeypatch,
):
    skill_uri = "https://example.test/skill/1"
    _write_valid_datasets(tmp_path, include_python=False)
    _set_expected_rows(monkeypatch, skills=2, relations=2)
    _write_dataset(
        tmp_path,
        "occupation_skill_relations",
        [
            _relation(skill_uri),
            _relation("https://example.test/skill/missing"),
        ],
    )
    statements = []

    @event.listens_for(ingestion_engine, "before_cursor_execute")
    def capture_dml(_connection, _cursor, statement, _params, _context, _many):
        _ = (_connection, _cursor, _params, _context, _many)
        command = statement.lstrip().split(None, 1)[0].upper()
        if command in {"INSERT", "UPDATE", "DELETE"}:
            statements.append(command)

    with Session(ingestion_engine) as db:
        report = run_esco_ingestion(db, tmp_path)

    assert report["dry_run"] is True
    assert report["write_performed"] is False
    assert report["datasets"]["skills"]["proposed_records"] == 1
    assert (
        report["datasets"]["occupation_skill_relations"][
            "invalid_references"
        ]
        == 1
    )
    assert statements == []
    with Session(ingestion_engine) as db:
        assert db.query(Skill).count() == 0
        assert db.query(ESCOOccupation).count() == 0
        assert db.query(ESCOOccupationSkill).count() == 0

    event.remove(
        ingestion_engine,
        "before_cursor_execute",
        capture_dml,
    )
    with Session(ingestion_engine) as db:
        actual = run_esco_ingestion(db, tmp_path, dry_run=False)
    assert actual["aborted"] is True
    assert actual["write_performed"] is False
    assert actual["datasets"]["occupation_skill_relations"][
        "source_complete"
    ] is False
    with Session(ingestion_engine) as db:
        assert db.query(Skill).count() == 0
        assert db.query(ESCOOccupation).count() == 0
        assert db.query(ESCOSkillHierarchyNode).count() == 0
        assert db.query(ESCOOccupationSkill).count() == 0


def test_failed_relationship_flush_rolls_back_every_dataset(
    tmp_path,
    ingestion_engine,
    monkeypatch,
):
    skill_uri, _ = _write_valid_datasets(tmp_path, include_python=False)
    _set_expected_rows(monkeypatch, skills=2, relations=2)

    def fail_before_relation_flush(session, _flush_context, _instances):
        _ = (_flush_context, _instances)
        if any(isinstance(item, ESCOOccupationSkill) for item in session.new):
            raise RuntimeError("forced relation flush failure")

    with Session(ingestion_engine) as db:
        event.listen(db, "before_flush", fail_before_relation_flush)
        with pytest.raises(RuntimeError, match="forced relation flush failure"):
            run_esco_ingestion(db, tmp_path, dry_run=False)
        event.remove(db, "before_flush", fail_before_relation_flush)
        db.rollback()

    with Session(ingestion_engine) as db:
        assert (
            db.query(Skill)
            .filter_by(esco_concept_uri=skill_uri)
            .count()
            == 0
        )
        assert db.query(ESCOOccupation).count() == 0
        assert db.query(ESCOSkillHierarchyNode).count() == 0
        assert db.query(ESCOOccupationSkill).count() == 0


def test_incomplete_source_aborts_without_partial_ingestion(
    tmp_path,
    ingestion_engine,
    monkeypatch,
):
    _write_valid_datasets(tmp_path, include_python=False)
    _set_expected_rows(monkeypatch, skills=2, relations=2)
    _write_dataset(
        tmp_path,
        "skills",
        [
            _skill(
                "https://example.test/skill/1",
                "Data analysis",
            )
            + ["unexpected"],
        ],
    )

    with Session(ingestion_engine) as db:
        report = run_esco_ingestion(db, tmp_path, dry_run=False)

    assert report["aborted"] is True
    assert report["write_performed"] is False
    assert report["summary"]["inserted_records"] == 0
    with Session(ingestion_engine) as db:
        assert db.query(Skill).count() == 0
        assert db.query(ESCOOccupation).count() == 0
        assert db.query(ESCOSkillHierarchyNode).count() == 0
        assert db.query(ESCOOccupationSkill).count() == 0


def test_header_only_dataset_aborts_while_other_sources_are_valid(
    tmp_path,
    ingestion_engine,
    monkeypatch,
):
    _write_valid_datasets(tmp_path, include_python=False)
    _set_expected_rows(monkeypatch, skills=2, relations=2)
    _write_dataset(tmp_path, "hierarchy", [])

    with Session(ingestion_engine) as db:
        report = run_esco_ingestion(db, tmp_path, dry_run=False)

    assert report["aborted"] is True
    assert report["write_performed"] is False
    assert report["datasets"]["hierarchy"]["source_rows"] == 0
    assert report["datasets"]["hierarchy"]["source_complete"] is False
    assert report["datasets"]["hierarchy"]["expected_source_rows"] == 1
    assert report["datasets"]["hierarchy"]["completeness_errors"] == [
        {
            "code": "source_row_count_mismatch",
            "expected": 1,
            "actual": 0,
        }
    ]
    assert all(
        report["datasets"][name]["source_complete"]
        for name in ("skills", "occupations", "occupation_skill_relations")
    )
    with Session(ingestion_engine) as db:
        assert db.query(Skill).count() == 0
        assert db.query(ESCOOccupation).count() == 0
        assert db.query(ESCOSkillHierarchyNode).count() == 0
        assert db.query(ESCOOccupationSkill).count() == 0


def test_empty_dataset_aborts_ingestion(
    tmp_path,
    ingestion_engine,
    monkeypatch,
):
    _write_valid_datasets(tmp_path, include_python=False)
    _set_expected_rows(monkeypatch, skills=2, relations=2)
    (tmp_path / DATASET_FILES["skills"]).write_text("", encoding="utf-8")

    with Session(ingestion_engine) as db:
        report = run_esco_ingestion(db, tmp_path, dry_run=False)

    assert report["aborted"] is True
    assert report["datasets"]["skills"]["source_complete"] is False
    assert report["datasets"]["skills"]["source_rows"] == 0
    assert {
        error["code"]
        for error in report["datasets"]["skills"]["completeness_errors"]
    } == {
        "csv_parse_incomplete",
        "source_row_count_mismatch",
    }
    with Session(ingestion_engine) as db:
        assert db.query(Skill).count() == 0
        assert db.query(ESCOOccupation).count() == 0
        assert db.query(ESCOSkillHierarchyNode).count() == 0
        assert db.query(ESCOOccupationSkill).count() == 0


def test_semantic_errors_fail_closed_and_failed_records_are_distinct(
    tmp_path,
    ingestion_engine,
    monkeypatch,
):
    skill_uri = "https://example.test/skill/invalid"
    _write_valid_datasets(tmp_path, include_python=False)
    _write_dataset(
        tmp_path,
        "skills",
        [
            _skill(
                skill_uri,
                "",
                skillType="x" * 41,
                modifiedDate="not-an-iso-date",
            )
        ],
    )
    _set_expected_rows(monkeypatch, skills=1, relations=2)

    with Session(ingestion_engine) as db:
        report = run_esco_ingestion(db, tmp_path, dry_run=False)

    skills_report = report["datasets"]["skills"]
    assert report["aborted"] is True
    assert skills_report["source_rows"] == 1
    assert skills_report["source_complete"] is False
    assert skills_report["failed_records"] == 1
    assert skills_report["completeness_errors"] == [
        {"code": "invalid_source_rows", "failed_records": 1}
    ]
    assert skills_report["failed_records"] == 1
    assert skills_report["validation_errors"] == 3
    with Session(ingestion_engine) as db:
        assert db.query(Skill).count() == 0
        assert db.query(ESCOOccupation).count() == 0
        assert db.query(ESCOSkillHierarchyNode).count() == 0
        assert db.query(ESCOOccupationSkill).count() == 0


def test_valid_row_boundary_truncation_is_detected_by_expected_count(
    tmp_path,
    ingestion_engine,
    monkeypatch,
):
    skill_uri, _ = _write_valid_datasets(tmp_path, include_python=False)
    _set_expected_rows(monkeypatch, skills=2, relations=2)
    _write_dataset(
        tmp_path,
        "occupation_skill_relations",
        [_relation(skill_uri)],
    )

    with Session(ingestion_engine) as db:
        report = run_esco_ingestion(db, tmp_path, dry_run=False)

    relation_report = report["datasets"]["occupation_skill_relations"]
    assert report["aborted"] is True
    assert relation_report["source_row_count_matches_expected"] is False
    assert relation_report["source_rows"] == 1
    assert relation_report["expected_source_rows"] == 2
    assert relation_report["completeness_errors"] == [
        {
            "code": "source_row_count_mismatch",
            "expected": 2,
            "actual": 1,
        }
    ]
    with Session(ingestion_engine) as db:
        assert db.query(Skill).count() == 0
        assert db.query(ESCOOccupation).count() == 0
        assert db.query(ESCOSkillHierarchyNode).count() == 0
        assert db.query(ESCOOccupationSkill).count() == 0


def test_ingestion_does_not_modify_company_job_skill_requirements(
    tmp_path,
    ingestion_engine,
    monkeypatch,
):
    _write_valid_datasets(tmp_path, include_python=False)
    _set_expected_rows(monkeypatch, skills=2, relations=2)
    with Session(ingestion_engine) as db:
        company = Company(company_name="Existing company")
        skill = Skill(skill_name="Curated requirement")
        db.add_all([company, skill])
        db.flush()
        requirement = JobSkill(
            company_id=company.company_id,
            job_title="Analyst",
            skill_id=skill.skill_id,
            required_proficiency=3,
            importance="High",
            approval_status="Approved",
        )
        db.add(requirement)
        db.commit()
        requirement_id = requirement.id
        before = (
            requirement.company_id,
            requirement.job_title,
            requirement.skill_id,
            requirement.required_proficiency,
            requirement.importance,
            requirement.approval_status,
        )

    with Session(ingestion_engine) as db:
        run_esco_ingestion(db, tmp_path, dry_run=False)
    with Session(ingestion_engine) as db:
        after = db.get(JobSkill, requirement_id)
        assert (
            after.company_id,
            after.job_title,
            after.skill_id,
            after.required_proficiency,
            after.importance,
            after.approval_status,
        ) == before
        assert db.query(JobSkill).count() == 1
