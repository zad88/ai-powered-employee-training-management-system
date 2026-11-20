import csv

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

import backend.app.db.models as _registered_models
from backend.app.db.base import Base
from backend.app.db.skill import Skill
from backend.app.services.esco_csv_parser import (
    DATASET_COLUMNS,
    DATASET_FILES,
    ESCOCSVReader,
    ESCOCSVRowIssue,
)
from backend.app.services.esco_dry_run import (
    _match_skills,
    _read_concepts,
    run_esco_dry_run,
)


ESCO_TABLES = (
    "skills",
    "esco_occupations",
    "esco_skill_hierarchy_nodes",
    "esco_occupation_skills",
)


@pytest.fixture
def esco_engine():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine,
        tables=[Base.metadata.tables[name] for name in ESCO_TABLES],
    )
    try:
        yield engine
    finally:
        engine.dispose()


def _csv_row(dataset, **values):
    return [values.get(column, "") for column in DATASET_COLUMNS[dataset]]


def _write_dataset(directory, dataset, rows, *, encoding="utf-8"):
    path = directory / DATASET_FILES[dataset]
    with path.open("w", encoding=encoding, newline="") as output:
        writer = csv.writer(output)
        writer.writerow(DATASET_COLUMNS[dataset])
        writer.writerows(rows)
    return path


def _write_all_datasets(
    directory,
    *,
    skills=(),
    occupations=(),
    hierarchy=(),
    relations=(),
):
    _write_dataset(directory, "skills", skills)
    _write_dataset(directory, "occupations", occupations)
    _write_dataset(directory, "hierarchy", hierarchy)
    _write_dataset(directory, "occupation_skill_relations", relations)


def _skill(uri, label, **extra):
    values = {
        "conceptUri": uri,
        "preferredLabel": label,
        "description": f"{label} description",
        "status": "released",
        "skillType": "skill/competence",
        "reuseLevel": "cross-sector",
    }
    values.update(extra)
    return _csv_row("skills", **values)


def _occupation(uri, label):
    return _csv_row(
        "occupations",
        conceptUri=uri,
        preferredLabel=label,
        description=f"{label} description",
        status="released",
        code="1",
        iscoGroup="1",
    )


def _hierarchy_path(*nodes):
    values = {}
    for level, (uri, label) in enumerate(nodes):
        values[f"Level {level} URI"] = uri
        values[f"Level {level} preferred term"] = label
    return _csv_row("hierarchy", **values)


def _relation(occupation_uri, skill_uri, relation_type="essential"):
    return _csv_row(
        "occupation_skill_relations",
        occupationUri=occupation_uri,
        occupationLabel="Occupation",
        relationType=relation_type,
        skillType="skill/competence",
        skillUri=skill_uri,
        skillLabel="Skill",
    )


def test_parser_supports_bom_and_multiline_quoted_values(tmp_path):
    multiline = _csv_row(
        "skills",
        conceptUri="https://example.test/skill/1",
        preferredLabel="Label",
        altLabels="first alias\nsecond alias",
    )
    path = _write_dataset(
        tmp_path,
        "skills",
        [multiline],
        encoding="utf-8-sig",
    )

    reader = ESCOCSVReader(path, "skills")
    records = list(reader)

    assert reader.encoding == "UTF-8 with BOM"
    assert len(records) == 1
    assert records[0].values["altLabels"] == "first alias\nsecond alias"


def test_parser_reports_malformed_width_and_streams_large_files(tmp_path):
    path = _write_dataset(
        tmp_path,
        "skills",
        [
            _csv_row(
                "skills",
                conceptUri="https://example.test/skill/extra",
                preferredLabel="Extra",
            )
            + ["unexpected"],
        ],
    )
    malformed = list(ESCOCSVReader(path, "skills"))
    assert isinstance(malformed[0], ESCOCSVRowIssue)
    assert malformed[0].code == "extra_columns"

    path = _write_dataset(
        tmp_path,
        "skills",
        (
            _csv_row(
                "skills",
                conceptUri=f"https://example.test/skill/{index}",
                preferredLabel=f"Skill {index}",
            )
            for index in range(10_001)
        ),
    )
    reader = ESCOCSVReader(path, "skills")
    records = iter(reader)
    next(records)
    next(records)
    assert reader.source_rows == 2
    assert sum(1 for _ in records) == 9_999
    assert reader.source_rows == 10_001


def test_concept_analysis_detects_duplicates_conflicts_and_alias_collisions(
    tmp_path,
):
    uri = "https://example.test/skill/duplicate"
    rows = [
        _skill(uri, "First", description="Same description"),
        _skill(uri, "Second", description="Same description"),
        _skill("https://example.test/skill/a", "Shared", altLabels="Alias"),
        _skill("https://example.test/skill/b", "Other", altLabels="shared"),
    ]
    _write_dataset(tmp_path, "skills", rows)
    report, concepts, _ = _read_concepts("skills", tmp_path)

    assert report["source_rows"] == 4
    assert report["unique_records"] == 3
    assert report["duplicate_records"] == 1
    assert report["inconsistent_duplicate_groups"]["count"] == 1
    assert report["preferred_label_conflicts"]["count"] == 0
    duplicate_example = report["inconsistent_duplicate_groups"]["examples"][0]
    assert duplicate_example["rows"] == [2, 3]
    assert duplicate_example["differing_fields"] == ["preferredLabel"]
    assert duplicate_example["field_values"]["preferredLabel"] == [
        {"row": 2, "value": "First"},
        {"row": 3, "value": "Second"},
    ]

    match_report, concepts, _ = _read_concepts("skills", tmp_path)
    _match_skills(match_report, concepts, [])
    assert match_report["ambiguous_alternative_labels"]["count"] == 1
    assert match_report["held_for_manual_review"]["count"] == 1
    assert match_report["held_for_manual_review"]["reason_counts"] == {
        "duplicate_uri_conflict": 1,
        "preferred_label_conflict": 0,
        "existing_database_identity_conflict": 0,
        "python_alias_review": 0,
        "other_reason": 0,
    }
    assert match_report["proposed_additions"] == 2


def test_preferred_label_conflicts_require_distinct_concept_uris(tmp_path):
    _write_dataset(
        tmp_path,
        "skills",
        [
            _skill("https://example.test/skill/a", "Shared label"),
            _skill("https://example.test/skill/b", " shared   label "),
        ],
    )
    report, concepts, _ = _read_concepts("skills", tmp_path)

    _match_skills(report, concepts, [])

    assert report["preferred_label_conflicts"]["count"] == 1
    assert report["held_for_manual_review"]["reason_counts"][
        "preferred_label_conflict"
    ] == 2
    assert report["proposed_additions"] == 0


def test_different_modified_dates_are_reported_as_real_conflicts(tmp_path):
    uri = "https://example.test/skill/modified"
    _write_dataset(
        tmp_path,
        "skills",
        [
            _skill(uri, "Skill", modifiedDate="2025-07-31T09:41:33.786Z"),
            _skill(uri, "Skill", modifiedDate="2025-11-26T10:07:57.331Z"),
        ],
    )

    report, _, _ = _read_concepts("skills", tmp_path)

    assert report["inconsistent_duplicate_groups"]["count"] == 1
    assert report["representation_only_duplicate_groups"]["count"] == 0
    conflict = report["inconsistent_duplicate_groups"]["examples"][0]
    assert conflict["rows"] == [2, 3]
    assert conflict["differing_fields"] == ["modifiedDate"]
    assert conflict["field_values"]["modifiedDate"] == [
        {"row": 2, "value": "2025-07-31T09:41:33.786Z"},
        {"row": 3, "value": "2025-11-26T10:07:57.331Z"},
    ]


def test_representation_only_duplicate_differences_are_not_conflicts(
    tmp_path,
):
    uri = "https://example.test/skill/representation"
    first = _skill(
        uri,
        "Shared label",
        altLabels="Alpha\nBeta",
        description="A  description",
        modifiedDate="2025-01-02T03:04:05Z",
    )
    second = _skill(
        uri,
        "Shared label",
        altLabels=" Beta \nAlpha ",
        description="A description",
        modifiedDate="2025-01-02T03:04:05+00:00",
    )
    _write_dataset(tmp_path, "skills", [first, second])

    report, concepts, _ = _read_concepts("skills", tmp_path)
    held = _match_skills(report, concepts, [])

    assert report["duplicate_records"] == 1
    assert report["inconsistent_duplicate_groups"]["count"] == 0
    assert report["representation_only_duplicate_groups"]["count"] == 1
    assert held == set()
    assert report["proposed_additions"] == 1


def test_ambiguous_aliases_warn_but_do_not_hold_uri_matches(
    tmp_path,
    esco_engine,
):
    occupation_uri = "https://example.test/occupation/1"
    skill_a = "https://example.test/skill/a"
    skill_b = "https://example.test/skill/b"
    _write_all_datasets(
        tmp_path,
        skills=[
            _skill(skill_a, "Alpha", altLabels="Shared alias"),
            _skill(skill_b, "Beta", altLabels=" shared   alias "),
        ],
        occupations=[_occupation(occupation_uri, "Occupation")],
        hierarchy=[_hierarchy_path(("https://example.test/root", "Root"))],
        relations=[
            _relation(occupation_uri, skill_a),
            _relation(occupation_uri, skill_b),
        ],
    )

    with Session(esco_engine) as db:
        report = run_esco_dry_run(db, tmp_path)

    skill_report = report["datasets"]["skills"]
    relation_report = report["datasets"]["occupation_skill_relations"]
    assert skill_report["ambiguous_alternative_labels"]["count"] == 1
    assert skill_report["ambiguous_alternative_labels"]["concept_count"] == 2
    assert skill_report["held_for_manual_review"]["count"] == 0
    assert skill_report["proposed_additions"] == 2
    assert relation_report["proposed_additions"] == 2
    assert relation_report["unresolved_relationship_count"] == 0
    assert relation_report["invalid_source_references"]["count"] == 0


def test_skill_matching_requires_uri_and_preserves_python_alias(tmp_path):
    rows = [
        _skill(
            "https://example.test/skill/python",
            "Programming in Python",
            altLabels="Python",
        ),
        _skill(
            "https://example.test/skill/existing",
            "Source label",
        ),
    ]
    _write_dataset(tmp_path, "skills", rows)
    report, concepts, _ = _read_concepts("skills", tmp_path)
    existing = [
        {
            "id": 1,
            "name": "Python",
            "uri": None,
            "alternative_labels": None,
            "metadata": {},
        },
        {
            "id": 2,
            "name": "Unrelated existing name",
            "uri": "https://example.test/skill/existing",
            "alternative_labels": None,
            "metadata": {
                "preferredLabel": "Source label",
                "altLabels": "",
                "description": "Source label description",
                "skillType": "skill/competence",
                "reuseLevel": "cross-sector",
                "status": "released",
                "modifiedDate": None,
            },
        },
    ]

    held = _match_skills(report, concepts, existing)

    assert report["existing_matches"] == 1
    assert "https://example.test/skill/python" in held
    assert "https://example.test/skill/existing" not in held
    assert report["proposed_additions"] == 0
    assert report["held_for_manual_review"]["reason_counts"] == {
        "duplicate_uri_conflict": 0,
        "preferred_label_conflict": 0,
        "existing_database_identity_conflict": 0,
        "python_alias_review": 1,
        "other_reason": 0,
    }
    python_review = report["held_for_manual_review"]["examples"][0]
    assert python_review["database_skill_name"] == "Python"
    assert python_review["automatic_link"] is False


def test_dry_run_reports_invalid_references_and_hierarchy_conflicts(
    tmp_path,
    esco_engine,
):
    occupation_uri = "https://example.test/occupation/1"
    missing_skill_uri = "https://example.test/skill/missing"
    root_uri = "https://example.test/hierarchy/root"
    second_root_uri = "https://example.test/hierarchy/second-root"
    child_uri = "https://example.test/hierarchy/child"
    shared_parent_uri = "https://example.test/hierarchy/shared-parent"

    _write_all_datasets(
        tmp_path,
        skills=[_skill("https://example.test/skill/1", "Skill")],
        occupations=[_occupation(occupation_uri, "Occupation")],
        hierarchy=[
            _hierarchy_path((shared_parent_uri, "Shared parent")),
            _hierarchy_path(
                (second_root_uri, "Second root"),
                (shared_parent_uri, "Shared parent"),
                (child_uri, "Child"),
            ),
            _hierarchy_path((root_uri, "Root")),
        ],
        relations=[
            _relation(occupation_uri, missing_skill_uri),
            _relation(
                "https://example.test/occupation/missing",
                "https://example.test/skill/1",
            ),
        ],
    )

    with Session(esco_engine) as db:
        report = run_esco_dry_run(db, tmp_path)

    relation_report = report["datasets"]["occupation_skill_relations"]
    hierarchy_report = report["datasets"]["hierarchy"]
    assert relation_report["source_file"].endswith(
        DATASET_FILES["occupation_skill_relations"]
    )
    assert relation_report["source_rows"] == 2
    assert relation_report["invalid_source_references"]["count"] == 2
    assert relation_report["unresolved_relationship_count"] == 2
    assert hierarchy_report["validation_errors"]["count"] >= 1
    assert any(
        example.get("code") == "parent_level_mismatch"
        for example in hierarchy_report["validation_errors"]["examples"]
    )


def test_dry_run_is_read_only_and_holds_python_relationships(
    tmp_path,
    esco_engine,
):
    occupation_uri = "https://example.test/occupation/1"
    python_uri = "https://example.test/skill/python"
    _write_all_datasets(
        tmp_path,
        skills=[_skill(python_uri, "Programming in Python", altLabels="Python")],
        occupations=[_occupation(occupation_uri, "Occupation")],
        hierarchy=[_hierarchy_path(("https://example.test/root", "Root"))],
        relations=[_relation(occupation_uri, python_uri)],
    )
    with Session(esco_engine) as seed_db:
        seed_db.add(Skill(skill_name="Python"))
        seed_db.commit()

    statements = []

    @event.listens_for(esco_engine, "before_cursor_execute")
    def capture_statement(
        _connection,
        _cursor,
        statement,
        _parameters,
        _context,
        _executemany,
    ):
        statements.append(statement.lstrip().split(None, 1)[0].upper())

    with Session(esco_engine) as db:
        report = run_esco_dry_run(db, tmp_path)
        assert not db.new
        assert not db.dirty
        assert not db.deleted

    assert report["dry_run"] is True
    assert report["write_performed"] is False
    assert "INSERT" not in statements
    assert "UPDATE" not in statements
    assert "DELETE" not in statements
    relation_report = report["datasets"]["occupation_skill_relations"]
    assert relation_report["invalid_source_references"]["count"] == 0
    assert relation_report["unresolved_relationship_count"] == 1
    assert relation_report["unresolved_relationships"]["examples"][0][
        "reason"
    ] == ["skill_held_for_manual_review"]
    with Session(esco_engine) as verify_db:
        assert verify_db.query(Skill).count() == 1
