from datetime import date, datetime, timedelta, timezone

import backend.app.db.models
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.api.auth import router as auth_router
from backend.app.api.employees import router as employees_router
from backend.app.api.dependencies import authorize_business_request, get_db
from backend.app.api.user_management import public_router, router
from backend.app.core.security import create_access_token, hash_password
from backend.app.db.auth_models import User, UserCompanyRole
from backend.app.db.base import Base
from backend.app.db.company import Company
from backend.app.db.employee import Employee
from backend.app.db.user_invitation import UserInvitation, UserManagementAudit
import backend.app.api.user_management as management
from backend.app.services.invitation_email import InvitationDeliveryError


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "user-management-tests-secret-key-123456")
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    tables = [Base.metadata.tables[name] for name in (
        "companies", "users", "employees", "user_company_roles", "revoked_access_tokens",
        "user_invitations", "user_management_audits",
    )]
    Base.metadata.create_all(engine, tables=tables)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)

    def employee(id, company):
        return Employee(
            id=id, company_id=company, employee_id=f"E{id}", full_name=f"Employee {id}",
            email=f"employee{id}@example.com", job_title="Engineer", department="IT",
            employment_status="Active", hire_date=date(2020, 1, 1), job_level="Staff",
            employment_type="Full-time", is_active=True,
        )

    with sessions() as db:
        db.add_all([Company(company_id=1, company_name="One"), Company(company_id=2, company_name="Two")])
        db.add_all([employee(1, 1), employee(2, 1), employee(3, 2)])
        db.add_all([
            User(user_id=1, full_name="Admin", email="admin@example.test",
                 password_hash=hash_password("correct-password"), is_active=True),
            User(user_id=2, full_name="Manager", email="manager@example.test",
                 password_hash=hash_password("correct-password"), is_active=True),
            User(user_id=3, full_name="Other", email="other@example.test",
                 password_hash=hash_password("correct-password"), is_active=True),
        ])
        db.add_all([
            UserCompanyRole(user_id=1, company_id=1, role="Training Manager", is_active=True),
            UserCompanyRole(user_id=2, company_id=1, employee_id=1, role="Manager", is_active=True),
            UserCompanyRole(user_id=3, company_id=2, employee_id=3, role="Training Manager", is_active=True),
        ])
        db.commit()
    sent = []
    monkeypatch.setattr(management, "send_invitation_email", lambda email, token: sent.append((email, token)))
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(public_router)
    app.include_router(router, dependencies=[Depends(authorize_business_request)])
    app.include_router(employees_router, dependencies=[Depends(authorize_business_request)])

    def override_db():
        with sessions() as db:
            yield db
    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as client:
        yield client, sessions, sent
    engine.dispose()


def headers(user_id=1, company_id=1, token=None):
    return {"Authorization": f"Bearer {token or create_access_token(user_id)}", "X-Company-ID": str(company_id)}


def invite(client, *, email="new@example.com", employee_id=None, role="Employee", **extra):
    return client.post("/user-management/invitations", headers=headers(), json={
        "full_name": "New User", "email": email, "role": role, "employee_id": employee_id, **extra,
    })


def test_unlinked_invitation_is_hashed_single_use_and_login_works(env):
    client, sessions, sent = env
    response = invite(client, email="NEW@example.com")
    assert response.status_code == 201
    token = sent[-1][1]
    with sessions() as db:
        invitation = db.query(UserInvitation).one()
        assert invitation.email == "new@example.com"
        assert invitation.token_hash != token
        assert token not in response.text
    assert client.post("/invitations/verify", json={"token": token}).status_code == 200
    assert client.post("/invitations/accept", json={"token": token, "password": "valid-password"}).status_code == 200
    assert client.post("/invitations/accept", json={"token": token, "password": "valid-password"}).status_code == 400
    login = client.post("/auth/login", data={"username": "new@example.com", "password": "valid-password"})
    assert login.status_code == 200
    unlinked_token = login.json()["access_token"]
    assert client.get("/employees/?company_id=1", headers=headers(token=unlinked_token)).status_code == 403
    with sessions() as db:
        user = db.query(User).filter_by(email="new@example.com").one()
        membership = db.query(UserCompanyRole).filter_by(user_id=user.user_id).one()
        assert (membership.company_id, membership.employee_id, membership.role) == (1, None, "Employee")
        assert db.query(Employee).count() == 3
        assert db.query(UserManagementAudit).filter_by(action="invitation_accepted").count() == 1


def test_linked_invitation_sets_employee_details_without_creating_employee(env):
    client, sessions, sent = env
    response = invite(client, employee_id=2, department="Engineering", manager_id=1)
    assert response.status_code == 201
    with sessions() as db:
        assert db.get(Employee, 2).department == "IT"
    assert client.post("/invitations/accept", json={
        "token": sent[-1][1], "password": "valid-password",
    }).status_code == 200
    with sessions() as db:
        user = db.query(User).filter_by(email="new@example.com").one()
        membership = db.query(UserCompanyRole).filter_by(user_id=user.user_id).one()
        employee = db.get(Employee, 2)
        assert membership.employee_id == 2
        assert (employee.department, employee.manager_internal_id, employee.manager_id) == ("Engineering", 1, "E1")
        assert db.query(Employee).count() == 3


def test_expired_revoked_and_resent_tokens_are_rejected(env):
    client, sessions, sent = env
    invitation_id = invite(client).json()["id"]
    original = sent[-1][1]
    with sessions() as db:
        db.get(UserInvitation, invitation_id).expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    assert client.post("/invitations/verify", json={"token": original}).status_code == 400
    assert client.post(f"/user-management/invitations/{invitation_id}/resend", headers=headers()).status_code == 200
    replacement = sent[-1][1]
    assert replacement != original
    assert client.post("/invitations/verify", json={"token": original}).status_code == 400
    assert client.post(f"/user-management/invitations/{invitation_id}/revoke", headers=headers()).status_code == 200
    assert client.post("/invitations/accept", json={"token": replacement, "password": "valid-password"}).status_code == 400


def test_duplicate_invitations_and_links_are_blocked(env):
    client, sessions, sent = env
    assert invite(client, employee_id=1).status_code == 409
    assert invite(client, employee_id=3).status_code == 422
    assert invite(client, employee_id=2).status_code == 201
    assert invite(client, email="NEW@example.com").status_code == 409
    assert client.post("/invitations/accept", json={"token": sent[-1][1], "password": "valid-password"}).status_code == 200
    assert client.patch("/user-management/users/1", headers=headers(), json={"employee_id": 2}).status_code == 409
    with sessions() as db:
        assert db.query(UserCompanyRole).filter_by(employee_id=2).count() == 1


def test_authorization_and_company_isolation(env):
    client, _, _ = env
    assert client.get("/user-management/users", headers=headers(2)).status_code == 403
    assert client.get("/user-management/users", headers=headers(1, 2)).status_code == 403
    assert client.get("/user-management/users/3", headers=headers()).status_code == 404
    assert client.patch("/user-management/users/3", headers=headers(), json={"role": "Employee"}).status_code == 404
    assert invite(client, company_id=2).status_code == 422
    assert client.patch("/user-management/users/1", headers=headers(), json={"role": "Employee"}).status_code == 403


def test_deactivation_invalidates_old_tokens_and_reactivation_does_not_restore_them(env):
    client, sessions, _ = env
    old_token = create_access_token(2)
    assert client.patch("/user-management/users/2", headers=headers(), json={"is_active": False}).status_code == 200
    assert client.post("/auth/login", data={"username": "manager@example.test", "password": "correct-password"}).status_code == 401
    assert client.get("/auth/me", headers=headers(2, token=old_token)).status_code == 401
    assert client.patch("/user-management/users/2", headers=headers(), json={"is_active": True}).status_code == 200
    assert client.get("/auth/me", headers=headers(2, token=old_token)).status_code == 401
    assert client.post("/auth/login", data={"username": "manager@example.test", "password": "correct-password"}).status_code == 200
    with sessions() as db:
        assert db.query(UserManagementAudit).filter_by(action="account_deactivated").count() == 1
        assert db.query(UserManagementAudit).filter_by(action="account_reactivated").count() == 1


def test_smtp_failure_does_not_create_invitation(env, monkeypatch):
    client, sessions, _ = env
    def fail(_email, _token):
        raise InvitationDeliveryError("secret details must not be exposed")
    monkeypatch.setattr(management, "send_invitation_email", fail)
    response = invite(client)
    assert response.status_code == 503
    assert "secret details" not in response.text
    with sessions() as db:
        assert db.query(UserInvitation).count() == 0


def test_smtp_authentication_failure_returns_safe_reason(env, monkeypatch):
    client, sessions, _ = env

    def fail(_email, _token):
        raise InvitationDeliveryError("authentication")

    monkeypatch.setattr(management, "send_invitation_email", fail)
    response = invite(client)
    assert response.status_code == 503
    assert "rejected authentication" in response.json()["detail"]
    with sessions() as db:
        assert db.query(UserInvitation).count() == 0


def test_smtp_failure_during_resend_preserves_original_token(env, monkeypatch):
    client, sessions, sent = env
    invitation_id = invite(client).json()["id"]
    original = sent[-1][1]

    def fail(_email, _token):
        raise InvitationDeliveryError("not exposed")

    monkeypatch.setattr(management, "send_invitation_email", fail)
    assert client.post(f"/user-management/invitations/{invitation_id}/resend", headers=headers()).status_code == 503
    assert client.post("/invitations/verify", json={"token": original}).status_code == 200
    with sessions() as db:
        assert db.query(UserManagementAudit).filter_by(action="invitation_resent").count() == 0


def test_acceptance_rolls_back_if_employee_was_linked_after_invitation(env):
    client, sessions, sent = env
    assert invite(client, employee_id=2).status_code == 201
    assert client.patch("/user-management/users/1", headers=headers(), json={"employee_id": 2}).status_code == 200
    response = client.post("/invitations/accept", json={"token": sent[-1][1], "password": "valid-password"})
    assert response.status_code == 400
    with sessions() as db:
        assert db.query(User).filter_by(email="new@example.com").count() == 0
        assert db.query(UserInvitation).one().status == "Pending"
        assert db.query(UserManagementAudit).filter_by(action="invitation_accepted").count() == 0


def test_other_company_cannot_modify_invitation(env):
    client, _, _ = env
    invitation_id = invite(client).json()["id"]
    assert client.post(f"/user-management/invitations/{invitation_id}/revoke", headers=headers(3, 2)).status_code == 404
    assert client.post(f"/user-management/invitations/{invitation_id}/resend", headers=headers(3, 2)).status_code == 404


def test_invitation_validation_never_reflects_secrets(env):
    client, _, sent = env
    assert invite(client).status_code == 201
    token = sent[-1][1]
    for payload in (
        {"token": "short-secret", "password": "valid-password"},
        {"token": token, "password": "tiny-secret"},
        {"token": token, "password": " " * 12},
        {"token": token, "password": "valid-password", "unexpected": "hidden-secret"},
    ):
        response = client.post("/invitations/accept", json=payload)
        assert response.status_code == 422
        assert response.json() == {"detail": "Invalid invitation request."}
        assert token not in response.text
        assert "secret" not in response.text
    response = client.post(
        "/invitations/verify", content='{"token":"malformed-secret"',
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422
    assert "malformed-secret" not in response.text


def test_link_existing_unlinked_account_and_reject_duplicate_membership(env):
    client, sessions, _ = env
    response = client.patch("/user-management/users/1", headers=headers(), json={"employee_id": 2})
    assert response.status_code == 200
    assert response.json()["employee_id"] == 2
    with sessions() as db:
        db.add(UserCompanyRole(user_id=1, company_id=2, role="Employee", is_active=True))
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()
    assert client.patch("/user-management/users/1", headers=headers(), json={"employee_id": None}).json()["employee_id"] is None


def test_reporting_manager_must_have_role_and_cannot_create_cycles(env):
    client, _, sent = env
    assert invite(client, employee_id=2, manager_id=3).status_code == 422
    assert invite(client, employee_id=2, manager_id=2).status_code == 422
    assert invite(client, employee_id=2, manager_id=1, role="Manager").status_code == 201
    assert client.post("/invitations/accept", json={"token": sent[-1][1], "password": "valid-password"}).status_code == 200
    response = client.patch("/user-management/users/2", headers=headers(), json={"manager_id": 2})
    assert response.status_code == 422
    assert "cycle" in response.json()["detail"]
    response = client.put("/employees/1?company_id=1", headers=headers(), json={"manager_id": "E2"})
    assert response.status_code == 422
    assert "cycle" in response.json()["detail"]


def test_reporting_manager_requires_appropriate_account_role(env):
    client, _, _ = env
    assert client.patch("/user-management/users/2", headers=headers(), json={"role": "Employee"}).status_code == 200
    assert invite(client, employee_id=2, manager_id=1).status_code == 422
    assert client.put("/employees/2?company_id=1", headers=headers(), json={"manager_id": "E1"}).status_code == 422


def test_employee_api_keeps_manager_fields_consistent(env):
    client, sessions, _ = env
    response = client.put("/employees/2?company_id=1", headers=headers(), json={"manager_id": "E1"})
    assert response.status_code == 200
    with sessions() as db:
        employee = db.get(Employee, 2)
        assert (employee.manager_id, employee.manager_internal_id) == ("E1", 1)
    assert client.put("/employees/2?company_id=1", headers=headers(), json={"manager_id": None}).status_code == 200
    with sessions() as db:
        employee = db.get(Employee, 2)
        assert employee.manager_id is None and employee.manager_internal_id is None


def test_role_change_revokes_session_and_unprivileged_roles_cannot_manage(env):
    client, _, _ = env
    old_token = create_access_token(2)
    assert client.patch("/user-management/users/2", headers=headers(), json={"role": "Director"}).status_code == 200
    assert client.get("/auth/me", headers=headers(2, token=old_token)).status_code == 401
    login = client.post("/auth/login", data={"username": "manager@example.test", "password": "correct-password"})
    assert login.status_code == 200
    new_token = login.json()["access_token"]
    assert client.get("/user-management/users", headers=headers(2, token=new_token)).status_code == 403
    assert client.patch("/user-management/users/2", headers=headers(2, token=new_token), json={"role": "Training Manager"}).status_code == 403
