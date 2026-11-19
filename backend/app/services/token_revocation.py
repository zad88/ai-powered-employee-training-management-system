from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.db.revoked_access_token import RevokedAccessToken


def is_access_token_revoked(db: Session, jti: str) -> bool:
    return (
        db.query(RevokedAccessToken.jti)
        .filter(RevokedAccessToken.jti == jti)
        .first()
        is not None
    )


def revoke_access_token(
    db: Session,
    jti: str,
    expires_at: datetime,
) -> None:
    db.add(RevokedAccessToken(jti=jti, expires_at=expires_at))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if not is_access_token_revoked(db, jti):
            raise


def cleanup_expired_access_tokens(
    db: Session,
    *,
    now: datetime | None = None,
) -> int:
    cleanup_before = now or datetime.now(timezone.utc)
    return (
        db.query(RevokedAccessToken)
        .filter(RevokedAccessToken.expires_at <= cleanup_before)
        .delete(synchronize_session=False)
    )
