from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import backend.app.db.models
import jwt
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.api.auth import router as auth_router
from backend.app.api.dependencies import (
    ACCESS_TOKEN_COOKIE,
    CSRF_COOKIE,
    authorize_business_request,
    get_db,
)
from backend.app.api.course_sessions import router as course_sessions_router
from backend.app.api.courses import router as courses_router
from backend.app.api.employee_imports import router as employee_imports_router
from backend.app.api.employees import router as employees_router
from backend.app.api.enrollment_assessments import (
    router as enrollment_assessments_router,
)
from backend.app.api.enrollments import router as enrollments_router
from backend.app.api.job_skills import router as job_skills_router
from backend.app.api.plan_courses import router as plan_courses_router
from backend.app.api.session_attendance import (
    router as session_attendance_router,
)
from backend.app.api.session_feedback import router as session_feedback_router
from backend.app.api.skills import router as skills_router
from backend.app.api.skill_assessments import router as skill_assessments_router
from backend.app.api.training_plans import router as training_plans_router
from backend.app.core.security import (
    JWT_ALGORITHM,
    create_access_token,
    get_secret_key,
)
from backend.app.db.auth_models import User, UserCompanyRole
from backend.app.db.base import Base
from backend.app.db.company import Company
from backend.app.db.course import Course
from backend.app.db.course_session import CourseSession
from backend.app.db.employee import Employee
from backend.app.db.enrollment import Enrollment
from backend.app.db.enrollment_assessment import EnrollmentAssessment
from backend.app.db.import_batch import ImportBatch
from backend.app.db.import_row_issue import ImportRowIssue
from backend.app.db.job_skill import JobSkill
from backend.app.db.plan_course import PlanCourse
from backend.app.db.revoked_access_token import RevokedAccessToken
from backend.app.db.session_attendance import SessionAttendance
from backend.app.db.session_feedback import SessionFeedback
from backend.app.db.skill import Skill
from backend.app.db.skill_assessment import SkillAssessment
from backend.app.db.training_plan import TrainingPlan
from backend.app.services.tna_service import analyze_company_tna
from backend.app.services.token_revocation import (
    cleanup_expired_access_tokens,
)
from backend.scripts.reconcile_manager_links import (
    reconcile_company_manager_links,
)


TABLE_NAMES = (
    "companies",
    "users",
    "revoked_access_tokens",
    "employees",
    "user_company_roles",
    "skills",
    "skill_assessments",
    "job_skills",
    "courses",
    "course_sessions",
    "enrollments",
    "enrollment_assessments",
    "session_attendance",
    "session_feedback",
    "import_batches",
    "import_row_issues",
    "training_plans",
    "plan_courses",
)


def _employee(
    employee_id: int,
    company_id: int,
    employee_code: str,
    *,
    manager_internal_id: int | None = None,
) -> Employee:
    return Employee(
        id=employee_id,
        company_id=company_id,
        employee_id=employee_code,
        full_name=f"Employee {employee_code}",
        email=f"{employee_code.lower()}@example.com",
        job_title="Engineer",
        department="Engineering",
        manager_id=None,
        manager_internal_id=manager_internal_id,
        employment_status="Active",
        hire_date=date(2020, 1, 1),
        job_level="Individual Contributor",
        employment_type="Full-time",
        is_active=True,
    )


@pytest.fixture
def authorization_env(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "authorization-tests-secret-key-123456")

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    tables = [Base.metadata.tables[name] for name in TABLE_NAMES]
    Base.metadata.create_all(engine, tables=tables)
    test_session = sessionmaker(bind=engine, expire_on_commit=False)

    with test_session() as db:
        db.add_all([
            Company(company_id=1, company_name="Company One"),
            Company(company_id=2, company_name="Company Two"),
        ])
        employees = [
            _employee(10, 1, "TM"),
            _employee(11, 1, "MGR"),
            _employee(12, 1, "REPORT", manager_internal_id=11),
            _employee(13, 1, "OTHER"),
            _employee(14, 1, "DIR"),
            _employee(21, 2, "FOREIGN"),
        ]
        employees[3].job_title = "Executive"
        db.add_all(employees)
        db.add_all([
            User(
                user_id=1,
                full_name="Training Manager",
                email="tm@example.test",
                password_hash="not-used",
                is_active=True,
            ),
            User(
                user_id=2,
                full_name="Director",
                email="director@example.test",
                password_hash="not-used",
                is_active=True,
            ),
            User(
                user_id=3,
                full_name="Manager",
                email="manager@example.test",
                password_hash="not-used",
                is_active=True,
            ),
            User(
                user_id=4,
                full_name="Employee",
                email="employee@example.test",
                password_hash="not-used",
                is_active=True,
            ),
            User(
                user_id=5,
                full_name="Foreign User",
                email="foreign@example.test",
                password_hash="not-used",
                is_active=True,
            ),
        ])
        db.add_all([
            UserCompanyRole(
                membership_id=1, user_id=1, company_id=1,
                employee_id=10, role="Training Manager", is_active=True,
            ),
            UserCompanyRole(
                membership_id=2, user_id=2, company_id=1,
                employee_id=14, role="Director", is_active=True,
            ),
            UserCompanyRole(
                membership_id=3, user_id=3, company_id=1,
                employee_id=11, role="Manager", is_active=True,
            ),
            UserCompanyRole(
                membership_id=4, user_id=4, company_id=1,
                employee_id=12, role="Employee", is_active=True,
            ),
            UserCompanyRole(
                membership_id=5, user_id=5, company_id=2,
                employee_id=21, role="Employee", is_active=True,
            ),
        ])
        db.add(Skill(skill_id=1, skill_name="Python"))
        db.add_all([
            JobSkill(
                id=1, company_id=1, job_title="Engineer", skill_id=1,
                required_proficiency=3, importance="Medium",
                approval_status="Pending", approved_by=14,
                approved_by_user_id=2,
            ),
            JobSkill(
                id=2, company_id=1, job_title="Executive", skill_id=1,
                required_proficiency=3, importance="Medium",
                approval_status="Pending",
            ),
            SkillAssessment(
                assessment_id=1,
                company_id=1,
                employee_id=12,
                skill_id=1,
                proficiency_level=2,
                assessment_source="Manager Assessment",
                evidence_quality="Medium",
                assessment_date=date.today(),
                evidence_status="Pending Review",
            ),
            Course(
                id=1, company_id=1, course_id="C1", course_title="Course One",
                course_category="Technical", course_duration_hours=2,
                delivery_mode="Online", is_active=True,
                has_assessment=False, provides_certificate=False,
                assessment_type="None",
            ),
            Course(
                id=2, company_id=2, course_id="C2", course_title="Course Two",
                course_category="Technical", course_duration_hours=2,
                delivery_mode="Online", is_active=True,
                has_assessment=False, provides_certificate=False,
                assessment_type="None",
            ),
            CourseSession(
                session_id=1,
                company_id=1,
                course_id=1,
                start_datetime=datetime(2030, 1, 1, 10),
                end_datetime=datetime(2030, 1, 1, 12),
                registration_deadline=datetime(2029, 12, 31, 10),
                session_status="Scheduled",
                location_type="Online",
            ),
            CourseSession(
                session_id=2,
                company_id=1,
                course_id=1,
                start_datetime=datetime(2030, 2, 1, 10),
                end_datetime=datetime(2030, 2, 1, 12),
                registration_deadline=datetime(2030, 1, 31, 10),
                session_status="Scheduled",
                location_type="Online",
            ),
            CourseSession(
                session_id=3,
                company_id=1,
                course_id=1,
                start_datetime=datetime(2030, 3, 1, 10),
                end_datetime=datetime(2030, 3, 1, 12),
                registration_deadline=datetime(2030, 2, 28, 10),
                session_status="Scheduled",
                location_type="Online",
            ),
            CourseSession(
                session_id=4,
                company_id=1,
                course_id=1,
                start_datetime=datetime(2030, 4, 1, 10),
                end_datetime=datetime(2030, 4, 1, 12),
                registration_deadline=datetime(2030, 3, 31, 10),
                session_status="Completed",
                location_type="Online",
            ),
            CourseSession(
                session_id=5,
                company_id=1,
                course_id=1,
                start_datetime=datetime(2030, 5, 1, 10),
                end_datetime=datetime(2030, 5, 1, 12),
                registration_deadline=datetime(2030, 4, 30, 10),
                session_status="Completed",
                location_type="Online",
            ),
            CourseSession(
                session_id=6,
                company_id=2,
                course_id=2,
                start_datetime=datetime(2030, 6, 1, 10),
                end_datetime=datetime(2030, 6, 1, 12),
                registration_deadline=datetime(2030, 5, 31, 10),
                session_status="Completed",
                location_type="Online",
            ),
            CourseSession(
                session_id=7,
                company_id=1,
                course_id=1,
                start_datetime=datetime(2030, 7, 1, 10),
                end_datetime=datetime(2030, 7, 1, 12),
                registration_deadline=datetime(2030, 6, 30, 10),
                session_status="Completed",
                location_type="Online",
            ),
            Enrollment(
                enrollment_id=1, company_id=1, employee_id=12, course_id=1,
                session_id=1, status="In Progress",
                approval_status="Approved", progress_percentage=25,
            ),
            Enrollment(
                enrollment_id=2, company_id=1, employee_id=12, course_id=1,
                session_id=2, status="Pending Approval",
                approval_status="Pending", progress_percentage=0,
            ),
            Enrollment(
                enrollment_id=3, company_id=1, employee_id=12, course_id=1,
                session_id=3, status="Withdrawn",
                approval_status="Rejected", progress_percentage=0,
            ),
            Enrollment(
                enrollment_id=4, company_id=1, employee_id=12, course_id=1,
                session_id=4, status="Completed",
                approval_status="Approved", progress_percentage=100,
            ),
            Enrollment(
                enrollment_id=5, company_id=1, employee_id=13, course_id=1,
                session_id=5, status="Completed",
                approval_status="Approved", progress_percentage=100,
            ),
            Enrollment(
                enrollment_id=6, company_id=2, employee_id=21, course_id=2,
                session_id=6, status="Completed",
                approval_status="Approved", progress_percentage=100,
            ),
            Enrollment(
                enrollment_id=7, company_id=1, employee_id=12, course_id=1,
                session_id=7, status="Completed",
                approval_status="Approved", progress_percentage=100,
            ),
            EnrollmentAssessment(
                assessment_id=1, company_id=1, enrollment_id=1,
                attempt_number=1, assessment_score=85,
                assessment_result="Passed",
            ),
            EnrollmentAssessment(
                assessment_id=2, company_id=2, enrollment_id=6,
                attempt_number=1, assessment_score=90,
                assessment_result="Passed",
            ),
            SessionAttendance(
                attendance_id=1, company_id=1, session_id=1,
                employee_id=12, attendance_status="Pending",
            ),
            SessionAttendance(
                attendance_id=2, company_id=1, session_id=5,
                employee_id=13, attendance_status="Present",
            ),
            SessionAttendance(
                attendance_id=3, company_id=2, session_id=6,
                employee_id=21, attendance_status="Present",
            ),
            SessionFeedback(
                feedback_id=1, company_id=1, session_id=4,
                employee_id=12, training_rating=5,
                trainer_rating=5, content_relevance_rating=4,
            ),
            SessionFeedback(
                feedback_id=2, company_id=1, session_id=5,
                employee_id=13, training_rating=4,
                trainer_rating=4, content_relevance_rating=4,
            ),
            SessionFeedback(
                feedback_id=3, company_id=2, session_id=6,
                employee_id=21, training_rating=5,
                trainer_rating=5, content_relevance_rating=5,
            ),
            ImportBatch(
                id=1, company_id=1, created_by_user_id=1,
                source_type="CSV", entity_type="employee",
                file_name="employees.csv", status="Completed",
                total_rows=1, successful_rows=0, failed_rows=1,
            ),
            ImportBatch(
                id=2, company_id=2, created_by_user_id=5,
                source_type="CSV", entity_type="employee",
                file_name="foreign.csv", status="Completed",
                total_rows=1, successful_rows=1, failed_rows=0,
            ),
            ImportBatch(
                id=3, company_id=1, created_by_user_id=1,
                source_type="CSV", entity_type="employee",
                file_name="empty-issues.csv", status="Completed",
                total_rows=1, successful_rows=1, failed_rows=0,
            ),
            ImportRowIssue(
                id=1, batch_id=1, row_number=2, field_name="email",
                issue_type="invalid_email", message="Invalid email",
                raw_value="invalid",
            ),
            ImportRowIssue(
                id=2, batch_id=2, row_number=2, field_name="email",
                issue_type="invalid_email", message="Invalid email",
                raw_value="foreign-invalid",
            ),
            TrainingPlan(
                plan_id=1, company_id=1, employee_id=12,
                plan_status="Draft", approval_status="Pending",
            ),
            TrainingPlan(
                plan_id=2, company_id=1, employee_id=13,
                plan_status="Draft", approval_status="Pending",
            ),
            TrainingPlan(
                plan_id=3, company_id=2, employee_id=21,
                plan_status="Draft", approval_status="Pending",
            ),
            TrainingPlan(
                plan_id=4, company_id=1, employee_id=12,
                plan_status="Approved", approval_status="Approved",
            ),
            PlanCourse(
                plan_course_id=1, plan_id=1, course_id=1,
                sequence_order=1, priority="Medium",
            ),
            PlanCourse(
                plan_course_id=2, plan_id=2, course_id=1,
                sequence_order=1, priority="Medium",
            ),
            PlanCourse(
                plan_course_id=3, plan_id=3, course_id=2,
                sequence_order=1, priority="Medium",
            ),
        ])
        db.commit()

    app = FastAPI()
    guard = [Depends(authorize_business_request)]
    app.include_router(auth_router)
    app.include_router(employees_router, dependencies=guard)
    app.include_router(courses_router, dependencies=guard)
    app.include_router(employee_imports_router, dependencies=guard)
    app.include_router(enrollments_router, dependencies=guard)
    app.include_router(enrollment_assessments_router, dependencies=guard)
    app.include_router(session_attendance_router, dependencies=guard)
    app.include_router(session_feedback_router, dependencies=guard)
    app.include_router(skills_router, dependencies=guard)
    app.include_router(job_skills_router, dependencies=guard)
    app.include_router(skill_assessments_router, dependencies=guard)
    app.include_router(course_sessions_router, dependencies=guard)
    app.include_router(training_plans_router, dependencies=guard)
    app.include_router(plan_courses_router, dependencies=guard)

    def override_get_db():
        with test_session() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db

    try:
        yield TestClient(app), test_session
    finally:
        Base.metadata.drop_all(engine, tables=list(reversed(tables)))
        engine.dispose()


def _headers(user_id: int, company_id: int = 1) -> dict[str, str]:
    return _token_headers(create_access_token(user_id), company_id)


def _token_headers(token: str, company_id: int = 1) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "X-Company-ID": str(company_id),
    }


@pytest.mark.parametrize(
    ("role_user_id", "allowed_ids"),
    [
        (1, {10, 11, 12, 13, 14}),
        (2, {10, 11, 12, 13, 14}),
        (3, {12}),
        (4, {12}),
    ],
)
def test_employee_listing_is_limited_by_role(authorization_env, role_user_id, allowed_ids):
    client, _ = authorization_env

    response = client.get(
        "/employees/?company_id=1",
        headers=_headers(role_user_id),
    )

    assert response.status_code == 200
    assert {employee["id"] for employee in response.json()} == allowed_ids


def test_business_endpoint_requires_authentication(authorization_env):
    client, _ = authorization_env

    response = client.get("/employees/?company_id=1")

    assert response.status_code == 401


@pytest.mark.parametrize("role_user_id", [2, 3, 4])
def test_odoo_configuration_is_training_manager_only(
    authorization_env,
    role_user_id,
):
    client, _ = authorization_env
    response = client.get(
        "/employee-imports/odoo/status",
        headers=_headers(role_user_id),
    )
    assert response.status_code == 403


def test_logout_revokes_only_the_current_access_token(authorization_env):
    client, _ = authorization_env
    revoked_session = create_access_token(1)
    active_session = create_access_token(1)
    before_logout = client.get(
        "/employees/?company_id=1",
        headers=_token_headers(revoked_session),
    )

    logout = client.post(
        "/auth/logout",
        headers={"Authorization": f"Bearer {revoked_session}"},
    )
    revoked_request = client.get(
        "/employees/?company_id=1",
        headers=_token_headers(revoked_session),
    )
    active_session_request = client.get(
        "/employees/?company_id=1",
        headers=_token_headers(active_session),
    )

    assert before_logout.status_code == 200
    assert logout.status_code == 200
    assert revoked_request.status_code == 401
    assert active_session_request.status_code == 200


def test_logout_without_authentication_returns_unauthorized(authorization_env):
    client, _ = authorization_env

    response = client.post("/auth/logout")

    assert response.status_code == 401


def test_cookie_logout_preserves_csrf_and_origin_checks(
    authorization_env,
    monkeypatch,
):
    client, _ = authorization_env
    monkeypatch.setenv("FRONTEND_ORIGINS", "https://app.example.test")
    client.cookies.set(ACCESS_TOKEN_COOKIE, create_access_token(1))
    client.cookies.set(CSRF_COOKIE, "logout-csrf")

    missing_csrf = client.post(
        "/auth/logout",
        headers={"Origin": "https://app.example.test"},
    )
    untrusted_origin = client.post(
        "/auth/logout",
        headers={
            "Origin": "https://untrusted.example.test",
            "X-CSRF-Token": "logout-csrf",
        },
    )
    valid_request = client.post(
        "/auth/logout",
        headers={
            "Origin": "https://app.example.test",
            "X-CSRF-Token": "logout-csrf",
        },
    )

    assert missing_csrf.status_code == 403
    assert untrusted_origin.status_code == 403
    assert valid_request.status_code == 200


def test_expired_and_legacy_access_tokens_are_rejected(authorization_env):
    client, _ = authorization_env
    expired_token = jwt.encode(
        {
            "sub": "1",
            "jti": str(uuid4()),
            "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
        },
        get_secret_key(),
        algorithm=JWT_ALGORITHM,
    )
    token_without_jti = jwt.encode(
        {
            "sub": "1",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        get_secret_key(),
        algorithm=JWT_ALGORITHM,
    )

    expired_response = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    legacy_response = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token_without_jti}"},
    )

    assert expired_response.status_code == 401
    assert legacy_response.status_code == 401


def test_expired_revocation_records_can_be_cleaned(authorization_env):
    _, test_session = authorization_env
    cleanup_time = datetime(2030, 1, 1, tzinfo=timezone.utc)
    with test_session() as db:
        db.add_all([
            RevokedAccessToken(
                jti=str(uuid4()),
                expires_at=cleanup_time - timedelta(seconds=1),
            ),
            RevokedAccessToken(
                jti=str(uuid4()),
                expires_at=cleanup_time + timedelta(seconds=1),
            ),
        ])
        db.commit()

        deleted_count = cleanup_expired_access_tokens(
            db,
            now=cleanup_time,
        )
        db.commit()
        remaining_count = db.query(RevokedAccessToken).count()

    assert deleted_count == 1
    assert remaining_count == 1


def test_cookie_mutations_require_csrf_and_trusted_origin(
    authorization_env,
    monkeypatch,
):
    client, _ = authorization_env
    monkeypatch.setenv("FRONTEND_ORIGINS", "https://app.example.test")
    client.cookies.set("tf_access_token", create_access_token(1))
    client.cookies.set("tf_csrf_token", "csrf-value")
    endpoint = "/training-plans/?company_id=1"
    payload = {"employee_id": 12}

    missing_header = client.post(
        endpoint,
        json=payload,
        headers={"Origin": "https://app.example.test"},
    )
    untrusted_origin = client.post(
        endpoint,
        json=payload,
        headers={
            "Origin": "https://untrusted.example.test",
            "X-CSRF-Token": "csrf-value",
        },
    )
    trusted_request = client.post(
        endpoint,
        json=payload,
        headers={
            "Origin": "https://app.example.test",
            "X-CSRF-Token": "csrf-value",
        },
    )

    assert missing_header.status_code == 403
    assert untrusted_origin.status_code == 403
    assert trusted_request.status_code == 201


def test_production_cookie_mutations_fail_closed_without_origins(
    authorization_env,
    monkeypatch,
):
    client, _ = authorization_env
    monkeypatch.setenv("NODE_ENV", "production")
    monkeypatch.delenv("FRONTEND_ORIGINS", raising=False)
    client.cookies.set("tf_access_token", create_access_token(1))
    client.cookies.set("tf_csrf_token", "csrf-value")

    response = client.post(
        "/training-plans/?company_id=1",
        json={"employee_id": 12},
        headers={
            "Origin": "https://app.example.test",
            "X-CSRF-Token": "csrf-value",
        },
    )

    assert response.status_code == 500


def test_inactive_user_is_rejected(authorization_env):
    client, test_session = authorization_env
    with test_session() as db:
        db.query(User).filter(User.user_id == 3).update({"is_active": False})
        db.commit()

    response = client.get("/employees/?company_id=1", headers=_headers(3))

    assert response.status_code == 401


def test_inactive_membership_is_rejected(authorization_env):
    client, test_session = authorization_env
    with test_session() as db:
        db.query(UserCompanyRole).filter(
            UserCompanyRole.membership_id == 3
        ).update({"is_active": False})
        db.commit()

    response = client.get("/employees/?company_id=1", headers=_headers(3))

    assert response.status_code == 403


def test_client_cannot_select_an_unmatched_company(authorization_env):
    client, _ = authorization_env

    response = client.get(
        "/employees/?company_id=2",
        headers=_headers(3, company_id=2),
    )

    assert response.status_code == 403


def test_manager_and_employee_cannot_read_other_employee_profiles(authorization_env):
    client, _ = authorization_env

    unrelated_for_manager = client.get(
        "/employees/13?company_id=1",
        headers=_headers(3),
    )
    own_for_manager = client.get(
        "/employees/11?company_id=1",
        headers=_headers(3),
    )
    manager_employees = client.get(
        "/employees/?company_id=1",
        headers=_headers(3),
    )
    other_for_employee = client.get(
        "/employees/11?company_id=1",
        headers=_headers(4),
    )
    own_for_employee = client.get(
        "/employees/12?company_id=1",
        headers=_headers(4),
    )

    assert unrelated_for_manager.status_code == 404
    assert own_for_manager.status_code == 404
    assert [row["employee_id"] for row in manager_employees.json()] == [
        "REPORT"
    ]
    assert other_for_employee.status_code == 404
    assert own_for_employee.status_code == 200


def test_training_plan_role_operations_and_manager_scope(authorization_env):
    client, test_session = authorization_env

    manager_report = client.post(
        "/training-plans/?company_id=1",
        json={"employee_id": 12},
        headers=_headers(3),
    )
    manager_unrelated = client.post(
        "/training-plans/?company_id=1",
        json={"employee_id": 13},
        headers=_headers(3),
    )
    employee_cannot_create = client.post(
        "/training-plans/?company_id=1",
        json={"employee_id": 12},
        headers=_headers(4),
    )
    director_cannot_create = client.post(
        "/training-plans/?company_id=1",
        json={"employee_id": 12},
        headers=_headers(2),
    )

    assert manager_report.status_code == 201
    assert manager_unrelated.status_code == 404
    assert employee_cannot_create.status_code == 403
    assert director_cannot_create.status_code == 403

    with test_session() as db:
        created = db.query(TrainingPlan).filter(
            TrainingPlan.plan_id == manager_report.json()["plan_id"]
        ).one()
        assert created.created_by_user_id == 3
        assert created.created_by == 11


def test_employee_cannot_complete_enrollment_but_can_report_progress(
    authorization_env,
):
    client, test_session = authorization_env

    progress = client.patch(
        "/enrollments/1/progress?company_id=1",
        json={"progress_percentage": 60},
        headers=_headers(4),
    )
    employee_completion = client.patch(
        "/enrollments/1/complete?company_id=1",
        headers=_headers(4),
    )
    manager_completion = client.patch(
        "/enrollments/1/complete?company_id=1&status_updated_by_user_id=1",
        headers=_headers(3),
    )

    assert progress.status_code == 200
    assert progress.json()["progress_percentage"] == 60
    assert employee_completion.status_code == 403
    assert manager_completion.status_code == 200
    assert manager_completion.json()["status"] == "Completed"

    with test_session() as db:
        enrollment = db.query(Enrollment).filter(
            Enrollment.enrollment_id == 1
        ).one()
        assert enrollment.status_updated_by_user_id == 3


def test_employee_and_manager_cannot_read_unowned_plan_or_child(authorization_env):
    client, _ = authorization_env

    manager_plan = client.get(
        "/training-plans/2?company_id=1",
        headers=_headers(3),
    )
    employee_plan = client.get(
        "/training-plans/1?company_id=1",
        headers=_headers(4),
    )
    unrelated_nested = client.get(
        "/plan-courses/?company_id=1&plan_id=2",
        headers=_headers(3),
    )
    foreign_nested = client.get(
        "/plan-courses/3?company_id=1",
        headers=_headers(1),
    )

    assert manager_plan.status_code == 404
    assert employee_plan.status_code == 200
    assert unrelated_nested.status_code == 404
    assert foreign_nested.status_code == 404


def test_approval_actor_comes_from_authenticated_identity(authorization_env):
    client, test_session = authorization_env

    response = client.put(
        "/training-plans/1/approval?company_id=1&approved_by=11",
        json={
            "approval_status": "Approved",
            "approval_comments": "Reviewed",
            "approved_by": 11,
        },
        headers=_headers(2),
    )

    assert response.status_code == 200
    with test_session() as db:
        approved_plan = db.query(TrainingPlan).filter(
            TrainingPlan.plan_id == 1
        ).one()
        assert approved_plan.approved_by == 14
        assert approved_plan.approved_by_user_id == 2


def test_plan_and_session_status_actors_come_from_authenticated_identity(
    authorization_env,
):
    client, test_session = authorization_env

    activated_plan = client.patch(
        "/training-plans/4/activate?company_id=1&status_updated_by=11",
        headers=_headers(1),
    )
    updated_session = client.patch(
        "/course-sessions/1/status?company_id=1&status_updated_by=11",
        json={"session_status": "In Progress", "status_updated_by": 11},
        headers=_headers(1),
    )

    assert activated_plan.status_code == 200
    assert activated_plan.json()["status_updated_by"] == 10
    assert activated_plan.json()["status_updated_by_user_id"] == 1
    assert updated_session.status_code == 200
    assert updated_session.json()["status_updated_by"] == 10
    assert updated_session.json()["status_updated_by_user_id"] == 1

    with test_session() as db:
        assert db.query(TrainingPlan).filter(
            TrainingPlan.plan_id == 4
        ).one().status_updated_by_user_id == 1
        assert db.query(CourseSession).filter(
            CourseSession.session_id == 1
        ).one().status_updated_by_user_id == 1


def test_assessment_creator_and_reviewer_are_authenticated_actors(authorization_env):
    client, test_session = authorization_env

    created = client.post(
        "/skill-assessments/?company_id=1&assessed_by=10&assessed_by_user_id=1",
        json={
            "employee_id": 12,
            "skill_id": 1,
            "proficiency_level": 3,
            "assessment_source": "Manager Assessment",
            "evidence_quality": "High",
            "evidence_title": "Team assessment",
            "assessment_date": date.today().isoformat(),
            "assessed_by": 10,
            "assessed_by_user_id": 1,
        },
        headers=_headers(3),
    )
    reviewed = client.put(
        "/skill-assessments/1/review?company_id=1&approved_by=10",
        json={"evidence_status": "Approved", "approved_by": 10},
        headers=_headers(3),
    )

    assert created.status_code == 201
    assert created.json()["assessed_by"] == 11
    assert created.json()["assessed_by_user_id"] == 3
    assert reviewed.status_code == 200
    assert reviewed.json()["reviewed_by"] == 11
    assert reviewed.json()["reviewed_by_user_id"] == 3

    with test_session() as db:
        assessment = db.query(SkillAssessment).filter(
            SkillAssessment.assessment_id == 1
        ).one()
        assert assessment.reviewed_by_user_id == 3


def test_employee_assessments_are_limited_to_self_assessment_source(
    authorization_env,
):
    client, _ = authorization_env
    payload = {
        "employee_id": 12,
        "skill_id": 1,
        "proficiency_level": 3,
        "assessment_source": "Manager Assessment",
        "evidence_quality": "High",
        "evidence_title": "Employee-submitted evidence",
        "assessment_date": date.today().isoformat(),
    }

    mislabeled = client.post(
        "/skill-assessments/?company_id=1",
        json=payload,
        headers=_headers(4),
    )
    payload["assessment_source"] = "Self-Assessment"
    self_assessment = client.post(
        "/skill-assessments/?company_id=1",
        json=payload,
        headers=_headers(4),
    )

    assert mislabeled.status_code == 422
    assert self_assessment.status_code == 201
    assert self_assessment.json()["assessment_source"] == "Self-Assessment"
    assert self_assessment.json()["evidence_status"] == "Pending Review"


def test_editing_assessment_evidence_clears_stale_review_attribution(
    authorization_env,
):
    client, test_session = authorization_env
    with test_session() as db:
        db.query(SkillAssessment).filter(
            SkillAssessment.assessment_id == 1
        ).update({
            "evidence_status": "Approved",
            "reviewed_by": 14,
            "reviewed_by_user_id": 2,
        })
        db.commit()

    response = client.put(
        "/skill-assessments/1?company_id=1",
        json={"assessor_comments": "Updated evidence"},
        headers=_headers(3),
    )

    assert response.status_code == 200
    assert response.json()["evidence_status"] == "Pending Review"
    assert response.json()["reviewed_by"] is None
    assert response.json()["reviewed_by_user_id"] is None


def test_job_skill_reset_clears_employee_and_user_approvers(authorization_env):
    client, test_session = authorization_env
    with test_session() as db:
        db.query(JobSkill).filter(JobSkill.id == 1).update({
            "approval_status": "Approved",
            "approved_by": 14,
            "approved_by_user_id": 2,
        })
        db.commit()

    response = client.put(
        "/job-skills/1?company_id=1",
        json={"required_proficiency": 4},
        headers=_headers(1),
    )

    assert response.status_code == 200
    with test_session() as db:
        requirement = db.query(JobSkill).filter(JobSkill.id == 1).one()
        assert requirement.approval_status == "Pending"
        assert requirement.approved_by is None
        assert requirement.approved_by_user_id is None


def test_training_plan_review_uses_authenticated_reviewer(
    authorization_env,
):
    client, test_session = authorization_env

    response = client.put(
        "/training-plans/1/review?company_id=1&reviewed_by_user_id=1",
        json={
            "plan_review_notes": "Manager review",
            "reviewed_by_user_id": 1,
        },
        headers=_headers(3),
    )

    assert response.status_code == 200
    assert response.json()["reviewed_by_user_id"] == 3
    with test_session() as db:
        plan = db.query(TrainingPlan).filter(
            TrainingPlan.plan_id == 1
        ).one()
        assert plan.reviewed_by_user_id == 3


def test_employee_session_visibility_requires_an_assigned_enrollment(
    authorization_env,
):
    client, _ = authorization_env
    manager_sessions = client.get(
        "/course-sessions/?company_id=1",
        headers=_headers(3),
    )
    employee_sessions = client.get(
        "/course-sessions/?company_id=1",
        headers=_headers(4),
    )
    own_assigned = client.get(
        "/course-sessions/1?company_id=1",
        headers=_headers(4),
    )
    own_pending = client.get(
        "/course-sessions/2?company_id=1",
        headers=_headers(4),
    )
    own_withdrawn = client.get(
        "/course-sessions/3?company_id=1",
        headers=_headers(4),
    )
    unrelated_manager_session = client.get(
        "/course-sessions/5?company_id=1",
        headers=_headers(3),
    )
    foreign_session = client.get(
        "/course-sessions/6?company_id=1",
        headers=_headers(1),
    )
    training_manager_session = client.get(
        "/course-sessions/5?company_id=1",
        headers=_headers(1),
    )

    visible_ids = {1, 4, 7}
    assert {row["session_id"] for row in manager_sessions.json()} == visible_ids
    assert {row["session_id"] for row in employee_sessions.json()} == visible_ids
    assert own_assigned.status_code == 200
    assert own_pending.status_code == 404
    assert own_withdrawn.status_code == 404
    assert unrelated_manager_session.status_code == 404
    assert foreign_session.status_code == 404
    assert training_manager_session.status_code == 200


def test_courses_are_company_scoped_and_training_manager_administered(
    authorization_env,
):
    client, _ = authorization_env
    employee_courses = client.get(
        "/courses/?company_id=1",
        headers=_headers(4),
    )
    foreign_course = client.get(
        "/courses/2?company_id=1",
        headers=_headers(1),
    )
    manager_create = client.post(
        "/courses/?company_id=1",
        json={
            "course_id": "NEW",
            "course_title": "New Course",
            "course_category": "Technical",
            "course_duration_hours": 2,
            "delivery_mode": "Online",
        },
        headers=_headers(3),
    )
    training_manager_create = client.post(
        "/courses/?company_id=1",
        json={
            "course_id": "NEW",
            "course_title": "New Course",
            "course_category": "Technical",
            "course_duration_hours": 2,
            "delivery_mode": "Online",
        },
        headers=_headers(1),
    )

    assert [row["id"] for row in employee_courses.json()] == [1]
    assert foreign_course.status_code == 404
    assert manager_create.status_code == 403
    assert training_manager_create.status_code == 201


def test_employee_import_routes_enforce_role_and_batch_company(
    authorization_env,
):
    client, _ = authorization_env
    manager_read = client.get(
        "/employee-imports/1/issues?company_id=1",
        headers=_headers(3),
    )
    director_read = client.get(
        "/employee-imports/1/issues?company_id=1",
        headers=_headers(2),
    )
    training_manager_read = client.get(
        "/employee-imports/1/issues?company_id=1",
        headers=_headers(1),
    )
    foreign_batch = client.get(
        "/employee-imports/2/issues?company_id=1",
        headers=_headers(1),
    )
    director_reprocess = client.post(
        "/employee-imports/3/reprocess?company_id=1",
        headers=_headers(2),
    )
    training_manager_reprocess = client.post(
        "/employee-imports/3/reprocess?company_id=1",
        headers=_headers(1),
    )

    assert manager_read.status_code == 403
    assert director_read.status_code == 200
    assert training_manager_read.status_code == 200
    assert foreign_batch.status_code == 404
    assert director_reprocess.status_code == 403
    assert training_manager_reprocess.status_code == 200


def test_enrollments_are_employee_scoped_and_company_scoped(authorization_env):
    client, _ = authorization_env
    manager_list = client.get(
        "/enrollments/?company_id=1",
        headers=_headers(3),
    )
    employee_list = client.get(
        "/enrollments/?company_id=1",
        headers=_headers(4),
    )
    manager_unrelated = client.get(
        "/enrollments/5?company_id=1",
        headers=_headers(3),
    )
    employee_unrelated = client.get(
        "/enrollments/5?company_id=1",
        headers=_headers(4),
    )
    foreign_enrollment = client.get(
        "/enrollments/6?company_id=1",
        headers=_headers(1),
    )

    own_enrollment_ids = {1, 2, 3, 4, 7}
    assert {row["enrollment_id"] for row in manager_list.json()} == own_enrollment_ids
    assert {row["enrollment_id"] for row in employee_list.json()} == own_enrollment_ids
    assert manager_unrelated.status_code == 404
    assert employee_unrelated.status_code == 404
    assert foreign_enrollment.status_code == 404


def test_enrollment_assessments_check_role_parent_and_company(
    authorization_env,
):
    client, _ = authorization_env
    manager_list = client.get(
        "/enrollment-assessments/?company_id=1",
        headers=_headers(3),
    )
    employee_list = client.get(
        "/enrollment-assessments/?company_id=1",
        headers=_headers(4),
    )
    foreign_assessment = client.get(
        "/enrollment-assessments/2?company_id=1",
        headers=_headers(1),
    )
    manager_create = client.post(
        "/enrollment-assessments/?company_id=1",
        json={
            "enrollment_id": 1,
            "attempt_number": 2,
            "assessment_result": "Passed",
        },
        headers=_headers(3),
    )
    employee_create = client.post(
        "/enrollment-assessments/?company_id=1",
        json={
            "enrollment_id": 1,
            "attempt_number": 3,
            "assessment_result": "Passed",
        },
        headers=_headers(4),
    )
    manager_unrelated_parent = client.post(
        "/enrollment-assessments/?company_id=1",
        json={
            "enrollment_id": 5,
            "attempt_number": 2,
            "assessment_result": "Passed",
        },
        headers=_headers(3),
    )

    assert [row["assessment_id"] for row in manager_list.json()] == [1]
    assert [row["assessment_id"] for row in employee_list.json()] == [1]
    assert foreign_assessment.status_code == 404
    assert manager_create.status_code == 201
    assert employee_create.status_code == 403
    assert manager_unrelated_parent.status_code == 404


def test_attendance_checks_direct_reports_employee_self_and_company(
    authorization_env,
):
    client, test_session = authorization_env
    manager_list = client.get(
        "/session-attendance/?company_id=1",
        headers=_headers(3),
    )
    employee_list = client.get(
        "/session-attendance/?company_id=1",
        headers=_headers(4),
    )
    employee_other_record = client.get(
        "/session-attendance/2?company_id=1",
        headers=_headers(4),
    )
    foreign_record = client.get(
        "/session-attendance/3?company_id=1",
        headers=_headers(1),
    )
    employee_check_in = client.patch(
        "/session-attendance/1/check-in?company_id=1",
        headers=_headers(4),
    )
    employee_record_attendance = client.post(
        "/session-attendance/?company_id=1",
        json={
            "session_id": 7,
            "employee_id": 12,
            "attendance_status": "Present",
            "recorded_by": 10,
            "recorded_by_user_id": 1,
        },
        headers=_headers(4),
    )
    manager_record_attendance = client.post(
        "/session-attendance/?company_id=1",
        json={
            "session_id": 7,
            "employee_id": 12,
            "attendance_status": "Present",
            "recorded_by": 10,
            "recorded_by_user_id": 1,
        },
        headers=_headers(3),
    )
    manager_other_record = client.put(
        "/session-attendance/2?company_id=1",
        json={"attendance_notes": "Not in manager's team"},
        headers=_headers(3),
    )

    assert [row["attendance_id"] for row in manager_list.json()] == [1]
    assert [row["attendance_id"] for row in employee_list.json()] == [1]
    assert employee_other_record.status_code == 404
    assert foreign_record.status_code == 404
    assert employee_check_in.status_code == 200
    assert employee_record_attendance.status_code == 403
    assert manager_record_attendance.status_code == 201
    assert manager_other_record.status_code == 404
    with test_session() as db:
        record = db.query(SessionAttendance).filter(
            SessionAttendance.session_id == 7
        ).one()
        assert record.recorded_by == 11
        assert record.recorded_by_user_id == 3


def test_feedback_checks_self_direct_report_role_and_company(
    authorization_env,
):
    client, _ = authorization_env
    employee_list = client.get(
        "/session-feedback/?company_id=1",
        headers=_headers(4),
    )
    manager_list = client.get(
        "/session-feedback/?company_id=1",
        headers=_headers(3),
    )
    employee_other_record = client.get(
        "/session-feedback/2?company_id=1",
        headers=_headers(4),
    )
    manager_other_record = client.get(
        "/session-feedback/2?company_id=1",
        headers=_headers(3),
    )
    foreign_record = client.get(
        "/session-feedback/3?company_id=1",
        headers=_headers(1),
    )
    manager_submit = client.post(
        "/session-feedback/?company_id=1&employee_id=12",
        json={"session_id": 7, "training_rating": 5},
        headers=_headers(3),
    )
    employee_submit_own = client.post(
        "/session-feedback/?company_id=1&employee_id=13",
        json={"session_id": 7, "training_rating": 5},
        headers=_headers(4),
    )

    assert [row["feedback_id"] for row in employee_list.json()] == [1]
    assert [row["feedback_id"] for row in manager_list.json()] == [1]
    assert employee_other_record.status_code == 404
    assert manager_other_record.status_code == 404
    assert foreign_record.status_code == 404
    assert manager_submit.status_code == 403
    assert employee_submit_own.status_code == 201
    assert employee_submit_own.json()["employee_id"] == 12


@pytest.mark.parametrize("role_user_id", [1, 2, 3, 4])
def test_shared_skills_are_readable_but_not_mutable(authorization_env, role_user_id):
    client, _ = authorization_env

    read_response = client.get("/skills/", headers=_headers(role_user_id))
    write_response = client.post(
        "/skills/",
        json={"skill_name": "New shared skill"},
        headers=_headers(role_user_id),
    )

    assert read_response.status_code == 200
    assert read_response.json()[0]["skill_name"] == "Python"
    assert write_response.status_code == 403


def test_non_training_manager_cannot_administer_employees(authorization_env):
    client, _ = authorization_env

    response = client.post(
        "/employees/?company_id=1",
        json={
            "employee_id": "NEW-1",
            "full_name": "New Employee",
            "email": "new@example.test",
            "job_title": "Engineer",
            "department": "Engineering",
            "employment_status": "Active",
            "hire_date": "2024-01-01",
            "job_level": "Individual Contributor",
            "employment_type": "Full-time",
        },
        headers=_headers(2),
    )

    assert response.status_code == 403


def test_unresolved_legacy_manager_reference_cannot_leave_a_stale_link(authorization_env):
    _, test_session = authorization_env

    with test_session() as db:
        report = db.query(Employee).filter(Employee.id == 12).one()
        report.manager_id = "missing-manager"
        report.manager_internal_id = 11
        db.flush()

        updated, unresolved = reconcile_company_manager_links(db, 1)

        assert updated == 1
        assert unresolved == 1
        assert report.manager_internal_id is None


def test_tna_results_exclude_positions_and_employees_outside_scope(authorization_env):
    _, test_session = authorization_env

    with test_session() as db:
        results = analyze_company_tna(db, company_id=1, employee_ids={12})

    assert results["summary"]["active_employees"] == 1
    assert {row["employee_id"] for row in results["employee_analysis"]} == {12}
    assert {row["job_title"] for row in results["position_analysis"]} == {"Engineer"}
    assert {row["department"] for row in results["department_analysis"]} == {
        "Engineering"
    }
