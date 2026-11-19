import hmac
import os
from collections.abc import Generator
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from fastapi import Cookie, Depends, Header, HTTPException, Query, Request, status
from fastapi.security import OAuth2PasswordBearer
import jwt
from sqlalchemy.orm import Session

from backend.app.core.security import decode_access_token
from backend.app.db.auth_models import User, UserCompanyRole
from backend.app.db.database import SessionLocal
from backend.app.db.employee import Employee
from backend.app.services.token_revocation import is_access_token_revoked


ACCESS_TOKEN_COOKIE = "tf_access_token"
CSRF_COOKIE = "tf_csrf_token"
ROLE_NAMES = {
    "training manager": "Training Manager",
    "director": "Director",
    "manager": "Manager",
    "employee": "Employee",
}

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/auth/login",
    auto_error=False,
)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@dataclass
class AuthContext:
    user: User
    membership: UserCompanyRole

    @property
    def company_id(self) -> int:
        return self.membership.company_id

    @property
    def role(self) -> str:
        return ROLE_NAMES[self.membership.role.strip().casefold()]


@dataclass(frozen=True)
class AuthenticatedAccessToken:
    user: User
    jti: str
    expires_at: datetime


def get_authenticated_access_token(
    token: str | None = Depends(oauth2_scheme),
    cookie_token: str | None = Cookie(
        default=None,
        alias=ACCESS_TOKEN_COOKIE,
    ),
    db: Session = Depends(get_db),
) -> AuthenticatedAccessToken:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired authentication token.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    encoded_token = token or cookie_token
    if not encoded_token:
        raise credentials_error

    try:
        payload = decode_access_token(encoded_token)
        user_id = int(payload["sub"])
        raw_jti = payload.get("jti")
        if not isinstance(raw_jti, str):
            raise ValueError("Token has no valid identifier.")
        jti = str(UUID(raw_jti))
        expires_at = datetime.fromtimestamp(payload["exp"], timezone.utc)
    except (
        jwt.InvalidTokenError,
        KeyError,
        OverflowError,
        OSError,
        TypeError,
        ValueError,
    ):
        raise credentials_error from None

    if is_access_token_revoked(db, jti):
        raise credentials_error

    user = db.query(User).filter(
        User.user_id == user_id,
        User.is_active.is_(True),
    ).first()
    if user is None:
        raise credentials_error
    return AuthenticatedAccessToken(
        user=user,
        jti=jti,
        expires_at=expires_at,
    )


def get_current_user(
    authenticated_token: AuthenticatedAccessToken = Depends(
        get_authenticated_access_token
    ),
) -> User:
    return authenticated_token.user


def get_auth_context(
    current_user: User = Depends(get_current_user),
    company_id: int | None = Query(default=None),
    x_company_id: int | None = Header(default=None, alias="X-Company-ID"),
    db: Session = Depends(get_db),
) -> AuthContext:
    if (
        company_id is not None
        and x_company_id is not None
        and company_id != x_company_id
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Company selectors do not match.",
        )

    selected_company_id = x_company_id or company_id
    query = db.query(UserCompanyRole).filter(
        UserCompanyRole.user_id == current_user.user_id,
        UserCompanyRole.is_active.is_(True),
    )
    if selected_company_id is not None:
        query = query.filter(
            UserCompanyRole.company_id == selected_company_id
        )

    memberships = query.order_by(UserCompanyRole.membership_id).all()
    if not memberships:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have an active membership in this company.",
        )
    if len(memberships) > 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Select one of your active company memberships.",
        )

    membership = memberships[0]
    normalized_role = membership.role.strip().casefold()
    if normalized_role not in ROLE_NAMES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your membership has an unsupported role.",
        )
    return AuthContext(user=current_user, membership=membership)


def get_company_id(
    context: AuthContext = Depends(get_auth_context),
) -> int:
    return context.membership.company_id


def require_roles(*allowed_roles: str):
    normalized_roles = {role.strip().casefold() for role in allowed_roles}

    def role_dependency(
        context: AuthContext = Depends(get_auth_context),
    ) -> AuthContext:
        if context.membership.role.strip().casefold() not in normalized_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )
        return context

    return role_dependency


def get_membership_employee(
    context: AuthContext,
    db: Session,
    *,
    required: bool = True,
) -> Employee | None:
    employee_id = context.membership.employee_id
    if employee_id is None:
        if required:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This account is not linked to an employee record.",
            )
        return None

    employee = db.query(Employee).filter(
        Employee.id == employee_id,
        Employee.company_id == context.membership.company_id,
        Employee.is_active.is_(True),
    ).first()
    if employee is None and required:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This membership is not linked to an active employee.",
        )
    return employee


def allowed_employee_ids(
    context: AuthContext,
    db: Session,
) -> set[int] | None:
    if context.role in {"Training Manager", "Director"}:
        return None

    employee = get_membership_employee(context, db)
    if employee is None:
        return set()
    if context.role == "Employee":
        return {employee.id}

    reports = db.query(Employee.id).filter(
        Employee.company_id == context.membership.company_id,
        Employee.manager_internal_id == employee.id,
        Employee.is_active.is_(True),
    ).all()
    return {row[0] for row in reports}


def ensure_employee_access(
    context: AuthContext,
    db: Session,
    employee_id: int,
) -> Employee:
    employee = db.query(Employee).filter(
        Employee.id == employee_id,
        Employee.company_id == context.membership.company_id,
        Employee.is_active.is_(True),
    ).first()
    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active employee not found in this company.",
        )

    if context.role in {"Training Manager", "Director"}:
        return employee

    actor = get_membership_employee(context, db)
    if context.role == "Employee" and employee.id == actor.id:
        return employee
    if (
        context.role == "Manager"
        and employee.manager_internal_id == actor.id
    ):
        return employee

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Employee not found in this company.",
    )


def enforce_cookie_csrf(request: Request) -> None:
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    if request.headers.get("authorization"):
        return

    csrf_cookie = request.cookies.get(CSRF_COOKIE)
    csrf_header = request.headers.get("X-CSRF-Token")
    if (
        not csrf_cookie
        or not csrf_header
        or not hmac.compare_digest(csrf_cookie, csrf_header)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="A valid CSRF token is required.",
        )

    origin = request.headers.get("origin")
    configured_origins = {
        value.strip().rstrip("/")
        for value in os.getenv("FRONTEND_ORIGINS", "").split(",")
        if value.strip()
    }
    if not configured_origins:
        if os.getenv("NODE_ENV", "").lower() == "production":
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Cookie request origin protection is not configured.",
            )
        configured_origins = {
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        }
    if origin is None or origin.rstrip("/") not in configured_origins:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Request origin is not allowed.",
        )


def enforce_business_route_policy(request: Request) -> None:
    route = request.scope.get("route")
    route_path = getattr(route, "path", "")
    method = request.method.upper()
    role = getattr(request.state, "auth_context", None)
    if role is None:
        return
    role = role.role

    training_manager = {"Training Manager"}
    director_approval = {"Training Manager", "Director"}
    team_admin = {"Training Manager", "Manager"}
    read_all = {"Training Manager", "Director", "Manager", "Employee"}

    allowed = read_all if method in {"GET", "HEAD", "OPTIONS"} else training_manager

    if route_path.startswith("/skills"):
        allowed = read_all if method in {"GET", "HEAD", "OPTIONS"} else set()
    elif route_path.startswith("/employee-imports"):
        allowed = (
            {"Training Manager", "Director"}
            if method == "GET"
            else training_manager
        )
    elif route_path.startswith("/job-skills"):
        if route_path.endswith("/approval"):
            allowed = director_approval
        elif method != "GET":
            allowed = training_manager
    elif route_path.startswith("/course-skills"):
        if route_path.endswith("/approval"):
            allowed = director_approval
        elif method != "GET":
            allowed = training_manager
    elif route_path.startswith("/skill-assessments"):
        if route_path.endswith("/review"):
            allowed = director_approval | {"Manager"}
        elif method == "POST":
            allowed = team_admin | {"Employee"}
        elif method in {"PUT", "PATCH"}:
            allowed = team_admin
        elif method == "DELETE":
            allowed = training_manager
    elif route_path.startswith("/tna"):
        allowed = (
            read_all
            if method == "GET"
            else {"Training Manager", "Director", "Manager"}
        )
    elif route_path.startswith("/courses") or route_path.startswith(
        "/course-sessions"
    ):
        allowed = read_all if method == "GET" else training_manager
    elif route_path.startswith("/training-plans"):
        if route_path.endswith("/approval"):
            allowed = director_approval
        elif method in {"POST", "PUT", "PATCH"}:
            allowed = team_admin
    elif route_path.startswith("/plan-courses"):
        allowed = read_all if method == "GET" else team_admin
    elif route_path.startswith("/enrollments"):
        if route_path.endswith("/approval"):
            allowed = director_approval
        elif route_path.endswith("/fail"):
            allowed = {"Training Manager", "Director", "Manager"}
        elif route_path.endswith("/complete"):
            allowed = team_admin
        elif route_path in {"/enrollments/", "/enrollments"}:
            allowed = team_admin | {"Employee"} if method == "POST" else read_all
        elif method in {"PATCH", "PUT"}:
            allowed = team_admin | {"Employee"}
    elif route_path.startswith("/enrollment-assessments"):
        allowed = read_all if method == "GET" else team_admin
        if method == "DELETE":
            allowed = training_manager
    elif route_path.startswith("/session-attendance"):
        allowed = read_all if method == "GET" else team_admin
        if route_path.endswith(("/check-in", "/check-out")):
            allowed = team_admin | {"Employee"}
    elif route_path.startswith("/session-feedback"):
        allowed = read_all if method == "GET" else training_manager | {"Employee"}
    elif route_path.startswith("/employees"):
        allowed = read_all if method == "GET" else training_manager

    if role not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to perform this action.",
        )


def authorize_business_request(
    request: Request,
    context: AuthContext = Depends(get_auth_context),
) -> None:
    request.state.auth_context = context
    enforce_cookie_csrf(request)
    enforce_business_route_policy(request)
