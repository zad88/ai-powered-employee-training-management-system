import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import backend.app.db.models
from backend.app.db.base import Base
from backend.app.db.esco_occupation import ESCOOccupation
from backend.app.db.esco_occupation_skill import ESCOOccupationSkill
from backend.app.db.esco_skill_hierarchy_node import ESCOSkillHierarchyNode
from backend.app.db.skill import Skill


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


def test_esco_models_are_registered_with_expected_schema(esco_engine):
    inspector = inspect(esco_engine)

    assert set(ESCO_TABLES).issubset(Base.metadata.tables)
    assert {
        "esco_skill_type",
        "esco_reuse_level",
        "esco_status",
        "esco_modified_date",
    }.issubset(
        {column["name"] for column in inspector.get_columns("skills")}
    )
    assert {
        "esco_concept_uri",
        "preferred_label",
        "alternative_labels",
        "isco_group",
        "code",
    }.issubset(
        {
            column["name"]
            for column in inspector.get_columns("esco_occupations")
        }
    )
    assert inspector.get_foreign_keys(
        "esco_occupation_skills"
    )
    assert inspector.get_foreign_keys(
        "esco_skill_hierarchy_nodes"
    )
    assert {
        tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints(
            "esco_occupation_skills"
        )
    } == {("occupation_id", "skill_id", "relation_type")}


def test_esco_relationships_persist_without_company_job_requirements(
    esco_engine,
):
    with Session(esco_engine) as db:
        occupation = ESCOOccupation(
            esco_concept_uri="https://example.test/occupation/1",
            preferred_label="Sample occupation",
        )
        root = ESCOSkillHierarchyNode(
            esco_concept_uri="https://example.test/hierarchy/root",
            label="Root",
            hierarchy_level=0,
        )
        child = ESCOSkillHierarchyNode(
            esco_concept_uri="https://example.test/hierarchy/child",
            label="Child",
            hierarchy_level=1,
            parent=root,
        )
        skill = Skill(
            skill_name="Sample skill",
            esco_concept_uri="https://example.test/skill/1",
        )
        relation = ESCOOccupationSkill(
            occupation=occupation,
            skill=skill,
            relation_type="essential",
            skill_type="knowledge",
        )
        db.add_all([occupation, root, child, skill, relation])
        db.commit()

        assert child.parent_id == root.id
        assert relation.occupation_id == occupation.id
        assert relation.skill_id == skill.skill_id
        assert "company_id" not in ESCOOccupationSkill.__table__.columns
        assert "approval_status" not in ESCOOccupationSkill.__table__.columns
        db.add(
            ESCOOccupationSkill(
                occupation=occupation,
                skill=skill,
                relation_type="essential",
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()


def test_esco_constraints_reject_duplicate_uris_and_invalid_relation_types(
    esco_engine,
):
    with Session(esco_engine) as db:
        first = Skill(
            skill_name="First",
            esco_concept_uri="https://example.test/skill/shared",
        )
        second = Skill(
            skill_name="Second",
            esco_concept_uri="https://example.test/skill/shared",
        )
        db.add_all([first, second])
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        occupation = ESCOOccupation(
            esco_concept_uri="https://example.test/occupation/1",
            preferred_label="Sample occupation",
        )
        skill = Skill(skill_name="Sample skill")
        db.add_all([occupation, skill])
        db.flush()
        db.add(
            ESCOOccupationSkill(
                occupation=occupation,
                skill=skill,
                relation_type="recommended",
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
