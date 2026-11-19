import os

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from backend.app.api.dependencies import (
    AuthenticatedAccessToken,
    ACCESS_TOKEN_COOKIE,
    CSRF_COOKIE,
    enforce_cookie_csrf,
    get_authenticated_access_token,
    get_current_user,
    get_db,
)
from backend.app.core.security import (
    create_access_token,
    verify_password,
)
from backend.app.db.auth_models import User, UserCompanyRole
from backend.app.schemas.auth import TokenResponse, UserResponse
from backend.app.services.token_revocation import revoke_access_token


router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=TokenResponse)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    email = form_data.username.strip().lower()

    user = db.query(User).filter(User.email == email).first()

    if (
        user is None
        or not user.is_active
        or not verify_password(form_data.password, user.password_hash)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return TokenResponse(access_token=create_access_token(user.user_id))


@router.get("/me", response_model=UserResponse)
def get_me(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    memberships = db.query(UserCompanyRole).filter(
        UserCompanyRole.user_id == current_user.user_id,
        UserCompanyRole.is_active.is_(True),
    ).all()

    return UserResponse(
        user_id=current_user.user_id,
        full_name=current_user.full_name,
        email=current_user.email,
        is_active=current_user.is_active,
        memberships=memberships,
    )


@router.post("/logout")
def logout(
    response: Response,
    authenticated_token: AuthenticatedAccessToken = Depends(
        get_authenticated_access_token
    ),
    __: None = Depends(enforce_cookie_csrf),
    db: Session = Depends(get_db),
):
    revoke_access_token(
        db,
        authenticated_token.jti,
        authenticated_token.expires_at,
    )
    response.delete_cookie(
        ACCESS_TOKEN_COOKIE,
        path="/",
        secure=os.getenv("NODE_ENV", "").lower() == "production",
        httponly=True,
        samesite="lax",
    )
    response.delete_cookie(
        CSRF_COOKIE,
        path="/",
        secure=os.getenv("NODE_ENV", "").lower() == "production",
        samesite="lax",
    )
    return {"message": "Logged out."}
