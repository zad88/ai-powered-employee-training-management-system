import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.api.dependencies import AuthContext, get_db, require_roles
from backend.app.core.security import hash_password
from backend.app.db.auth_models import User, UserCompanyRole
from backend.app.db.company import Company
from backend.app.db.employee import Employee
from backend.app.db.user_invitation import UserInvitation, UserManagementAudit
from backend.app.services.employee_reporting import validate_reporting_manager
from backend.app.services.invitation_email import InvitationDeliveryError, send_invitation_email


class InvitationRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def sanitized_handler(request: Request) -> Response:
            try:
                return await handler(request)
            except RequestValidationError:
                return JSONResponse(status_code=422, content={"detail": "Invalid invitation request."})

        return sanitized_handler


router = APIRouter(prefix="/user-management", tags=["User Management"])
public_router = APIRouter(prefix="/invitations", tags=["Invitations"], route_class=InvitationRoute)
training_manager = require_roles("Training Manager")
Role = Literal["Training Manager", "Director", "Manager", "Employee"]
INVALID_INVITATION = "This invitation is invalid, expired, or no longer available."


class InvitationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    full_name: str = Field(min_length=1, max_length=150)
    email: EmailStr
    role: Role
    employee_id: int | None = Field(default=None, gt=0)
    department: str | None = Field(default=None, max_length=100)
    manager_id: int | None = Field(default=None, gt=0)

    @field_validator("full_name", "department")
    @classmethod
    def clean_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Value must not be blank.")
        return value


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    full_name: str | None = Field(default=None, min_length=1, max_length=150)
    email: EmailStr | None = None
    role: Role | None = None
    is_active: bool | None = None
    employee_id: int | None = Field(default=None, gt=0)
    department: str | None = Field(default=None, max_length=100)
    manager_id: int | None = Field(default=None, gt=0)

    @field_validator("full_name", "department")
    @classmethod
    def clean_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Value must not be blank.")
        return value


class InvitationToken(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=32, max_length=200)


class InvitationAcceptance(InvitationToken):
    password: str = Field(min_length=12, max_length=128)

    @field_validator("password")
    @classmethod
    def password_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Password must not be blank.")
        return value


def _lock_company(db: Session, company_id: int) -> None:
    db.query(Company.company_id).filter(Company.company_id == company_id).with_for_update().one()


def _audit(db: Session, company_id: int, action: str, *, actor: int | None = None,
           target: int | None = None, invitation: int | None = None) -> None:
    db.add(UserManagementAudit(
        company_id=company_id, action=action, actor_user_id=actor,
        target_user_id=target, invitation_id=invitation,
    ))


def _employee(db: Session, company_id: int, employee_id: int | None,
              *, target_user_id: int | None = None,
              require_active: bool = True) -> Employee | None:
    if employee_id is None:
        return None
    query = db.query(Employee).filter(
        Employee.id == employee_id, Employee.company_id == company_id,
    )
    if require_active:
        query = query.filter(Employee.is_active.is_(True))
    employee = query.first()
    if employee is None:
        raise HTTPException(422, "Select an active employee in your company.")
    linked = db.query(UserCompanyRole).filter(
        UserCompanyRole.employee_id == employee_id,
    ).first()
    if linked is not None and linked.user_id != target_user_id:
        raise HTTPException(409, "This employee is already linked to an account.")
    return employee


def _set_employee_details(db: Session, company_id: int, employee: Employee | None,
                          department: str | None, manager_id: int | None,
                          *, set_department: bool, set_manager: bool,
                          apply: bool = True) -> None:
    if employee is None:
        if (set_department and department is not None) or (set_manager and manager_id is not None):
            raise HTTPException(422, "Link an employee before assigning a department or manager.")
        return
    if set_department:
        if department is None:
            raise HTTPException(422, "An employee department is required.")
        if apply:
            employee.department = department
    if not set_manager:
        return
    if manager_id is None:
        if apply:
            employee.manager_internal_id = None
            employee.manager_id = None
        return
    manager = validate_reporting_manager(db, company_id, manager_id, employee.id)
    if apply:
        employee.manager_internal_id = manager.id
        employee.manager_id = manager.employee_id


def _user_row(user: User, membership: UserCompanyRole, employee: Employee | None,
              manager: Employee | None) -> dict:
    return {
        "id": user.user_id, "full_name": user.full_name, "email": user.email,
        "role": membership.role, "is_active": user.is_active and membership.is_active,
        "employee_id": membership.employee_id,
        "department": employee.department if employee else None,
        "manager_id": manager.id if manager else None,
        "manager_name": manager.full_name if manager else None,
        "created_at": user.created_at,
    }


def _company_user(db: Session, company_id: int, user_id: int):
    row = db.query(User, UserCompanyRole).join(
        UserCompanyRole, UserCompanyRole.user_id == User.user_id
    ).filter(UserCompanyRole.company_id == company_id, User.user_id == user_id).first()
    if row is None:
        raise HTTPException(404, "User not found.")
    return row


def _render_user(db: Session, company_id: int, user: User, membership: UserCompanyRole) -> dict:
    employee = db.query(Employee).filter(
        Employee.id == membership.employee_id, Employee.company_id == company_id
    ).first() if membership.employee_id is not None else None
    manager = db.query(Employee).filter(
        Employee.id == employee.manager_internal_id, Employee.company_id == company_id
    ).first() if employee and employee.manager_internal_id else None
    return _user_row(user, membership, employee, manager)


def _invitation(db: Session, company_id: int, invitation_id: int) -> UserInvitation:
    invitation = db.query(UserInvitation).filter(
        UserInvitation.id == invitation_id, UserInvitation.company_id == company_id,
    ).with_for_update().first()
    if invitation is None:
        raise HTTPException(404, "Invitation not found.")
    return invitation


def _valid_invitation(db: Session, token: str, *, lock: bool = False) -> UserInvitation:
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    query = db.query(UserInvitation).filter(
        UserInvitation.token_hash == token_hash,
        UserInvitation.status == "Pending",
        UserInvitation.expires_at > datetime.now(timezone.utc),
    )
    invitation = (query.with_for_update() if lock else query).first()
    if invitation is None:
        raise HTTPException(400, INVALID_INVITATION)
    return invitation


def _send(email: str, token: str) -> None:
    try:
        send_invitation_email(email, token)
    except InvitationDeliveryError as exc:
        raise HTTPException(503, str(exc)) from None


@router.get("/employees")
def list_linkable_employees(context: AuthContext = Depends(training_manager), db: Session = Depends(get_db)):
    rows = db.query(Employee, UserCompanyRole, User).outerjoin(
        UserCompanyRole, UserCompanyRole.employee_id == Employee.id
    ).outerjoin(
        User, User.user_id == UserCompanyRole.user_id
    ).filter(Employee.company_id == context.company_id, Employee.is_active.is_(True)).order_by(
        Employee.full_name, Employee.id
    ).all()
    return [{
        "id": employee.id, "full_name": employee.full_name, "department": employee.department,
        "linked_user_id": membership.user_id if membership else None,
        "role": membership.role if membership and membership.is_active and user and user.is_active else None,
        "manager_id": employee.manager_internal_id,
    } for employee, membership, user in rows]


@router.get("/users")
def list_users(context: AuthContext = Depends(training_manager), db: Session = Depends(get_db)):
    rows = db.query(User, UserCompanyRole).join(
        UserCompanyRole, UserCompanyRole.user_id == User.user_id
    ).filter(UserCompanyRole.company_id == context.company_id).order_by(User.full_name, User.user_id).all()
    return [_render_user(db, context.company_id, user, membership) for user, membership in rows]


@router.get("/users/{user_id}")
def get_user(user_id: int, context: AuthContext = Depends(training_manager), db: Session = Depends(get_db)):
    user, membership = _company_user(db, context.company_id, user_id)
    return _render_user(db, context.company_id, user, membership)


@router.get("/invitations")
def list_invitations(context: AuthContext = Depends(training_manager), db: Session = Depends(get_db)):
    rows = db.query(UserInvitation).filter(
        UserInvitation.company_id == context.company_id
    ).order_by(UserInvitation.created_at.desc(), UserInvitation.id.desc()).all()
    now = datetime.now(timezone.utc)
    return [{
        "id": item.id, "full_name": item.full_name, "email": item.email, "role": item.role,
        "employee_id": item.employee_id, "department": item.department, "manager_id": item.manager_id,
        "status": "Expired" if item.status == "Pending" and (
            item.expires_at if item.expires_at.tzinfo else item.expires_at.replace(tzinfo=timezone.utc)
        ) <= now else item.status,
        "created_at": item.created_at, "expires_at": item.expires_at,
    } for item in rows]


@router.post("/invitations", status_code=201)
def invite_user(request: InvitationRequest, context: AuthContext = Depends(training_manager),
                db: Session = Depends(get_db)):
    _lock_company(db, context.company_id)
    email = str(request.email).strip().lower()
    if db.query(User).filter(func.lower(func.trim(User.email)) == email).first():
        raise HTTPException(409, "This email cannot be invited.")
    if db.query(UserInvitation).filter(
        UserInvitation.company_id == context.company_id,
        func.lower(func.trim(UserInvitation.email)) == email,
        UserInvitation.status == "Pending",
    ).first():
        raise HTTPException(409, "An invitation is already pending for this email.")
    employee = _employee(db, context.company_id, request.employee_id)
    _set_employee_details(
        db, context.company_id, employee, request.department, request.manager_id,
        set_department=request.department is not None, set_manager=request.manager_id is not None,
        apply=False,
    )
    token = secrets.token_urlsafe(32)
    invitation = UserInvitation(
        company_id=context.company_id, email=email, full_name=request.full_name,
        role=request.role, employee_id=request.employee_id, department=request.department,
        manager_id=request.manager_id, token_hash=hashlib.sha256(token.encode()).hexdigest(),
        status="Pending", expires_at=datetime.now(timezone.utc) + timedelta(hours=72),
        created_by_user_id=context.user.user_id,
    )
    try:
        db.add(invitation)
        db.flush()
        _audit(db, context.company_id, "invitation_created", actor=context.user.user_id, invitation=invitation.id)
        _send(email, token)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "The invitation could not be created; refresh and retry.") from None
    except HTTPException:
        db.rollback()
        raise
    return {"id": invitation.id, "status": "Pending", "message": "Invitation submitted to the mail server."}


@router.post("/invitations/{invitation_id}/resend")
def resend_invitation(invitation_id: int, context: AuthContext = Depends(training_manager),
                      db: Session = Depends(get_db)):
    _lock_company(db, context.company_id)
    invitation = _invitation(db, context.company_id, invitation_id)
    if invitation.status != "Pending":
        raise HTTPException(409, "Only pending invitations can be resent.")
    token = secrets.token_urlsafe(32)
    invitation.token_hash = hashlib.sha256(token.encode()).hexdigest()
    invitation.expires_at = datetime.now(timezone.utc) + timedelta(hours=72)
    try:
        _audit(db, context.company_id, "invitation_resent", actor=context.user.user_id, invitation=invitation.id)
        _send(invitation.email, token)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "The invitation changed; refresh and retry.") from None
    except HTTPException:
        db.rollback()
        raise
    return {"message": "Invitation submitted to the mail server."}


@router.post("/invitations/{invitation_id}/revoke")
def revoke_invitation(invitation_id: int, context: AuthContext = Depends(training_manager),
                      db: Session = Depends(get_db)):
    _lock_company(db, context.company_id)
    invitation = _invitation(db, context.company_id, invitation_id)
    if invitation.status != "Pending":
        raise HTTPException(409, "Only pending invitations can be revoked.")
    invitation.status = "Revoked"
    _audit(db, context.company_id, "invitation_revoked", actor=context.user.user_id, invitation=invitation.id)
    db.commit()
    return {"status": "Revoked"}


@router.patch("/users/{user_id}")
def update_user(user_id: int, request: UserUpdate, context: AuthContext = Depends(training_manager),
                db: Session = Depends(get_db)):
    _lock_company(db, context.company_id)
    user, membership = _company_user(db, context.company_id, user_id)
    fields = request.model_fields_set
    if ("role" in fields and request.role is None) or ("is_active" in fields and request.is_active is None):
        raise HTTPException(422, "Role and account status cannot be null.")
    if ("full_name" in fields and request.full_name is None) or ("email" in fields and request.email is None):
        raise HTTPException(422, "Name and email cannot be null.")
    if user_id == context.user.user_id and ({"role", "is_active"} & fields):
        raise HTTPException(403, "You cannot change your own role or account status.")
    if membership.role.strip().casefold() == "training manager" and user.is_active and membership.is_active and (
        ("role" in fields and request.role != "Training Manager")
        or ("is_active" in fields and not request.is_active)
    ):
        active_managers = db.query(UserCompanyRole).join(User).filter(
            UserCompanyRole.company_id == context.company_id,
            func.lower(func.trim(UserCompanyRole.role)) == "training manager",
            UserCompanyRole.is_active.is_(True),
            User.is_active.is_(True),
        ).count()
        if active_managers <= 1:
            raise HTTPException(409, "The company must retain an active Training Manager.")
    employee_id = request.employee_id if "employee_id" in fields else membership.employee_id
    employee = _employee(
        db, context.company_id, employee_id, target_user_id=user_id,
        require_active="employee_id" in fields and employee_id != membership.employee_id,
    )
    _set_employee_details(
        db, context.company_id, employee, request.department, request.manager_id,
        set_department="department" in fields, set_manager="manager_id" in fields,
    )
    if "full_name" in fields:
        user.full_name = request.full_name
    if "email" in fields:
        email = str(request.email).strip().lower()
        if user.email != email:
            user.email = email
            user.auth_version += 1
    if "employee_id" in fields:
        membership.employee_id = employee_id
    if "role" in fields and membership.role != request.role:
        membership.role = request.role
        user.auth_version += 1
        _audit(db, context.company_id, "role_changed", actor=context.user.user_id, target=user_id)
    if "is_active" in fields and (
        user.is_active != request.is_active or membership.is_active != request.is_active
    ):
        user.is_active = request.is_active
        membership.is_active = request.is_active
        user.auth_version += 1
        _audit(db, context.company_id, "account_reactivated" if request.is_active else "account_deactivated",
               actor=context.user.user_id, target=user_id)
    _audit(db, context.company_id, "user_updated", actor=context.user.user_id, target=user_id)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "The email or employee is already linked to an account.") from None
    return _render_user(db, context.company_id, user, membership)


@public_router.post("/verify")
def verify_invitation(request: InvitationToken, db: Session = Depends(get_db)):
    _valid_invitation(db, request.token)
    return {"valid": True}


@public_router.post("/accept")
def accept_invitation(request: InvitationAcceptance, db: Session = Depends(get_db)):
    invitation = _valid_invitation(db, request.token)
    _lock_company(db, invitation.company_id)
    invitation = _valid_invitation(db, request.token, lock=True)
    if db.query(User).filter(func.lower(func.trim(User.email)) == invitation.email).first():
        raise HTTPException(400, INVALID_INVITATION)
    try:
        employee = _employee(db, invitation.company_id, invitation.employee_id)
        _set_employee_details(
            db, invitation.company_id, employee, invitation.department, invitation.manager_id,
            set_department=invitation.department is not None, set_manager=invitation.manager_id is not None,
        )
        user = User(full_name=invitation.full_name, email=invitation.email,
                    password_hash=hash_password(request.password), is_active=True)
        db.add(user)
        db.flush()
        db.add(UserCompanyRole(
            user_id=user.user_id, company_id=invitation.company_id,
            employee_id=invitation.employee_id, role=invitation.role, is_active=True,
        ))
        invitation.status = "Accepted"
        invitation.accepted_at = datetime.now(timezone.utc)
        _audit(db, invitation.company_id, "invitation_accepted", target=user.user_id, invitation=invitation.id)
        db.commit()
    except (IntegrityError, HTTPException):
        db.rollback()
        raise HTTPException(400, INVALID_INVITATION) from None
    return {"message": "Account activated. You can now sign in."}
