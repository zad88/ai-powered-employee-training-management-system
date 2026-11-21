from datetime import date
from importlib import import_module

import backend.app.db.models
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.api.company_esco_mappings import router
from backend.app.api.job_skills import router as job_skills_router
from backend.app.api.dependencies import authorize_business_request, get_db
from backend.app.core.security import create_access_token
from backend.app.db.auth_models import User, UserCompanyRole
from backend.app.db.base import Base
from backend.app.db.company import Company
from backend.app.db.company_esco_occupation_mapping import CompanyESCOOccupationMapping
from backend.app.db.employee import Employee
from backend.app.db.esco_occupation import ESCOOccupation
from backend.app.db.esco_occupation_skill import ESCOOccupationSkill
from backend.app.db.job_skill import JobSkill
from backend.app.db.skill import Skill


TABLES = (
    "companies", "users", "revoked_access_tokens", "employees",
    "user_company_roles", "skills", "esco_occupations",
    "esco_occupation_skills", "job_skills", "company_esco_occupation_mappings",
)


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "company-esco-tests-secret-key-123456")
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    tables = [Base.metadata.tables[name] for name in TABLES]
    Base.metadata.create_all(engine, tables=tables)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions() as db:
        db.add_all([
            Company(company_id=1, company_name="One"),
            Company(company_id=2, company_name="Two"),
            User(user_id=1, full_name="Manager One", email="one@example.test",
                 password_hash="unused", is_active=True),
            User(user_id=2, full_name="Manager Two", email="two@example.test",
                 password_hash="unused", is_active=True),
            User(user_id=3, full_name="Director", email="director@example.test",
                 password_hash="unused", is_active=True),
        ])
        for employee_id, company_id, title in (
            (1, 1, "Engineer"), (2, 1, " engineer "),
            (3, 2, "Private Role"), (4, 2, "Engineer"),
        ):
            db.add(Employee(
                id=employee_id, company_id=company_id,
                employee_id=f"E{employee_id}", full_name=f"Employee {employee_id}",
                email=f"e{employee_id}@example.test", job_title=title,
                department="Team", employment_status="Active",
                hire_date=date(2020, 1, 1), job_level="Staff",
                employment_type="Full-time", is_active=True,
            ))
        db.add_all([
            UserCompanyRole(membership_id=1, user_id=1, company_id=1,
                            role="Training Manager", is_active=True),
            UserCompanyRole(membership_id=2, user_id=2, company_id=2,
                            role="Training Manager", is_active=True),
            UserCompanyRole(membership_id=3, user_id=3, company_id=1,
                            role="Director", is_active=True),
            ESCOOccupation(id=1, esco_concept_uri="https://example.test/occupation/1",
                           preferred_label="Developer"),
            ESCOOccupation(id=2, esco_concept_uri="https://example.test/occupation/2",
                           preferred_label="Other"),
            Skill(skill_id=1, skill_name="Design"),
            Skill(skill_id=2, skill_name="Testing"),
            Skill(skill_id=3, skill_name="Unrelated"),
        ])
        db.flush()
        db.add_all([
            ESCOOccupationSkill(occupation_id=1, skill_id=1, relation_type="essential"),
            ESCOOccupationSkill(occupation_id=1, skill_id=2, relation_type="optional"),
            ESCOOccupationSkill(occupation_id=2, skill_id=3, relation_type="essential"),
            JobSkill(company_id=1, job_title="ENGINEER", skill_id=1,
                     required_proficiency=5, importance="High",
                     approval_status="Approved"),
        ])
        db.commit()
    app = FastAPI()
    app.include_router(router, dependencies=[Depends(authorize_business_request)])
    app.include_router(
        job_skills_router, dependencies=[Depends(authorize_business_request)]
    )

    def override_db():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as client:
        yield client, sessions
    engine.dispose()


def headers(user_id: int, company_id: int = 1):
    return {
        "Authorization": f"Bearer {create_access_token(user_id)}",
        "X-Company-ID": str(company_id),
    }


def test_titles_auth_and_company_isolation(env):
    client, _ = env
    assert client.get("/company-esco-mappings/titles").status_code == 401
    assert client.get("/company-esco-mappings/titles", headers=headers(3)).status_code == 403
    response = client.get("/company-esco-mappings/titles", headers=headers(1))
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0].strip().lower() == "engineer"
    assert client.get(
        "/company-esco-mappings/titles", headers=headers(1, 2)
    ).status_code == 403
    assert client.put(
        "/company-esco-mappings/mapping", headers=headers(1),
        json={"job_title": "Private Role", "occupation_id": 1},
    ).status_code == 404
    assert client.put(
        "/company-esco-mappings/mapping", headers=headers(1),
        json={"job_title": "Engineer", "occupation_id": 1, "company_id": 2},
    ).status_code == 422


def test_mapping_persists_per_company_and_requires_valid_occupation(env):
    client, _ = env
    path = "/company-esco-mappings/mapping"
    assert client.put(path, headers=headers(1), json={
        "job_title": "Engineer", "occupation_id": 999
    }).status_code == 404
    assert client.put(path, headers=headers(1), json={
        "job_title": "Engineer", "occupation_id": 1
    }).status_code == 200
    assert client.get(path, headers=headers(1), params={
        "job_title": "ENGINEER"
    }).json()["occupation_id"] == 1
    assert client.get(path, headers=headers(2, 2), params={
        "job_title": "Private Role"
    }).json()["occupation_id"] is None
    assert client.get(path, headers=headers(2, 2), params={
        "job_title": "Engineer"
    }).json()["occupation_id"] is None
    assert client.put(path, headers=headers(2, 2), json={
        "job_title": "Engineer", "occupation_id": 2
    }).status_code == 200
    assert client.get(path, headers=headers(1), params={
        "job_title": "Engineer"
    }).json()["occupation_id"] == 1
    assert client.put(path, headers=headers(1), json={
        "job_title": "engineer", "occupation_id": 2
    }).status_code == 200
    assert client.get(path, headers=headers(1), params={
        "job_title": "Engineer"
    }).json()["occupation_id"] == 2


def test_review_creates_only_selected_pending_and_preserves_existing(env):
    client, sessions = env
    client.put("/company-esco-mappings/mapping", headers=headers(1), json={
        "job_title": "Engineer", "occupation_id": 1
    })
    payload = {
        "job_title": "Engineer", "occupation_id": 1,
        "skills": [
            {"skill_id": 1, "required_proficiency": 2, "importance": "Low"},
            {"skill_id": 2, "required_proficiency": 4, "importance": "Critical"},
        ],
    }
    response = client.post(
        "/company-esco-mappings/requirements", headers=headers(1), json=payload
    )
    assert response.status_code == 201
    assert response.json() == {"created": 1, "already_existing": 1}
    repeat = client.post(
        "/company-esco-mappings/requirements", headers=headers(1), json=payload
    )
    assert repeat.json() == {"created": 0, "already_existing": 2}
    with sessions() as db:
        rows = db.query(JobSkill).order_by(JobSkill.skill_id).all()
        assert len(rows) == 2
        assert (rows[0].approval_status, rows[0].required_proficiency) == ("Approved", 5)
        assert (rows[1].approval_status, rows[1].required_proficiency,
                rows[1].importance) == ("Pending", 4, "Critical")
        assert db.query(CompanyESCOOccupationMapping).count() == 1


def test_invalid_or_stale_review_creates_nothing(env):
    client, sessions = env
    client.put("/company-esco-mappings/mapping", headers=headers(1), json={
        "job_title": "Engineer", "occupation_id": 1
    })
    base = {"job_title": "Engineer", "occupation_id": 1}
    skill = {"skill_id": 2, "required_proficiency": 3, "importance": "Medium"}
    for payload, expected in (
        ({**base, "occupation_id": 2, "skills": [skill]}, 409),
        ({**base, "skills": [skill, skill]}, 422),
        ({**base, "skills": [skill, {**skill, "skill_id": 3}]}, 422),
        ({**base, "skills": [{**skill, "required_proficiency": 6}]}, 422),
        ({**base, "skills": []}, 422),
    ):
        response = client.post(
            "/company-esco-mappings/requirements", headers=headers(1), json=payload
        )
        assert response.status_code == expected
    with sessions() as db:
        assert db.query(JobSkill).count() == 1


def test_insertion_failure_rolls_back_all_requirements(env, monkeypatch):
    client, sessions = env
    client.put("/company-esco-mappings/mapping", headers=headers(1), json={
        "job_title": "Engineer", "occupation_id": 1
    })

    def fail_commit(db):
        db.flush()
        raise IntegrityError("insert", {}, RuntimeError("test failure"))

    monkeypatch.setattr(Session, "commit", fail_commit)
    response = client.post(
        "/company-esco-mappings/requirements", headers=headers(1),
        json={
            "job_title": "Engineer", "occupation_id": 1,
            "skills": [{"skill_id": 2, "required_proficiency": 3, "importance": "Medium"}],
        },
    )
    assert response.status_code == 409
    with sessions() as db:
        assert db.query(JobSkill).count() == 1


def test_manual_creation_rejects_normalized_existing_title(env):
    client, _ = env
    response = client.post(
        "/job-skills/?company_id=1", headers=headers(1),
        json={
            "job_title": "  Engineer  ", "skill_id": 1,
            "required_proficiency": 3, "importance": "Medium",
        },
    )
    assert response.status_code == 409


def test_mapping_migration_upgrades_and_downgrades_in_isolated_database():
    migration = import_module(
        "backend.migrations.versions.71eab962f143_add_company_esco_occupation_mapping"
    )
    engine = create_engine("sqlite://")
    tables = [
        Base.metadata.tables["companies"],
        Base.metadata.tables["esco_occupations"],
    ]
    Base.metadata.create_all(engine, tables=tables)
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            migration.upgrade()
            assert "company_esco_occupation_mappings" in inspect(connection).get_table_names()
            migration.downgrade()
            assert "company_esco_occupation_mappings" not in inspect(connection).get_table_names()
    engine.dispose()
